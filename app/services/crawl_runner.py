"""소스 한 건의 락·크롤링·영속화·실행 이력을 원자적으로 조율한다."""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from app.core.locks import release_source_lock, try_acquire_source_lock
from app.crawlers import CrawlResult, CrawlSource, get_crawler
from app.crawlers.http import HttpClient
from app.models import CrawlStatus, CrawlTrigger, Source
from app.repositories import CrawlRunRepository, SourceRepository
from app.services.collector import CollectorService
from app.services.crawl_health import (
    CrawlErrorType,
    OperationalAlert,
    classify_crawl_error,
    collection_drop_alert,
    is_collection_drop,
    source_disabled_alert,
)

CrawlCallable = Callable[[CrawlSource], CrawlResult]
SessionFactory = Callable[[], Session]
OperationalAlertSender = Callable[[OperationalAlert], None]
_RUNTIME_CREDENTIAL_CONFIG_KEYS = frozenset({"service_key"})
logger = logging.getLogger(__name__)


class SourceNotFoundError(LookupError):
    """수동 트리거가 존재하지 않는 소스를 가리킬 때 발생한다."""


@dataclass(frozen=True, slots=True)
class CrawlExecutionResult:
    """한 소스 수집 시도의 영속 실행 이력 결과."""

    source_id: int
    run_id: int | None
    status: CrawlStatus


