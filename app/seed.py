"""개발·초기 운영 환경에 필요한 기본 데이터를 넣는다.

uv run --extra db python -m app.seed
"""

import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import SessionLocal, get_engine
from app.models import Keyword

DEFAULT_KEYWORDS = (
    "데이터",
    "데이터분석",
    "IT",
    "디지털",
    "AI",
    "개발",
    "신입",
    "인턴",
)


def _force_utf8_stdout() -> None:
    """Windows 기본 코드페이지에서도 시드 결과의 한글을 올바르게 출력한다."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


def seed_default_keywords(session: Session) -> int:
    """빠진 기본 키워드만 추가하고, 새로 등록한 수를 반환한다."""
    existing_terms = set(
        session.scalars(select(Keyword.term).where(Keyword.term.in_(DEFAULT_KEYWORDS))).all()
    )
    for term in DEFAULT_KEYWORDS:
        if term not in existing_terms:
            session.add(Keyword(term=term))
    session.flush()
    return len(DEFAULT_KEYWORDS) - len(existing_terms)


def main() -> int:
    """시드 트랜잭션을 커밋하고 결과를 한 줄로 알린다."""
    _force_utf8_stdout()
    get_engine()
    with SessionLocal() as session:
        added = seed_default_keywords(session)
        session.commit()
    print(f"기본 키워드 시드 완료: {added}건 추가")
    return 0


if __name__ == "__main__":
    sys.exit(main())
