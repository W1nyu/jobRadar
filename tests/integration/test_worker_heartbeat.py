"""M6 워커 하트비트의 app_settings 저장을 검증한다."""

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.models import AppSetting
from app.worker.main import record_worker_heartbeat
from tests.integration.test_database import TEST_DATABASE_URL


@pytest.mark.integration
def test_워커_하트비트는_현재_시각을_app_settings에_기록한다() -> None:
    engine = create_engine(TEST_DATABASE_URL)
    try:
        with engine.connect() as probe:
            migrated = probe.execute(text("SELECT to_regclass('public.app_settings')")).scalar()
    except OperationalError:
        pytest.skip("로컬 PostgreSQL이 준비되지 않았습니다. M2 DB를 먼저 기동하세요.")

    if migrated is None:
        pytest.skip("M2 마이그레이션이 적용되지 않았습니다. alembic upgrade head를 실행하세요.")

    connection = engine.connect()
    transaction = connection.begin()

    def session_factory() -> Session:
        return Session(bind=connection, join_transaction_mode="create_savepoint")

    try:
        record_worker_heartbeat(session_factory)
        with session_factory() as session:
            heartbeat = session.get(AppSetting, "worker_heartbeat")
            assert heartbeat is not None
            assert heartbeat.value["at"].endswith("+00:00")
    finally:
        transaction.rollback()
        connection.close()
        engine.dispose()
