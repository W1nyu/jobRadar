"""내용 해시가 달라진 공고의 표시용 변경 이력을 만든다."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.models import JobPosting
from app.schemas import JobPostingDTO

_TRACKED_FIELDS = ("title", "deadline_at", "description")


def changed_fields(posting: JobPosting, job: JobPostingDTO) -> dict[str, dict[str, Any]]:
    """내용 해시에 포함된 필드만 이전 값과 새 값으로 직렬화한다."""
    changes: dict[str, dict[str, Any]] = {}
    for field in _TRACKED_FIELDS:
        old_value = getattr(posting, field)
        new_value = getattr(job, field)
        if old_value != new_value:
            changes[field] = {"old": _json_value(old_value), "new": _json_value(new_value)}
    return changes


def _json_value(value: Any) -> Any:
    """JSONB 이력에 datetime을 안전하게 기록한다."""
    return value.isoformat() if isinstance(value, datetime) else value
