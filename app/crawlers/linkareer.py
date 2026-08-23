"""링커리어 SSR 목록 HTML 크롤러."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from html import unescape
from typing import ClassVar
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.crawlers.base import BaseCrawler, RawJob, RawPage
from app.crawlers.http import decode_html
from app.crawlers.registry import register_crawler

_ACTIVITY_ID_PATTERN = re.compile(r"/activity/(\d+)(?:$|[/?#])")
_NON_RECRUITMENT_TERMS = (
    "서포터즈",
    "홍보단",
    "자원봉사",
    "대외활동",
    "공모전",
    "국민평가단",
    "기획단",
    "동아리",
)


@register_crawler("linkareer")
class LinkareerCrawler(BaseCrawler):
    """목록 페이지의 JSON-LD ItemList를 읽어 가볍게 공고를 수집한다."""

    strategy = "html"
    _LIST_PATH = "/list/recruit"
    _LIST_PARAMS: ClassVar[dict[str, str | int]] = {
        "filterBy_activityTypeID": 5,
        "filterBy_status": "OPEN",
        "orderBy_direction": "DESC",
        "orderBy_field": "RECENT",
        "page": 1,
    }

    def fetch(self) -> Iterator[RawPage]:
        url = f"{self.source.base_url.rstrip('/')}{self._LIST_PATH}"
        cache = self.config.setdefault("_http_cache", {})
        cached = cache.get(url, {})
        page = self.http.get(
            url,
            params=self._LIST_PARAMS,
            etag=cached.get("etag"),
            last_modified=cached.get("last_modified"),
        )
        if page is None:
            return

        cache[url] = {
            "etag": page.headers.get("etag"),
            "last_modified": page.headers.get("last-modified"),
        }
        yield page

    def parse(self, page: RawPage) -> list[RawJob]:
        soup = BeautifulSoup(decode_html(page.body), "lxml")
        apollo_state = _load_apollo_state(soup)
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            payload = _load_json(script.get_text())
            if not isinstance(payload, dict) or payload.get("@type") != "ItemList":
                continue
            return _parse_item_list(payload, self.source.base_url, apollo_state)
        return []


def _load_json(value: str) -> object | None:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _load_apollo_state(soup: BeautifulSoup) -> dict[str, object]:
    """SSR 초기 상태에서 목록에 표시된 기업·마감일·직무 정보를 읽는다."""
    script = soup.find("script", id="__NEXT_DATA__")
    if script is None:
        return {}
    payload = _load_json(script.get_text())
    if not isinstance(payload, dict):
        return {}
    props = payload.get("props")
    if not isinstance(props, dict):
        return {}
    page_props = props.get("pageProps")
    if not isinstance(page_props, dict):
        return {}
    state = page_props.get("__APOLLO_STATE__")
    return state if isinstance(state, dict) else {}


def _parse_item_list(
    payload: dict[str, object], base_url: str, apollo_state: dict[str, object]
) -> list[RawJob]:
    elements = payload.get("itemListElement")
    if not isinstance(elements, list):
        return []

    items: list[RawJob] = []
    for element in elements:
        if not isinstance(element, dict):
            continue
        title = element.get("name")
        raw_url = element.get("url")
        if not isinstance(title, str) or not isinstance(raw_url, str):
            continue
        title = unescape(title).strip()
        if _is_non_recruitment(title):
            continue
        url = urljoin(base_url, raw_url)
        activity_id = _ACTIVITY_ID_PATTERN.search(url)
        activity = _activity_data(apollo_state, activity_id.group(1) if activity_id else None)
        items.append(
            RawJob(
                url=url,
                title=title,
                external_id=activity_id.group(1) if activity_id else None,
                employment_type=_employment_type(activity.get("jobTypes")),
                deadline_at=_deadline_at(activity.get("recruitCloseAt")),
                raw={
                    "position": element.get("position"),
                    "image": element.get("image"),
                    "job_types": activity.get("jobTypes"),
                    "recruit_type": activity.get("recruitType"),
                },
            )
        )
    return items


def _is_non_recruitment(title: str) -> bool:
    """채용 목록에 섞인 활동·서포터즈 성격의 항목을 방어적으로 제외한다."""
    normalized = title.casefold()
    return any(term in normalized for term in _NON_RECRUITMENT_TERMS)


def _activity_data(state: dict[str, object], activity_id: str | None) -> dict[str, object]:
    value = state.get(f"Activity:{activity_id}") if activity_id else None
    return value if isinstance(value, dict) else {}


def _employment_type(value: object) -> str | None:
    if not isinstance(value, list):
        return None
    labels = {"NEW": "신입", "INTERN": "인턴", "CONTRACT": "계약직"}
    names = [labels[item] for item in value if isinstance(item, str) and item in labels]
    return ", ".join(names) or None


def _deadline_at(value: object) -> datetime | None:
    if not isinstance(value, int) or value <= 0:
        return None
    return datetime.fromtimestamp(value / 1_000, tz=UTC)
