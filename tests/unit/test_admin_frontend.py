"""관리자 화면의 공통 디자인 시스템 계약."""

from pathlib import Path

PROJECT_ROOT = Path(__file__).parents[2]


def test_관리자_스타일은_일관된_애플식_토큰과_반응형_구조를_제공한다() -> None:
    """모든 관리 화면에서 공유하는 시각적 언어가 CSS에 남아 있어야 한다."""
    stylesheet = (PROJECT_ROOT / "app/static/admin.css").read_text(encoding="utf-8")

    assert "--action-blue: #0066cc" in stylesheet
    assert ".app-shell" in stylesheet
    assert ".subnav" in stylesheet
    assert ".page-hero" in stylesheet
    assert ".metric-grid" in stylesheet
    assert "@media (max-width: 734px)" in stylesheet


def test_공통_레이아웃은_상단바와_페이지_내비게이션을_사용한다() -> None:
    """현재 위치와 페이지 맥락을 작은 화면에서도 잃지 않게 한다."""
    base_template = (PROJECT_ROOT / "app/templates/base.html").read_text(encoding="utf-8")

    assert 'class="app-shell"' in base_template
    assert 'class="subnav"' in base_template
    assert 'aria-current="page"' in base_template
