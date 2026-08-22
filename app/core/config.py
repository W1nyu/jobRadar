"""애플리케이션 설정.

환경변수와 `.env`에서 값을 읽는다. 필드명은 소문자로 두되 별칭을 대문자로 생성해,
검증 에러 메시지가 `.env`에 적어야 할 이름 그대로(`SECRET_KEY`) 나오게 한다.

외부 API 키는 모두 선택값이다. 키가 없으면 해당 소스만 꺼지고 앱은 정상 기동한다.
승인 대기 중인 API(사람인 등) 때문에 전체가 멈추면 안 되기 때문이다.
"""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _is_blank(value: str | None) -> bool:
    """미설정, 빈 문자열, 공백만 있는 값을 모두 '없음'으로 본다.

    `.env`에 `SARAMIN_ACCESS_KEY=`처럼 자리만 잡아둔 상태를 설정된 것으로
    오인하면, 빈 키로 API를 호출해 401을 맞고 원인을 찾느라 시간을 쓰게 된다.
    """
    return value is None or not value.strip()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        alias_generator=str.upper,
        populate_by_name=True,
        case_sensitive=True,
        extra="ignore",
    )

    # ---- 앱 ----
    app_env: Literal["development", "production"] = "development"
    app_base_url: str
    secret_key: str
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_json: bool = Field(
        default=False,
        description="True면 JSON 로그(운영용), False면 사람이 읽는 컬러 로그(개발용)",
    )

    # ---- 데이터베이스 ----
    # Windows 개발 Docker의 IPv6 localhost 우선 해석으로 인한 연결 지연을 피하려고 IPv4 loopback을 쓴다.
    database_url: str = "postgresql+psycopg://jobradar:jobradar@127.0.0.1:5432/jobradar"
    db_pool_size: int = 5
    db_max_overflow: int = 2

    # ---- 외부 API 키 (모두 선택값) ----
    data_go_kr_service_key: str | None = None
    msit_recruitment_service_key: str | None = None
    work24_service_key: str | None = None
    alio_service_key: str | None = None
    saramin_access_key: str | None = None

    # ---- 수집 (M3부터 사용) ----
    crawl_max_workers: int = 3
    crawl_max_items_per_run: int = 500
    crawl_max_pages_per_run: int = 10
    crawl_max_response_bytes: int = 5 * 1024 * 1024
    crawl_user_agent: str = "jobRadar/1.0 (personal job monitor; contact@example.com)"

    @field_validator("app_base_url")
    @classmethod
    def _strip_trailing_slash(cls, v: str) -> str:
        """URL을 조립할 때 `//`가 생기지 않도록 끝 슬래시를 떼어둔다."""
        return v.rstrip("/")

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def data_go_kr_enabled(self) -> bool:
        """공공데이터포털 공용 소스 사용 가능 여부 (M7에서 사용)."""
        return not _is_blank(self.data_go_kr_service_key)

    @property
    def msit_recruitment_enabled(self) -> bool:
        """과기정통부 모집채용 API 키 설정 여부 (M3에서 사용)."""
        return not _is_blank(self.msit_recruitment_service_key)

    @property
    def work24_enabled(self) -> bool:
        """고용24 채용정보 API의 authKey 설정 여부 (M7 이후 사용)."""
        return not _is_blank(self.work24_service_key)

    @property
    def alio_enabled(self) -> bool:
        """잡알리오 소스 사용 가능 여부 (M7에서 사용)."""
        return not _is_blank(self.alio_service_key)

    @property
    def saramin_enabled(self) -> bool:
        """사람인 소스 사용 가능 여부 (M7에서 사용).

        승인이 나면 `.env`에 `SARAMIN_ACCESS_KEY`를 채우는 것만으로 켜진다.
        코드 변경은 필요 없다.
        """
        return not _is_blank(self.saramin_access_key)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """프로세스 수명 동안 한 번만 읽는다. FastAPI 의존성으로도 쓴다."""
    return Settings()  # type: ignore[call-arg]
