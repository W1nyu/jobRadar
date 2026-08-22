"""M6 PostgreSQL advisory lock의 중복 차단과 세션 종료 해제를 검증한다."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.pool import NullPool

from app.core.locks import release_source_lock, try_acquire_source_lock
from tests.integration.test_database import TEST_DATABASE_URL


@pytest.mark.integration
def test_같은_소스_락은_동시_획득을_막고_세션_종료_뒤_해제된다() -> None:
    # pooled logical connection.close()는 PostgreSQL 세션을 유지하므로, 강제 종료를 검증할 때는
    # 물리 연결을 실제로 닫는 NullPool을 사용한다.
    engine = create_engine(TEST_DATABASE_URL, poolclass=NullPool)
    first_connection = engine.connect()
    second_connection = engine.connect()
    try:
        try:
            assert try_acquire_source_lock(first_connection, source_id=987_654) is True
        except OperationalError:
            pytest.skip("로컬 PostgreSQL이 준비되지 않았습니다. M2 DB를 먼저 기동하세요.")

        assert try_acquire_source_lock(second_connection, source_id=987_654) is False

        first_connection.close()
        assert try_acquire_source_lock(second_connection, source_id=987_654) is True
        release_source_lock(second_connection, source_id=987_654)
    finally:
        first_connection.close()
        second_connection.close()
        engine.dispose()
