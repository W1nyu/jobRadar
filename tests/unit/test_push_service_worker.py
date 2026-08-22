"""M9 브라우저 Service Worker 알림 클릭 동작 계약."""

from pathlib import Path


def test_service_worker는_푸시를_표시하고_클릭하면_공고_경로를_연다() -> None:
    script = Path("app/static/sw.js").read_text(encoding="utf-8")

    assert 'addEventListener("push' in script
    assert "showNotification" in script
    assert 'addEventListener("notificationclick' in script
    assert "clients.openWindow" in script
