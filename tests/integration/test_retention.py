"""M11 보존 정책의 로컬 PostgreSQL 계약."""

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.models import (
    CrawlRun,
    CrawlStatus,
    CrawlTrigger,
    FetchStrategy,
    JobPosting,
    JobPostingRevision,
    Notification,
    NotificationChannel,
    NotificationStatus,
    Source,
)
from app.services.retention import RetentionService
from tests.integration.test_database import TEST_DATABASE_URL


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """기존 통합 테스트와 같은 로컬 PostgreSQL 격리 세션을 만든다."""
    engine = create_engine(TEST_DATABASE_URL)
    try:
        with engine.connect() as connection:
            migrated = connection.execute(
                text("SELECT to_regclass('public.job_postings')")
            ).scalar()
    except OperationalError:
        pytest.skip("로컬 PostgreSQL이 준비되지 않았습니다. M2 DB를 먼저 기동하세요.")

    if migrated is None:
        pytest.skip("M2 마이그레이션이 적용되지 않았습니다. alembic upgrade head를 실행하세요.")

    session = Session(engine)
    try:
        yield session
    finally:
        session.rollback()
        session.close()
        engine.dispose()


def _source() -> Source:
    return Source(
        slug=f"retention-{uuid4().hex}",
        name="보존 정책 테스트 소스",
        crawler_key="fixture",
        base_url="https://example.com",
        fetch_strategy=FetchStrategy.API,
    )


@pytest.mark.integration
def test_보존_정책은_기한지난_본문과_실행이력_알림_변경이력만_정리한다(
    db_session: Session,
) -> None:
    now = datetime(2026, 8, 23, tzinfo=UTC)
    source = _source()
    db_session.add(source)
    db_session.flush()
    posting = JobPosting(
        source_id=source.id,
        external_id=uuid4().hex,
        fingerprint=uuid4().hex,
        content_hash="a" * 64,
        url="https://example.com/jobs/retention",
        title="보존 대상 공고",
        description="90일 뒤 비울 본문",
        raw={"payload": "90일 뒤 비울 원본"},
        is_open=False,
        closed_at=now - timedelta(days=91),
    )
    db_session.add(posting)
    db_session.flush()
    crawl_run = CrawlRun(
        source_id=source.id,
        trigger=CrawlTrigger.SCHEDULED,
        status=CrawlStatus.SUCCESS,
        started_at=now - timedelta(days=31),
    )
    notification = Notification(
        job_posting_id=posting.id,
        channel=NotificationChannel.WEB_PUSH,
        status=NotificationStatus.SENT,
        sent_at=now - timedelta(days=91),
    )
    revision = JobPostingRevision(
        job_posting_id=posting.id,
        changed_fields={"title": {"old": "이전", "new": "현재"}},
        old_content_hash="b" * 64,
        new_content_hash="a" * 64,
        detected_at=now - timedelta(days=181),
    )
    db_session.add_all([crawl_run, notification, revision])
    db_session.flush()

    summary = RetentionService(db_session).run(now=now)
    db_session.flush()
    db_session.refresh(posting)

    assert summary.content_cleared == 1
    assert summary.crawl_runs_deleted == 1
    assert summary.notifications_deleted == 1
    assert summary.revisions_deleted == 1
    assert posting.description is None
    assert posting.raw == {}
    assert db_session.get(CrawlRun, crawl_run.id) is None
    assert db_session.get(Notification, notification.id) is None
    assert (
        db_session.scalar(select(JobPostingRevision).where(JobPostingRevision.id == revision.id))
        is None
    )
