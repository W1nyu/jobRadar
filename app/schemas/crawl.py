"""M6 수동 수집 트리거 API의 반환 계약."""

from pydantic import BaseModel

from app.models import CrawlStatus


class CrawlExecutionResponse(BaseModel):
    """수동 또는 스케줄 수집 한 번의 실행 이력 식별자와 상태."""

    source_id: int
    run_id: int | None
    status: CrawlStatus
