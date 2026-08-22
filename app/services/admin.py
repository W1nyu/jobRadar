"""M8 관리자 화면용 조회·소스 관리 서비스.

웹 라우터는 이 모듈의 서비스만 호출한다. SQLAlchemy 조회와 변경은 repository에 남겨 API와
웹 UI가 같은 트랜잭션 경계를 공유하게 한다.
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from math import ceil
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.crawlers import CRAWLERS
from app.models import CrawlRun, FetchStrategy, JobPosting, Source
from app.repositories import (
    AppSettingRepository,
    CrawlRunRepository,
    JobPostingRepository,
    SourceRepository,
)

PAGE_SIZE = 20
WORKER_HEARTBEAT_MAX_AGE = timedelta(minutes=15)
_SLUG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,99}$")
_SENSITIVE_CONFIG_KEY_PARTS = ("password", "secret", "token", "service_key", "access_key")


class AdminEntityNotFoundError(LookupError):
    """관리 화면이 존재하지 않는 공고 또는 소스를 요청한 경우."""


class SourceValidationError(ValueError):
    """소스 폼 입력이 등록 정책을 충족하지 못한 경우."""


class SourceConflictError(ValueError):
    """이미 사용 중인 소스 slug를 저장하려 한 경우."""


@dataclass(frozen=True, slots=True)
class JobSearchFilters:
    """공고 목록 화면이 허용하는 검색 조건."""

    query: str | None = None
    source_id: int | None = None
    matched_only: bool = False
    is_open: bool | None = True
    first_seen_from: date | None = None
    first_seen_to: date | None = None
    deadline_soon: bool = False
    page: int = 1


@dataclass(frozen=True, slots=True)
class JobPage:
    """페이지네이션을 포함한 공고 목록 결과."""

    items: Sequence[JobPosting]
    total: int
    page: int
    total_pages: int


@dataclass(frozen=True, slots=True)
class DashboardSource:
    """소스별 운영 요약."""

    source: Source
    latest_run: CrawlRun | None
    items_fetched_24h: int


@dataclass(frozen=True, slots=True)
class DashboardSnapshot:
    """대시보드 렌더링에 필요한 제한된 데이터 묶음."""

    sources: Sequence[DashboardSource]
    recent_runs: Sequence[CrawlRun]
    worker_heartbeat_at: datetime | None
    worker_is_stale: bool


@dataclass(frozen=True, slots=True)
class SourceInput:
    """관리 폼이 서비스에 전달하는 검증 전 소스 값."""

    slug: str
    name: str
    crawler_key: str
    base_url: str
    fetch_strategy: FetchStrategy
    interval_minutes: int
    rate_limit_per_min: int
    config_json: str
    is_active: bool


class JobAdminService:
    """공고 목록·상세 조회를 서비스 경계로 제공한다."""

    def __init__(self, session: Session) -> None:
        self.postings = JobPostingRepository(session)

    def list(self, filters: JobSearchFilters) -> JobPage:
        """필터 조건과 페이지 번호를 정규화해 공고 목록을 반환한다."""
        page = max(filters.page, 1)
        first_seen_from = _start_of_day(filters.first_seen_from)
        first_seen_to = _start_of_next_day(filters.first_seen_to)
        deadline_before = datetime.now(UTC) + timedelta(days=7) if filters.deadline_soon else None
        items, total = self.postings.search(
            query=_clean_text(filters.query),
            source_id=filters.source_id,
            matched_only=filters.matched_only,
            is_open=filters.is_open,
            first_seen_from=first_seen_from,
            first_seen_to=first_seen_to,
            deadline_before=deadline_before,
            page=page,
            page_size=PAGE_SIZE,
        )
        return JobPage(
            items=items,
            total=total,
            page=page,
            total_pages=max(ceil(total / PAGE_SIZE), 1),
        )

    def get(self, posting_id: int) -> JobPosting:
        """상세 화면의 공고와 매칭 근거를 반환한다."""
        posting = self.postings.get_for_admin(posting_id)
        if posting is None:
            raise AdminEntityNotFoundError(posting_id)
        return posting


class DashboardService:
    """워커 상태·수집 이력·소스 요약을 조립한다."""

    def __init__(self, session: Session) -> None:
        self.sources = SourceRepository(session)
        self.runs = CrawlRunRepository(session)
        self.settings = AppSettingRepository(session)

    def get(self, *, now: datetime | None = None) -> DashboardSnapshot:
        """워크 하트비트의 15분 만료 기준을 반영한 대시보드 데이터를 만든다."""
        now = now or datetime.now(UTC)
        sources = self.sources.list()
        latest_runs = self.runs.latest_for_sources([source.id for source in sources])
        fetched_24h = self.runs.items_fetched_since(since=now - timedelta(hours=24))
        heartbeat = self.settings.get("worker_heartbeat")
        heartbeat_at = _heartbeat_at(heartbeat.value if heartbeat else None)
        return DashboardSnapshot(
            sources=[
                DashboardSource(
                    source=source,
                    latest_run=latest_runs.get(source.id),
                    items_fetched_24h=fetched_24h.get(source.id, 0),
                )
                for source in sources
            ],
            recent_runs=self.runs.list_recent(limit=15),
            worker_heartbeat_at=heartbeat_at,
            worker_is_stale=(heartbeat_at is None or now - heartbeat_at > WORKER_HEARTBEAT_MAX_AGE),
        )


class SourceAdminService:
    """소스 등록·수정·삭제의 검증과 커밋을 담당한다."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.sources = SourceRepository(session)

    def list(self) -> Sequence[Source]:
        """관리 화면의 모든 소스를 반환한다."""
        return self.sources.list()

    def get(self, source_id: int) -> Source:
        """수정할 소스를 찾고 없으면 도메인 오류를 낸다."""
        source = self.sources.get(source_id)
        if source is None:
            raise AdminEntityNotFoundError(source_id)
        return source

    def create(self, data: SourceInput) -> Source:
        """검증된 소스를 저장해 다음 워커 동기화 주기에 노출한다."""
        values = self._validated_values(data)
        try:
            source = self.sources.create(**values)
            self.session.commit()
        except IntegrityError as error:
            self.session.rollback()
            raise SourceConflictError(data.slug) from error
        return source

    def update(self, source_id: int, data: SourceInput) -> Source:
        """소스의 공개 설정만 갱신한다. 비밀 값은 저장할 수 없다."""
        source = self.get(source_id)
        try:
            self.sources.update(source, **self._validated_values(data))
            self.session.commit()
        except IntegrityError as error:
            self.session.rollback()
            raise SourceConflictError(data.slug) from error
        return source

    def delete(self, source_id: int) -> None:
        """사용자가 명시적으로 삭제한 소스와 종속 데이터를 제거한다."""
        self.sources.delete(self.get(source_id))
        self.session.commit()

    @staticmethod
    def crawler_choices() -> tuple[tuple[str, str], ...]:
        """등록된 크롤러와 실제 수집 전략만 폼 선택지로 제공한다."""
        return tuple(sorted((key, crawler.strategy) for key, crawler in CRAWLERS.items()))

    def _validated_values(self, data: SourceInput) -> dict[str, Any]:
        slug = data.slug.strip().lower()
        name = data.name.strip()
        if not _SLUG_PATTERN.fullmatch(slug):
            raise SourceValidationError("slug는 영문 소문자, 숫자, 하이픈만 사용할 수 있습니다.")
        if not name:
            raise SourceValidationError("소스 이름을 입력하세요.")
        crawler = CRAWLERS.get(data.crawler_key)
        if crawler is None:
            raise SourceValidationError("등록되지 않은 크롤러 키입니다.")
        if crawler.strategy != data.fetch_strategy.value:
            raise SourceValidationError("크롤러의 수집 방식과 선택한 방식이 다릅니다.")
        base_url = data.base_url.strip().rstrip("/")
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise SourceValidationError("http 또는 https 주소를 입력하세요.")
        if not 1 <= data.interval_minutes <= 24 * 60:
            raise SourceValidationError("수집 주기는 1~1440분 범위여야 합니다.")
        if not 1 <= data.rate_limit_per_min <= 60:
            raise SourceValidationError("분당 요청 수는 1~60 범위여야 합니다.")
        return {
            "slug": slug,
            "name": name,
            "crawler_key": data.crawler_key,
            "base_url": base_url,
            "fetch_strategy": data.fetch_strategy,
            "interval_minutes": data.interval_minutes,
            "rate_limit_per_min": data.rate_limit_per_min,
            "config": _parse_public_config(data.config_json),
            "is_active": data.is_active,
        }


