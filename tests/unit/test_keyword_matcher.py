"""M5 키워드 판정의 DB-독립 계약을 검증한다."""

from app.models import JobPosting, Keyword, KeywordKind, MatchMode
from app.services.keyword_matcher import evaluate_keywords


def _posting(*, title: str, description: str | None = None) -> JobPosting:
    return JobPosting(id=1, title=title, description=description)


def _keyword(
    *,
    keyword_id: int,
    term: str,
    kind: KeywordKind = KeywordKind.INCLUDE,
    match_mode: MatchMode = MatchMode.SUBSTRING,
    target_fields: list[str] | None = None,
    weight: int = 1,
) -> Keyword:
    return Keyword(
        id=keyword_id,
        term=term,
        kind=kind,
        match_mode=match_mode,
        target_fields=target_fields or ["title", "description"],
        weight=weight,
    )


def test_include_키워드는_대상_필드에서_부분_일치하고_근거를_반환한다() -> None:
    result = evaluate_keywords(
        posting=_posting(title="데이터 분석가", description="제품 지표를 분석합니다."),
        keywords=[_keyword(keyword_id=11, term="데이터")],
    )

    assert result.is_matched is True
    assert [
        (match.keyword_id, match.matched_field, match.score) for match in result.include_matches
    ] == [(11, "title", 1)]
    assert "데이터 분석가" in result.include_matches[0].matched_snippet


def test_exclude_키워드가_일치하면_include_공고도_관심_대상에서_제외된다() -> None:
    result = evaluate_keywords(
        posting=_posting(title="데이터 분석가", description="경력 5년 이상"),
        keywords=[
            _keyword(keyword_id=11, term="데이터", weight=3),
            _keyword(keyword_id=12, term="경력 5년", kind=KeywordKind.EXCLUDE),
        ],
    )

    assert result.is_matched is False
    assert [match.keyword_id for match in result.include_matches] == [11]
    assert [match.keyword_id for match in result.exclude_matches] == [12]


def test_match_mode과_target_fields를_적용한다() -> None:
    posting = _posting(title="AInative 플랫폼", description="AI 기반 데이터   분석 서비스")
    result = evaluate_keywords(
        posting=posting,
        keywords=[
            _keyword(
                keyword_id=1,
                term="AI",
                match_mode=MatchMode.WORD,
                target_fields=["title"],
            ),
            _keyword(
                keyword_id=2,
                term="AI",
                match_mode=MatchMode.WORD,
                target_fields=["description"],
            ),
            _keyword(
                keyword_id=3,
                term=r"데이터\s+분석",
                match_mode=MatchMode.REGEX,
                target_fields=["description"],
            ),
        ],
    )

    assert [match.keyword_id for match in result.include_matches] == [2, 3]
    assert [match.matched_field for match in result.include_matches] == [
        "description",
        "description",
    ]


def test_include_매칭은_가중치_내림차순으로_정렬된다() -> None:
    result = evaluate_keywords(
        posting=_posting(title="AI 데이터분석가"),
        keywords=[
            _keyword(keyword_id=1, term="AI", weight=1),
            _keyword(keyword_id=2, term="데이터분석", weight=5),
        ],
    )

    assert [(match.keyword_id, match.score) for match in result.include_matches] == [(2, 5), (1, 1)]
