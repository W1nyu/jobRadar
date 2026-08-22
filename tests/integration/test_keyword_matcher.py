"""M5 키워드 매칭 근거 저장과 PostgreSQL 검색 인덱스를 검증한다."""

from collections.abc import Generator
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, delete, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.crawlers.base import RawJob
from app.models import (
    FetchStrategy,
    JobKeywordMatch,
    JobPosting,
    Keyword,
    KeywordKind,
    MatchMode,
    Source,
)
from app.services.collector import CollectorService
from app.services.keyword_matcher import KeywordMatcher
from tests.integration.test_database import TEST_DATABASE_URL


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """로컬 M2 DB가 준비된 경우에만 rollback 격리 세션을 제공한다."""
    engine = create_engine(TEST_DATABASE_URL)
    try:
        with engine.connect() as connection:
            migrated = connection.execute(
                text("SELECT to_regclass('public.job_keyword_matches')")
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
def posting(db_session: Session) -> JobPosting:
    """기본 키워드를 rollback 격리로 지우고, 각 테스트가 전용 키워드를 만든다."""
    db_session.execute(delete(Keyword))
    source = Source(
        slug=f"keyword-{uuid4().hex}",
        name="M5 매칭 테스트",
        crawler_key="test",
        base_url="https://example.com",
        fetch_strategy=FetchStrategy.API,
    )
    db_session.add(source)
    db_session.flush()
    posting = JobPosting(
        source_id=source.id,
        external_id=f"job-{uuid4().hex}",
        content_hash="0" * 64,
        url="https://example.com/jobs/1",
        title="데이터 분석가",
        description="제품 지표를 분석하고 AI 모델을 개발합니다.",
    )
    db_session.add(posting)
    db_session.flush()
    return posting


def _keyword(
    db_session: Session,
    *,
    term: str,
    kind: KeywordKind = KeywordKind.INCLUDE,
    match_mode: MatchMode = MatchMode.SUBSTRING,
    target_fields: list[str] | None = None,
    weight: int = 1,
) -> Keyword:
    keyword = Keyword(
        term=term,
        kind=kind,
        match_mode=match_mode,
        target_fields=target_fields or ["title", "description"],
        weight=weight,
        is_active=True,
    )
    db_session.add(keyword)
    db_session.flush()
    return keyword


@pytest.mark.integration
def test_데이터_include_키워드는_데이터_분석가_공고에_매칭된다(
    db_session: Session, posting: JobPosting
) -> None:
    keyword = _keyword(db_session, term="데이터")

    result = KeywordMatcher(db_session).match_and_record(posting=posting)

    assert result.is_matched is True
    assert [match.keyword_id for match in result.include_matches] == [keyword.id]


@pytest.mark.integration
def test_exclude_키워드가_일치한_공고는_관심_대상에서_제외된다(
    db_session: Session, posting: JobPosting
) -> None:
    _keyword(db_session, term="데이터")
    excluded = _keyword(db_session, term="AI 모델", kind=KeywordKind.EXCLUDE)

    result = KeywordMatcher(db_session).match_and_record(posting=posting)

    assert result.is_matched is False
    assert [match.keyword_id for match in result.exclude_matches] == [excluded.id]


@pytest.mark.integration
def test_매칭_근거_snippet이_job_keyword_matches에_저장된다(
    db_session: Session, posting: JobPosting
) -> None:
    keyword = _keyword(db_session, term="지표", target_fields=["description"])

    KeywordMatcher(db_session).match_and_record(posting=posting)

    match = db_session.scalar(
        select(JobKeywordMatch).where(
            JobKeywordMatch.job_posting_id == posting.id,
            JobKeywordMatch.keyword_id == keyword.id,
        )
    )
    assert match is not None
    assert match.matched_field == "description"
    assert "제품 지표를 분석" in (match.matched_snippet or "")


@pytest.mark.integration
def test_title_부분일치_검색은_trgm_GIN_인덱스를_사용한다(
    db_session: Session, posting: JobPosting
) -> None:
    db_session.execute(text("SET LOCAL enable_seqscan = off"))

    plan = db_session.scalar(
        text(
            "EXPLAIN (ANALYZE, FORMAT JSON) "
            "SELECT id FROM job_postings WHERE title ILIKE '%데이터%'"
        )
    )

    assert posting.id is not None
    assert "ix_job_postings_title_trgm" in str(plan)


@pytest.mark.integration
def test_가중치가_높은_데이터분석_매칭이_AI보다_먼저_정렬된다(
    db_session: Session, posting: JobPosting
) -> None:
    posting.title = "AI 데이터분석가"
    ai = _keyword(db_session, term="AI", weight=1)
    data_analysis = _keyword(db_session, term="데이터분석", weight=5)

    result = KeywordMatcher(db_session).match_and_record(posting=posting)

    assert [(match.keyword_id, match.score) for match in result.include_matches] == [
        (data_analysis.id, 5),
        (ai.id, 1),
    ]


@pytest.mark.integration
def test_수집기가_신규_공고의_키워드_근거를_함께_저장한다(
    db_session: Session, posting: JobPosting
) -> None:
    keyword = _keyword(db_session, term="데이터")

    result = CollectorService(db_session).collect(
        source_id=posting.source_id,
        raw_jobs=[
            RawJob(
                external_id=f"collector-{uuid4().hex}",
                url="https://example.com/jobs/collector",
                title="데이터 엔지니어",
                description="데이터 파이프라인을 개발합니다.",
            )
        ],
    )

    match = db_session.scalar(
        select(JobKeywordMatch).where(JobKeywordMatch.keyword_id == keyword.id)
    )
    assert result.items_new == 1
    assert result.items_matched == 1
    assert match is not None