def _parse_public_config(value: str) -> dict[str, Any]:
    """소스별 공개 JSON 설정을 읽고 비밀 키 저장을 차단한다."""
    try:
        config = json.loads(value or "{}")
    except json.JSONDecodeError as error:
        raise SourceValidationError("소스 설정은 올바른 JSON 객체여야 합니다.") from error
    if not isinstance(config, dict):
        raise SourceValidationError("소스 설정은 JSON 객체여야 합니다.")
    if _contains_sensitive_config_key(config):
        raise SourceValidationError("API 키·토큰·비밀번호는 소스 설정에 저장할 수 없습니다.")
    return config


def _contains_sensitive_config_key(value: object) -> bool:
    if isinstance(value, dict):
        for key, nested in value.items():
            lowered = str(key).lower()
            if any(part in lowered for part in _SENSITIVE_CONFIG_KEY_PARTS):
                return True
            if _contains_sensitive_config_key(nested):
                return True
    if isinstance(value, list):
        return any(_contains_sensitive_config_key(item) for item in value)
    return False


def _clean_text(value: str | None) -> str | None:
    text = value.strip() if value else ""
    return text or None


def _start_of_day(value: date | None) -> datetime | None:
    return datetime.combine(value, time.min, tzinfo=UTC) if value else None


def _start_of_next_day(value: date | None) -> datetime | None:
    return datetime.combine(value + timedelta(days=1), time.min, tzinfo=UTC) if value else None


def _heartbeat_at(value: dict[str, Any] | None) -> datetime | None:
    raw = value.get("at") if value else None
    if not isinstance(raw, str):
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
