"""M7에서 스케줄할 기본 채용 소스의 비밀 없는 정의.

카탈로그는 크롤러와 ORM 모델을 직접 연결하지 않는다. DB 시드는 이 정의를 읽어 Source 행을
만들고, 실제 API 키는 실행 시점에만 Settings에서 주입한다.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.config import Settings


@dataclass(frozen=True, slots=True)
class BuiltinSourceDefinition:
    """기본 소스 하나를 등록·시드하는 데 필요한 공개 설정."""

    slug: str
    name: str
    crawler_key: str
    base_url: str
    fetch_strategy: str
    interval_minutes: int
    rate_limit_per_min: int
    config: dict[str, Any] = field(default_factory=dict)
    required_setting: str | None = None


BUILTIN_SOURCE_DEFINITIONS = (
    BuiltinSourceDefinition(
        slug="datagokr-msit-recruitment",
        name="과기정통부 모집채용",
        crawler_key="datagokr-msit-recruitment",
        base_url="https://apis.data.go.kr",
        fetch_strategy="api",
        interval_minutes=60,
        rate_limit_per_min=30,
        config={"display": 20},
        required_setting="msit_recruitment_enabled",
    ),
    BuiltinSourceDefinition(
        slug="linkareer",
        name="링커리어",
        crawler_key="linkareer",
        base_url="https://linkareer.com",
        fetch_strategy="html",
        interval_minutes=60,
        rate_limit_per_min=30,
    ),
    BuiltinSourceDefinition(
        slug="inthiswork",
        name="인디스워크",
        crawler_key="inthiswork",
        base_url="https://inthiswork.com",
        fetch_strategy="json",
        interval_minutes=60,
        rate_limit_per_min=10,
        config={"categories": [191700167, 191700168], "display": 20},
    ),
    BuiltinSourceDefinition(
        slug="kofia",
        name="금융투자협회 채용안내",
        crawler_key="kofia",
        base_url="https://www.kofia.or.kr",
        fetch_strategy="html",
        interval_minutes=60,
        rate_limit_per_min=10,
    ),
    BuiltinSourceDefinition(
        slug="alio-recruitment",
        name="잡알리오 공공기관 채용정보",
        crawler_key="alio-recruitment",
        base_url="https://opendata.alio.go.kr",
        fetch_strategy="json",
        interval_minutes=60,
        rate_limit_per_min=10,
        config={"display": 20, "ongoing_only": True},
    ),
)


def get_builtin_source_definition(slug: str) -> BuiltinSourceDefinition:
    """slug에 맞는 기본 소스 정의를 반환한다."""
    for definition in BUILTIN_SOURCE_DEFINITIONS:
        if definition.slug == slug:
            return definition
    raise LookupError(f"등록되지 않은 기본 소스입니다: {slug}")


def enabled_builtin_sources(settings: Settings) -> tuple[BuiltinSourceDefinition, ...]:
    """현재 선택형 키 상태에서 안전하게 활성화할 기본 소스만 반환한다."""
    return tuple(
        definition
        for definition in BUILTIN_SOURCE_DEFINITIONS
        if definition.required_setting is None
        or bool(getattr(settings, definition.required_setting))
    )
