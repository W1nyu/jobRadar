"""M4 수집 오케스트레이션: 정규화·UPSERT·변경 이력·종료 판정을 묶는다."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.crawlers.base import RawJob
from app.repositories import JobPostingRepository, JobPostingRevisionRepository, SourceRepository
from app.services.change_detector import changed_fields
from app.services.deduplicator import Deduplicator
from app.services.keyword_matcher import KeywordMatcher
from app.services.normalizer import normalize


@dataclass(frozen=True, slots=True)
class CollectResult:
    """한 번의 완전 수집에서 영속화된 항목 수."""

    items_fetched: int
    items_new: int
    items_updated: int
    items_closed: int
    items_matched: int


class CollectorService:
    """DB 트랜잭션 안에서 공고 수집 결과 하나를 원자적으로 반영한다."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.sources = SourceRepository(session)
        self.postings = JobPostingRepository(session)
        self.revisions = JobPostingRevisionRepository(session)
        self.deduplicator = Deduplicator(self.postings)
        self.keyword_matcher = KeywordMatcher(session)

    def collect(
        self, *, source_id: int, raw_jobs: list[RawJob], complete: bool = True
    ) -> CollectResult:
        """완전한 사이트 목록을 반영하고, 부분 수집이면 종료 판정은 건너뛴다."""
        now = datetime.now(UTC)
        items_new = 0
        items_updated = 0
        items_matched = 0
        external_ids: set[str] = set()
        fingerprints: set[str] = set()

        # 상위 호출자가 commit을 결정하더라도, 이 유스케이스 내부 변경은 함께 되돌릴 수 있다.
        with self.session.begin_nested():
            if self.sources.get(source_id) is None:
                raise ValueError(f"존재하지 않는 소스입니다: {source_id}")

            for raw_job in raw_jobs:
                job = normalize(source_id=source_id, raw_job=raw_job)
                if job.external_id is not None:
                    external_ids.add(job.external_id)
                else:
                    fingerprints.add(job.identity)

                deduplicated = self.deduplicator.upsert(job)
                if deduplicated.is_new:
                    items_new += 1
                    if self.keyword_matcher.match_and_record(
                        posting=deduplicated.posting
                    ).is_matched:
                        items_matched += 1
                    continue

                posting = deduplicated.posting

                if posting.content_hash != job.content_hash:
                    fields = changed_fields(posting, job)
                    self.revisions.create(
                        job_posting_id=posting.id,
                        changed_fields=fields,
                        old_content_hash=posting.content_hash,
                        new_content_hash=job.content_hash,
                    )
                    items_updated += 1
                self.postings.apply_seen(posting, job, seen_at=now)

            items_closed = (
                self.postings.close_missing(
                    source_id=source_id,
                    external_ids=external_ids,
                    fingerprints=fingerprints,
                    closed_at=now,
                )
                if complete
                else 0
            )
            self.session.flush()

        return CollectResult(
            items_fetched=len(raw_jobs),
            items_new=items_new,
            items_updated=items_updated,
            items_closed=items_closed,
            items_matched=items_matched,
        )
