"""개발·초기 운영 환경에 필요한 기본 데이터를 넣는다.

uv run --extra db python -m app.seed
"""

import sys

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.db import SessionLocal, get_engine
from app.models import FetchStrategy, Keyword, Source
from app.source_catalog import enabled_builtin_sources

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


def seed_builtin_sources(session: Session, settings: Settings) -> int:
    """현재 사용 가능한 기본 채용 소스만 처음 한 번 등록한다.

    기존 행은 운영자가 바꿨을 수 있으므로 갱신하지 않는다. API 키도 config에 넣지 않고,
    워커·수동 실행이 Settings에서 실행 시점에만 주입한다.
    """
    definitions = enabled_builtin_sources(settings)
    existing_slugs = set(
        session.scalars(
            select(Source.slug).where(Source.slug.in_([item.slug for item in definitions]))
        ).all()
    )
    for definition in definitions:
        if definition.slug in existing_slugs:
            continue
        session.add(
            Source(
                slug=definition.slug,
                name=definition.name,
                crawler_key=definition.crawler_key,
                base_url=definition.base_url,
                config=dict(definition.config),
                fetch_strategy=FetchStrategy(definition.fetch_strategy),
                interval_minutes=definition.interval_minutes,
                is_active=True,
                rate_limit_per_min=definition.rate_limit_per_min,
            )
        )
    session.flush()
    return len(definitions) - len(existing_slugs)


def main() -> int:
    """시드 트랜잭션을 커밋하고 결과를 한 줄로 알린다."""
    _force_utf8_stdout()
    get_engine()
    settings = get_settings()
    with SessionLocal() as session:
        keyword_added = seed_default_keywords(session)
        source_added = seed_builtin_sources(session, settings)
        session.commit()
    print(f"기본 키워드 시드 완료: {keyword_added}건 추가")
    print(f"기본 소스 시드 완료: {source_added}건 추가")
    return 0


if __name__ == "__main__":
    sys.exit(main())
