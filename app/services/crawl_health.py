"""M10 수집 장애를 일관되게 기록하고 운영자에게 전달하는 계약."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

import httpx

from app.crawlers.errors import CrawlAuthenticationError, CrawlParserError, CrawlSchemaError
from app.crawlers.http import HttpClientError, HttpRateLimitError, HttpStatusError


class CrawlErrorType(StrEnum):
    """실행 이력의 `error_type`에 저장할 안정적인 운영 분류."""

    NETWORK = "network"
    RATE_LIMIT = "rate_limit"
    PARSER = "parser"
    SCHEMA = "schema"
    AUTHENTICATION = "authentication"
    COLLECTION_DROP = "collection_drop"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class OperationalAlert:
    """채널이 DB를 모르도록 서비스가 조립한 운영 알림 내용."""

    title: str
    body: str
    path: str
    tag: str


def classify_crawl_error(error: Exception) -> CrawlErrorType:
    """HTTP·파서·스키마 예외를 `crawl_runs.error_type`의 공통 값으로 바꾼다."""
    if isinstance(error, HttpRateLimitError):
        return CrawlErrorType.RATE_LIMIT
    if isinstance(error, (CrawlAuthenticationError,)):
        return CrawlErrorType.AUTHENTICATION
    if isinstance(error, HttpStatusError) and any(
        code in str(error) for code in ("HTTP 401", "HTTP 403")
    ):
        return CrawlErrorType.AUTHENTICATION
    if isinstance(error, CrawlParserError):
        return CrawlErrorType.PARSER
    if isinstance(error, CrawlSchemaError):
        return CrawlErrorType.SCHEMA
    if isinstance(error, (httpx.TimeoutException, httpx.TransportError, HttpClientError)):
        return CrawlErrorType.NETWORK
    if isinstance(error, ValueError):
        return CrawlErrorType.SCHEMA
    return CrawlErrorType.UNKNOWN


def source_disabled_alert(*, source_id: int, source_name: str, failures: int) -> OperationalAlert:
    """서킷브레이커가 열린 단 한 번의 운영 알림을 만든다."""
    return OperationalAlert(
        title="수집 소스 자동 비활성화",
        body=f"{source_name} 소스가 {failures}회 연속 실패해 자동 중지되었습니다.",
        path=f"/admin/sources/{source_id}",
        tag=f"jobradar-source-disabled-{source_id}",
    )


def collection_drop_alert(
    *,
    source_id: int,
    source_name: str,
    previous_items: int,
    current_items: int,
    drop_ratio: float,
) -> OperationalAlert:
    """직전 성공 수집보다 급감한 경우의 운영 알림을 만든다."""
    return OperationalAlert(
        title="수집 건수 급감 감지",
        body=(
            f"{source_name} 소스의 수집 건수가 직전 {previous_items}건에서 "
            f"{current_items}건으로 {int(drop_ratio * 100)}% 이상 급감했습니다."
        ),
        path=f"/admin/sources/{source_id}",
        tag=f"jobradar-collection-drop-{source_id}",
    )


def is_collection_drop(*, previous_items: int | None, current_items: int, ratio: float) -> bool:
    """첫 수집·0건 기준선은 제외하고, 설정한 비율 이상 감소했는지 판단한다."""
    if previous_items is None or previous_items <= 0 or current_items >= previous_items:
        return False
    return previous_items - current_items >= previous_items * ratio