class CrawlExecutionService:
    """전용 DB 연결의 advisory lock 아래에서 한 소스를 수집한다."""

    def __init__(
        self,
        *,
        engine: Engine,
        session_factory: SessionFactory,
        crawl: CrawlCallable,
        failure_threshold: int = 5,
        collection_drop_ratio: float = 0.8,
        operational_alert_sender: OperationalAlertSender | None = None,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError("실패 자동 중지 기준은 1 이상이어야 합니다.")
        if not 0 <= collection_drop_ratio <= 1:
            raise ValueError("수집 급감 기준은 0과 1 사이여야 합니다.")
        self.engine = engine
        self.session_factory = session_factory
        self.crawl = crawl
        self.failure_threshold = failure_threshold
        self.collection_drop_ratio = collection_drop_ratio
        self.operational_alert_sender = operational_alert_sender

    def run_source(self, source_id: int, trigger: CrawlTrigger) -> CrawlExecutionResult:
        """소스 한 건을 실행하거나 이미 실행 중이면 skipped 실행 이력을 남긴다."""
        source = self._load_active_source(source_id)
        if source is None:
            return CrawlExecutionResult(
                source_id=source_id, run_id=None, status=CrawlStatus.SKIPPED
            )

        lock_connection = self.engine.connect()
        acquired = False
        try:
            acquired = try_acquire_source_lock(lock_connection, source_id=source_id)
            if not acquired:
                return self._record_skipped(source_id=source_id, trigger=trigger)

            started = self._start_run(source_id=source_id, trigger=trigger)
            if started is None:
                return CrawlExecutionResult(
                    source_id=source_id, run_id=None, status=CrawlStatus.SKIPPED
                )
            run_id, crawl_source = started
            started_at = time.perf_counter()
            try:
                result = self.crawl(crawl_source)
                return self._finish_run(
                    source_id=source_id,
                    run_id=run_id,
                    crawl_source=crawl_source,
                    result=result,
                    duration_ms=_duration_ms(started_at),
                )
            except Exception as error:
                return self._mark_failed(
                    source_id=source_id,
                    run_id=run_id,
                    duration_ms=_duration_ms(started_at),
                    error=error,
                )
        finally:
            if acquired:
                try:
                    release_source_lock(lock_connection, source_id=source_id)
                except Exception:
                    # pooled connection에 세션 락이 남는 것을 막기 위해 물리 연결을 폐기한다.
                    lock_connection.invalidate()
                    raise
            lock_connection.close()

    def _load_active_source(self, source_id: int) -> Source | None:
        """비활성 소스는 다음 스케줄 사이클에서 크롤러까지 도달하지 않게 막는다."""
        with self.session_factory() as session:
            source = SourceRepository(session).get(source_id)
            if source is None:
                raise SourceNotFoundError(source_id)
            return source if source.is_active else None

    def _record_skipped(self, *, source_id: int, trigger: CrawlTrigger) -> CrawlExecutionResult:
        """다른 워커/수동 요청이 락을 보유한 경우에도 실행 이력을 남긴다."""
        with self.session_factory() as session:
            run = CrawlRunRepository(session).create(
                source_id=source_id,
                trigger=trigger,
                status=CrawlStatus.SKIPPED,
                items_fetched=0,
                items_new=0,
                items_updated=0,
                http_status_summary={},
                error_message="동일 소스의 수집이 이미 실행 중입니다.",
            )
            session.commit()
            return CrawlExecutionResult(source_id=source_id, run_id=run.id, status=run.status)

    def _start_run(
        self, *, source_id: int, trigger: CrawlTrigger
    ) -> tuple[int, CrawlSource] | None:
        """running 행을 먼저 commit해 프로세스 중단에도 시작 사실을 남긴다."""
        with self.session_factory() as session:
            source = SourceRepository(session).get(source_id)
            if source is None:
                raise SourceNotFoundError(source_id)
            if not source.is_active:
                return None
            run = CrawlRunRepository(session).create(
                source_id=source.id,
                trigger=trigger,
                status=CrawlStatus.RUNNING,
                items_fetched=0,
                items_new=0,
                items_updated=0,
                http_status_summary={},
            )
            crawl_source = _to_crawl_source(source)
            session.commit()
            return run.id, crawl_source

    def _finish_run(
        self,
        *,
        source_id: int,
        run_id: int,
        crawl_source: CrawlSource,
        result: CrawlResult,
        duration_ms: int,
    ) -> CrawlExecutionResult:
        """수집 결과와 공고 변경을 같은 DB 트랜잭션에 commit한다."""
        alert: OperationalAlert | None = None
        with self.session_factory() as session:
            source = SourceRepository(session).get(source_id)
            runs = CrawlRunRepository(session)
            run = runs.get(run_id)
            if source is None:
                raise SourceNotFoundError(source_id)
            if run is None:
                raise RuntimeError(f"실행 이력이 없습니다: {run_id}")

            previous_items = runs.latest_successful_items_fetched(source_id=source_id)
            collection_dropped = is_collection_drop(
                previous_items=previous_items,
                current_items=len(result.items),
                ratio=self.collection_drop_ratio,
            )
            is_partial = result.partial or collection_dropped
            collected = CollectorService(session).collect(
                source_id=source_id,
                raw_jobs=result.items,
                complete=not is_partial,
            )
            run.status = CrawlStatus.PARTIAL if is_partial else CrawlStatus.SUCCESS
            run.duration_ms = duration_ms
            run.items_fetched = len(result.items)
            run.items_new = collected.items_new
            run.items_updated = collected.items_updated
            run.http_status_summary = result.http_status_summary
            if collection_dropped:
                run.error_type = CrawlErrorType.COLLECTION_DROP.value
                run.error_message = (
                    f"수집 건수가 직전 성공 {previous_items}건에서 {len(result.items)}건으로 "
                    f"{int(self.collection_drop_ratio * 100)}% 이상 감소했습니다."
                )
                alert = collection_drop_alert(
                    source_id=source.id,
                    source_name=source.name,
                    previous_items=previous_items or 0,
                    current_items=len(result.items),
                    drop_ratio=self.collection_drop_ratio,
                )
            elif result.partial:
                run.error_type = CrawlErrorType.PARSER.value
                run.error_message = (
                    "\n".join(result.errors)[:4_000] or "일부 페이지 파싱에 실패했습니다."
                )
            # 실행 시 Settings에서만 주입한 API 키는 크롤러에 전달하되 DB에는 남기지 않는다.
            source.config = _public_source_config(crawl_source.config)
            if run.status is CrawlStatus.SUCCESS:
                source.last_success_at = datetime.now(UTC)
                source.consecutive_failures = 0
            session.commit()
            execution = CrawlExecutionResult(source_id=source_id, run_id=run.id, status=run.status)
        self._send_operational_alert(alert)
        return execution

    def _mark_failed(
        self,
        *,
        source_id: int,
        run_id: int,
        duration_ms: int,
        error: Exception,
    ) -> CrawlExecutionResult:
        """크롤러·파서 실패를 실행 이력으로 전환하고 다음 소스 실행은 계속 허용한다."""
        alert: OperationalAlert | None = None
        with self.session_factory() as session:
            source = SourceRepository(session).get(source_id)
            run = CrawlRunRepository(session).get(run_id)
            if source is None:
                raise SourceNotFoundError(source_id)
            if run is None:
                raise RuntimeError(f"실행 이력이 없습니다: {run_id}")
            run.status = CrawlStatus.FAILED
            run.duration_ms = duration_ms
            run.error_type = classify_crawl_error(error).value
            run.error_message = str(error)[:4_000]
            source.consecutive_failures += 1
            if source.consecutive_failures == self.failure_threshold:
                source.is_active = False
                alert = source_disabled_alert(
                    source_id=source.id,
                    source_name=source.name,
                    failures=source.consecutive_failures,
                )
            session.commit()
            result = CrawlExecutionResult(source_id=source_id, run_id=run.id, status=run.status)
        self._send_operational_alert(alert)
        return result

    def _send_operational_alert(self, alert: OperationalAlert | None) -> None:
        """운영 알림 장애가 수집 실행 이력이나 자동 중지를 되돌리지 않게 격리한다."""
        if alert is None or self.operational_alert_sender is None:
            return
        try:
            self.operational_alert_sender(alert)
        except Exception:
            logger.exception("운영 알림 전송에 실패했습니다.")


def crawl_registered_source(
    source: CrawlSource, *, user_agent: str, max_response_bytes: int
) -> CrawlResult:
    """등록 크롤러에 소스별 HTTP 정책을 적용하고 연결을 즉시 닫는다."""
    client = HttpClient(
        rate_limit_per_min=source.rate_limit_per_min,
        user_agent=user_agent,
        max_response_bytes=max_response_bytes,
    )
    try:
        return get_crawler(source, client).run()
    finally:
        client.close()


def _to_crawl_source(source: Source) -> CrawlSource:
    """ORM Source를 크롤러가 DB 없이 사용할 최소 계약으로 복사한다."""
    return CrawlSource(
        slug=source.slug,
        crawler_key=source.crawler_key,
        base_url=source.base_url,
        config=dict(source.config),
        rate_limit_per_min=source.rate_limit_per_min,
    )


def _duration_ms(started_at: float) -> int:
    """단조 시계를 써서 시스템 시간 변경과 무관한 실행 시간을 기록한다."""
    return int((time.perf_counter() - started_at) * 1_000)


def _public_source_config(config: dict[str, object]) -> dict[str, object]:
    """소스 설정에 남겨도 되는 수집 상태만 복사한다.

    ETag·Last-Modified 같은 공개 캐시는 보존하지만, 실행 직전에만 주입한 자격 증명은
    관리자 UI·DB 백업·로그에 섞이지 않도록 제외한다.
    """
    return {
        key: value for key, value in config.items() if key not in _RUNTIME_CREDENTIAL_CONFIG_KEYS
    }
