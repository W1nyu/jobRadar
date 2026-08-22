"""관심·제외 키워드를 공고 텍스트에 적용하고 매칭 근거를 만든다."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.models import KeywordKind, MatchMode
from app.repositories import JobKeywordMatchRepository, KeywordRepository

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy.orm import Session

    from app.models import JobPosting, Keyword

_SNIPPET_RADIUS = 30


@dataclass(frozen=True, slots=True)
class KeywordMatchEvidence:
    """키워드 하나가 어느 공고 필드에서 왜 일치했는지 보여주는 근거."""

    keyword_id: int
    kind: KeywordKind
    matched_field: str
    matched_snippet: str
    score: int


@dataclass(frozen=True, slots=True)
class KeywordMatchResult:
    """include/exclude 판정과 저장할 매칭 근거 묶음."""

    include_matches: tuple[KeywordMatchEvidence, ...]
    exclude_matches: tuple[KeywordMatchEvidence, ...]

    @property
    def is_matched(self) -> bool:
        """관심 키워드가 하나 이상이고 제외 키워드는 없어야 관심 공고다."""
        return bool(self.include_matches) and not self.exclude_matches

    @property
    def all_matches(self) -> tuple[KeywordMatchEvidence, ...]:
        """UI 근거 조회를 위해 include와 exclude 모두 보존한다."""
        return self.include_matches + self.exclude_matches


class KeywordMatcher:
    """활성 키워드를 공고에 적용하고 매칭 근거를 저장하는 서비스."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.keywords = KeywordRepository(session)
        self.matches = JobKeywordMatchRepository(session)

    def match_and_record(self, *, posting: JobPosting) -> KeywordMatchResult:
        """현재 활성 키워드 기준으로 공고의 매칭 근거 전체를 교체한다."""
        with self.session.begin_nested():
            result = evaluate_keywords(posting=posting, keywords=self.keywords.list_active())
            self.matches.replace_for_posting(
                job_posting_id=posting.id,
                matches=[
                    (
                        evidence.keyword_id,
                        evidence.matched_field,
                        evidence.matched_snippet,
                        evidence.score,
                    )
                    for evidence in result.all_matches
                ],
            )
        return result


def evaluate_keywords(*, posting: JobPosting, keywords: Sequence[Keyword]) -> KeywordMatchResult:
    """DB 접근 없이 활성 키워드와 공고 한 건의 매칭 결과를 계산한다."""
    include_matches: list[KeywordMatchEvidence] = []
    exclude_matches: list[KeywordMatchEvidence] = []
    fields = {"title": posting.title, "description": posting.description or ""}

    for keyword in keywords:
        if keyword.is_active is False or keyword.id is None:
            continue
        found = _find_first_match(keyword=keyword, fields=fields)
        if found is None:
            continue
        field_name, match = found
        evidence = KeywordMatchEvidence(
            keyword_id=keyword.id,
            kind=keyword.kind,
            matched_field=field_name,
            matched_snippet=_snippet(fields[field_name], match.start(), match.end()),
            score=keyword.weight,
        )
        if keyword.kind is KeywordKind.INCLUDE:
            include_matches.append(evidence)
        else:
            exclude_matches.append(evidence)

    return KeywordMatchResult(
        include_matches=tuple(sorted(include_matches, key=_sort_key)),
        exclude_matches=tuple(sorted(exclude_matches, key=_sort_key)),
    )


def _find_first_match(
    *, keyword: Keyword, fields: dict[str, str]
) -> tuple[str, re.Match[str]] | None:
    """키워드가 지정한 첫 필드에서 일치한 정규식 객체를 반환한다."""
    pattern = _compile_pattern(keyword.term, keyword.match_mode)
    if pattern is None:
        return None
    for field_name in keyword.target_fields:
        field_value = fields.get(field_name)
        if field_value is None:
            continue
        if match := pattern.search(field_value):
            return field_name, match
    return None


def _compile_pattern(term: str, mode: MatchMode) -> re.Pattern[str] | None:
    """사용자 키워드를 선택한 매칭 모드의 대소문자 무시 정규식으로 바꾼다."""
    if not term:
        return None
    if mode is MatchMode.SUBSTRING:
        expression = re.escape(term)
    elif mode is MatchMode.WORD:
        expression = rf"(?<!\w){re.escape(term)}(?!\w)"
    else:
        expression = term
    try:
        return re.compile(expression, re.IGNORECASE)
    except re.error:
        # 잘못 저장된 정규식 하나가 전체 수집을 실패시키지 않도록 그 키워드만 건너뛴다.
        return None


def _snippet(value: str, start: int, end: int) -> str:
    """일치 문자열 주변의 공백을 압축한 짧은 UI 표시용 근거를 만든다."""
    left = max(0, start - _SNIPPET_RADIUS)
    right = min(len(value), end + _SNIPPET_RADIUS)
    prefix = "…" if left > 0 else ""
    suffix = "…" if right < len(value) else ""
    return prefix + re.sub(r"\s+", " ", value[left:right]).strip() + suffix


def _sort_key(evidence: KeywordMatchEvidence) -> tuple[int, int]:
    """동일 가중치에서는 키워드 ID로 결과 순서를 고정한다."""
    return (-evidence.score, evidence.keyword_id)
