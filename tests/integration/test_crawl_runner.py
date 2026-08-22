"""M6 수집 실행 서비스의 실행 이력·락·비활성 소스 처리를 검증한다."""

from __future__ import annotations

from collections.abc import Generator
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.locks import release_source_lock, try_acquire_source_lock
from app.crawlers.base import CrawlResult, CrawlSource, RawJob
from app.models import CrawlRun, CrawlStatus, CrawlTrigger, FetchStrategy, Source
from app.services.crawl_runner import CrawlExecutionService
from tests.integration.test_database import TEST_DATABASE_URL


class FixtureCrawler:
    """네트워크 없이 성공 수집 결과를 반환하는 실행용 가짜 크롤러."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, source: CrawlSource) -> CrawlResult:
        self.calls += 1
        return CrawlResult(
            items=[
                RawJob(
                    external_id=f"fixture-{source.slug}",
                    url=f"{source.base_url}/jobs/1",
                    title="데이터 엔지니어",
                    description="데이터 파이프라인을 개발합니다.",
                )
            ],
            pages_fetched=1,
            http_status_summary={"200": 1},
        )


@pytest.fixture
def runner_context() -> Generator[
    tuple[CrawlExecutionService, Session, Source, FixtureCrawler], None, None
]:
    """여러 내부 세션의 commit을 바깥 트랜잭션으로 되돌릴 수 있게 구성한다."""
    engine = create_engine(TEST_DATABASE_URL)
    try:
        with engine.connect() as probe:
            migrated = probe.execute(text("SELECT to_regclass('public.crawl_runs')")).scalar()
    except OperationalError:
        pytest.skip("로컬 PostgreSQL이 준비되지 않았습니다. M2 DB를 먼저 기동하세요.")

    if migrated is None:
        pytest.skip("M2 마이그레이션이 적용되지 않았습니다. alembic upgrade head를 실행하세요.")

    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    source = Source(
        slug=f"runner-{uuid4().hex}",
        name="M6 실행 테스트",
        crawler_key="fixture",
        base_url="https://example.com",
        fetch_strategy=FetchStrategy.API,
        interval_minutes=1,
    )
    session.add(source)
    session.flush()
    crawler = FixtureCrawler()

    def session_factory() -> Session:
        return Session(bind=connection, join_transaction_mode="create_savepoint")

    runner = CrawlExecutionService(
        engine=engine,
        session_factory=session_factory,
        crawl=crawler,
    )
    try:
        yield runner, session, source, crawler
    finally:
        session.close()
        transaction.rollback()
        connection.close()
        engine.dispose()


@pytest.mark.integration
def test_성공_수집은_crawl_runs_요약과_공고_집계를_남긴다(
    runner_context: tuple[CrawlExecutionService, Session, Source, FixtureCrawler],
) -> None:
    runner, session, source, crawler = runner_context

    result = runner.run_source(source_id=source.id, trigger=CrawlTrigger.SCHEDULED)

    run = session.get(CrawlRun, result.run_id)
    assert crawler.calls == 1
    assert result.status is CrawlStatus.SUCCESS
    assert run is not None
    assert run.status is CrawlStatus.SUCCESS
    assert run.duration_ms is not None
    assert run.items_fetched == 1
    assert run.items_new == 1
    assert run.http_status_summary == {"200": 1}


@pytest.mark.integration
def test_실행시에만_주입한_api_키는_소스_설정에_저장하지_않는다(
    runner_context: tuple[CrawlExecutionService, Session, Source, FixtureCrawler],
) -> None:
    runner, session, source, crawler = runner_context

    def crawl_with_runtime_credential(crawl_source: CrawlSource) -> CrawlResult:
        crawl_source.config["service_key"] = "runtime-secret"
        return crawler(crawl_source)

    runner.crawl = crawl_with_runtime_credential
    runner.run_source(source_id=source.id, trigger=CrawlTrigger.SCHEDULED)
    session.refresh(source)

    assert source.config == {}
    assert "runtime-secret" not in str(source.config)


@pytest.mark.integration
def test_이미_수집_중인_소스의_수동_트리거는_skipped로_기록된다(
    runner_context: tuple[CrawlExecutionService, Session, Source, FixtureCrawler],
) -> None:
    runner, session, source, crawler = runner_context
    lock_connection = runner.engine.connect()
    try:
        assert try_acquire_source_lock(lock_connection, source_id=source.id) is True

        result = runner.run_source(source_id=source.id, trigger=CrawlTrigger.MANUAL)

        run = session.get(CrawlRun, result.run_id)
        assert crawler.calls == 0
        assert result.status is CrawlStatus.SKIPPED
        assert run is not None
        assert run.status is CrawlStatus.SKIPPED
    finally:
        release_source_lock(lock_connection, source_id=source.id)
        lock_connection.close()


@pytest.mark.integration
def test_비활성_소스는_다음_스케줄_사이클에_크롤러를_실행하지_않는다(
    runner_context: tuple[CrawlExecutionService, Session, Source, FixtureCrawler],
) -> None:
    runner, session, source, crawler = runner_context
    source.is_active = False
    session.flush()

    result = runner.run_source(source_id=source.id, trigger=CrawlTrigger.SCHEDULED)

    assert crawler.calls == 0
    assert result.run_id is None
    assert result.status is CrawlStatus.SKIPPED


@pytest.mark.integration
def test_부분_수집과_예외는_각각_partial과_failed_실행_이력으로_남는다(
    runner_context: tuple[CrawlExecutionService, Session, Source, FixtureCrawler],
) -> None:
    runner, session, source, _ = runner_context

    runner.crawl = lambda _source: CrawlResult(
        items=[], pages_fetched=1, http_status_summary={"200": 1, "500": 1}, partial=True
    )
    partial_result = runner.run_source(source_id=source.id, trigger=CrawlTrigger.SCHEDULED)

    def raise_network_error(_source: CrawlSource) -> CrawlResult:
        raise RuntimeError("fixture network failure")

    runner.crawl = raise_network_error
    failed_result = runner.run_source(source_id=source.id, trigger=CrawlTrigger.SCHEDULED)

    partial_run = session.get(CrawlRun, partial_result.run_id)
    failed_run = session.get(CrawlRun, failed_result.run_id)
    assert partial_run is not None
    assert partial_run.status is CrawlStatus.PARTIAL
    assert failed_run is not None
    assert failed_run.status is CrawlStatus.FAILED
    assert failed_run.error_type == "RuntimeError"
