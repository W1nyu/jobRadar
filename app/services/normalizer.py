"""RawJob을 중복 판정·변경 탐지에 안전한 공고 DTO로 정규화한다."""

from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import UTC, datetime
from urllib.parse import urlparse

from app.crawlers.base import RawJob
from app.schemas.job_posting import JobPostingDTO

_WHITESPACE = re.compile(r"\s+")
_LEADING_TAG = re.compile(r"^(?:\[[^\]]+\]|\([^)]*\)|【[^】]+】)\s*")
_EDGE_SPECIAL_CHARS = "-–—_~|/\\:;,.!?·•'\"“”‘’[](){}<>"


def normalize_text(value: str | None, *, remove_leading_tags: bool = False) -> str:
    """유니코드·공백·표시용 접두 태그를 안정적인 비교 문자열로 바꾼다."""
    normalized = unicodedata.normalize("NFKC", value or "")
    normalized = _WHITESPACE.sub(" ", normalized).strip()
    if remove_leading_tags:
        while matched := _LEADING_TAG.match(normalized):
            normalized = normalized[matched.end() :]
    return normalized.strip(_EDGE_SPECIAL_CHARS + " ").casefold()


def _display_text(value: str | None, *, remove_leading_tags: bool = False) -> str | None:
    """빈 값은 NULL로, 나머지는 비교 기준과 같은 공백 규칙으로 보관한다."""
    normalized = normalize_text(value, remove_leading_tags=remove_leading_tags)
    return normalized or None


def _utc(value: datetime | None) -> datetime | None:
    """사이트별 naive 시간을 UTC로 명시해 PostgreSQL 시간대 컬럼에 일관되게 저장한다."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _digest(*parts: str) -> str:
    """구분자를 넣어 모호하지 않은 SHA-256 입력을 만든다."""
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()


def normalize(*, source_id: int, raw_job: RawJob) -> JobPostingDTO:
    """사이트 원본 공고 하나를 M4 공통 DTO로 바꾼다."""
    title = _display_text(raw_job.title, remove_leading_tags=True)
    if title is None:
        raise ValueError("공고 제목은 비어 있을 수 없습니다.")

    company = _display_text(raw_job.company)
    location = _display_text(raw_job.location)
    employment_type = _display_text(raw_job.employment_type)
    description = _display_text(raw_job.description)
    posted_at = _utc(raw_job.posted_at)
    deadline_at = _utc(raw_job.deadline_at)
    external_id = _display_text(raw_job.external_id)
    url = raw_job.url.strip()

    fingerprint = None
    if external_id is None:
        fingerprint = _digest(
            str(source_id),
            title,
            company or "",
            urlparse(url).path,
        )

    content_hash = _digest(
        title,
        deadline_at.isoformat() if deadline_at else "",
        (description or "")[:2000],
    )
    return JobPostingDTO(
        source_id=source_id,
        external_id=external_id,
        fingerprint=fingerprint,
        content_hash=content_hash,
        url=url,
        title=title,
        company=company,
        location=location,
        employment_type=employment_type,
        description=description,
        posted_at=posted_at,
        deadline_at=deadline_at,
        raw=dict(raw_job.raw),
    )
