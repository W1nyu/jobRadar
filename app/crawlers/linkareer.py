"""링커리어 SSR 목록 HTML 크롤러."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from html import unescape
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from app.crawlers.base import BaseCrawler, RawJob, RawPage
from app.crawlers.http import decode_html
from app.crawlers.registry import register_crawler

_ACTIVITY_ID_PATTERN = re.compile(r"/activity/(\d+)(?:$|[/?#])")


@register_crawler("linkareer")
class LinkareerCrawler(BaseCrawler):
    """목록 페이지의 JSON-LD ItemList를 읽어 가볍게 공고를 수집한다."""

    strategy = "html"
    _LIST_PATH = "/list/activity"

    def fetch(self) -> Iterator[RawPage]:
        url = f"{self.source.base_url.rstrip('/')}{self._LIST_PATH}"
        cache = self.config.setdefault("_http_cache", {})
        cached = cache.get(url, {})
        page = self.http.get(
            url,
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
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            payload = _load_json(script.get_text())
            if not isinstance(payload, dict) or payload.get("@type") != "ItemList":
                continue
            return _parse_item_list(payload, self.source.base_url)
        return []


def _load_json(value: str) -> object | None:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return None


def _parse_item_list(payload: dict[str, object], base_url: str) -> list[RawJob]:
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
        url = urljoin(base_url, raw_url)
        activity_id = _ACTIVITY_ID_PATTERN.search(url)
        items.append(
            RawJob(
                url=url,
                title=unescape(title).strip(),
                external_id=activity_id.group(1) if activity_id else None,
                raw={
                    "position": element.get("position"),
                    "image": element.get("image"),
                },
            )
        )
    return items
