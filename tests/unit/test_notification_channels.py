"""M9 DB-독립 알림 채널의 전송 계약."""

from __future__ import annotations

import json
from urllib.parse import parse_qs

import httpx
import respx

from app.notifications.contracts import NotificationItem, NotificationPayload
from app.notifications.kakao import KakaoChannel
from app.notifications.webpush import WebPushChannel


def _payload() -> NotificationPayload:
    return NotificationPayload(
        title="새 채용공고 5건",
        body="데이터 분석가 외 4건",
        url="https://example.com/admin/jobs?matched=true",
        items=(
            NotificationItem(
                posting_id=1,
                title="데이터 분석가",
                source_name="링커리어",
                url="https://example.com/jobs/1",
                keywords=("데이터", "신입"),
            ),
            NotificationItem(
                posting_id=2,
                title="AI 인턴",
                source_name="잡알리오",
                url="https://example.com/jobs/2",
                keywords=("AI",),
            ),
        ),
    )


@respx.mock
def test_카카오_채널은_나에게_보내기_list_템플릿을_전송한다() -> None:
    route = respx.post("https://kapi.kakao.com/v2/api/talk/memo/default/send").mock(
        return_value=httpx.Response(200, json={"result_code": 0})
    )
    channel = KakaoChannel(access_token="test-access-token")

    result = channel.send(_payload())

    assert result.succeeded is True
    assert route.called is True
    request = route.calls.last.request
    assert request.headers["Authorization"] == "Bearer test-access-token"
    template = json.loads(parse_qs(request.content.decode())["template_object"][0])
    assert template["object_type"] == "list"
    assert template["header_title"] == "새 채용공고 5건"
    assert template["contents"][0]["title"] == "데이터 분석가"


@respx.mock
def test_카카오_채널은_단건을_텍스트_템플릿으로_전송한다() -> None:
    """카카오 list 템플릿은 콘텐츠를 두 건 이상 요구한다."""
    route = respx.post("https://kapi.kakao.com/v2/api/talk/memo/default/send").mock(
        return_value=httpx.Response(200, json={"result_code": 0})
    )
    payload = _payload()
    single_payload = NotificationPayload(
        title="새 채용공고 1건",
        body="데이터 분석가",
        url=payload.url,
        items=payload.items[:1],
    )

    result = KakaoChannel(access_token="test-access-token").send(single_payload)

    assert result.succeeded is True
    template = json.loads(parse_qs(route.calls.last.request.content.decode())["template_object"][0])
    assert template["object_type"] == "text"
    assert "데이터 분석가" in template["text"]
    assert template["link"]["web_url"] == single_payload.url


def test_웹푸시_410_응답은_구독_비활성화_대상으로_반환한다() -> None:
    def rejected_push(**_: object) -> None:
        raise _PushError(status_code=410)

    channel = WebPushChannel(
        subscriptions=(
            {"endpoint": "https://push.example/expired", "p256dh": "key", "auth": "auth"},
        ),
        vapid_private_key="private-key",
        vapid_subject="mailto:admin@example.com",
        push_sender=rejected_push,
    )

    result = channel.send(_payload())

    assert result.succeeded is False
    assert result.invalid_endpoints == ("https://push.example/expired",)


def test_웹푸시_채널은_표준_keys_중첩_구독형태로_발송한다() -> None:
    sent_subscriptions: list[dict[str, object]] = []

    def accepted_push(**kwargs: object) -> None:
        sent_subscriptions.append(kwargs["subscription_info"])  # type: ignore[arg-type]

    channel = WebPushChannel(
        subscriptions=(
            {"endpoint": "https://push.example/active", "p256dh": "key", "auth": "auth"},
        ),
        vapid_private_key="private-key",
        vapid_subject="mailto:admin@example.com",
        push_sender=accepted_push,
    )

    result = channel.send(_payload())

    assert result.succeeded is True
    assert sent_subscriptions == [
        {
            "endpoint": "https://push.example/active",
            "keys": {"p256dh": "key", "auth": "auth"},
        }
    ]


class _Response:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _PushError(Exception):
    def __init__(self, *, status_code: int) -> None:
        self.response = _Response(status_code)
