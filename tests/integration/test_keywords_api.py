"""M5 키워드 CRUD API를 실제 PostgreSQL 트랜잭션에서 검증한다."""

from collections.abc import Generator
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.db import get_db
from app.main import create_app
from tests.integration.test_database import TEST_DATABASE_URL


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    """API의 commit도 바깥 연결 트랜잭션으로 되돌릴 수 있는 세션을 제공한다."""
    engine = create_engine(TEST_DATABASE_URL)
    try:
        with engine.connect() as connection:
            migrated = connection.execute(text("SELECT to_regclass('public.keywords')")).scalar()
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
    """테스트 세션을 FastAPI 의존성으로 주입해 실제 설정/환경을 읽지 않는다."""
    settings = Settings(
        _env_file=None,
        APP_BASE_URL="https://example.com",
        SECRET_KEY="test-secret",
    )
    app = create_app(settings=settings)

    def override_get_db() -> Generator[Session, None, None]:
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client


@pytest.mark.integration
def test_키워드_CRUD는_검증된_필드로_생성_조회_수정_삭제한다(client: TestClient) -> None:
    term = f"테스트키워드-{uuid4().hex}"
    created = client.post(
        "/api/v1/keywords",
        json={
            "term": term,
            "kind": "include",
            "match_mode": "word",
            "target_fields": ["title"],
            "weight": 4,
        },
    )

    assert created.status_code == 201
    keyword_id = created.json()["id"]
    assert created.json()["term"] == term

    listed = client.get("/api/v1/keywords")
    assert listed.status_code == 200
    assert any(keyword["id"] == keyword_id for keyword in listed.json())

    updated = client.patch(
        f"/api/v1/keywords/{keyword_id}",
        json={"kind": "exclude", "target_fields": ["description"], "weight": 2},
    )
    assert updated.status_code == 200
    assert updated.json()["kind"] == "exclude"
    assert updated.json()["target_fields"] == ["description"]
    assert updated.json()["weight"] == 2

    deleted = client.delete(f"/api/v1/keywords/{keyword_id}")
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/keywords/{keyword_id}").status_code == 404


@pytest.mark.integration
def test_키워드_API는_잘못된_정규식과_대상_필드를_거절한다(client: TestClient) -> None:
    invalid_regex = client.post(
        "/api/v1/keywords",
        json={"term": "[", "match_mode": "regex", "target_fields": ["title"]},
    )
    invalid_field = client.post(
        "/api/v1/keywords",
        json={"term": "데이터", "target_fields": ["company"]},
    )

    assert invalid_regex.status_code == 422
    assert invalid_field.status_code == 422
