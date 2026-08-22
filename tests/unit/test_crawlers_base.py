"""크롤러 공통 계약과 템플릿 메서드를 검증한다."""

from collections.abc import Iterator

from app.crawlers.base import BaseCrawler, CrawlSource, RawJob, RawPage


class ExampleCrawler(BaseCrawler):
    key = "example"
    strategy = "api"

    def fetch(self) -> Iterator[RawPage]:
        yield RawPage(
            url="https://example.com/list",
            body=b"example",
            status_code=200,
            headers={},
        )

    def parse(self, page: RawPage) -> list[RawJob]:
        assert page.body == b"example"
        return [RawJob(url="https://example.com/jobs/1", title="데이터 분석 인턴")]


class BrokenParserCrawler(ExampleCrawler):
    def parse(self, page: RawPage) -> list[RawJob]:
        raise ValueError("마크업이 바뀌었습니다")


def _source() -> CrawlSource:
    return CrawlSource(
        slug="example",
        crawler_key="example",
        base_url="https://example.com",
        config={},
        rate_limit_per_min=30,
    )


def test_서로_다른_크롤러가_동일한_raw_job_계약을_반환한다() -> None:
    result = ExampleCrawler(_source(), http=object()).run()

    assert result.pages_fetched == 1
    assert result.http_status_summary == {"200": 1}
    assert result.items == [RawJob(url="https://example.com/jobs/1", title="데이터 분석 인턴")]


def test_페이지_하나의_파싱_실패는_partial_결과로_남긴다() -> None:
    result = BrokenParserCrawler(_source(), http=object()).run()

    assert result.partial is True
    assert result.items == []
    assert result.errors == ["마크업이 바뀌었습니다"]
