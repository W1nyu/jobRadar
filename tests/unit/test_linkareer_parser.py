"""링커리어 목록 골든 파일 파서 검증."""

from pathlib import Path

from app.crawlers.base import CrawlSource, RawPage
from app.crawlers.linkareer import LinkareerCrawler

FIXTURE = Path(__file__).parents[1] / "fixtures" / "linkareer" / "list_2026-08-22.html"


def test_링커리어_목록_골든_파일을_raw_job으로_변환한다() -> None:
    crawler = LinkareerCrawler(
        CrawlSource(
            slug="linkareer",
            crawler_key="linkareer",
            base_url="https://linkareer.com",
            config={},
            rate_limit_per_min=30,
        ),
        http=object(),
    )
    page = RawPage(
        url="https://linkareer.com/list/activity",
        body=FIXTURE.read_bytes(),
        status_code=200,
        headers={},
    )

    items = crawler.parse(page)

    assert [(item.external_id, item.title, item.url) for item in items] == [
        (
            "344617",
            "2026 살생물제 안전관리 홍보단 모집",
            "https://linkareer.com/activity/344617",
        ),
        (
            "344601",
            "2026년 국립인천해양박물관 자원봉사자 모집",
            "https://linkareer.com/activity/344601",
        ),
        (
            "344585",
            "2026 농식품 국민평가단 모집",
            "https://linkareer.com/activity/344585",
        ),
        (
            "344464",
            "<시즌21> 사랑의 몰래산타대작전 '산타마을에서 누가돌아왔게?'「산타기획단」 모집",
            "https://linkareer.com/activity/344464",
        ),
    ]
