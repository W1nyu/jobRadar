"""M3 크롤러 구현을 등록하고 공개한다."""

from app.crawlers.base import BaseCrawler, CrawlResult, CrawlSource, RawJob, RawPage
from app.crawlers.datagokr_msit import DataGoKrMsitCrawler
from app.crawlers.linkareer import LinkareerCrawler
from app.crawlers.registry import get_crawler

__all__ = [
    "BaseCrawler",
    "CrawlResult",
    "CrawlSource",
    "DataGoKrMsitCrawler",
    "LinkareerCrawler",
    "RawJob",
    "RawPage",
    "get_crawler",
]
