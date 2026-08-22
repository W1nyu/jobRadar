"""금융투자협회 회원사 채용안내 HTML 크롤러."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import datetime
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup

from app.crawlers.base import BaseCrawler, RawJob, RawPage
from app.crawlers.http import decode_html
from app.crawlers.registry import register_crawler


@register_crawler("kofia")
class KofiaCrawler(BaseCrawler):
    """공식 회원사 채용안내 목록의 표 행을 RawJob으로 변환한다."""

    strategy = "html"
    _LIST_PATH = "/brd/m_96/list.do"

    def fetch(self) -> Iterator[RawPage]:
        page = self.http.get(f"{self.source.base_url.rstrip('/')}{self._LIST_PATH}")
        if page is not None:
            yield page

    def parse(self, page: RawPage) -> list[RawJob]:
        soup = BeautifulSoup(decode_html(page.body), "lxml")
        table = _find_recruitment_table(soup)
        if table is None:
            return []

        items: list[RawJob] = []
        for row in table.select("tbody > tr"):
            cells = row.find_all("td", recursive=False)
            if len(cells) < 5:
                continue
            link = cells[2].find("a", href=True)
            if link is None:
                continue
            raw_url = urljoin(page.url, str(link["href"]))
            external_id = _sequence_from_url(raw_url)
            title = cells[2].get_text(" ", strip=True)
            company = cells[1].get_text(" ", strip=True)
            if external_id is None or not title or not company:
                continue
            url = f"{self.source.base_url.rstrip('/')}/brd/m_96/view.do?seq={external_id}"
            items.append(
                RawJob(
                    external_id=external_id,
                    url=url,
                    title=title,
                    company=company,
                    posted_at=_parse_date(cells[-1].get_text(" ", strip=True)),
                    raw={"board_number": cells[0].get_text(" ", strip=True)},
                )
            )
        return items


def _find_recruitment_table(soup: BeautifulSoup):
    for table in soup.find_all("table"):
        caption = table.find("caption")
        if caption is not None and "회원사 채용안내" in caption.get_text(" ", strip=True):
            return table
    return None


def _sequence_from_url(url: str) -> str | None:
    values = parse_qs(urlparse(url).query).get("seq")
    return values[0] if values else None


def _parse_date(value: str) -> datetime | None:
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None
