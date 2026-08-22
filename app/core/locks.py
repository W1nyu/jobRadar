"""PostgreSQL 세션 단위 advisory lock 헬퍼."""

from sqlalchemy import text
from sqlalchemy.engine import Connection


def try_acquire_source_lock(connection: Connection, *, source_id: int) -> bool:
    """같은 소스 수집이 이미 진행 중이면 ``False``를 반환한다.

    PostgreSQL 세션 락이므로 호출자는 수집이 끝날 때까지 이 connection을 유지해야 한다.
    연결이 비정상 종료돼도 PostgreSQL이 자동으로 락을 해제한다.
    """
    acquired = connection.scalar(
        text("SELECT pg_try_advisory_lock(hashtext(:lock_name))"),
        {"lock_name": _source_lock_name(source_id)},
    )
    return bool(acquired)


def release_source_lock(connection: Connection, *, source_id: int) -> None:
    """정상 완료 경로에서 소스 수집 락을 즉시 해제한다."""
    connection.execute(
        text("SELECT pg_advisory_unlock(hashtext(:lock_name))"),
        {"lock_name": _source_lock_name(source_id)},
    )


def _source_lock_name(source_id: int) -> str:
    """기획서의 소스별 락 이름을 한 곳에서 일관되게 만든다."""
    return f"source:{source_id}"
