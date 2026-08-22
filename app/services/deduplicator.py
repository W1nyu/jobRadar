"""공고 안정 식별자에 따른 PostgreSQL UPSERT 중복 판정."""

from __future__ import annotations

from dataclasses import dataclass

from app.models import JobPosting
from app.repositories import JobPostingRepository
from app.schemas import JobPostingDTO


@dataclass(frozen=True, slots=True)
class DeduplicationResult:
    """UPSERT 후 공고와 신규 여부를 함께 전달한다."""

    posting: JobPosting
    is_new: bool


class Deduplicator:
    """외부 ID 우선, fingerprint 대체 식별자로 원자적 중복 판정을 수행한다."""

    def __init__(self, postings: JobPostingRepository) -> None:
        self.postings = postings

    def upsert(self, job: JobPostingDTO) -> DeduplicationResult:
        """경합에도 안전한 ``ON CONFLICT DO NOTHING`` 뒤 기존 행을 반환한다."""
        posting = self.postings.insert_if_absent(job)
        if posting is not None:
            return DeduplicationResult(posting=posting, is_new=True)

        posting = self.postings.get_by_identity(job)
        if posting is None:
            raise RuntimeError("UPSERT 충돌 뒤 기존 공고를 찾지 못했습니다.")
        return DeduplicationResult(posting=posting, is_new=False)
