"""공공데이터포털 과기정통부 모집채용 JSON 파서 검증."""

from datetime import datetime
from pathlib import Path

import pytest

from app.crawlers.base import CrawlSource, RawPage
from app.crawlers.datagokr_msit import DataGoKrMsitApiError, DataGoKrMsitCrawler

FIXTURE = Path(__file__).parents[1] / "fixtures" / "datagokr_msit" / "recruit_list_contract.json"
ERROR_FIXTURE = (
    Path(__file__).parents[1]
    / "fixtures"
    / "datagokr_msit"
    / "service_key_not_registered_2026-08-22.json"
)


def _crawler() -> DataGoKrMsitCrawler:
    return DataGoKrMsitCrawler(
        CrawlSource(
            slug="datagokr-msit-recruitment",
            crawler_key="datagokr-msit-recruitment",
            base_url="https://apis.data.go.kr",
            config={},
            rate_limit_per_min=30,
        ),
        http=object(),
    )


def test_모집채용_json_계약을_raw_job으로_변환한다() -> None:
    page = RawPage(
        url="https://apis.data.go.kr/1721000/msitrecruitinfo/recruitList",
        body=FIXTURE.read_bytes(),
        status_code=200,
        headers={},
    )

    items = _crawler().parse(page)

    assert [(item.title, item.company, item.posted_at, item.url) for item in items] == [
        (
            "과학기술정보통신부 5급 이하 공무원 일방전입(경력경쟁채용) 모집 공고(기간연장)",
            "운영지원과",
            datetime(2026, 8, 20),
            "https://www.msit.go.kr/bbs/view.do?sCode=user&mId=125&mPid=121&bbsSeqNo=98&nttSeqNo=3186431",
        ),
        (
            "우정사업본부 과장급 공모직위 공개모집",
            "운영지원과",
            datetime(2026, 8, 18),
            "https://www.msit.go.kr/bbs/view.do?sCode=user&mId=125&mPid=121&bbsSeqNo=98&nttSeqNo=3186430",
        ),
    ]
    assert items[0].description is not None
    assert "제2026-0898호" in items[0].description


def test_공공데이터포털_오류_응답은_빈_목록으로_오인하지_않는다() -> None:
    page = RawPage(
        url="https://apis.data.go.kr/1721000/msitrecruitinfo/recruitList",
        body=ERROR_FIXTURE.read_bytes(),
        status_code=200,
        headers={},
    )

    with pytest.raises(DataGoKrMsitApiError, match="30"):
        _crawler().parse(page)


def test_서비스키는_http_요청_전에_url_디코딩한다() -> None:
    class RecordingHttp:
        def __init__(self) -> None:
            self.params: dict[str, object] | None = None

        def get(self, _: str, **kwargs: object) -> None:
            self.params = kwargs["params"]  # type: ignore[assignment]
            return None

    http = RecordingHttp()
    crawler = DataGoKrMsitCrawler(
        CrawlSource(
            slug="datagokr-msit-recruitment",
            crawler_key="datagokr-msit-recruitment",
            base_url="https://apis.data.go.kr",
            config={"service_key": "encoded%2Fkey", "display": 1},
            rate_limit_per_min=30,
        ),
        http=http,  # type: ignore[arg-type]
    )

    assert list(crawler.fetch()) == []
    assert http.params is not None
    assert http.params["ServiceKey"] == "encoded/key"
