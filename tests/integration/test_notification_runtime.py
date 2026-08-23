"""M9 카카오 재인증 Web Push 폴백의 DB 상태 계약."""

from __future__ import annotations

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import AppSetting
from app.notifications.contracts import NotificationPayload, SendResult
from app.services.crawl_health import source_disabled_alert
from app.services.notification_runtime import NotificationRuntime
from tests.integration.test_database import TEST_DATABASE_URL


class ReauthRecordingChannel:
    """네트워크 없이 재인증 Web Push 페이로드만 기록한다."""

    def __init__(self) -> None:
        self.payloads: list[NotificationPayload] = []

    def send(self, payload: NotificationPayload) -> SendResult:
        self.payloads.append(payload)
        return SendResult(succeeded=True)


@pytest.fixture
def db_session() -> Generator[Session, None, None]:
    engine = create_engine(TEST_DATABASE_URL)
    try:
        with engine.connect() as connection:
            migrated = connection.execute(
                text("SELECT to_regclass('public.app_settings')")
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


@pytest.mark.integration
def test_카카오_재인증_실패는_web_push로_한번_안내하고_ui_상태를_남긴다(
    db_session: Session,
) -> None:
    state = db_session.get(AppSetting, "kakao_reauth")
    if state is None:
        db_session.add(
            AppSetting(
                key="kakao_reauth",
                value={"required": True, "error": "invalid_grant", "notified": False},
            )
        )
    else:
        state.value = {"required": True, "error": "invalid_grant", "notified": False}
    db_session.flush()
    runtime = NotificationRuntime(
        Settings(
            _env_file=None,
            APP_BASE_URL="https://example.com",
            SECRET_KEY="test-secret",
        )
    )
    channel = ReauthRecordingChannel()

    runtime._send_reauth_notice(db_session, channel)  # type: ignore[arg-type]
    runtime._send_reauth_notice(db_session, channel)  # type: ignore[arg-type]

    state = db_session.get(AppSetting, "kakao_reauth")
    assert len(channel.payloads) == 1
    assert channel.payloads[0].title == "카카오 재인증 필요"
    assert channel.payloads[0].url == "https://example.com/admin/kakao/connect"
    assert state is not None
    assert state.value["notified"] is True


@pytest.mark.integration
def test_수집_장애_운영_알림은_web_push로_보내고_공고_알림_이력에는_섞지_않는다(
    db_session: Session,
) -> None:
    runtime = NotificationRuntime(
        Settings(
            _env_file=None,
            APP_BASE_URL="https://example.com",
            SECRET_KEY="test-secret",
        )
    )
    channel = ReauthRecordingChannel()
    runtime._web_push_channel = lambda _session: channel  # type: ignore[method-assign]

    runtime.send_operational_alert(
        db_session,
        source_disabled_alert(source_id=42, source_name="테스트 소스", failures=5),
    )

    assert len(channel.payloads) == 1
    assert channel.payloads[0].title == "수집 소스 자동 비활성화"
    assert channel.payloads[0].url == "https://example.com/admin/sources/42"
