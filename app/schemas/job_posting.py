"""수집 결과를 영속화 전에 전달하는 공고 DTO."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class JobPostingDTO:
    """M4 정규화가 보장한 공고 저장 계약.

    크롤러의 ``RawJob``과 SQLAlchemy 모델 사이에 둬, 두 계층이 서로를 알지 않도록 한다.
    """

    source_id: int
    external_id: str | None
    fingerprint: str | None
    content_hash: str
    url: str
    title: str
    company: str | None
    location: str | None
    employment_type: str | None
    description: str | None
    posted_at: datetime | None
    deadline_at: datetime | None
    raw: dict[str, Any]

    @property
    def identity(self) -> str:
        """소스 안에서 중복 판정에 사용할 값."""
        return self.external_id or self.fingerprint or ""
