"""M9 관리자 카카오 OAuth 연결 콜백의 end-to-end 계약."""

from __future__ import annotations

from collections.abc import Generator
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import respx
from argon2 import PasswordHasher
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.db import get_db
from app.main import create_app
from app.models import OAuthToken
from tests.integration.test_database import TEST_DATABASE_URL


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(TEST_DATABASE_URL)
    try:
        with engine.connect() as connection:
            migrated = connection.execute(
                text("SELECT to_regclass('public.oauth_tokens')")
            ).scalar()
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
        FERNET_KEY=Fernet.generate_key().decode(),
        KAKAO_REST_API_KEY="rest-key",
        KAKAO_CLIENT_SECRET="client-secret",
        KAKAO_REDIRECT_URI="https://example.com/oauth/kakao/callback",
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


@pytest.mark.integration
@respx.mock
def test_카카오_동의_callback은_암호화_토큰을_저장하고_알림화면으로_돌아온다(
    client: TestClient, db_session: Session
) -> None:
    authorize = client.get("/admin/kakao/connect")
    state = parse_qs(urlsplit(authorize.headers["location"]).query)["state"][0]
    respx.post("https://kauth.kakao.com/oauth/token").mock(
        return_value=httpx.Response(
            200,
            json={
                "access_token": "access-token",
                "refresh_token": "refresh-token",
                "expires_in": 21600,
                "refresh_token_expires_in": 5_184_000,
            },
        )
    )

    callback = client.get(f"/oauth/kakao/callback?code=code-value&state={state}")

    token = db_session.scalar(select(OAuthToken).where(OAuthToken.provider == "kakao"))
    assert authorize.status_code == 303
    assert callback.status_code == 303
    assert callback.headers["location"] == "/admin/notifications?oauth=connected"
    assert token is not None
    assert token.access_token_enc != "access-token"

    history = client.get("/admin/notifications?oauth=connected")

    assert "카카오 연결이 완료되었습니다." in history.text
    assert "카카오 연결됨" in history.text


@pytest.mark.integration
@respx.mock
def test_토큰_교환_실패는_알림화면에_실패원인을_표시한다(client: TestClient) -> None:
    authorize = client.get("/admin/kakao/connect")
    state = parse_qs(urlsplit(authorize.headers["location"]).query)["state"][0]
    respx.post("https://kauth.kakao.com/oauth/token").mock(
        return_value=httpx.Response(401, json={"error": "invalid_client"})
    )

    callback = client.get(f"/oauth/kakao/callback?code=code-value&state={state}")

    assert callback.headers["location"] == "/admin/notifications?oauth=failed&reason=invalid_client"

    history = client.get(callback.headers["location"])

    assert "클라이언트 시크릿" in history.text
