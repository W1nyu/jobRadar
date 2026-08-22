"""잡알리오 공개 채용목록 골든 파일 파서 검증."""

from datetime import datetime
from pathlib import Path

from app.crawlers.alio import AlioCrawler
from app.crawlers.base import CrawlSource, RawPage

FIXTURE = Path(__file__).parents[1] / "fixtures" / "alio" / "recruit_list_2026-08-22.json"


def test_잡알리오_공개_채용목록_골든_파일을_raw_job으로_변환한다() -> None:
    crawler = AlioCrawler(
        CrawlSource(
            slug="alio-recruitment",
            crawler_key="alio-recruitment",
            base_url="https://opendata.alio.go.kr",
            config={},
            rate_limit_per_min=10,
        ),
        http=object(),
    )
    page = RawPage(
        url="https://opendata.alio.go.kr/new/odaApiMng/recrutInquiryAjaxList.do",
        body=FIXTURE.read_bytes(),
        status_code=200,
        headers={},
    )

    items = crawler.parse(page)

    assert [
        (item.external_id, item.title, item.company, item.posted_at, item.deadline_at)
        for item in items
    ] == [
        (
            "304149",
            "2026년도 우체국물류지원단 4분기 정기채용(공무직_소포) 공고",
            "(재)우체국물류지원단",
            datetime(2026, 8, 21),
            datetime(2026, 9, 4),
        ),
    ]
