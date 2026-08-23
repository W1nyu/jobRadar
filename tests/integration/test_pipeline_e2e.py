"""M10 로컬 PostgreSQL 수집→매칭→알림 파이프라인 종단 간 계약."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.crawlers.base import CrawlResult, CrawlSource, RawJob
from app.models import (
    CrawlRun,
    CrawlStatus,
    CrawlTrigger,
    FetchStrategy,
    JobKeywordMatch,
    JobPosting,
    Keyword,
    KeywordKind,
    Notification,
    NotificationChannel,
    NotificationStatus,
    Source,
)
from app.notifications.contracts import NotificationPayload, SendResult
from app.services.crawl_runner import CrawlExecutionService
from app.services.dispatcher import DispatchSettings, NotificationDispatcher
from app.worker.diagnostics import measure_worker_cycle
from tests.integration.test_database import TEST_DATABASE_URL


class PipelineCrawler:
    """종단 간 테스트에 필요한 한 건의 신규 공고만 반환한다."""

    def __call__(self, source: CrawlSource) -> CrawlResult:
        return CrawlResult(
            items=[
                RawJob(
                    external_id=f"pipeline-{source.slug}",
                    url=f"{source.base_url}/jobs/1",
                    title=f"{source.slug} 데이터 엔지니어 신입",
                    description="데이터 파이프라인 업무",
                )
            ],
            pages_fetched=1,
            http_status_summary={"200": 1},
        )


class RecordingChannel:
    """외부 전송 없이 묶음 알림만 기록하는 채널 대역."""

    name = NotificationChannel.WEB_PUSH

    def __init__(self) -> None:
        self.payloads: list[NotificationPayload] = []

    def send(self, payload: NotificationPayload) -> SendResult:
        self.payloads.append(payload)
        return SendResult(succeeded=True)


@pytest.fixture
def pipeline_context() -> Generator[tuple[CrawlExecutionService, Session, Source], None, None]:
    """여러 서비스의 commit을 테스트 뒤 하나의 바깥 트랜잭션으로 되돌린다."""
    engine = create_engine(TEST_DATABASE_URL)
    try:
        with engine.connect() as probe:
            migrated = probe.execute(text("SELECT to_regclass('public.notifications')")).scalar()
    except OperationalError:
        pytest.skip("로컬 PostgreSQL이 준비되지 않았습니다. M2 DB를 먼저 기동하세요.")
    if migrated is None:
        pytest.skip("M2 마이그레이션이 적용되지 않았습니다. alembic upgrade head를 실행하세요.")

    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    source = Source(
        slug=f"pipeline-{uuid4().hex}",
        name="파이프라인 E2E 소스",
        crawler_key="fixture",
        base_url="https://example.com",
        fetch_strategy=FetchStrategy.API,
    )
    session.add(source)
    session.flush()
    session.add(Keyword(term=source.slug, kind=KeywordKind.INCLUDE))
    session.flush()

    def session_factory() -> Session:
        return Session(bind=connection, join_transaction_mode="create_savepoint")

    runner = CrawlExecutionService(
        engine=engine,
        session_factory=session_factory,
        crawl=PipelineCrawler(),
    )
    try:
        yield runner, session, source
    finally:
        session.close()
        transaction.rollback()
        connection.close()
        engine.dispose()


@pytest.mark.integration
def test_수집부터_키워드_매칭과_중복없는_알림까지_한_파이프라인으로_완료된다(
    pipeline_context: tuple[CrawlExecutionService, Session, Source],
) -> None:
    runner, session, source = pipeline_context

    crawl_results = []
    measurement = measure_worker_cycle(
        lambda: crawl_results.append(
            runner.run_source(source_id=source.id, trigger=CrawlTrigger.MANUAL)
        )
    )
    crawl_result = crawl_results[0]
    posting = session.scalar(select(JobPosting).where(JobPosting.source_id == source.id))
    assert posting is not None
    notification_now = datetime(2099, 8, 22, 3, 0, tzinfo=UTC)
    posting.first_seen_at = notification_now
    session.flush()
    channel = RecordingChannel()
    dispatcher = NotificationDispatcher(
        session,
        channels=(channel,),
        settings=DispatchSettings(lookback_minutes=10, app_base_url="https://example.com"),
    )

    first_dispatch = dispatcher.dispatch(now=notification_now)
    second_dispatch = dispatcher.dispatch(now=notification_now)
    crawl_run = session.get(CrawlRun, crawl_result.run_id)
    matches = session.scalars(
        select(JobKeywordMatch)
        .join(Keyword, JobKeywordMatch.keyword_id == Keyword.id)
        .where(JobKeywordMatch.job_posting_id == posting.id, Keyword.term == source.slug)
    ).all()
    notifications = session.scalars(
        select(Notification).where(Notification.job_posting_id == posting.id)
    ).all()

    assert crawl_result.status is CrawlStatus.SUCCESS
    assert measurement.peak_megabytes < 150
    assert crawl_run is not None
    assert crawl_run.items_new == 1
    assert len(matches) == 1
    assert first_dispatch.sent == 1
    assert second_dispatch.sent == 0
    assert len(channel.payloads) == 1
    assert len(channel.payloads[0].items) == 1
    assert [notification.status for notification in notifications] == [NotificationStatus.SENT]
