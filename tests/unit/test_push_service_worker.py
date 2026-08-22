"""M9 브라우저·휴대폰 Web Push 자산 계약."""

import json
from pathlib import Path

from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


def test_service_worker는_푸시를_표시하고_클릭하면_공고_경로를_연다() -> None:
    script = Path("app/static/sw.js").read_text(encoding="utf-8")

    assert 'addEventListener("push' in script
    assert "showNotification" in script
    assert 'addEventListener("notificationclick' in script
    assert "clients.openWindow" in script


def test_휴대폰_web_push는_앱_전체를_제어하는_service_worker를_등록한다() -> None:
    script = Path("app/static/push.js").read_text(encoding="utf-8")
    client = TestClient(
        create_app(
            Settings(
                _env_file=None,
                APP_BASE_URL="https://example.com",
                SECRET_KEY="test-secret",
            )
        )
    )

    response = client.get("/sw.js")

    assert 'register("/sw.js")' in script
    assert response.status_code == 200
    assert "showNotification" in response.text


def test_휴대폰_홈화면_웹앱용_manifest는_standalone_시작점을_제공한다() -> None:
    manifest = json.loads(Path("app/static/manifest.webmanifest").read_text(encoding="utf-8"))

    assert manifest["start_url"] == "/admin"
    assert manifest["display"] == "standalone"
