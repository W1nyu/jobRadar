"""잡알리오 공개 채용목록 JSON 크롤러."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from datetime import datetime
from typing import Any

from app.crawlers.base import BaseCrawler, RawJob, RawPage
from app.crawlers.errors import CrawlSchemaError
from app.crawlers.registry import register_crawler


class AlioApiError(CrawlSchemaError):
    """잡알리오 공개 목록 응답이 계약과 다를 때 발생한다."""


@register_crawler("alio-recruitment")
class AlioCrawler(BaseCrawler):
    """잡알리오 채용정보 조회 화면이 사용하는 공개 JSON 목록을 변환한다."""

    strategy = "json"
    _LIST_PATH = "/new/odaApiMng/recrutInquiryAjaxList.do"

    def fetch(self) -> Iterator[RawPage]:
        page = self.http.get(
            f"{self.source.base_url.rstrip('/')}{self._LIST_PATH}",
            params={
                "pageNo": _bounded_positive_int(self.config.get("start_page", 1), maximum=1_000),
                "numOfRows": _bounded_positive_int(self.config.get("display", 20), maximum=100),
                "ongoingYn": "Y" if self.config.get("ongoing_only", True) else "",
            },
        )
        if page is not None:
            yield page

    def parse(self, page: RawPage) -> list[RawJob]:
        try:
            payload = json.loads(page.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise AlioApiError("잡알리오 채용목록 응답이 올바른 JSON이 아닙니다.") from error

        records = _records(payload)
        items: list[RawJob] = []
        for record in records:
            identifier = _text(record.get("recrutPblntSn"))
            title = _text(record.get("recrutPbancTtl"))
            url = _text(record.get("srcUrl"))
            if identifier is None or title is None or url is None:
                continue
            items.append(
                RawJob(
                    external_id=identifier,
                    url=url,
                    title=title,
                    company=_text(record.get("instNm")),
                    location=_text(record.get("workRgnNmLst")),
                    employment_type=_text(record.get("hireTypeNmLst")),
                    experience_level=_text(record.get("recrutSeNm")),
                    description=_text(record.get("aplyQlfcCn")),
                    posted_at=_parse_date(_text(record.get("pbancBgngYmd"))),
                    deadline_at=_parse_date(_text(record.get("pbancEndYmd"))),
                    raw=dict(record),
                )
            )
        return items


def _records(payload: object) -> list[Mapping[str, Any]]:
    if not isinstance(payload, Mapping):
        raise AlioApiError("잡알리오 채용목록 최상위 객체가 올바르지 않습니다.")
    data = payload.get("data")
    if not isinstance(data, Mapping):
        raise AlioApiError("잡알리오 채용목록에 data 객체가 없습니다.")
    result = data.get("result", [])
    if not isinstance(result, list):
        raise AlioApiError("잡알리오 채용목록 result 형식이 올바르지 않습니다.")
    return [record for record in result if isinstance(record, Mapping)]


def _bounded_positive_int(value: object, *, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise AlioApiError("잡알리오 페이지 설정은 정수여야 합니다.") from error
    return min(max(number, 1), maximum)


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _parse_date(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.strptime(value, "%Y%m%d")
    except ValueError:
        return None
