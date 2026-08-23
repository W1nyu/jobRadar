"""M6 소스 수동 수집 트리거 API."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.db import SessionLocal, get_engine
from app.crawlers.sources import with_runtime_credentials
from app.models import CrawlTrigger
from app.schemas.crawl import CrawlExecutionResponse
from app.services.crawl_health import OperationalAlert
from app.services.crawl_runner import (
    CrawlExecutionService,
    SourceNotFoundError,
    crawl_registered_source,
)
from app.services.notification_runtime import NotificationRuntime

router = APIRouter(prefix="/api/v1/sources", tags=["sources"])


def get_crawl_execution_service(request: Request) -> CrawlExecutionService:
    """API 요청용 실행 서비스를 앱 설정과 지연 초기화 DB 팩토리로 조립한다."""
    settings = request.app.state.settings
    engine = get_engine()
    notifications = NotificationRuntime(settings)

    def send_operational_alert(alert: OperationalAlert) -> None:
        with SessionLocal() as session:
            notifications.send_operational_alert(session, alert)

    return CrawlExecutionService(
        engine=engine,
        session_factory=SessionLocal,
        crawl=lambda source: crawl_registered_source(
            with_runtime_credentials(source, settings),
            user_agent=settings.crawl_user_agent,
            max_response_bytes=settings.crawl_max_response_bytes,
        ),
        failure_threshold=settings.source_failure_threshold,
        collection_drop_ratio=settings.collection_drop_ratio,
        operational_alert_sender=send_operational_alert,
    )


ExecutionServiceDependency = Annotated[CrawlExecutionService, Depends(get_crawl_execution_service)]


@router.post("/{source_id}/crawl", response_model=CrawlExecutionResponse, summary="소스 수동 수집")
def trigger_crawl(source_id: int, service: ExecutionServiceDependency) -> CrawlExecutionResponse:
    """즉시 한 번 수집한다. 이미 같은 소스가 실행 중이면 skipped 실행 이력을 반환한다."""
    try:
        result = service.run_source(source_id, CrawlTrigger.MANUAL)
    except SourceNotFoundError as error:
        raise HTTPException(status_code=404, detail=f"소스가 없습니다: {source_id}") from error
    return CrawlExecutionResponse(
        source_id=result.source_id,
        run_id=result.run_id,
        status=result.status,
    )
