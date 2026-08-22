"""M8 단일 관리자 로그인 검증.

사용자 테이블 없이 환경변수의 argon2 해시 하나만 검증한다. 세션 서명과 쿠키 속성은 웹 계층의
SessionMiddleware가 담당하고, 이 서비스는 평문 비밀번호를 저장하거나 로그에 남기지 않는다.
"""

from __future__ import annotations

import hmac

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import Settings


class AdminAuthService:
    """설정된 단일 관리자 계정의 자격 증명을 검증한다."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.password_hasher = PasswordHasher()

    def verify(self, *, username: str, password: str) -> bool:
        """계정명과 argon2 해시를 모두 검증한다."""
        password_hash = self.settings.admin_password_hash
        if not password_hash or not hmac.compare_digest(username, self.settings.admin_username):
            return False
        try:
            return self.password_hasher.verify(password_hash, password)
        except (InvalidHashError, VerificationError):
            return False
