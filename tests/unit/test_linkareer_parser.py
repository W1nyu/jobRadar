"""링커리어 목록 골든 파일 파서 검증."""

from datetime import UTC, datetime
from pathlib import Path

from app.crawlers.base import CrawlSource, RawPage
from app.crawlers.linkareer import LinkareerCrawler

FIXTURE = Path(__file__).parents[1] / "fixtures" / "linkareer" / "recruit_list_2026-08-23.html"


def test_링커리어_채용_목록_골든_파일은_채용공고만_raw_job으로_변환한다() -> None:
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
        url="https://linkareer.com/list/recruit?filterBy_activityTypeID=5",
        body=FIXTURE.read_bytes(),
        status_code=200,
        headers={},
    )

    items = crawler.parse(page)

    assert [(item.external_id, item.title, item.url) for item in items] == [
        (
            "344570",
            "GenOS AI Engineer (전환형 인턴)",
            "https://linkareer.com/activity/344570",
        ),
        (
            "344551",
            "[Onetake Studio] 오리지널IP 신작 콘솔 프로젝트 클라이언트 프로그래머",
            "https://linkareer.com/activity/344551",
        ),
    ]
    assert items[0].employment_type == "인턴"
    assert items[0].deadline_at == datetime(2026, 8, 31, 14, 59, 59, 999000, tzinfo=UTC)


def test_링커리어는_대외활동_목록이_아닌_채용_목록_url을_요청한다() -> None:
    class RecordingHttp:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict[str, object]]] = []

        def get(self, url: str, **kwargs: object) -> None:
            self.calls.append((url, kwargs))
            return None

    http = RecordingHttp()
    crawler = LinkareerCrawler(
        CrawlSource(
            slug="linkareer",
            crawler_key="linkareer",
            base_url="https://linkareer.com",
            config={},
            rate_limit_per_min=30,
        ),
        http=http,  # type: ignore[arg-type]
    )

    assert list(crawler.fetch()) == []
    assert http.calls == [
        (
            "https://linkareer.com/list/recruit",
            {
                "params": {
                    "filterBy_activityTypeID": 5,
                    "filterBy_status": "OPEN",
                    "orderBy_direction": "DESC",
                    "orderBy_field": "RECENT",
                    "page": 1,
                },
                "etag": None,
                "last_modified": None,
            },
        )
    ]
