"""FastAPI 앱 팩토리.

`create_app()`이 설정을 인자로 받는 이유: 테스트가 `.env`나 OS 환경변수에 의존하지
않게 하기 위해서다. 운영에서는 인자 없이 호출해 `.env`를 읽는다.

모듈 레벨에 `app` 인스턴스를 두지 않는다. 그러면 `app.main`을 임포트하는 것만으로
설정 검증이 돌아, `.env`가 없는 환경에서는 테스트 수집조차 실패한다.
대신 uvicorn을 팩토리 모드로 띄운다::

    uvicorn app.main:create_app --factory
"""

from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.v1.keywords import router as keywords_router
from app.api.v1.sources import router as sources_router
from app.core.config import Settings, get_settings
from app.core.logging import configure_logging


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    configure_logging(level=settings.log_level, json_output=settings.log_json)

    # 운영에서는 문서 엔드포인트를 닫는다. 공인 IP에 스키마를 노출할 이유가 없다.
    docs_enabled = not settings.is_production

    app = FastAPI(
        title="jobRadar",
        description="개인용 채용공고 모니터링 서비스",
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
    )
    app.state.settings = settings
    app.include_router(health_router)
    app.include_router(keywords_router)
    app.include_router(sources_router)
    return app
