"""M3 크롤러 구현을 등록하고 공개한다."""

from app.crawlers.alio import AlioCrawler
from app.crawlers.base import BaseCrawler, CrawlResult, CrawlSource, RawJob, RawPage
from app.crawlers.datagokr_msit import DataGoKrMsitCrawler
from app.crawlers.inthiswork import InThisWorkCrawler
from app.crawlers.kofia import KofiaCrawler
from app.crawlers.linkareer import LinkareerCrawler
from app.crawlers.registry import CRAWLERS, get_crawler

__all__ = [
    "CRAWLERS",
    "AlioCrawler",
    "BaseCrawler",
    "CrawlResult",
    "CrawlSource",
    "DataGoKrMsitCrawler",
    "InThisWorkCrawler",
    "KofiaCrawler",
    "LinkareerCrawler",
    "RawJob",
    "RawPage",
    "get_crawler",
]
