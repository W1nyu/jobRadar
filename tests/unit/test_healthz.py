"""헬스체크 엔드포인트 동작 검증."""

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def build_client(**overrides: object) -> TestClient:
    settings = Settings(
        _env_file=None,
        APP_BASE_URL="https://example.com",
        SECRET_KEY="test-secret",
        **overrides,
    )
    return TestClient(create_app(settings=settings))


def test_healthz는_200과_ok를_반환한다() -> None:
    response = build_client().get("/healthz")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_healthz는_버전을_알려준다() -> None:
    """배포 후 어떤 버전이 떠 있는지 확인하는 용도."""
    body = build_client().get("/healthz").json()

    assert body["version"]


def test_healthz는_설정_객체를_주입받아_동작한다() -> None:
    """.env 파일 없이도 앱을 만들 수 있어야 테스트가 환경에 의존하지 않는다."""
    body = build_client().get("/healthz").json()

    assert body["env"] == "development"


def test_운영_모드에서는_문서_엔드포인트가_닫힌다() -> None:
    """/docs는 스키마와 내부 구조를 그대로 노출한다. 공인 IP에 열어둘 이유가 없다."""
    response = build_client(APP_ENV="production").get("/docs")

    assert response.status_code == 404


def test_개발_모드에서는_문서_엔드포인트가_열린다() -> None:
    response = build_client().get("/docs")

    assert response.status_code == 200
