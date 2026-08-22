"""각 M2 모델에 대응하는 타입 안전한 기본 저장소."""

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from app.models import (
    AppSetting,
    CrawlRun,
    JobKeywordMatch,
    JobPosting,
    JobPostingRevision,
    Keyword,
    Notification,
    OAuthToken,
    PushSubscription,
    Source,
)
from app.repositories.base import CRUDRepository
from app.schemas import JobPostingDTO


class SourceRepository(CRUDRepository[Source]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Source)


class JobPostingRepository(CRUDRepository[JobPosting]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, JobPosting)

    def insert_if_absent(self, job: JobPostingDTO) -> JobPosting | None:
        """소스별 안정 식별자에 PostgreSQL UPSERT를 적용해 새 공고만 삽입한다."""
        values = {
            "source_id": job.source_id,
            "external_id": job.external_id,
            "fingerprint": job.fingerprint,
            "content_hash": job.content_hash,
            "url": job.url,
            "title": job.title,
            "company": job.company,
            "location": job.location,
            "employment_type": job.employment_type,
            "description": job.description,
            "posted_at": job.posted_at,
            "deadline_at": job.deadline_at,
            "raw": job.raw,
            "is_open": True,
            "consecutive_missing_runs": 0,
        }
        index_elements = (
            [JobPosting.source_id, JobPosting.external_id]
            if job.external_id is not None
            else [JobPosting.source_id, JobPosting.fingerprint]
        )
        statement = (
            insert(JobPosting)
            .values(**values)
            .on_conflict_do_nothing(index_elements=index_elements)
            .returning(JobPosting.id)
        )
        posting_id = self.session.execute(statement).scalar_one_or_none()
        return self.get(posting_id) if posting_id is not None else None

    def get_by_identity(self, job: JobPostingDTO) -> JobPosting | None:
        """UPSERT 충돌 뒤 기존 공고를 잠가 변경 이력과 상태를 일관되게 갱신한다."""
        identity_column = (
            JobPosting.external_id if job.external_id is not None else JobPosting.fingerprint
        )
        return self.session.scalar(
            select(JobPosting)
            .where(JobPosting.source_id == job.source_id, identity_column == job.identity)
            .with_for_update()
        )

    def apply_seen(self, posting: JobPosting, job: JobPostingDTO, *, seen_at: datetime) -> None:
        """현재 응답의 저장 값과 관측 상태를 기존 공고에 반영한다."""
        posting.content_hash = job.content_hash
        posting.url = job.url
        posting.title = job.title
        posting.company = job.company
        posting.location = job.location
        posting.employment_type = job.employment_type
        posting.description = job.description
        posting.posted_at = job.posted_at
        posting.deadline_at = job.deadline_at
        posting.raw = job.raw
        posting.is_open = True
        posting.consecutive_missing_runs = 0
        posting.last_seen_at = seen_at
        posting.closed_at = None

    def close_missing(
        self,
        *,
        source_id: int,
        external_ids: set[str],
        fingerprints: set[str],
        closed_at: datetime,
    ) -> int:
        """이번 완전 수집에 없던 열린 공고를 세고, 3회째면 종료한다."""
        postings = self.session.scalars(
            select(JobPosting)
            .where(JobPosting.source_id == source_id, JobPosting.is_open.is_(True))
            .with_for_update()
        ).all()
        closed = 0
        for posting in postings:
            seen = (
                posting.external_id in external_ids
                if posting.external_id is not None
                else posting.fingerprint in fingerprints
            )
            if seen:
                continue
            posting.consecutive_missing_runs += 1
            if posting.consecutive_missing_runs >= 3:
                posting.is_open = False
                posting.closed_at = closed_at
                closed += 1
        return closed


class JobPostingRevisionRepository(CRUDRepository[JobPostingRevision]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, JobPostingRevision)


class KeywordRepository(CRUDRepository[Keyword]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Keyword)


class JobKeywordMatchRepository(CRUDRepository[JobKeywordMatch]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, JobKeywordMatch)


class CrawlRunRepository(CRUDRepository[CrawlRun]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, CrawlRun)


class NotificationRepository(CRUDRepository[Notification]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Notification)


class PushSubscriptionRepository(CRUDRepository[PushSubscription]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, PushSubscription)


class OAuthTokenRepository(CRUDRepository[OAuthToken]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, OAuthToken)


class AppSettingRepository(CRUDRepository[AppSetting]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, AppSetting)
