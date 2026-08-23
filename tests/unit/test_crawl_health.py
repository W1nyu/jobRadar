"""M10 수집 실패 분류의 단위 계약."""

import httpx
import pytest

from app.crawlers.errors import CrawlParserError, CrawlSchemaError
from app.crawlers.http import HttpRateLimitError
from app.services.crawl_health import CrawlErrorType, classify_crawl_error


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (httpx.ReadTimeout("응답 시간 초과"), CrawlErrorType.NETWORK),
        (HttpRateLimitError("HTTP 429"), CrawlErrorType.RATE_LIMIT),
        (CrawlParserError("목록 마크업이 바뀌었습니다."), CrawlErrorType.PARSER),
        (CrawlSchemaError("응답 필드가 없습니다."), CrawlErrorType.SCHEMA),
    ],
)
def test_수집_예외를_운영_분석용_유형으로_분류한다(
    error: Exception, expected: CrawlErrorType
) -> None:
    assert classify_crawl_error(error) is expected
