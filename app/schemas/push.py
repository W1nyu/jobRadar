"""브라우저 Push API 구독 요청 계약."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class PushSubscriptionKeys(BaseModel):
    """PushManager subscription의 암호화 공개 키 묶음."""

    p256dh: str = Field(min_length=1, max_length=10_000)
    auth: str = Field(min_length=1, max_length=10_000)


class PushSubscriptionCreate(BaseModel):
    """브라우저가 서버로 보내는 표준 PushSubscription 일부."""

    endpoint: str = Field(min_length=8, max_length=10_000)
    keys: PushSubscriptionKeys

    @field_validator("endpoint")
    @classmethod
    def _https_endpoint(cls, value: str) -> str:
        if not value.startswith("https://"):
            raise ValueError("Web Push endpoint는 https 주소여야 합니다.")
        return value
