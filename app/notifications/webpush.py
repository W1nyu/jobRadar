"""VAPID Web Push 채널."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from app.models import NotificationChannel
from app.notifications.contracts import NotificationPayload, SendResult

PushSender = Callable[..., object]


class WebPushChannel:
    """활성 구독에 동일한 배치 알림을 보내는 DB-독립 채널."""

    name = NotificationChannel.WEB_PUSH

    def __init__(
        self,
        *,
        subscriptions: Sequence[Mapping[str, str]],
        vapid_private_key: str,
        vapid_subject: str,
        push_sender: PushSender | None = None,
    ) -> None:
        self.subscriptions = tuple(subscriptions)
        self.vapid_private_key = vapid_private_key
        self.vapid_subject = vapid_subject
        self.push_sender = push_sender or _send_web_push

    def send(self, payload: NotificationPayload) -> SendResult:
        """모든 활성 브라우저에 보내고 만료·실패 endpoint를 구분한다."""
        if not self.subscriptions:
            return SendResult(succeeded=False, error_message="활성 Web Push 구독이 없습니다.")
        invalid: list[str] = []
        failed: list[str] = []
        sent = 0
        data = json.dumps(
            {"title": payload.title, "body": payload.body, "url": payload.url, "tag": payload.tag},
            ensure_ascii=False,
        )
        for subscription in self.subscriptions:
            endpoint = subscription["endpoint"]
            try:
                self.push_sender(
                    subscription_info={
                        "endpoint": endpoint,
                        "keys": {
                            "p256dh": subscription["p256dh"],
                            "auth": subscription["auth"],
                        },
                    },
                    data=data,
                    vapid_private_key=self.vapid_private_key,
                    vapid_claims={"sub": self.vapid_subject},
                )
            except Exception as error:  # pywebpush 예외 타입은 선택 의존성에 묶이지 않는다.
                if _status_code(error) in {404, 410}:
                    invalid.append(endpoint)
                else:
                    failed.append(endpoint)
                continue
            sent += 1
        if sent:
            return SendResult(
                succeeded=True,
                invalid_endpoints=tuple(invalid),
                failed_endpoints=tuple(failed),
            )
        return SendResult(
            succeeded=False,
            error_message="모든 Web Push 전송이 실패했습니다.",
            invalid_endpoints=tuple(invalid),
            failed_endpoints=tuple(failed),
        )


def _send_web_push(**kwargs: Any) -> object:
    """런타임에만 pywebpush를 import해 단위 테스트 의존을 분리한다."""
    from pywebpush import webpush

    return webpush(**kwargs)


def _status_code(error: Exception) -> int | None:
    response = getattr(error, "response", None)
    status_code = getattr(response, "status_code", None)
    return status_code if isinstance(status_code, int) else None
