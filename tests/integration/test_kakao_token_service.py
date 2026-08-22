"""M9 Fernet 카카오 토큰 저장과 갱신 실패 재인증 상태 계약."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime, timedelta

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import create_engine, select, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.models import AppSetting, OAuthToken
from app.services.kakao import (
    EncryptedTokenCipher,
    KakaoOAuthError,
    KakaoReauthenticationRequired,
    KakaoTokenService,
    KakaoTokenSet,
)
from tests.integration.test_database import TEST_DATABASE_URL


class RefreshFailingClient:
    """카카오 refresh token 무효화를 재현하는 DB-독립 HTTP 가짜."""

    def refresh(self, _: str, *, now: datetime) -> KakaoTokenSet:
        raise KakaoOAuthError("invalid_grant")


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(TEST_DATABASE_URL)
    try:
        with engine.connect() as connection:
            migrated = connection.execute(
                text(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = 'oauth_tokens' AND column_name = 'last_error'"
                )
            ).scalar()
    except OperationalError:
        pytest.skip("로컬 PostgreSQL이 준비되지 않았습니다. M2 DB를 먼저 기동하세요.")
    if migrated is None:
        pytest.skip("M9 마이그레이션이 적용되지 않았습니다. alembic upgrade head를 실행하세요.")

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


@pytest.mark.integration
def test_카카오_토큰은_암호화돼_저장되고_갱신_실패는_재인증_상태로_남는다(
    db_session: Session,
) -> None:
    now = datetime(2026, 8, 22, tzinfo=UTC)
    cipher = EncryptedTokenCipher(Fernet.generate_key().decode())
    service = KakaoTokenService(db_session, cipher=cipher, client=RefreshFailingClient())
    service.save(
        KakaoTokenSet(
            access_token="access-token",
            refresh_token="refresh-token",
            access_expires_at=now - timedelta(minutes=1),
            refresh_expires_at=now + timedelta(days=30),
        )
    )

    with pytest.raises(KakaoReauthenticationRequired):
        service.access_token(now=now)

    token = db_session.scalar(select(OAuthToken).where(OAuthToken.provider == "kakao"))
    reauth = db_session.get(AppSetting, "kakao_reauth")
    assert token is not None
    assert token.access_token_enc != "access-token"
    assert token.refresh_token_enc != "refresh-token"
    assert cipher.decrypt(token.access_token_enc) == "access-token"
    assert reauth is not None
    assert reauth.value["required"] is True
    assert token.last_error == "invalid_grant"
