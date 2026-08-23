"""카카오톡 나에게 보내기 기본 list 템플릿 채널."""

from __future__ import annotations

import json

import httpx

from app.models import NotificationChannel
from app.notifications.contracts import NotificationPayload, SendResult

_SEND_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"


class KakaoChannel:
    """전달받은 access token으로만 카카오 API를 호출하는 DB-독립 채널."""

    name = NotificationChannel.KAKAO

    def __init__(self, *, access_token: str, client: httpx.Client | None = None) -> None:
        self.access_token = access_token
        self.client = client or httpx.Client(timeout=10)
        self._owns_client = client is None

    def send(self, payload: NotificationPayload) -> SendResult:
        """상위 세 공고를 포함한 기본 list 템플릿을 나에게 보낸다."""
        try:
            response = self.client.post(
                _SEND_URL,
                headers={"Authorization": f"Bearer {self.access_token}"},
                data={
                    "template_object": json.dumps(_message_template(payload), ensure_ascii=False)
                },
            )
            response.raise_for_status()
            if response.json().get("result_code") != 0:
                return SendResult(
                    succeeded=False, error_message="카카오 API가 발송을 거절했습니다."
                )
            return SendResult(succeeded=True)
        except (httpx.HTTPError, ValueError) as error:
            return SendResult(succeeded=False, error_message=str(error)[:1_000])
        finally:
            if self._owns_client:
                self.client.close()


def _message_template(payload: NotificationPayload) -> dict[str, object]:
    """항목 수에 맞춰 카카오 기본 템플릿을 고른다.

    카카오 list 템플릿은 콘텐츠를 최소 두 건 요구한다. 한 건짜리 신규 공고는
    텍스트 템플릿으로 보내야 실제 운영에서 조용히 발송이 거절되지 않는다.
    """
    if len(payload.items) < 2:
        return _text_template(payload)
    return _list_template(payload)


def _list_template(payload: NotificationPayload) -> dict[str, object]:
    """카카오 기본 list 템플릿의 최대 세 항목을 만든다."""
    contents = [
        {
            "title": item.title,
            "description": _item_description(item.source_name, item.deadline, item.keywords),
            "link": {"web_url": item.url, "mobile_web_url": item.url},
        }
        for item in payload.items[:3]
    ]
    return {
        "object_type": "list",
        "header_title": payload.title,
        "header_link": {"web_url": payload.url, "mobile_web_url": payload.url},
        "contents": contents,
        "buttons": [
            {
                "title": "전체 보기",
                "link": {"web_url": payload.url, "mobile_web_url": payload.url},
            }
        ],
    }


def _text_template(payload: NotificationPayload) -> dict[str, object]:
    """단건 공고를 카카오 텍스트 템플릿으로 만든다."""
    item = payload.items[0] if payload.items else None
    text_parts = [payload.title, payload.body]
    if item is not None:
        text_parts.append(_item_description(item.source_name, item.deadline, item.keywords))
    text = "\n".join(part for part in text_parts if part).strip()[:200]
    return {
        "object_type": "text",
        "text": text,
        "link": {"web_url": payload.url, "mobile_web_url": payload.url},
        "button_title": "공고 보기",
    }


def _item_description(source_name: str, deadline: str | None, keywords: tuple[str, ...]) -> str:
    """카카오 목록의 짧은 설명을 빈 값 없이 조립한다."""
    parts = [source_name]
    if deadline:
        parts.append(f"~{deadline} 마감")
    if keywords:
        parts.append(f"키워드: {', '.join(keywords)}")
    return " · ".join(parts)
