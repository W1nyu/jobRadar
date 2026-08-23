"""M8 관리자 웹 UI의 DB 연동 계약."""

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
from time import perf_counter
from uuid import uuid4

import pytest
from argon2 import PasswordHasher
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.db import get_db
from app.main import create_app
from app.models import (
    AppSetting,
    CrawlRun,
    CrawlStatus,
    CrawlTrigger,
    FetchStrategy,
    JobKeywordMatch,
    JobPosting,
    Keyword,
    KeywordKind,
    Source,
)
from app.worker.main import load_active_sources
from tests.integration.test_database import TEST_DATABASE_URL


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """커밋하는 웹 서비스도 테스트 뒤 되돌릴 수 있는 세션을 제공한다."""
    engine = create_engine(TEST_DATABASE_URL)
    try:
        with engine.connect() as connection:
            migrated = connection.execute(text("SELECT to_regclass('public.sources')")).scalar()
    except OperationalError:
        pytest.skip("로컬 PostgreSQL이 준비되지 않았습니다. M2 DB를 먼저 기동하세요.")
    if migrated is None:
        pytest.skip("M2 마이그레이션이 적용되지 않았습니다. alembic upgrade head를 실행하세요.")

    connection = engine.connect()
    transaction = connection.begin()
    session = Session(bind=connection, join_transaction_mode="create_savepoint")
    try:
        yield session
    finally:
        session.close()
        transaction.rollback()
        connection.close()
        engine.dispose()


@pytest.fixture
def client(db_session: Session) -> Generator[TestClient, None, None]:
    settings = Settings(
        _env_file=None,
        APP_BASE_URL="https://example.com",
        SECRET_KEY="test-secret",
        ADMIN_USERNAME="admin",
        ADMIN_PASSWORD_HASH=PasswordHasher().hash("correct-password"),
    )
    app = create_app(settings=settings)

    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app, follow_redirects=False) as test_client:
        login = test_client.post(
            "/login", data={"username": "admin", "password": "correct-password"}
        )
        assert login.status_code == 303
        yield test_client


def _source() -> Source:
    return Source(
        slug=f"admin-web-{uuid4().hex}",
        name="관리 UI 테스트 소스",
        crawler_key="linkareer",
        base_url="https://linkareer.com",
        fetch_strategy=FetchStrategy.HTML,
    )


@pytest.mark.integration
def test_검색과상세화면은_매칭근거를_표시하고_1초안에_응답한다(
    client: TestClient, db_session: Session
) -> None:
    source = _source()
    keyword = Keyword(term=f"데이터-{uuid4().hex}", kind=KeywordKind.INCLUDE)
    db_session.add_all([source, keyword])
    db_session.flush()
    posting = JobPosting(
        source_id=source.id,
        external_id=uuid4().hex,
        fingerprint=uuid4().hex,
        content_hash="a" * 64,
        url="https://example.com/jobs/data",
        title="데이터 분석 인턴",
        description="데이터 기반 제품 분석 업무",
    )
    db_session.add(posting)
    db_session.flush()
    db_session.add(
        JobKeywordMatch(
            job_posting_id=posting.id,
            keyword_id=keyword.id,
            matched_field="title",
            matched_snippet="데이터 분석",
        )
    )
    db_session.flush()

    started = perf_counter()
    listed = client.get("/admin/jobs?query=%EB%8D%B0%EC%9D%B4%ED%84%B0&matched=true")
    elapsed = perf_counter() - started
    detail = client.get(f"/admin/jobs/{posting.id}")

    assert listed.status_code == 200
    assert "데이터 분석 인턴" in listed.text
    assert elapsed < 1
    assert detail.status_code == 200
    assert "데이터 분석" in detail.text


