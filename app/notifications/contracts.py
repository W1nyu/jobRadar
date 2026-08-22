"""알림 채널이 공유하는 DB-독립 전송 계약."""

from __future__ import annotations

from dataclasses import dataclass

from app.models import NotificationChannel


@dataclass(frozen=True, slots=True)
class NotificationItem:
    """묶음 알림에 들어갈 공고 한 건의 공개 정보."""

    posting_id: int
    title: str
    source_name: str
    url: str
    keywords: tuple[str, ...]
    deadline: str | None = None


@dataclass(frozen=True, slots=True)
class NotificationPayload:
    """채널이 발송에 필요한 값만 받도록 만든 공통 페이로드."""

    title: str
    body: str
    url: str
    items: tuple[NotificationItem, ...]
    tag: str = "jobradar-new-postings"


@dataclass(frozen=True, slots=True)
class SendResult:
    """채널 전송 결과와 정리할 Web Push 구독을 전달한다."""

    succeeded: bool
    error_message: str | None = None
    invalid_endpoints: tuple[str, ...] = ()
    failed_endpoints: tuple[str, ...] = ()


class NotificationSender:
    """DB를 모르는 채널 구현체의 최소 인터페이스."""

    name: NotificationChannel

    def send(self, payload: NotificationPayload) -> SendResult:
        """묶음 페이로드 하나를 전송하고 결과만 반환한다."""
        raise NotImplementedError
