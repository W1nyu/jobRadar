"""M12 채용공고 알림의 전역 활성화 상태를 관리한다."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.repositories import AppSettingRepository

_NOTIFICATIONS_ENABLED_KEY = "notifications_enabled"


@dataclass(frozen=True, slots=True)
class NotificationPreferences:
    """관리 화면과 워커가 공유하는 알림 수신 설정."""

    enabled: bool


class NotificationPreferenceService:
    """알림 수신 여부의 기본값·변경·트랜잭션 경계를 담당한다."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.settings = AppSettingRepository(session)

    def get(self) -> NotificationPreferences:
        """저장된 값이 없으면 기존 사용자에게 안전한 기본값인 켜짐을 반환한다."""
        setting = self.settings.get(_NOTIFICATIONS_ENABLED_KEY)
        if setting is None:
            return NotificationPreferences(enabled=True)
        return NotificationPreferences(enabled=setting.value.get("enabled") is not False)

    def set_enabled(self, enabled: bool) -> NotificationPreferences:
        """카카오·브라우저 채용공고 알림을 함께 켜거나 끈다."""
        setting = self.settings.get(_NOTIFICATIONS_ENABLED_KEY)
        value = {"enabled": enabled}
        if setting is None:
            self.settings.create(key=_NOTIFICATIONS_ENABLED_KEY, value=value)
        else:
            self.settings.update(setting, value=value)
        self.session.commit()
        return NotificationPreferences(enabled=enabled)
