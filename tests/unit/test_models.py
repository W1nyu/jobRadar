"""M2 데이터 모델의 스키마 계약을 검증한다."""

from sqlalchemy import UniqueConstraint

from app.models import Base, JobKeywordMatch, JobPosting, Notification


def test_메타데이터에_설계된_테이블_10종이_등록된다() -> None:
    assert set(Base.metadata.tables) == {
        "sources",
        "job_postings",
        "job_posting_revisions",
        "keywords",
        "job_keyword_matches",
        "crawl_runs",
        "notifications",
        "push_subscriptions",
        "oauth_tokens",
        "app_settings",
    }


def _unique_column_sets(model: type[object]) -> set[tuple[str, ...]]:
    table = model.__table__  # type: ignore[attr-defined]
    return {
        tuple(column.name for column in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }


def test_중복_방지_unique_제약이_모델에_정의된다() -> None:
    assert {("source_id", "external_id"), ("source_id", "fingerprint")} <= _unique_column_sets(
        JobPosting
    )
    assert {("job_posting_id", "keyword_id")} <= _unique_column_sets(JobKeywordMatch)
    assert {("job_posting_id", "channel")} <= _unique_column_sets(Notification)


def test_공고_검색과_마감_필터용_인덱스가_정의된다() -> None:
    names = {index.name for index in JobPosting.__table__.indexes}

    assert {
        "ix_job_postings_source_first_seen_at",
        "ix_job_postings_title_trgm",
        "ix_job_postings_deadline_at_open",
        "ix_job_postings_first_seen_at_open",
    } <= names
