"""실제 PostgreSQL 스키마의 제약과 시드를 검증한다."""

from collections.abc import Generator
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import (
    FetchStrategy,
    JobPosting,
    Notification,
    NotificationChannel,
    Source,
)
from app.repositories import SourceRepository
from app.seed import DEFAULT_KEYWORDS, seed_builtin_sources, seed_default_keywords

TEST_DATABASE_URL = "postgresql+psycopg://jobradar:jobradar@127.0.0.1:5432/jobradar"


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """로컬 M2 DB가 준비되지 않은 개발 환경에서는 통합 테스트를 건너뛴다."""
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
    token = uuid4().hex
    return Source(
        slug=f"test-{token}",
        name="제약 검증 소스",
        crawler_key="test",
        base_url="https://example.com",
        fetch_strategy=FetchStrategy.API,
    )


def _job(source_id: int) -> JobPosting:
    token = uuid4().hex
    return JobPosting(
        source_id=source_id,
        external_id=f"external-{token}",
        fingerprint=f"fingerprint-{token}",
        content_hash="0" * 64,
        url="https://example.com/jobs/1",
        title="데이터 분석 인턴",
    )


@pytest.mark.integration
def test_공고와_알림의_unique_제약은_integrity_error를_발생시킨다(db_session: Session) -> None:
    source = _source()
    db_session.add(source)
    db_session.flush()

    job = _job(source.id)
    db_session.add(job)
    db_session.flush()

    db_session.add(
        JobPosting(
            source_id=source.id,
            external_id=job.external_id,
            fingerprint="different-fingerprint",
            content_hash="1" * 64,
            url="https://example.com/jobs/2",
            title="중복 공고",
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()

    db_session.rollback()
    source = _source()
    db_session.add(source)
    db_session.flush()
    job = _job(source.id)
    db_session.add(job)
    db_session.flush()
    db_session.add(
        Notification(
            job_posting_id=job.id,
            channel=NotificationChannel.KAKAO,
        )
    )
    db_session.flush()
    db_session.add(
        Notification(
            job_posting_id=job.id,
            channel=NotificationChannel.KAKAO,
        )
    )
    with pytest.raises(IntegrityError):
        db_session.flush()


@pytest.mark.integration
def test_기본_키워드_시드는_8개를_중복_없이_등록한다(db_session: Session) -> None:
    seed_default_keywords(db_session)
    db_session.flush()
    added_on_repeat = seed_default_keywords(db_session)

    terms = set(db_session.scalars(text("SELECT term FROM keywords")).all())

    assert added_on_repeat == 0
    assert set(DEFAULT_KEYWORDS) <= terms


@pytest.mark.integration
def test_기본_소스_시드는_키를_db에_저장하지_않고_네개_이상을_활성화한다(
    db_session: Session,
) -> None:
    settings = Settings(
        _env_file=None,
        APP_BASE_URL="https://example.com",
        SECRET_KEY="test-secret",
        MSIT_RECRUITMENT_SERVICE_KEY="test-msit-key",
    )

    seed_builtin_sources(db_session, settings)
    sources = list(
        db_session.scalars(
            select(Source).where(
                Source.slug.in_(
                    (
                        "datagokr-msit-recruitment",
                        "linkareer",
                        "inthiswork",
                        "kofia",
                        "alio-recruitment",
                    )
                )
            )
        )
    )

    assert len(sources) >= 4
    assert all(source.is_active for source in sources)
    assert all("test-msit-key" not in str(source.config) for source in sources)


@pytest.mark.integration
def test_저장소_crud는_트랜잭션을_서비스_호출자에게_맡긴다(db_session: Session) -> None:
    repository = SourceRepository(db_session)
    source = repository.create(
        slug=f"repo-{uuid4().hex}",
        name="초기 이름",
        crawler_key="test",
        base_url="https://example.com",
        fetch_strategy=FetchStrategy.HTML,
    )

    assert repository.get(source.id) is source
    assert repository.update(source, name="변경된 이름").name == "변경된 이름"

    repository.delete(source)
    assert repository.get(source.id) is None
