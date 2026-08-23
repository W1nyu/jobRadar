"""M12 자동 알림 활성화 상태와 수동 발송 제어 계약."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.services.dispatcher import DispatchSummary
from app.services.notification_preferences import NotificationPreferenceService
from app.services.notification_runtime import NotificationRuntime
from tests.integration.test_database import TEST_DATABASE_URL


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
def test_알림은_기본_활성이고_꺼두면_수동_발송도_생략한다(
    db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    preferences = NotificationPreferenceService(db_session)
    assert preferences.get().enabled is True

    preferences.set_enabled(False)
    assert preferences.get().enabled is False

    runtime = NotificationRuntime(
        Settings(
            _env_file=None,
            APP_BASE_URL="https://example.com",
            SECRET_KEY="test-secret",
        )
    )

    class UnexpectedDispatcher:
        def __init__(self, *args: object, **kwargs: object) -> None:
            raise AssertionError("알림을 끈 상태에서는 디스패처를 만들면 안 됩니다.")

    monkeypatch.setattr(
        "app.services.notification_runtime.NotificationDispatcher", UnexpectedDispatcher
    )

    assert runtime.dispatch(db_session, now=datetime(2026, 8, 23, tzinfo=UTC)) == DispatchSummary()