@pytest.mark.integration
def test_대시보드는_실패이력과_15분_지난_워커하트비트_경고를_표시한다(
    client: TestClient, db_session: Session
) -> None:
    source = _source()
    db_session.add(source)
    db_session.flush()
    db_session.add(
        CrawlRun(
            source_id=source.id,
            trigger=CrawlTrigger.SCHEDULED,
            status=CrawlStatus.FAILED,
            error_type="ParserError",
            error_message="목록 구조가 바뀌었습니다.",
        )
    )
    db_session.add(
        AppSetting(
            key="worker_heartbeat",
            value={"at": (datetime.now(UTC) - timedelta(minutes=16)).isoformat()},
        )
    )
    db_session.flush()

    response = client.get("/admin")

    assert response.status_code == 200
    assert "워커 하트비트가 15분 이상 갱신되지 않았습니다." in response.text
    assert "목록 구조가 바뀌었습니다." in response.text


@pytest.mark.integration
def test_대시보드는_수집_시각을_한국_표준시로_표시한다(
    client: TestClient, db_session: Session
) -> None:
    collected_at = datetime(2026, 8, 22, 15, 30, tzinfo=UTC)
    source = _source()
    source.last_success_at = collected_at
    db_session.add(source)
    db_session.flush()
    db_session.add(
        CrawlRun(
            source_id=source.id,
            trigger=CrawlTrigger.MANUAL,
            status=CrawlStatus.SUCCESS,
            started_at=collected_at,
        )
    )
    db_session.flush()

    response = client.get("/admin")

    assert response.status_code == 200
    assert response.text.count("2026-08-23 00:30 KST") >= 2
    assert "표시 시각: KST (UTC+9)" in response.text


@pytest.mark.integration
def test_소스_생성은_다음_스케줄러_동기화에서_읽을_활성행을_만든다(
    client: TestClient, db_session: Session
) -> None:
    slug = f"ui-source-{uuid4().hex[:12]}"

    response = client.post(
        "/admin/sources",
        data={
            "slug": slug,
            "name": "UI 등록 소스",
            "crawler_key": "linkareer",
            "base_url": "https://linkareer.com",
            "fetch_strategy": "html",
            "interval_minutes": "30",
            "rate_limit_per_min": "10",
            "config_json": "{}",
            "is_active": "on",
        },
    )

    assert response.status_code == 303
    assert any(source.id for source in load_active_sources(lambda: db_session) if source.id)
    assert (
        db_session.scalar(text("SELECT slug FROM sources WHERE slug = :slug"), {"slug": slug})
        == slug
    )


@pytest.mark.integration
def test_소스와_키워드는_관리_화면에서_수정하고_삭제할_수_있다(
    client: TestClient, db_session: Session
) -> None:
    source = _source()
    keyword = Keyword(term=f"관리키워드-{uuid4().hex}", kind=KeywordKind.INCLUDE)
    db_session.add_all([source, keyword])
    db_session.flush()

    assert client.get("/admin/sources").status_code == 200
    assert client.get("/admin/keywords").status_code == 200
    assert client.get("/admin/notifications").status_code == 200

    source_update = client.post(
        f"/admin/sources/{source.id}",
        data={
            "slug": source.slug,
            "name": "수정한 소스",
            "crawler_key": "linkareer",
            "base_url": "https://linkareer.com",
            "fetch_strategy": "html",
            "interval_minutes": "45",
            "rate_limit_per_min": "8",
            "config_json": "{}",
            "is_active": "on",
        },
    )
    keyword_update = client.post(
        f"/admin/keywords/{keyword.id}",
        data={
            "term": "수정키워드",
            "kind": "include",
            "match_mode": "substring",
            "target_fields": ["title", "description"],
            "weight": "2",
            "is_active": "on",
        },
    )

    assert source_update.status_code == 303
    assert keyword_update.status_code == 303
    assert db_session.get(Source, source.id).name == "수정한 소스"
    assert db_session.get(Keyword, keyword.id).term == "수정키워드"
    assert client.post(f"/admin/sources/{source.id}/delete").status_code == 303
    assert client.post(f"/admin/keywords/{keyword.id}/delete").status_code == 303
    assert db_session.get(Source, source.id) is None
    assert db_session.get(Keyword, keyword.id) is None
