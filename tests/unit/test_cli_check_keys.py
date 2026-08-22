"""외부 API 키 설정 상태 점검과 M9 키 생성 동작 검증.

사람인 API는 승인 대기 중이다. 승인이 난 뒤 `.env`에 키를 넣었을 때
"정말 인식됐는지"를 앱을 띄우지 않고 확인할 수단이 필요하다.
"""

from base64 import urlsafe_b64decode

from argon2 import PasswordHasher

from app.cli import generate_fernet_key, generate_password_hash, generate_vapid_keys, key_statuses
from app.core.config import Settings


def make_settings(**overrides: str) -> Settings:
    return Settings(
        _env_file=None,
        APP_BASE_URL="https://example.com",
        SECRET_KEY="test-secret",
        **overrides,
    )


def status_for(settings: Settings, name: str):
    return next(s for s in key_statuses(settings) if s.name == name)


def test_공공데이터포털과_사람인_상태를_모두_보고한다() -> None:
    names = {s.name for s in key_statuses(make_settings())}

    assert names == {
        "DATA_GO_KR_SERVICE_KEY",
        "MSIT_RECRUITMENT_SERVICE_KEY",
        "WORK24_SERVICE_KEY",
        "ALIO_SERVICE_KEY",
        "SARAMIN_ACCESS_KEY",
    }


def test_키가_없으면_미설정으로_보고한다() -> None:
    status = status_for(make_settings(), "SARAMIN_ACCESS_KEY")

    assert status.configured is False


def test_키를_넣으면_설정됨으로_보고한다() -> None:
    settings = make_settings(SARAMIN_ACCESS_KEY="approved-key")

    assert status_for(settings, "SARAMIN_ACCESS_KEY").configured is True


def test_키_값_자체는_노출하지_않는다() -> None:
    """터미널 출력이나 로그에 키가 그대로 찍히면 안 된다."""
    settings = make_settings(SARAMIN_ACCESS_KEY="super-secret-value")

    status = status_for(settings, "SARAMIN_ACCESS_KEY")

    assert "super-secret-value" not in repr(status)


def test_어느_마일스톤에서_필요한지_알려준다() -> None:
    """지금 비어 있는 게 문제인지 아닌지 판단할 수 있어야 한다."""
    assert status_for(make_settings(), "DATA_GO_KR_SERVICE_KEY").needed_by == "M7"
    assert status_for(make_settings(), "MSIT_RECRUITMENT_SERVICE_KEY").needed_by == "M3"
    assert status_for(make_settings(), "WORK24_SERVICE_KEY").needed_by == "M7"
    assert status_for(make_settings(), "ALIO_SERVICE_KEY").needed_by == "M7"
    assert status_for(make_settings(), "SARAMIN_ACCESS_KEY").needed_by == "M7"


def test_vapid_키생성은_urlsafe_공개키와_비밀키를_반환한다() -> None:
    public_key, private_key = generate_vapid_keys()

    assert len(urlsafe_b64decode(public_key + "=" * (-len(public_key) % 4))) == 65
    assert len(urlsafe_b64decode(private_key + "=" * (-len(private_key) % 4))) == 32


def test_fernet_키생성은_정확한_base64_길이를_반환한다() -> None:
    key = generate_fernet_key()

    assert len(urlsafe_b64decode(key)) == 32


def test_관리자_비밀번호는_argon2_해시로_생성한다() -> None:
    password_hash = generate_password_hash("admin-password")

    assert PasswordHasher().verify(password_hash, "admin-password") is True
