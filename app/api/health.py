"""헬스체크 라우터.

`/healthz`는 DB를 건드리지 않는다. 프로세스가 살아 있는지만 답한다.
DB 연결까지 확인하는 `/readyz`는 M2에서 추가한다.
"""

from importlib.metadata import PackageNotFoundError, version

from fastapi import APIRouter, Request

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
