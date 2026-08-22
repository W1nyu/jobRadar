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
                data={"template_object": json.dumps(_list_template(payload), ensure_ascii=False)},
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


def _item_description(source_name: str, deadline: str | None, keywords: tuple[str, ...]) -> str:
    """카카오 목록의 짧은 설명을 빈 값 없이 조립한다."""
    parts = [source_name]
    if deadline:
        parts.append(f"~{deadline} 마감")
    if keywords:
        parts.append(f"키워드: {', '.join(keywords)}")
    return " · ".join(parts)
