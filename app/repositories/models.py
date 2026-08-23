"""각 M2 모델에 대응하는 타입 안전한 기본 저장소."""

from collections.abc import Sequence
from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, joinedload, selectinload

from app.models import (
    AppSetting,
    CrawlRun,
    CrawlStatus,
    JobKeywordMatch,
    JobPosting,
    JobPostingRevision,
    Keyword,
    KeywordKind,
    Notification,
    NotificationChannel,
    NotificationStatus,
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

    def search(
        self,
        *,
        query: str | None,
        source_id: int | None,
        matched_only: bool,
        is_open: bool | None,
        first_seen_from: datetime | None,
        first_seen_to: datetime | None,
        deadline_before: datetime | None,
        page: int,
        page_size: int,
    ) -> tuple[Sequence[JobPosting], int]:
        """관리 화면의 공고 목록 조건을 한 번의 count·목록 조회로 실행한다."""
        conditions = []
        if query:
            pattern = f"%{query}%"
            conditions.append(JobPosting.title.ilike(pattern) | JobPosting.company.ilike(pattern))
        if source_id is not None:
            conditions.append(JobPosting.source_id == source_id)
        if matched_only:
            conditions.append(JobPosting.keyword_matches.any())
        if is_open is not None:
            conditions.append(JobPosting.is_open.is_(is_open))
        if first_seen_from is not None:
            conditions.append(JobPosting.first_seen_at >= first_seen_from)
        if first_seen_to is not None:
            conditions.append(JobPosting.first_seen_at < first_seen_to)
        if deadline_before is not None:
            conditions.append(
                JobPosting.deadline_at.is_not(None), JobPosting.deadline_at <= deadline_before
            )

        count_statement = select(func.count()).select_from(JobPosting).where(*conditions)
        statement = (
            select(JobPosting)
            .options(joinedload(JobPosting.source))
            .where(*conditions)
            .order_by(JobPosting.first_seen_at.desc(), JobPosting.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        return self.session.scalars(statement).all(), int(self.session.scalar(count_statement) or 0)

    def get_for_admin(self, posting_id: int) -> JobPosting | None:
        """상세 화면에 필요한 소스와 매칭 근거를 함께 읽는다."""
        return self.session.scalar(
            select(JobPosting)
            .options(
                joinedload(JobPosting.source),
                selectinload(JobPosting.keyword_matches).joinedload(JobKeywordMatch.keyword),
            )
            .where(JobPosting.id == posting_id)
        )

    def list_notification_candidates(
        self, *, channel: NotificationChannel, since: datetime
    ) -> Sequence[JobPosting]:
        """아직 해당 채널로 보내지 않은 신규 관심 공고만 조회한다."""
        include_match = (
            select(JobKeywordMatch.id)
            .join(Keyword, JobKeywordMatch.keyword_id == Keyword.id)
            .where(
                JobKeywordMatch.job_posting_id == JobPosting.id,
                Keyword.kind == KeywordKind.INCLUDE,
            )
            .exists()
        )
        exclude_match = (
            select(JobKeywordMatch.id)
            .join(Keyword, JobKeywordMatch.keyword_id == Keyword.id)
            .where(
                JobKeywordMatch.job_posting_id == JobPosting.id,
                Keyword.kind == KeywordKind.EXCLUDE,
            )
            .exists()
        )
        already_notified = (
            select(Notification.id)
            .where(
                Notification.job_posting_id == JobPosting.id,
                Notification.channel == channel,
            )
            .exists()
        )
        return self.session.scalars(
            select(JobPosting)
            .options(
                joinedload(JobPosting.source),
                selectinload(JobPosting.keyword_matches).joinedload(JobKeywordMatch.keyword),
            )
            .where(
                JobPosting.first_seen_at >= since,
                JobPosting.is_open.is_(True),
                include_match,
                ~exclude_match,
                ~already_notified,
            )
            .order_by(JobPosting.first_seen_at, JobPosting.id)
        ).all()

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

    def list_active(self) -> Sequence[Keyword]:
        """매칭 대상인 활성 키워드를 안정적인 기본 키 순서로 조회한다."""
        return self.session.scalars(
            select(Keyword).where(Keyword.is_active.is_(True)).order_by(Keyword.id)
        ).all()


class JobKeywordMatchRepository(CRUDRepository[JobKeywordMatch]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, JobKeywordMatch)

    def replace_for_posting(
        self,
        *,
        job_posting_id: int,
        matches: Sequence[tuple[int, str, str, int]],
    ) -> None:
        """공고의 이전 매칭을 현재 키워드 판정 근거로 원자적으로 교체한다."""
        self.session.execute(
            delete(JobKeywordMatch).where(JobKeywordMatch.job_posting_id == job_posting_id)
        )
        self.session.add_all(
            JobKeywordMatch(
                job_posting_id=job_posting_id,
                keyword_id=keyword_id,
                matched_field=matched_field,
                matched_snippet=matched_snippet,
                score=score,
            )
            for keyword_id, matched_field, matched_snippet, score in matches
        )
        self.session.flush()


class CrawlRunRepository(CRUDRepository[CrawlRun]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, CrawlRun)

    def latest_for_sources(self, source_ids: Sequence[int]) -> dict[int, CrawlRun]:
        """소스별 최신 실행 이력을 window 함수로 한 번에 읽는다."""
        if not source_ids:
            return {}
        ranked = (
            select(
                CrawlRun.id,
                CrawlRun.source_id,
                func.row_number()
                .over(partition_by=CrawlRun.source_id, order_by=CrawlRun.started_at.desc())
                .label("rank"),
            )
            .where(CrawlRun.source_id.in_(source_ids))
            .subquery()
        )
        runs = self.session.scalars(
            select(CrawlRun).join(ranked, CrawlRun.id == ranked.c.id).where(ranked.c.rank == 1)
        ).all()
        return {run.source_id: run for run in runs}

    def latest_successful_items_fetched(self, *, source_id: int) -> int | None:
        """급감 판단 기준이 되는 가장 최근 완전 성공 수집 건수를 반환한다."""
        return self.session.scalar(
            select(CrawlRun.items_fetched)
            .where(CrawlRun.source_id == source_id, CrawlRun.status == CrawlStatus.SUCCESS)
            .order_by(CrawlRun.started_at.desc(), CrawlRun.id.desc())
            .limit(1)
        )

    def items_fetched_since(self, *, since: datetime) -> dict[int, int]:
        """대시보드의 최근 24시간 소스별 수집 건수를 집계한다."""
        rows = self.session.execute(
            select(CrawlRun.source_id, func.sum(CrawlRun.items_fetched))
            .where(CrawlRun.started_at >= since)
            .group_by(CrawlRun.source_id)
        ).all()
        return {int(source_id): int(items_fetched or 0) for source_id, items_fetched in rows}

    def list_recent(self, *, limit: int) -> Sequence[CrawlRun]:
        """최근 실행 이력과 소스명을 대시보드용으로 함께 읽는다."""
        return self.session.scalars(
            select(CrawlRun)
            .options(joinedload(CrawlRun.source))
            .order_by(CrawlRun.started_at.desc(), CrawlRun.id.desc())
            .limit(limit)
        ).all()


class RetentionRepository:
    """보존 기간이 지난 운영 데이터를 한 트랜잭션에서 정리한다."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def clear_closed_posting_content(self, *, closed_before: datetime) -> int:
        """마감 후 오래된 공고는 메타데이터만 남기고 큰 본문·원본을 비운다."""
        postings = self.session.scalars(
            select(JobPosting)
            .where(
                JobPosting.is_open.is_(False),
                JobPosting.closed_at.is_not(None),
                JobPosting.closed_at < closed_before,
            )
            .with_for_update()
        ).all()
        cleared = 0
        for posting in postings:
            if posting.description is None and posting.raw == {}:
                continue
            posting.description = None
            # raw는 NOT NULL 컬럼이라 NULL 대신 빈 객체로 비워 메타데이터 행을 보존한다.
            posting.raw = {}
            cleared += 1
        return cleared

    def delete_crawl_runs_before(self, *, started_before: datetime) -> int:
        """대시보드에 더 이상 필요 없는 오래된 실행 이력을 삭제한다."""
        result = self.session.execute(delete(CrawlRun).where(CrawlRun.started_at < started_before))
        return int(result.rowcount or 0)

    def delete_notifications_before(self, *, sent_before: datetime) -> int:
        """발송 완료 시각 기준으로 오래된 알림 이력을 삭제한다."""
        result = self.session.execute(
            delete(Notification).where(
                Notification.sent_at.is_not(None), Notification.sent_at < sent_before
            )
        )
        return int(result.rowcount or 0)

    def delete_revisions_before(self, *, detected_before: datetime) -> int:
        """오래된 변경 이력을 삭제해 JSONB 누적을 막는다."""
        result = self.session.execute(
            delete(JobPostingRevision).where(JobPostingRevision.detected_at < detected_before)
        )
        return int(result.rowcount or 0)


class NotificationRepository(CRUDRepository[Notification]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, Notification)

    def list_due(self, *, channel: NotificationChannel, now: datetime) -> Sequence[Notification]:
        """방해금지 종료 후 전송할 pending 이력을 오래된 순으로 읽는다."""
        return self.session.scalars(
            select(Notification)
            .where(
                Notification.channel == channel,
                Notification.status == NotificationStatus.PENDING,
                (Notification.scheduled_at.is_(None)) | (Notification.scheduled_at <= now),
            )
            .order_by(Notification.id)
        ).all()

    def list_recent(self, *, limit: int) -> Sequence[Notification]:
        """관리 화면용 최근 알림 이력과 공고·소스 정보를 함께 조회한다."""
        return self.session.scalars(
            select(Notification)
            .options(joinedload(Notification.job_posting).joinedload(JobPosting.source))
            .order_by(Notification.id.desc())
            .limit(limit)
        ).all()


class PushSubscriptionRepository(CRUDRepository[PushSubscription]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, PushSubscription)

    def get_by_endpoint(self, endpoint: str) -> PushSubscription | None:
        """중복 구독 갱신에 사용할 endpoint 고유 행을 찾는다."""
        return self.session.scalar(
            select(PushSubscription).where(PushSubscription.endpoint == endpoint)
        )

    def list_active(self) -> Sequence[PushSubscription]:
        """실제 전송 대상으로 남아 있는 브라우저 구독만 조회한다."""
        return self.session.scalars(
            select(PushSubscription)
            .where(PushSubscription.is_active.is_(True))
            .order_by(PushSubscription.id)
        ).all()


class OAuthTokenRepository(CRUDRepository[OAuthToken]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, OAuthToken)

    def get_by_provider(self, provider: str) -> OAuthToken | None:
        """공급자별 한 개만 보관하는 암호화 OAuth 토큰을 조회한다."""
        return self.session.scalar(select(OAuthToken).where(OAuthToken.provider == provider))


class AppSettingRepository(CRUDRepository[AppSetting]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, AppSetting)
