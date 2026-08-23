"""M3 단발 크롤 CLI의 공통 반환 계약 검증."""

from pathlib import Path

from app.cli import crawl_once
from app.core.config import Settings
from app.crawlers.base import RawPage


class FixtureHttp:
    def get(self, url: str, **_: object) -> RawPage:
        return RawPage(
            url=url,
            body=(
                Path(__file__).parents[1]
                / "fixtures"
                / "linkareer"
                / "recruit_list_2026-08-23.html"
            ).read_bytes(),
            status_code=200,
            headers={},
        )


class DataGoKrFixtureHttp:
    def get(self, url: str, **_: object) -> RawPage:
        return RawPage(
            url=url,
            body=(
                Path(__file__).parents[1]
                / "fixtures"
                / "datagokr_msit"
                / "recruit_list_contract.json"
            ).read_bytes(),
            status_code=200,
            headers={},
        )


def test_crawl_once는_소스와_무관하게_raw_job_목록을_반환한다() -> None:
    settings = Settings(
        _env_file=None,
        APP_BASE_URL="https://example.com",
        SECRET_KEY="test-secret",
    )

    result = crawl_once("linkareer", settings, http=FixtureHttp())

    assert len(result.items) == 2
    assert result.items[0].title == "GenOS AI Engineer (전환형 인턴)"


def test_공공데이터포털_수집도_raw_job_목록을_반환한다() -> None:
    settings = Settings(
        _env_file=None,
        APP_BASE_URL="https://example.com",
        SECRET_KEY="test-secret",
        MSIT_RECRUITMENT_SERVICE_KEY="msit-key",
    )

    result = crawl_once("datagokr-msit-recruitment", settings, http=DataGoKrFixtureHttp())

    assert len(result.items) == 2
    assert result.items[0].external_id == (
        "https://www.msit.go.kr/bbs/view.do?sCode=user&mId=125&mPid=121&bbsSeqNo=98&nttSeqNo=3186431"
    )
