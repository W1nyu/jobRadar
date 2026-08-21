"""설정 로딩 동작 검증.

이 테스트들은 `.env` 파일을 읽지 않는다(`_env_file=None`). 개발자의 실제 `.env`나
OS 환경변수가 결과를 바꾸면 테스트가 환경에 따라 달라지기 때문이다.
"""

import pytest
from pydantic import ValidationError

from app.core.config import Settings

REQUIRED = {
    "APP_BASE_URL": "https://example.com",
    "SECRET_KEY": "test-secret",
}


def make_settings(**overrides: str) -> Settings:
    return Settings(_env_file=None, **{**REQUIRED, **overrides})


def test_필수_변수가_없으면_어떤_변수인지_알려주는_에러가_난다() -> None:
    with pytest.raises(ValidationError) as exc:
        Settings(_env_file=None, APP_BASE_URL="https://example.com")

    assert "SECRET_KEY" in str(exc.value)


def test_사람인_키가_없어도_기동된다() -> None:
    """사람인 API는 승인 대기 중이다. 키가 없다고 앱이 뜨지 않으면 안 된다."""
    settings = make_settings()

    assert settings.saramin_access_key is None
    assert settings.saramin_enabled is False


def test_사람인_키를_넣으면_활성화된다() -> None:
    """승인이 나면 .env에 키만 넣어도 켜져야 한다."""
    settings = make_settings(SARAMIN_ACCESS_KEY="approved-key")

    assert settings.saramin_access_key == "approved-key"
    assert settings.saramin_enabled is True


def test_사람인_키가_빈_문자열이면_비활성으로_본다() -> None:
    """`.env`에 `SARAMIN_ACCESS_KEY=`처럼 자리만 잡아둔 상태를 미설정으로 취급한다."""
    settings = make_settings(SARAMIN_ACCESS_KEY="   ")

    assert settings.saramin_enabled is False


def test_base_url_끝의_슬래시는_제거된다() -> None:
    """콜백 URL 등을 조립할 때 `//`가 생기는 것을 막는다."""
    settings = make_settings(APP_BASE_URL="https://example.com/")

    assert settings.app_base_url == "https://example.com"


def test_기본값은_운영이_아니라_개발이다() -> None:
    """설정 실수로 운영 모드가 켜지는 것보다 개발 모드가 안전하다."""
    settings = make_settings()

    assert settings.app_env == "development"
    assert settings.is_production is False


def test_데이터베이스_연결과_풀_설정을_환경변수로_받는다() -> None:
    settings = make_settings(
        DATABASE_URL="postgresql+psycopg://test:test@localhost:5432/jobradar_test",
        DB_POOL_SIZE="3",
        DB_MAX_OVERFLOW="1",
    )

    assert settings.database_url == "postgresql+psycopg://test:test@localhost:5432/jobradar_test"
    assert settings.db_pool_size == 3
    assert settings.db_max_overflow == 1
