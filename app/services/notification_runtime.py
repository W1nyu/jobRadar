"""워커가 설정·DB로 실제 M9 채널을 조립하는 얇은 어댑터."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import PushSubscription
from app.notifications import KakaoChannel, NotificationPayload, SendResult, WebPushChannel
from app.repositories import AppSettingRepository, PushSubscriptionRepository
from app.services.dispatcher import DispatchSettings, DispatchSummary, NotificationDispatcher
from app.services.kakao import (
    EncryptedTokenCipher,
    KakaoOAuthClient,
    KakaoReauthenticationRequired,
    KakaoTokenService,
)


class NotificationRuntime:
    """DB를 모르는 채널과 DB를 아는 디스패처 사이의 운영 조립 지점."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def dispatch(self, session: Session, *, now: datetime | None = None) -> DispatchSummary:
        """설정된 채널로 신규 공고를 발송하고 필요하면 카카오 재인증을 Web Push로 알린다."""
        now = now or datetime.now(UTC)
        web_push = self._web_push_channel(session)
        channels = [web_push] if web_push is not None else []
        if self.settings.kakao_enabled:
            client = self._kakao_client()
            try:
                access_token = self._kakao_service(session, client).access_token(now=now)
                channels.append(KakaoChannel(access_token=access_token))
            except KakaoReauthenticationRequired:
                self._send_reauth_notice(session, web_push)
            finally:
                client.close()
        return NotificationDispatcher(
            session,
            channels=channels,
            settings=DispatchSettings(
                quiet_hours_start=self.settings.quiet_hours_start,
                quiet_hours_end=self.settings.quiet_hours_end,
                timezone=self.settings.timezone,
                lookback_minutes=self.settings.notification_lookback_minutes,
                app_base_url=self.settings.app_base_url,
            ),
        ).dispatch(now=now)

    def refresh_kakao_tokens(self, session: Session, *, now: datetime | None = None) -> None:
        """매일 잡에서 refresh token을 갱신하고 실패 시 한 번만 Web Push 폴백을 보낸다."""
        if not self.settings.kakao_enabled:
            return
        client = self._kakao_client()
        try:
            self._kakao_service(session, client).refresh_daily(now=now)
        except KakaoReauthenticationRequired:
            self._send_reauth_notice(session, self._web_push_channel(session))
        finally:
            client.close()

    def _web_push_channel(self, session: Session) -> WebPushChannel | None:
        if not self.settings.vapid_enabled:
            return None
        subscriptions = PushSubscriptionRepository(session).list_active()
        if not subscriptions:
            return None
        return WebPushChannel(
            subscriptions=tuple(
                _subscription_values(subscription) for subscription in subscriptions
            ),
            vapid_private_key=self.settings.vapid_private_key or "",
            vapid_subject=self.settings.vapid_subject or "",
        )

    def _kakao_client(self) -> KakaoOAuthClient:
        return KakaoOAuthClient(
            rest_api_key=self.settings.kakao_rest_api_key or "",
            redirect_uri=self.settings.kakao_redirect_uri or "",
            client_secret=self.settings.kakao_client_secret,
        )

    def _kakao_service(self, session: Session, client: KakaoOAuthClient) -> KakaoTokenService:
        return KakaoTokenService(
            session,
            cipher=EncryptedTokenCipher(self.settings.fernet_key or ""),
            client=client,
        )

    def _send_reauth_notice(self, session: Session, channel: WebPushChannel | None) -> None:
        """같은 카카오 오류로 매분 알림이 반복되지 않도록 한 번만 Web Push로 보낸다."""
        setting_repository = AppSettingRepository(session)
        setting = setting_repository.get("kakao_reauth")
        if setting is None or not setting.value.get("required") or setting.value.get("notified"):
            return
        if channel is None:
            return
        result = channel.send(
            NotificationPayload(
                title="카카오 재인증 필요",
                body="카카오 알림 토큰을 갱신할 수 없습니다. 관리자 화면에서 다시 연결하세요.",
                url=f"{self.settings.app_base_url}/admin/kakao/connect",
                items=(),
                tag="jobradar-kakao-reauth",
            )
        )
        _apply_web_push_result(session, result)
        if result.succeeded:
            setting.value = {**setting.value, "notified": True}
        session.commit()


def _subscription_values(subscription: PushSubscription) -> dict[str, str]:
    """ORM 구독을 채널이 받을 공개 dict로 복사한다."""
    return {
        "endpoint": subscription.endpoint,
        "p256dh": subscription.p256dh,
        "auth": subscription.auth,
    }


def _apply_web_push_result(session: Session, result: SendResult) -> None:
    """런타임 직접 전송의 만료·실패 구독도 동일 정책으로 정리한다."""
    subscriptions = PushSubscriptionRepository(session)
    for endpoint in result.invalid_endpoints:
        if subscription := subscriptions.get_by_endpoint(endpoint):
            subscription.is_active = False
    for endpoint in result.failed_endpoints:
        if subscription := subscriptions.get_by_endpoint(endpoint):
            subscription.failure_count += 1
            if subscription.failure_count >= 5:
                subscription.is_active = False
