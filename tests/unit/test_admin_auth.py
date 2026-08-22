"""M8 관리자 로그인과 세션 접근 제어 계약."""

from argon2 import PasswordHasher
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def _client() -> TestClient:
    settings = Settings(
        _env_file=None,
        APP_BASE_URL="https://example.com",
        SECRET_KEY="test-secret",
        ADMIN_USERNAME="admin",
        ADMIN_PASSWORD_HASH=PasswordHasher().hash("correct-password"),
    )
    return TestClient(create_app(settings=settings), follow_redirects=False)


def test_비로그인_관리_경로는_로그인으로_리다이렉트된다() -> None:
    response = _client().get("/admin/jobs?query=데이터")

    assert response.status_code == 303
    assert (
        response.headers["location"]
        == "/login?next=%2Fadmin%2Fjobs%3Fquery%3D%EB%8D%B0%EC%9D%B4%ED%84%B0"
    )


def test_로그인_실패는_세션을_발급하지_않는다() -> None:
    client = _client()

    response = client.post("/login", data={"username": "admin", "password": "wrong"})

    assert response.status_code == 401
    assert "session" not in response.headers.get("set-cookie", "")


def test_로그인_성공_뒤_관리자_대시보드를_볼_수_있다() -> None:
    client = _client()

    login = client.post(
        "/login",
        data={"username": "admin", "password": "correct-password", "next": "/admin"},
    )

    assert login.status_code == 303
    assert login.headers["location"] == "/admin"
    assert client.get("/admin").status_code == 200
