"""관리 화면 시간 표시의 한국 표준시 변환 계약."""

from datetime import UTC, datetime

from app.api.web.admin import format_kst


def test_utc_시각을_한국_표준시로_표시한다() -> None:
    value = datetime(2026, 8, 22, 15, 30, tzinfo=UTC)

    assert format_kst(value) == "2026-08-23 00:30 KST"


def test_시간대가_없는_저장_시각은_utc로_간주한다() -> None:
    value = datetime(2026, 8, 22, 15, 30)

    assert format_kst(value) == "2026-08-23 00:30 KST"


def test_없는_시각은_대시로_표시한다() -> None:
    assert format_kst(None) == "-"
