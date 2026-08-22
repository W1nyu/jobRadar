"""Web Push 브라우저 구독의 등록·갱신 서비스."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.models import PushSubscription
from app.repositories import PushSubscriptionRepository


@dataclass(frozen=True, slots=True)
class PushSubscriptionInput:
    """브라우저 PushManager가 반환한 공개 구독 값."""

    endpoint: str
    p256dh: str
    auth: str


class PushSubscriptionService:
    """endpoint 유일성을 지키며 브라우저 구독을 최신 키로 갱신한다."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.subscriptions = PushSubscriptionRepository(session)

    def upsert(self, data: PushSubscriptionInput) -> tuple[PushSubscription, bool]:
        """새 endpoint는 만들고 기존 endpoint는 키 회전으로 갱신한다."""
        subscription = self.subscriptions.get_by_endpoint(data.endpoint)
        if subscription is None:
            subscription = self.subscriptions.create(
                endpoint=data.endpoint,
                p256dh=data.p256dh,
                auth=data.auth,
                is_active=True,
                failure_count=0,
            )
            created = True
        else:
            self.subscriptions.update(
                subscription,
                p256dh=data.p256dh,
                auth=data.auth,
                is_active=True,
                failure_count=0,
            )
            created = False
        self.session.commit()
        return subscription, created
