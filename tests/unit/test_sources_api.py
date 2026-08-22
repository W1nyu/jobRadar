"""M6 수동 수집 트리거 API의 서비스 위임 계약을 검증한다."""

from fastapi.testclient import TestClient

from app.api.v1.sources import get_crawl_execution_service
from app.core.config import Settings
from app.main import create_app
from app.models import CrawlStatus, CrawlTrigger
from app.services.crawl_runner import CrawlExecutionResult, SourceNotFoundError


class RecordingExecutionService:
    """API가 수집 구현 대신 서비스 계약만 호출하는지 확인하는 가짜 서비스."""

    def __init__(self) -> None:
        self.calls: list[tuple[int, CrawlTrigger]] = []

    def run_source(self, source_id: int, trigger: CrawlTrigger) -> CrawlExecutionResult:
        self.calls.append((source_id, trigger))
        if source_id == 404:
            raise SourceNotFoundError(source_id)
        return CrawlExecutionResult(source_id=source_id, run_id=15, status=CrawlStatus.SKIPPED)


def _client(service: RecordingExecutionService) -> TestClient:
    settings = Settings(
        _env_file=None,
        APP_BASE_URL="https://example.com",
        SECRET_KEY="test-secret",
    )
    app = create_app(settings=settings)
    app.dependency_overrides[get_crawl_execution_service] = lambda: service
    return TestClient(app)


def test_수동_수집_트리거는_manual_실행_결과를_반환한다() -> None:
    service = RecordingExecutionService()

    response = _client(service).post("/api/v1/sources/8/crawl")

    assert response.status_code == 200
    assert response.json() == {"source_id": 8, "run_id": 15, "status": "skipped"}
    assert service.calls == [(8, CrawlTrigger.MANUAL)]


def test_없는_소스를_수동_트리거하면_404를_반환한다() -> None:
    response = _client(RecordingExecutionService()).post("/api/v1/sources/404/crawl")

    assert response.status_code == 404
