"""기본 소스의 실행 설정과 실행 시점 자격 증명 주입."""

from app.core.config import Settings
from app.crawlers.base import CrawlSource
from app.source_catalog import get_builtin_source_definition


class UnknownBuiltinSourceError(LookupError):
    """CLI가 등록하지 않은 기본 소스 slug를 요청한 경우."""


class MissingCrawlCredentialError(ValueError):
    """공식 API 소스에 필요한 선택형 키가 비어 있는 경우."""


def build_builtin_source(slug: str, settings: Settings) -> CrawlSource:
    """CLI용 기본 소스 설정을 만들고, 필요한 키는 메모리에만 넣는다."""
    try:
        definition = get_builtin_source_definition(slug)
    except LookupError as error:
        raise UnknownBuiltinSourceError(f"등록되지 않은 기본 소스입니다: {slug}") from error
    return with_runtime_credentials(
        CrawlSource(
            slug=definition.slug,
            crawler_key=definition.crawler_key,
            base_url=definition.base_url,
            config=dict(definition.config),
            rate_limit_per_min=definition.rate_limit_per_min,
        ),
        settings,
    )


def with_runtime_credentials(source: CrawlSource, settings: Settings) -> CrawlSource:
    """DB·카탈로그에는 저장하지 않는 API 키를 해당 실행에만 복사한다."""
    config = dict(source.config)
    if source.crawler_key == "datagokr-msit-recruitment":
        service_key = settings.msit_recruitment_service_key
        if not service_key or not service_key.strip():
            raise MissingCrawlCredentialError("MSIT_RECRUITMENT_SERVICE_KEY가 설정되지 않았습니다.")
        config["service_key"] = service_key
    return CrawlSource(
        slug=source.slug,
        crawler_key=source.crawler_key,
        base_url=source.base_url,
        config=config,
        rate_limit_per_min=source.rate_limit_per_min,
    )
