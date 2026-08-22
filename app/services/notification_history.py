"""관리 UI가 알림 이력과 카카오 재인증 상태를 읽는 서비스."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import Notification
from app.repositories import AppSettingRepository, NotificationRepository


@dataclass(frozen=True, slots=True)
class NotificationHistory:
    """알림 이력 화면에 필요한 목록과 운영 경고 상태."""

    notifications: Sequence[Notification]
    kakao_reauth_required: bool
    kakao_reauth_error: str | None


class NotificationHistoryService:
    """알림 채널이 아닌 관리 웹 계층을 위한 읽기 전용 서비스."""

    def __init__(self, session: Session) -> None:
        self.notifications = NotificationRepository(session)
        self.settings = AppSettingRepository(session)

    def get(self) -> NotificationHistory:
        """최근 100건과 카카오 재연결 필요 상태를 반환한다."""
        reauth = self.settings.get("kakao_reauth")
        value = reauth.value if reauth else {}
        return NotificationHistory(
            notifications=self.notifications.list_recent(limit=100),
            kakao_reauth_required=value.get("required") is True,
            kakao_reauth_error=value.get("error") if isinstance(value.get("error"), str) else None,
        )
