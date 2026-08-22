"""카카오 OAuth 토큰 교환·Fernet 암호화 저장·선제 갱신 서비스."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import urlencode

import httpx
from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from app.models import OAuthToken
from app.repositories import AppSettingRepository, OAuthTokenRepository

_AUTHORIZE_URL = "https://kauth.kakao.com/oauth/authorize"
_TOKEN_URL = "https://kauth.kakao.com/oauth/token"
_PROVIDER = "kakao"


class KakaoOAuthError(RuntimeError):
    """토큰 교환·갱신 중 카카오가 반환한 실패."""

    def __init__(self, message: str, *, reason: str = "token_exchange") -> None:
        super().__init__(message)
        self.reason = reason


class KakaoReauthenticationRequired(KakaoOAuthError):
    """저장된 refresh token이 더는 갱신할 수 없는 경우."""


@dataclass(frozen=True, slots=True)
class KakaoTokenSet:
    """카카오가 발급하거나 갱신한 평문 토큰의 짧은 수명 객체."""

    access_token: str
    refresh_token: str | None
    access_expires_at: datetime
    refresh_expires_at: datetime | None


class EncryptedTokenCipher:
    """DB에 평문 OAuth 토큰을 남기지 않는 Fernet 래퍼."""

    def __init__(self, key: str) -> None:
        self.fernet = Fernet(key.encode())

    def encrypt(self, value: str) -> str:
        """평문 토큰을 URL-safe Fernet 문자열로 암호화한다."""
        return self.fernet.encrypt(value.encode()).decode()

    def decrypt(self, value: str) -> str:
        """암호문 토큰을 발송 직전 메모리에서만 복호화한다."""
        try:
            return self.fernet.decrypt(value.encode()).decode()
        except (InvalidToken, UnicodeDecodeError) as error:
            raise KakaoReauthenticationRequired("카카오 토큰을 복호화할 수 없습니다.") from error


class KakaoOAuthClient:
    """카카오 공식 OAuth endpoint만 호출하는 동기 HTTP 클라이언트."""

    def __init__(
        self,
        *,
        rest_api_key: str,
        redirect_uri: str,
        client_secret: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        self.rest_api_key = rest_api_key
        self.redirect_uri = redirect_uri
        self.client_secret = client_secret
        self.client = client or httpx.Client(timeout=10)
        self._owns_client = client is None

    def authorization_url(self, *, state: str) -> str:
        """talk_message 동의를 포함하고 callback 위조를 막는 인가 URL을 만든다."""
        return f"{_AUTHORIZE_URL}?{
            urlencode(
                {
                    'response_type': 'code',
                    'client_id': self.rest_api_key,
                    'redirect_uri': self.redirect_uri,
                    'scope': 'talk_message',
                    'state': state,
                }
            )
        }"

    def close(self) -> None:
        """호출 없이 끝난 OAuth 클라이언트의 보유 연결도 닫는다."""
        if self._owns_client:
            self.client.close()

    def exchange_code(self, code: str, *, now: datetime | None = None) -> KakaoTokenSet:
        """인가 코드를 access·refresh token으로 한 번 교환한다."""
        return self._request_tokens(
            {"grant_type": "authorization_code", "code": code, "redirect_uri": self.redirect_uri},
            now=now,
        )

    def refresh(self, refresh_token: str, *, now: datetime | None = None) -> KakaoTokenSet:
        """만료 임박 access token을 refresh token으로 교환한다."""
        return self._request_tokens(
            {"grant_type": "refresh_token", "refresh_token": refresh_token}, now=now
        )

    def _request_tokens(self, data: dict[str, str], *, now: datetime | None) -> KakaoTokenSet:
        request_data = {"client_id": self.rest_api_key, **data}
        if self.client_secret:
            request_data["client_secret"] = self.client_secret
        try:
            response = self.client.post(_TOKEN_URL, data=request_data)
            response.raise_for_status()
            body = response.json()
        except httpx.HTTPStatusError as error:
            raise KakaoOAuthError(
                "카카오 토큰 발급 요청이 거절됐습니다.",
                reason=_kakao_error_reason(error.response),
            ) from error
        except httpx.HTTPError as error:
            raise KakaoOAuthError(
                "카카오 토큰 서버와 통신하지 못했습니다.", reason="network"
            ) from error
        except ValueError as error:
            raise KakaoOAuthError("카카오 토큰 응답을 해석할 수 없습니다.") from error
        finally:
            if self._owns_client:
                self.client.close()
        if not isinstance(body.get("access_token"), str) or not isinstance(
            body.get("expires_in"), int
        ):
            raise KakaoOAuthError("카카오 토큰 응답에 access_token 또는 expires_in이 없습니다.")
        issued_at = now or datetime.now(UTC)
        refresh_token = body.get("refresh_token")
        refresh_expires_in = body.get("refresh_token_expires_in")
        return KakaoTokenSet(
            access_token=body["access_token"],
            refresh_token=refresh_token if isinstance(refresh_token, str) else None,
            access_expires_at=issued_at + timedelta(seconds=body["expires_in"]),
            refresh_expires_at=(
                issued_at + timedelta(seconds=refresh_expires_in)
                if isinstance(refresh_expires_in, int)
                else None
            ),
        )


class KakaoTokenService:
    """암호화 OAuth 토큰을 저장하고 발송 직전·매일 갱신한다."""

    def __init__(
        self, session: Session, *, cipher: EncryptedTokenCipher, client: KakaoOAuthClient
    ) -> None:
        self.session = session
        self.cipher = cipher
        self.client = client
        self.tokens = OAuthTokenRepository(session)
        self.settings = AppSettingRepository(session)

    def save(self, token_set: KakaoTokenSet) -> OAuthToken:
        """새 토큰을 암호화해 provider별 한 행에 저장하고 오류 배너를 지운다."""
        token = self.tokens.get_by_provider(_PROVIDER)
        values = _token_values(token_set, self.cipher)
        if token is None:
            token = self.tokens.create(provider=_PROVIDER, **values, last_error=None)
        else:
            self.tokens.update(token, **values, last_error=None)
        self._set_reauth_error(None)
        self.session.commit()
        return token

    def access_token(self, *, now: datetime | None = None) -> str:
        """5분 이내 만료면 선제 갱신하고, 실패 시 UI용 재인증 상태를 남긴다."""
        now = now or datetime.now(UTC)
        token = self.tokens.get_by_provider(_PROVIDER)
        if token is None or token.refresh_token_enc is None:
            self._require_reauthentication("카카오 연결이 필요합니다.")
        try:
            if token.access_expires_at is not None and token.access_expires_at > now + timedelta(
                minutes=5
            ):
                return self.cipher.decrypt(token.access_token_enc)
        except KakaoReauthenticationRequired as error:
            self._require_reauthentication(str(error))
        try:
            refreshed = self.client.refresh(self.cipher.decrypt(token.refresh_token_enc), now=now)
            if refreshed.refresh_token is None:
                refreshed = KakaoTokenSet(
                    access_token=refreshed.access_token,
                    refresh_token=self.cipher.decrypt(token.refresh_token_enc),
                    access_expires_at=refreshed.access_expires_at,
                    refresh_expires_at=token.refresh_expires_at,
                )
            self.tokens.update(token, **_token_values(refreshed, self.cipher), last_error=None)
            self._set_reauth_error(None)
            self.session.commit()
            return refreshed.access_token
        except KakaoOAuthError as error:
            token.last_error = str(error)[:1_000]
            self._set_reauth_error(token.last_error)
            self.session.commit()
            raise KakaoReauthenticationRequired(token.last_error) from error

    def refresh_daily(self, *, now: datetime | None = None) -> str:
        """매일 04:00 잡이 access token 만료 여부와 무관하게 갱신하도록 한다."""
        now = now or datetime.now(UTC)
        token = self.tokens.get_by_provider(_PROVIDER)
        if token is None or token.refresh_token_enc is None:
            self._require_reauthentication("카카오 연결이 필요합니다.")
        try:
            refreshed = self.client.refresh(self.cipher.decrypt(token.refresh_token_enc), now=now)
            if refreshed.refresh_token is None:
                refreshed = KakaoTokenSet(
                    access_token=refreshed.access_token,
                    refresh_token=self.cipher.decrypt(token.refresh_token_enc),
                    access_expires_at=refreshed.access_expires_at,
                    refresh_expires_at=token.refresh_expires_at,
                )
            self.tokens.update(token, **_token_values(refreshed, self.cipher), last_error=None)
            self._set_reauth_error(None)
            self.session.commit()
            return refreshed.access_token
        except (KakaoOAuthError, KakaoReauthenticationRequired) as error:
            token.last_error = str(error)[:1_000]
            self._set_reauth_error(token.last_error)
            self.session.commit()
            raise KakaoReauthenticationRequired(token.last_error) from error

    def _require_reauthentication(self, error: str) -> None:
        """토큰 부재·복호화 실패도 UI와 Web Push 폴백이 알 수 있게 기록한다."""
        self._set_reauth_error(error)
        self.session.commit()
        raise KakaoReauthenticationRequired(error)

    def _set_reauth_error(self, error: str | None) -> None:
        """대시보드가 읽는 카카오 재인증 필요 상태를 갱신한다."""
        setting = self.settings.get("kakao_reauth")
        previous = setting.value if setting is not None else {}
        value = (
            {
                "required": True,
                "error": error,
                "notified": bool(previous.get("notified"))
                if previous.get("error") == error
                else False,
            }
            if error
            else {"required": False}
        )
        if setting is None:
            self.settings.create(key="kakao_reauth", value=value)
        else:
            self.settings.update(setting, value=value)


def _token_values(token_set: KakaoTokenSet, cipher: EncryptedTokenCipher) -> dict[str, object]:
    """ORM 저장 전 평문 토큰을 모두 암호화한다."""
    return {
        "access_token_enc": cipher.encrypt(token_set.access_token),
        "refresh_token_enc": (
            cipher.encrypt(token_set.refresh_token) if token_set.refresh_token is not None else None
        ),
        "access_expires_at": token_set.access_expires_at,
        "refresh_expires_at": token_set.refresh_expires_at,
    }


def _kakao_error_reason(response: httpx.Response) -> str:
    """카카오 응답에서 화면에 안전하게 표시할 오류 코드만 추린다."""
    try:
        body = response.json()
    except ValueError:
        return "token_exchange"
    error = body.get("error") if isinstance(body, dict) else None
    return error if error in {"invalid_client", "invalid_grant"} else "token_exchange"
