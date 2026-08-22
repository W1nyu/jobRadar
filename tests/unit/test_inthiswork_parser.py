"""인디스워크 RSS 골든 파일 파서 검증."""

from datetime import datetime
from pathlib import Path

from app.crawlers.base import CrawlSource, RawPage
from app.crawlers.inthiswork import InThisWorkCrawler

FIXTURE = Path(__file__).parents[1] / "fixtures" / "inthiswork" / "posts_2026-08-22.json"


def test_인디스워크_채용분류_json_골든_파일을_raw_job으로_변환한다() -> None:
    crawler = InThisWorkCrawler(
        CrawlSource(
            slug="inthiswork",
            crawler_key="inthiswork",
            base_url="https://inthiswork.com",
            config={},
            rate_limit_per_min=10,
        ),
        http=object(),
    )
    page = RawPage(
        url="https://inthiswork.com/wp-json/wp/v2/posts",
        body=FIXTURE.read_bytes(),
        status_code=200,
        headers={},
    )

    items = crawler.parse(page)

    assert [(item.external_id, item.title, item.posted_at, item.url) for item in items] == [
        (
            "389416",
            "베어로보틱스｜Software Engineer",
            datetime(2026, 8, 21, 22, 44, 33),
            "https://inthiswork.com/archives/389416",
        ),
    ]
