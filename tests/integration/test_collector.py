"""M4 수집 정규화·중복·변경·종료 규칙을 실제 PostgreSQL에서 검증한다."""

from collections.abc import Generator
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.crawlers.base import RawJob
from app.models import FetchStrategy, JobPosting, JobPostingRevision, Source
from app.services.collector import CollectorService
from tests.integration.test_database import TEST_DATABASE_URL


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """기존 M2 통합 테스트와 같은 격리 세션을 재사용한다."""
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


@pytest.fixture
def source(db_session: Session) -> Source:
    """각 테스트가 독립된 소스에서 연속 수집을 실행한다."""
    source = Source(
        slug=f"collector-{uuid4().hex}",
        name="M4 수집 테스트",
        crawler_key="test",
        base_url="https://example.com",
        fetch_strategy=FetchStrategy.API,
    )
    db_session.add(source)
    db_session.flush()
    return source


def _job(
    *,
    external_id: str | None = "example-1",
    title: str = "데이터 분석가 채용",
    deadline_at: datetime | None = None,
    raw: dict[str, int] | None = None,
) -> RawJob:
    return RawJob(
        external_id=external_id,
        url="https://example.com/jobs/1?from=list",
        title=title,
        company="예시 회사",
        description="분석 업무를 담당합니다.",
        deadline_at=deadline_at,
        raw=raw or {},
    )


@pytest.mark.integration
def test_같은_소스를_두번_수집하면_두번째는_신규_0건이다(
    db_session: Session, source: Source
) -> None:
    collector = CollectorService(db_session)

    first = collector.collect(source_id=source.id, raw_jobs=[_job()])
    second = collector.collect(source_id=source.id, raw_jobs=[_job()])

    assert first.items_new == 1
    assert second.items_new == 0
    assert second.items_updated == 0


@pytest.mark.integration
def test_마감일이_바뀌면_이전_값과_새_값을_담은_수정_이력이_생긴다(
    db_session: Session, source: Source
) -> None:
    collector = CollectorService(db_session)
    initial_deadline = datetime(2026, 9, 1, 18, 0, tzinfo=UTC)
    changed_deadline = datetime(2026, 9, 8, 18, 0, tzinfo=UTC)

    collector.collect(source_id=source.id, raw_jobs=[_job(deadline_at=initial_deadline)])
    result = collector.collect(source_id=source.id, raw_jobs=[_job(deadline_at=changed_deadline)])

    revisions = db_session.scalars(
        select(JobPostingRevision).join(JobPosting).where(JobPosting.source_id == source.id)
    ).all()
    assert result.items_updated == 1
    assert len(revisions) == 1
    assert revisions[0].changed_fields == {
        "deadline_at": {
            "old": initial_deadline.isoformat(),
            "new": changed_deadline.isoformat(),
        }
    }


@pytest.mark.integration
def test_조회수만_바뀌면_수정_이력이_생기지_않는다(db_session: Session, source: Source) -> None:
    collector = CollectorService(db_session)

    collector.collect(source_id=source.id, raw_jobs=[_job(raw={"views": 10})])
    result = collector.collect(source_id=source.id, raw_jobs=[_job(raw={"views": 500})])

    assert result.items_updated == 0
    assert (
        db_session.scalars(
            select(JobPostingRevision).join(JobPosting).where(JobPosting.source_id == source.id)
        ).all()
        == []
    )


@pytest.mark.integration
def test_신입_접두_태그가_붙어도_같은_공고로_정규화한다(
    db_session: Session, source: Source
) -> None:
    collector = CollectorService(db_session)

    collector.collect(source_id=source.id, raw_jobs=[_job(external_id=None)])
    result = collector.collect(
        source_id=source.id,
        raw_jobs=[_job(external_id=None, title="[신입] 데이터 분석가 채용")],
    )

    postings = db_session.scalars(select(JobPosting).where(JobPosting.source_id == source.id)).all()
    assert result.items_new == 0
    assert len(postings) == 1
    assert postings[0].title == "데이터 분석가 채용"


@pytest.mark.integration
def test_세번_연속_미노출된_공고는_종료된다(db_session: Session, source: Source) -> None:
    collector = CollectorService(db_session)
    collector.collect(source_id=source.id, raw_jobs=[_job()])

    collector.collect(source_id=source.id, raw_jobs=[])
    collector.collect(source_id=source.id, raw_jobs=[])
    result = collector.collect(source_id=source.id, raw_jobs=[])

    posting = db_session.scalar(select(JobPosting).where(JobPosting.source_id == source.id))
    assert result.items_closed == 1
    assert posting is not None
    assert posting.is_open is False
    assert posting.closed_at is not None
