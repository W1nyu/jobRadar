"""M6 APScheduler 기반 자동 수집 워커의 스케줄 등록 책임."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Event
from zoneinfo import ZoneInfo

from apscheduler.executors.pool import ThreadPoolExecutor
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import SessionLocal, get_engine
from app.core.logging import configure_logging
from app.crawlers.sources import with_runtime_credentials
from app.models import CrawlTrigger, Source
from app.repositories import AppSettingRepository
from app.services.crawl_health import OperationalAlert
from app.services.crawl_runner import CrawlExecutionService, crawl_registered_source
from app.services.notification_runtime import NotificationRuntime


@dataclass(frozen=True, slots=True)
class ScheduledSource:
    """스케줄러가 필요한 활성 소스의 최소 정보."""

    id: int
    interval_minutes: float


class CrawlRunner:
    """순환 import 없이 스케줄러가 의존할 수 있는 수집 실행 계약."""

    def run_source(self, source_id: int, trigger: CrawlTrigger) -> None:
        """소스 한 건의 수집을 실행한다."""
        raise NotImplementedError


class WorkerScheduler:
    """활성 소스별 interval 잡과 워커 하트비트를 관리한다."""

    def __init__(
        self,
        *,
        runner: CrawlRunner,
        source_loader: Callable[[], Sequence[ScheduledSource]],
        heartbeat: Callable[[], None],
        max_workers: int,
        dispatch_notifications: Callable[[], None] | None = None,
        refresh_kakao_tokens: Callable[[], None] | None = None,
        timezone: str = "Asia/Seoul",
    ) -> None:
        if max_workers < 1:
            raise ValueError("max_workers는 1 이상이어야 합니다.")
        self.runner = runner
        self.source_loader = source_loader
        self.heartbeat = heartbeat
        self.dispatch_notifications = dispatch_notifications
        self.refresh_kakao_tokens = refresh_kakao_tokens
        self.timezone = timezone
        self.scheduler = BackgroundScheduler(
            executors={"default": ThreadPoolExecutor(max_workers=max_workers)},
            job_defaults={"coalesce": True, "max_instances": 1},
        )

    def start(self) -> None:
        """즉시 하트비트를 남기고 활성 소스의 자동 수집을 시작한다."""
        self.refresh_jobs()
        self.heartbeat()
        self.scheduler.add_job(
            self.refresh_jobs,
            trigger="interval",
            seconds=60,
            id="refresh-source-jobs",
            replace_existing=True,
            coalesce=True,
        )
        if self.dispatch_notifications is not None:
            self.scheduler.add_job(
                self.dispatch_notifications,
                trigger="interval",
                seconds=60,
                id="notification-dispatch",
                replace_existing=True,
                coalesce=True,
            )
        if self.refresh_kakao_tokens is not None:
            self.scheduler.add_job(
                self.refresh_kakao_tokens,
                trigger="cron",
                hour=4,
                minute=0,
                timezone=ZoneInfo(self.timezone),
                id="kakao-token-refresh",
                replace_existing=True,
                coalesce=True,
            )
        self.scheduler.add_job(
            self.heartbeat,
            trigger="interval",
            seconds=60,
            id="worker-heartbeat",
            replace_existing=True,
            coalesce=True,
        )
        self.scheduler.start()

    def shutdown(self) -> None:
        """테스트와 systemd 종료 시 새 실행을 기다리지 않고 스케줄러를 멈춘다."""
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def refresh_jobs(self) -> None:
        """현재 활성 소스 목록과 등록된 interval 잡을 동기화한다."""
        sources = {source.id: source for source in self.source_loader()}
        registered_ids = {
            int(job.id.removeprefix("crawl-source-"))
            for job in self.scheduler.get_jobs()
            if job.id.startswith("crawl-source-")
        }

        for source_id in registered_ids - sources.keys():
            self.scheduler.remove_job(f"crawl-source-{source_id}")

        for source in sources.values():
            self.scheduler.add_job(
                self.runner.run_source,
                trigger="interval",
                minutes=source.interval_minutes,
                jitter=_jitter_seconds(source.interval_minutes),
                id=f"crawl-source-{source.id}",
                args=[source.id, CrawlTrigger.SCHEDULED],
                replace_existing=True,
                coalesce=True,
                max_instances=1,
            )


def _jitter_seconds(interval_minutes: float) -> int:
    """소스 시작을 최대 30초 분산해 여러 사이트가 동시에 요청하지 않게 한다."""
    return min(30, max(0, int(interval_minutes * 60 * 0.1)))


def load_active_sources(session_factory: Callable[[], Session]) -> Sequence[ScheduledSource]:
    """DB의 활성 소스만 APScheduler 등록에 필요한 최소 정보로 읽는다."""
    with session_factory() as session:
        return [
            ScheduledSource(id=source.id, interval_minutes=source.interval_minutes)
            for source in session.scalars(
                select(Source).where(Source.is_active.is_(True)).order_by(Source.id)
            )
        ]


def record_worker_heartbeat(session_factory: Callable[[], Session]) -> None:
    """워커가 살아 있음을 UTC 시각으로 기록한다."""
    with session_factory() as session:
        repository = AppSettingRepository(session)
        heartbeat = repository.get("worker_heartbeat")
        value = {"at": datetime.now(UTC).isoformat()}
        if heartbeat is None:
            repository.create(key="worker_heartbeat", value=value)
        else:
            repository.update(heartbeat, value=value)
        session.commit()


def build_worker(settings: Settings | None = None) -> WorkerScheduler:
    """운영 설정으로 크롤러 실행·소스 로딩·하트비트를 조립한다."""
    settings = settings or get_settings()
    engine = get_engine()
    notifications = NotificationRuntime(settings)

    def send_operational_alert(alert: OperationalAlert) -> None:
        with SessionLocal() as session:
            notifications.send_operational_alert(session, alert)

    runner = CrawlExecutionService(
        engine=engine,
        session_factory=SessionLocal,
        crawl=lambda source: crawl_registered_source(
            with_runtime_credentials(source, settings),
            user_agent=settings.crawl_user_agent,
            max_response_bytes=settings.crawl_max_response_bytes,
        ),
        failure_threshold=settings.source_failure_threshold,
        collection_drop_ratio=settings.collection_drop_ratio,
        operational_alert_sender=send_operational_alert,
    )

    def dispatch_notifications() -> None:
        with SessionLocal() as session:
            notifications.dispatch(session)

    def refresh_kakao_tokens() -> None:
        with SessionLocal() as session:
            notifications.refresh_kakao_tokens(session)

    return WorkerScheduler(
        runner=runner,
        source_loader=lambda: load_active_sources(SessionLocal),
        heartbeat=lambda: record_worker_heartbeat(SessionLocal),
        max_workers=settings.crawl_max_workers,
        dispatch_notifications=dispatch_notifications,
        refresh_kakao_tokens=refresh_kakao_tokens,
        timezone=settings.timezone,
    )


def main() -> int:
    """systemd가 실행하는 워커 프로세스를 시작하고 종료 신호를 기다린다."""
    settings = get_settings()
    configure_logging(level=settings.log_level, json_output=settings.log_json)
    worker = build_worker(settings)
    stopped = Event()
    worker.start()
    try:
        stopped.wait()
    except KeyboardInterrupt:
        return 0
    finally:
        worker.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
