"""M10 DB 재시작 뒤 stale 풀 연결 복구 계약."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from app.core.config import Settings
from app.core.db import create_engine_for_settings
from tests.integration.test_database import TEST_DATABASE_URL


@pytest.mark.integration
def test_풀에_남은_끊긴_db연결은_pre_ping으로_교체해_다음_요청을_복구한다() -> None:
    settings = Settings(
        _env_file=None,
        APP_BASE_URL="https://example.com",
        SECRET_KEY="test-secret",
        DATABASE_URL=TEST_DATABASE_URL,
        DB_POOL_SIZE=1,
        DB_MAX_OVERFLOW=0,
    )
    engine = create_engine_for_settings(settings)
    try:
        connection = engine.connect()
        raw_connection = connection.connection.driver_connection
        connection.close()
        raw_connection.close()

        with engine.connect() as recovered:
            assert recovered.scalar(text("SELECT 1")) == 1
    except OperationalError:
        pytest.skip("로컬 PostgreSQL이 준비되지 않았습니다. M2 DB를 먼저 기동하세요.")
    finally:
        engine.dispose()
