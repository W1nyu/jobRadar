"""크롤러 키와 구현체를 연결하는 레지스트리."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.crawlers.base import BaseCrawler, CrawlSource

if TYPE_CHECKING:
    from app.crawlers.http import HttpClient

CRAWLERS: dict[str, type[BaseCrawler]] = {}


class UnknownCrawlerError(LookupError):
    """소스가 가리키는 크롤러 구현이 등록되지 않은 경우."""


def register_crawler(key: str):
    """새 사이트 구현체를 선언 위치에서 레지스트리에 등록한다."""

    def decorator(crawler_class: type[BaseCrawler]) -> type[BaseCrawler]:
        if key in CRAWLERS:
            raise ValueError(f"이미 등록된 크롤러 키입니다: {key}")
        crawler_class.key = key
        CRAWLERS[key] = crawler_class
        return crawler_class

    return decorator


def get_crawler(source: CrawlSource, http: HttpClient) -> BaseCrawler:
    """소스의 crawler_key에 해당하는 구현체를 생성한다."""
    try:
        crawler_class = CRAWLERS[source.crawler_key]
    except KeyError as error:
        raise UnknownCrawlerError(f"등록되지 않은 크롤러: {source.crawler_key}") from error
    return crawler_class(source, http)
