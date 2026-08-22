"""M7 기본 소스 카탈로그와 자격 증명 주입 검증."""

from app.core.config import Settings
from app.crawlers.base import CrawlSource
from app.crawlers.sources import build_builtin_source, with_runtime_credentials
from app.source_catalog import enabled_builtin_sources


def _settings(**values: object) -> Settings:
    return Settings(
        _env_file=None,
        APP_BASE_URL="https://example.com",
        SECRET_KEY="test-secret",
        **values,
    )


def test_기본_스케줄_소스는_사람인_승인_없이도_네개_이상이다() -> None:
    slugs = {source.slug for source in enabled_builtin_sources(_settings())}

    assert {"linkareer", "inthiswork", "kofia", "alio-recruitment"} <= slugs
    assert len(slugs) >= 4


def test_api_자격증명은_실행시만_소스_설정에_주입한다() -> None:
    source = build_builtin_source(
        "datagokr-msit-recruitment", _settings(MSIT_RECRUITMENT_SERVICE_KEY="test-msit-key")
    )

    assert source.config["service_key"] == "test-msit-key"


def test_실행시_주입은_원본_db_소스_설정을_변경하지_않는다() -> None:
    original = CrawlSource(
        slug="datagokr-msit-recruitment",
        crawler_key="datagokr-msit-recruitment",
        base_url="https://apis.data.go.kr",
        config={"display": 20},
        rate_limit_per_min=30,
    )

    enriched = with_runtime_credentials(
        original, _settings(MSIT_RECRUITMENT_SERVICE_KEY="test-msit-key")
    )

    assert original.config == {"display": 20}
    assert enriched.config == {"display": 20, "service_key": "test-msit-key"}
