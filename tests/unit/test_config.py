"""설정 로딩 동작 검증.

이 테스트들은 `.env` 파일을 읽지 않는다(`_env_file=None`). 개발자의 실제 `.env`나
OS 환경변수가 결과를 바꾸면 테스트가 환경에 따라 달라지기 때문이다.
"""

from pathlib import Path

import pytest
from dotenv import dotenv_values
from pydantic import ValidationError

from app.core.config import Settings

REQUIRED = {
    "APP_BASE_URL": "https://example.com",
    "SECRET_KEY": "test-secret",
}


def make_settings(**overrides: str) -> Settings:
    return Settings(_env_file=None, **{**REQUIRED, **overrides})


def test_필수_변수가_없으면_어떤_변수인지_알려주는_에러가_난다(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("APP_BASE_URL", raising=False)
    monkeypatch.delenv("SECRET_KEY", raising=False)
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


def test_잡알리오_키가_없어도_기동하고_입력하면_활성화된다() -> None:
    assert make_settings().alio_enabled is False
    assert make_settings(ALIO_SERVICE_KEY="alio-key").alio_enabled is True


def test_과기정통부_모집채용_키를_별도로_받는다() -> None:
    assert make_settings().msit_recruitment_enabled is False

    settings = make_settings(MSIT_RECRUITMENT_SERVICE_KEY="msit-key")

    assert settings.msit_recruitment_service_key == "msit-key"
    assert settings.msit_recruitment_enabled is True


def test_고용24_전용_인증키를_선택적으로_받는다() -> None:
    assert make_settings().work24_enabled is False

    settings = make_settings(WORK24_SERVICE_KEY="work24-key")

    assert settings.work24_service_key == "work24-key"
    assert settings.work24_enabled is True


def test_base_url_끝의_슬래시는_제거된다() -> None:
    """콜백 URL 등을 조립할 때 `//`가 생기는 것을 막는다."""
    settings = make_settings(APP_BASE_URL="https://example.com/")

    assert settings.app_base_url == "https://example.com"


def test_기본값은_운영이_아니라_개발이다() -> None:
    """설정 실수로 운영 모드가 켜지는 것보다 개발 모드가 안전하다."""
    settings = make_settings()

    assert settings.app_env == "development"
    assert settings.is_production is False


def test_환경변수_예시는_그대로_읽을_수_있다() -> None:
    """복사한 `.env`가 어떤 로더에서도 설정값으로 안전하게 읽히는지 확인한다."""
    example_path = Path(__file__).parents[2] / ".env.example"
    values = {key: value for key, value in dotenv_values(example_path).items() if value is not None}

    settings = Settings(_env_file=None, **values)

    assert settings.app_env == "development"
    assert settings.log_json is False


def test_데이터베이스_연결과_풀_설정을_환경변수로_받는다() -> None:
    settings = make_settings(
        DATABASE_URL="postgresql+psycopg://test:test@localhost:5432/jobradar_test",
        DB_POOL_SIZE="3",
        DB_MAX_OVERFLOW="1",
    )

    assert settings.database_url == "postgresql+psycopg://test:test@localhost:5432/jobradar_test"
    assert settings.db_pool_size == 3
    assert settings.db_max_overflow == 1


def test_web_push와_카카오_설정은_필수값이_모였을때만_활성화된다() -> None:
    assert make_settings().vapid_enabled is False
    assert make_settings().kakao_enabled is False

    vapid = make_settings(
        VAPID_PUBLIC_KEY="public",
        VAPID_PRIVATE_KEY="private",
        VAPID_SUBJECT="mailto:admin@example.com",
    )
    kakao = make_settings(
        FERNET_KEY="fernet-key",
        KAKAO_REST_API_KEY="rest-key",
        KAKAO_REDIRECT_URI="https://example.com/oauth/kakao/callback",
    )

    assert vapid.vapid_enabled is True
    assert kakao.kakao_enabled is True
