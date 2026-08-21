"""DB 세션 구성은 연결 없이도 설정값을 반영해야 한다."""

from app.core.config import Settings
from app.core.db import create_engine_for_settings


def test_엔진이_설정된_연결_풀_한도를_사용한다() -> None:
    settings = Settings(
        _env_file=None,
        APP_BASE_URL="https://example.com",
        SECRET_KEY="test-secret",
        DATABASE_URL="postgresql+psycopg://test:test@localhost:5432/jobradar_test",
        DB_POOL_SIZE=3,
        DB_MAX_OVERFLOW=1,
    )

    engine = create_engine_for_settings(settings)
    try:
        assert engine.pool.size() == 3
        assert engine.pool._max_overflow == 1  # type: ignore[attr-defined]
    finally:
        engine.dispose()
