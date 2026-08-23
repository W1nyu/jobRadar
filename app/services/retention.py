"""디스크 예산을 지키기 위한 M11 일일 보존 정책."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy.orm import Session

from app.repositories import RetentionRepository


@dataclass(frozen=True, slots=True)
class RetentionSummary:
    """한 번의 보존 정책 실행 결과."""

    content_cleared: int
    crawl_runs_deleted: int
    notifications_deleted: int
    revisions_deleted: int


class RetentionService:
    """마감 공고 원문과 오래된 운영 이력을 정해진 기간 뒤 정리한다."""

    def __init__(self, session: Session) -> None:
        self.repository = RetentionRepository(session)

    def run(self, *, now: datetime | None = None) -> RetentionSummary:
        """호출자가 commit할 수 있도록 삭제·갱신만 수행한다."""
        now = now or datetime.now(UTC)
        return RetentionSummary(
            content_cleared=self.repository.clear_closed_posting_content(
                closed_before=now - timedelta(days=90)
            ),
            crawl_runs_deleted=self.repository.delete_crawl_runs_before(
                started_before=now - timedelta(days=30)
            ),
            notifications_deleted=self.repository.delete_notifications_before(
                sent_before=now - timedelta(days=90)
            ),
            revisions_deleted=self.repository.delete_revisions_before(
                detected_before=now - timedelta(days=180)
            ),
        )
