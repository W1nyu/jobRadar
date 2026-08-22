"""사이트와 무관한 크롤러 공통 반환 계약과 실행 흐름.

이 모듈은 SQLAlchemy 모델이나 세션을 import하지 않는다. 크롤러는 필요한 소스 설정만 받고
`RawJob`을 반환하며, DB 저장은 이후 서비스 계층의 책임으로 남긴다.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.crawlers.http import HttpClient


@dataclass(frozen=True, slots=True)
class RawJob:
    """사이트별 응답을 정규화하기 전의 공통 채용공고 계약."""

    url: str
    title: str
    external_id: str | None = None
    company: str | None = None
    location: str | None = None
    employment_type: str | None = None
    experience_level: str | None = None
    description: str | None = None
    posted_at: datetime | None = None
    deadline_at: datetime | None = None
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RawPage:
    """HTTP 계층이 크롤러에 전달하는 원본 페이지."""

    url: str
    body: bytes
    status_code: int
    headers: dict[str, str]


@dataclass(slots=True)
class CrawlResult:
    """한 소스의 단발 수집 결과."""

    items: list[RawJob]
    pages_fetched: int
    http_status_summary: dict[str, int]
    partial: bool = False
    errors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class CrawlSource:
    """크롤러가 필요한 소스 정보만 담는 DB-독립 입력 객체."""

    slug: str
    crawler_key: str
    base_url: str
    config: dict[str, Any]
    rate_limit_per_min: int


class BaseCrawler(ABC):
    """fetch → 순수 parse → 결과 집계를 고정하는 템플릿 메서드."""

    key: str
    strategy: str

    def __init__(self, source: CrawlSource, http: HttpClient) -> None:
        self.source = source
        self.http = http
        self.config = source.config

    @abstractmethod
    def fetch(self) -> Iterator[RawPage]:
        """페이지네이션을 포함한 원본 페이지를 순차적으로 반환한다."""

    @abstractmethod
    def parse(self, page: RawPage) -> list[RawJob]:
        """원본 페이지 하나를 RawJob 목록으로 변환한다. 네트워크·DB를 호출하지 않는다."""

    def run(self) -> CrawlResult:
        """모든 페이지를 파싱해 성공·부분 실패 상태를 집계한다."""
        items: list[RawJob] = []
        statuses: Counter[str] = Counter()
        errors: list[str] = []
        pages_fetched = 0

        try:
            for page in self.fetch():
                pages_fetched += 1
                statuses[str(page.status_code)] += 1
                try:
                    items.extend(self.parse(page))
                except Exception as error:
                    errors.append(str(error))
        except Exception as error:
            errors.append(str(error))

        return CrawlResult(
            items=items,
            pages_fetched=pages_fetched,
            http_status_summary=dict(statuses),
            partial=bool(errors),
            errors=errors,
        )
