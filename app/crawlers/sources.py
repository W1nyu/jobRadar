"""M3 단발 실행에 필요한 최소 소스 설정.

M8 관리 UI와 M6 워커는 DB의 sources 행을 이 형태로 변환해 넘긴다. 이 모듈은 그 전까지
CLI 검증을 위해 두 개의 초기 소스만 제공한다.
"""

from app.core.config import Settings
from app.crawlers.base import CrawlSource


class UnknownBuiltinSourceError(LookupError):
    """M3 CLI가 아직 알지 못하는 소스 slug를 요청한 경우."""


class MissingCrawlCredentialError(ValueError):
    """공식 API 소스에 필요한 선택형 키가 비어 있는 경우."""


def build_builtin_source(slug: str, settings: Settings) -> CrawlSource:
    """M3에서 검증할 공공데이터포털·링커리어 소스 설정을 만든다."""
    if slug == "datagokr-msit-recruitment":
        service_key = settings.msit_recruitment_service_key
        if not service_key:
            raise MissingCrawlCredentialError("MSIT_RECRUITMENT_SERVICE_KEY가 설정되지 않았습니다.")
        return CrawlSource(
            slug=slug,
            crawler_key=slug,
            base_url="https://apis.data.go.kr",
            config={"service_key": service_key, "display": 20},
            rate_limit_per_min=30,
        )
    if slug == "linkareer":
        return CrawlSource(
            slug=slug,
            crawler_key=slug,
            base_url="https://linkareer.com",
            config={},
            rate_limit_per_min=30,
        )
    raise UnknownBuiltinSourceError(f"M3에 등록된 소스가 아닙니다: {slug}")
