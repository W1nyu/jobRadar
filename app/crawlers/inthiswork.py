"""인디스워크의 공개 WordPress 채용 분류 API 크롤러."""

from __future__ import annotations

import json
from collections.abc import Iterator, Mapping
from datetime import datetime
from html import unescape

from bs4 import BeautifulSoup

from app.crawlers.base import BaseCrawler, RawJob, RawPage
from app.crawlers.errors import CrawlSchemaError
from app.crawlers.registry import register_crawler


class InThisWorkApiError(CrawlSchemaError):
    """인디스워크 WordPress API 응답이 계약과 다를 때 발생한다."""


@register_crawler("inthiswork")
class InThisWorkCrawler(BaseCrawler):
    """신입·주니어경력 WordPress 분류의 게시글만 RawJob으로 변환한다."""

    strategy = "json"
    _POSTS_PATH = "/wp-json/wp/v2/posts"
    _DEFAULT_CATEGORIES = (191700167, 191700168)

    def fetch(self) -> Iterator[RawPage]:
        categories = _category_ids(self.config.get("categories", self._DEFAULT_CATEGORIES))
        page = self.http.get(
            f"{self.source.base_url.rstrip('/')}{self._POSTS_PATH}",
            params={
                "categories": ",".join(str(category) for category in categories),
                "per_page": _bounded_positive_int(self.config.get("display", 20), maximum=100),
                "_fields": "id,date,link,title,content,excerpt,categories",
            },
        )
        if page is not None:
            yield page

    def parse(self, page: RawPage) -> list[RawJob]:
        try:
            records = json.loads(page.body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise InThisWorkApiError(
                "인디스워크 채용 API 응답이 올바른 JSON이 아닙니다."
            ) from error
        if not isinstance(records, list):
            raise InThisWorkApiError("인디스워크 채용 API 목록 형식이 올바르지 않습니다.")

        items: list[RawJob] = []
        for record in records:
            if not isinstance(record, Mapping):
                continue
            identifier = _text(record.get("id"))
            url = _text(record.get("link"))
            title = _rendered_text(record.get("title"))
            if identifier is None or url is None or title is None:
                continue
            items.append(
                RawJob(
                    external_id=identifier,
                    url=url,
                    title=title,
                    company=_company_from_title(title),
                    description=_rendered_text(record.get("content"))
                    or _rendered_text(record.get("excerpt")),
                    posted_at=_parse_datetime(_text(record.get("date"))),
                    raw={"categories": record.get("categories", [])},
                )
            )
        return items


def _category_ids(value: object) -> tuple[int, ...]:
    if not isinstance(value, (list, tuple)):
        raise InThisWorkApiError("인디스워크 categories 설정은 정수 목록이어야 합니다.")
    categories: list[int] = []
    for item in value:
        try:
            category = int(item)
        except (TypeError, ValueError) as error:
            raise InThisWorkApiError(
                "인디스워크 categories 설정은 정수 목록이어야 합니다."
            ) from error
        if category > 0:
            categories.append(category)
    if not categories:
        raise InThisWorkApiError("인디스워크 categories 설정이 비어 있습니다.")
    return tuple(categories)


def _bounded_positive_int(value: object, *, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError) as error:
        raise InThisWorkApiError("인디스워크 페이지 설정은 정수여야 합니다.") from error
    return min(max(number, 1), maximum)


def _text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _rendered_text(value: object) -> str | None:
    if not isinstance(value, Mapping):
        return None
    rendered = _text(value.get("rendered"))
    if rendered is None:
        return None
    text = BeautifulSoup(unescape(rendered), "lxml").get_text(" ", strip=True)
    return text or None


def _company_from_title(title: str) -> str | None:
    company, separator, _ = title.partition("｜")
    return company.strip() if separator and company.strip() else None


def _parse_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None
