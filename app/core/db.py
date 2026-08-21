"""동기 SQLAlchemy 엔진과 FastAPI 세션 의존성.

엔진 생성은 지연한다. 그러면 DB를 쓰지 않는 헬스체크와 단위 테스트가 PostgreSQL 접속
가능 여부에 묶이지 않고, 실제 API/워커 프로세스가 세션을 요청할 때만 연결 풀이 만들어진다.
"""

from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import Settings, get_settings

# 모듈 임포트만으로 설정 검증이나 DB 접속을 하지 않는다.
engine: Engine | None = None
SessionLocal = sessionmaker[Session](autoflush=False, expire_on_commit=False)


def create_engine_for_settings(settings: Settings) -> Engine:
    """설정값을 그대로 반영한 PostgreSQL 연결 풀을 만든다."""
    return create_engine(
        settings.database_url,
        pool_size=settings.db_pool_size,
        max_overflow=settings.db_max_overflow,
        pool_pre_ping=True,
        pool_recycle=1800,
    )


def get_engine() -> Engine:
    """프로세스당 하나의 엔진과 세션 팩토리를 초기화한다."""
    global engine

    if engine is None:
        engine = create_engine_for_settings(get_settings())
        SessionLocal.configure(bind=engine)
    return engine


def get_db() -> Generator[Session, None, None]:
    """요청 단위 세션을 제공하고, 응답 뒤 반드시 연결 풀로 돌려준다."""
    get_engine()
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()
