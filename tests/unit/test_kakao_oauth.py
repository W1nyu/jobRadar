"""M9 카카오 OAuth HTTP 계약과 Fernet 토큰 암호화."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
import respx
from cryptography.fernet import Fernet

from app.services.kakao import (
    EncryptedTokenCipher,
    KakaoOAuthClient,
    KakaoOAuthError,
    KakaoTokenSet,
)


def test_카카오_인가_url은_talk_message_scope와_state를_포함한다() -> None:
    client = KakaoOAuthClient(
        rest_api_key="rest-key",
        redirect_uri="https://example.com/oauth/kakao/callback",
    )

    url = client.authorization_url(state="state-value")
    query = parse_qs(urlsplit(url).query)

    assert urlsplit(url).scheme == "https"
    assert query["client_id"] == ["rest-key"]
    assert query["scope"] == ["talk_message"]
    assert query["state"] == ["state-value"]


@respx.mock
def test_인가코드는_카카오_토큰_응답으로_교환된다() -> None:
    route = respx.post("https://kauth.kakao.com/oauth/token").mock(
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
    client = KakaoOAuthClient(
        rest_api_key="rest-key",
        redirect_uri="https://example.com/oauth/kakao/callback",
        client_secret="client-secret",
    )

    tokens = client.exchange_code("authorization-code", now=datetime(2026, 8, 22, tzinfo=UTC))

    assert tokens.access_token == "access-token"
    assert tokens.refresh_token == "refresh-token"
    assert tokens.access_expires_at == datetime(2026, 8, 22, 6, tzinfo=UTC)
    assert route.called is True
    assert b"grant_type=authorization_code" in route.calls.last.request.content
    assert b"client_secret=client-secret" in route.calls.last.request.content


@respx.mock
def test_카카오_토큰_교환의_invalid_client는_안전한_원인으로_분류한다() -> None:
    respx.post("https://kauth.kakao.com/oauth/token").mock(
        return_value=httpx.Response(
            401,
            json={"error": "invalid_client", "error_description": "Bad client credentials"},
        )
    )
    client = KakaoOAuthClient(
        rest_api_key="rest-key",
        redirect_uri="https://example.com/oauth/kakao/callback",
    )

    with pytest.raises(KakaoOAuthError) as raised:
        client.exchange_code("authorization-code")

    assert raised.value.reason == "invalid_client"


def test_토큰은_fernet으로_암호화한_뒤에만_복호화된다() -> None:
    cipher = EncryptedTokenCipher(Fernet.generate_key().decode())
    tokens = KakaoTokenSet(
        access_token="access-token",
        refresh_token="refresh-token",
        access_expires_at=datetime.now(UTC) + timedelta(hours=1),
        refresh_expires_at=datetime.now(UTC) + timedelta(days=60),
    )

    encrypted = cipher.encrypt(tokens.access_token)

    assert encrypted != tokens.access_token
    assert cipher.decrypt(encrypted) == tokens.access_token
