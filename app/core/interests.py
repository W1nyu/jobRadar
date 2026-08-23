"""관심 공고 판정에서 보조 조건으로만 쓰는 키워드 정책."""

# 신입·인턴은 채용 형태를 나타낼 뿐 직무 관심사를 특정하지 않는다. 이 단어만 일치한
# 공고(예: 마케팅 인턴)는 저장하지 않고, IT 직무 같은 주 관심 키워드와 함께 일치할 때만
# 관심 공고로 취급한다.
CONTEXT_ONLY_INCLUDE_TERMS = frozenset({"신입", "인턴"})


def is_primary_include_term(term: str) -> bool:
    """공고를 저장할 근거가 되는 주 관심 키워드인지 판정한다."""
    return term.strip().casefold() not in CONTEXT_ONLY_INCLUDE_TERMS
