"""금융투자협회 채용안내 골든 파일 파서 검증."""

from datetime import datetime
from pathlib import Path

from app.crawlers.base import CrawlSource, RawPage
from app.crawlers.kofia import KofiaCrawler

FIXTURE = Path(__file__).parents[1] / "fixtures" / "kofia" / "list_2026-08-22.html"


def test_금융투자협회_채용안내_골든_파일을_raw_job으로_변환한다() -> None:
    crawler = KofiaCrawler(
        CrawlSource(
            slug="kofia",
            crawler_key="kofia",
            base_url="https://www.kofia.or.kr",
            config={},
            rate_limit_per_min=10,
        ),
        http=object(),
    )
    page = RawPage(
        url="https://www.kofia.or.kr/brd/m_96/list.do",
        body=FIXTURE.read_bytes(),
        status_code=200,
        headers={},
    )

    items = crawler.parse(page)

    assert [
        (item.external_id, item.title, item.company, item.posted_at, item.url) for item in items
    ] == [
        (
            "41797",
            "[하나대체투자자산운용] 2026년 하반기 인턴사원 채용",
            "하나대체투자자산운용",
            datetime(2026, 8, 21),
            "https://www.kofia.or.kr/brd/m_96/view.do?seq=41797",
        ),
    ]
