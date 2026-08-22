"""공공데이터포털 과학기술정보통신부 모집채용 API 크롤러."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from datetime import datetime
from typing import Any
from urllib.parse import unquote

from app.crawlers.base import BaseCrawler, RawJob, RawPage
from app.crawlers.registry import register_crawler


class DataGoKrMsitApiError(ValueError):
    """공공데이터포털 모집채용 API가 정상 응답을 반환하지 않은 경우."""


@register_crawler("datagokr-msit-recruitment")
class DataGoKrMsitCrawler(BaseCrawler):
    """과기정통부와 산하기관의 모집채용 JSON을 RawJob 계약으로 변환한다."""

    strategy = "api"
    _LIST_PATH = "/1721000/msitrecruitinfo/recruitList"

    def fetch(self) -> Iterator[RawPage]:
        service_key = self.config.get("service_key")
        if not isinstance(service_key, str) or not service_key.strip():
            raise DataGoKrMsitApiError("공공데이터포털 서비스키가 설정되지 않았습니다.")

        page = self.http.get(
            f"{self.source.base_url.rstrip('/')}{self._LIST_PATH}",
            params={
                "ServiceKey": unquote(service_key),
                "pageNo": _bounded_positive_int(self.config.get("start_page", 1), maximum=1_000),
                "numOfRows": _bounded_positive_int(self.config.get("display", 20), maximum=100),
                "returnType": "json",
            },
        )
        if page is not None:
            yield page

    def parse(self, page: RawPage) -> list[RawJob]:
        try:
            payload = json.loads(page.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise DataGoKrMsitApiError(
                "공공데이터포털 모집채용 응답이 올바른 JSON이 아닙니다."
            ) from error

        gateway_error = _optional_mapping(payload, "OpenAPI_ServiceResponse")
        if gateway_error is not None:
            header = _mapping(gateway_error, "cmmMsgHeader")
            code = _optional_text(header.get("returnReasonCode")) or "알 수 없음"
            message = _optional_text(header.get("errMsg")) or "알 수 없는 오류"
            raise DataGoKrMsitApiError(f"공공데이터포털 API 오류 코드 {code}: {message}")

        header, body = _response_parts(payload)
        result_code = _optional_text(header.get("resultCode"))
        if result_code != "00":
            message = _optional_text(header.get("resultMsg")) or "알 수 없는 오류"
            raise DataGoKrMsitApiError(f"공공데이터포털 API 오류 코드 {result_code}: {message}")

        items_container = body.get("items", [])
        if isinstance(items_container, Mapping):
            records = items_container.get("item", [])
        else:
            records = items_container
        if isinstance(records, Mapping):
            records = [records]
        if not isinstance(records, list):
            raise DataGoKrMsitApiError("공공데이터포털 모집채용 목록 형식이 올바르지 않습니다.")

        items: list[RawJob] = []
        for record in records:
            if not isinstance(record, Mapping):
                continue
            nested_item = record.get("item")
            if isinstance(nested_item, Mapping):
                record = nested_item
            title = _optional_text(record.get("subject"))
            url = _optional_text(record.get("viewUrl"))
            if title is None or url is None:
                continue
            items.append(
                RawJob(
                    url=url,
                    title=title,
                    external_id=url,
                    company=_optional_text(record.get("deptName")),
                    description=_first_file_name(record),
                    posted_at=_parse_date(_optional_text(record.get("pressDt"))),
                    raw=dict(record),
                )
            )
        return items


def _response_parts(payload: object) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    if not isinstance(payload, Mapping):
        raise DataGoKrMsitApiError("공공데이터포털 모집채용 응답 최상위 객체가 올바르지 않습니다.")

    response = payload.get("response")
    if isinstance(response, Mapping):
        return _mapping(response, "header"), _mapping(response, "body")
    if isinstance(response, list):
        return _section_mapping(response, "header"), _section_mapping(response, "body")
    raise DataGoKrMsitApiError("공공데이터포털 모집채용 응답에 response 객체가 없습니다.")


def _section_mapping(sections: list[object], name: str) -> Mapping[str, Any]:
    for section in sections:
        value = _optional_mapping(section, name)
        if value is not None:
            return value
    raise DataGoKrMsitApiError(f"공공데이터포털 모집채용 응답에 {name} 객체가 없습니다.")


def _mapping(parent: object, name: str) -> Mapping[str, Any]:
    value = _optional_mapping(parent, name)
    if value is None:
        raise DataGoKrMsitApiError(f"공공데이터포털 모집채용 응답에 {name} 객체가 없습니다.")
    return value


def _optional_mapping(parent: object, name: str) -> Mapping[str, Any] | None:
    if not isinstance(parent, Mapping):
        return None
    value = parent.get(name)
    if not isinstance(value, Mapping):
        return None
    return value


def _optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _first_file_name(record: Mapping[str, Any]) -> str | None:
    direct_name = _optional_text(record.get("fileName"))
    if direct_name is not None:
        return direct_name

    files = record.get("files")
    if isinstance(files, Mapping):
        files = [files]
    if not isinstance(files, list):
        return None
    for entry in files:
        if not isinstance(entry, Mapping):
            continue
        file_info = entry.get("file")
        if isinstance(file_info, Mapping):
            name = _optional_text(file_info.get("fileName"))
            if name is not None:
                return name
    return None


def _parse_date(value: str | None) -> datetime | None:
    if value is None:
        return None
    for format_ in ("%Y-%m-%d", "%Y%m%d", "%Y.%m.%d"):
        try:
            return datetime.strptime(value, format_)
        except ValueError:
            pass
    return None


def _bounded_positive_int(value: object, *, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError("공공데이터포털 페이지 설정은 정수여야 합니다.") from error
    return min(max(number, 1), maximum)
