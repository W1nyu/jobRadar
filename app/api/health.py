"""헬스체크 라우터.

`/healthz`는 DB를 건드리지 않는다. 프로세스가 살아 있는지만 답한다.
DB 연결까지 확인하는 `/readyz`는 M2에서 추가한다.
"""

from importlib.metadata import PackageNotFoundError, version

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.db import create_engine_for_settings

router = APIRouter(tags=["health"])


def _app_version() -> str:
    try:
        return version("jobradar")
    except PackageNotFoundError:  # pragma: no cover - 설치 없이 실행하는 경우
        return "unknown"


@router.get("/healthz", summary="프로세스 생존 확인")
def healthz(request: Request) -> dict[str, str]:
    return {
        "status": "ok",
        "version": _app_version(),
        "env": request.app.state.settings.app_env,
    }


@router.get("/readyz", summary="DB 준비 상태 확인")
def readyz(request: Request) -> dict[str, str]:
    """DB 연결과 최소 질의를 성공할 수 있을 때만 준비 상태를 반환한다."""
    engine = create_engine_for_settings(request.app.state.settings)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except SQLAlchemyError as exc:
        raise HTTPException(status_code=503, detail="database unavailable") from exc
    finally:
        engine.dispose()
    return {"status": "ready"}
