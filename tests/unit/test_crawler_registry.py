"""사이트별 크롤러 레지스트리 동작 검증."""

from collections.abc import Iterator

import pytest

from app.crawlers.base import BaseCrawler, CrawlSource, RawJob, RawPage
from app.crawlers.registry import UnknownCrawlerError, get_crawler, register_crawler


@register_crawler("registry-test")
class RegistryTestCrawler(BaseCrawler):
    strategy = "api"

    def fetch(self) -> Iterator[RawPage]:
        return iter(())

    def parse(self, page: RawPage) -> list[RawJob]:
        return []


def test_등록한_키로_크롤러를_생성한다() -> None:
    source = CrawlSource(
        slug="registry-test",
        crawler_key="registry-test",
        base_url="https://example.com",
        config={},
        rate_limit_per_min=30,
    )

    crawler = get_crawler(source, http=object())

    assert isinstance(crawler, RegistryTestCrawler)
    assert crawler.key == "registry-test"


def test_미등록_크롤러는_명시적인_오류를_낸다() -> None:
    source = CrawlSource(
        slug="missing",
        crawler_key="missing",
        base_url="https://example.com",
        config={},
        rate_limit_per_min=30,
    )

    with pytest.raises(UnknownCrawlerError, match="missing"):
        get_crawler(source, http=object())
