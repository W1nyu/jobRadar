"""운영용 CLI.

    uv run python -m app.cli check-keys

M3 이후 `crawl <slug>` 등이 여기에 추가된다.
"""

import argparse
import sys
from base64 import urlsafe_b64encode
from dataclasses import dataclass
from typing import TYPE_CHECKING

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from app.core.config import Settings, get_settings
from app.crawlers import CrawlResult, get_crawler
from app.crawlers.http import HttpClient
from app.crawlers.sources import build_builtin_source
from app.source_catalog import BUILTIN_SOURCE_DEFINITIONS

if TYPE_CHECKING:
    from app.crawlers.base import CrawlSource


@dataclass(frozen=True)
class KeyStatus:
    """외부 API 키 하나의 설정 상태.

    키 값 자체는 담지 않는다. 이 객체는 터미널에 출력되고 로그에 남을 수 있다.
    """

    name: str
    configured: bool
    needed_by: str
    note: str


def key_statuses(settings: Settings) -> list[KeyStatus]:
    return [
        KeyStatus(
            name="DATA_GO_KR_SERVICE_KEY",
            configured=settings.data_go_kr_enabled,
            needed_by="M7",
            note="공공데이터포털 공용 키 · 잡알리오 등 확장 소스용",
        ),
        KeyStatus(
            name="MSIT_RECRUITMENT_SERVICE_KEY",
            configured=settings.msit_recruitment_enabled,
            needed_by="M3",
            note="과기정통부 모집채용 API 전용 키",
        ),
        KeyStatus(
            name="WORK24_SERVICE_KEY",
            configured=settings.work24_enabled,
            needed_by="M7",
            note="고용24 채용정보 API의 authKey · 개인회원 키는 현재 보류",
        ),
        KeyStatus(
            name="ALIO_SERVICE_KEY",
            configured=settings.alio_enabled,
            needed_by="M7",
            note="잡알리오 공공기관 채용정보 · 별도 활용신청",
        ),
        KeyStatus(
            name="SARAMIN_ACCESS_KEY",
            configured=settings.saramin_enabled,
            needed_by="M7",
            note="사람인 채용정보 API · 승인 절차 필요",
        ),
    ]


def _print_key_report(settings: Settings) -> int:
    print("외부 API 키 상태\n")
    for status in key_statuses(settings):
        mark = "설정됨  " if status.configured else "미설정  "
        print(f"  [{mark}] {status.name}")
        print(f"              필요 시점: {status.needed_by} · {status.note}")
    print("\n미설정 키는 해당 소스만 비활성화되며, 앱 기동에는 영향이 없다.")
    return 0


def _force_utf8_stdout() -> None:
    """Windows 콘솔의 기본 코드페이지(cp949)에서 한글 출력이 깨지는 것을 막는다.

    운영 환경(Linux)은 이미 UTF-8이라 무해하다. 개발 장비가 Windows일 때만 의미가 있다.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8")


def crawl_once(
    slug: str, settings: Settings, *, http: HttpClient | object | None = None
) -> CrawlResult:
    """M3 소스를 한 번 수집하고, DB와 무관한 RawJob 결과를 반환한다."""
    source: CrawlSource = build_builtin_source(slug, settings)
    owns_http = http is None
    client = http or HttpClient(
        rate_limit_per_min=source.rate_limit_per_min,
        user_agent=settings.crawl_user_agent,
        max_response_bytes=settings.crawl_max_response_bytes,
    )
    try:
        return get_crawler(source, client).run()  # type: ignore[arg-type]
    finally:
        if owns_http:
            client.close()  # type: ignore[union-attr]


def _print_crawl_result(result: CrawlResult) -> int:
    """단발 수집 결과를 사람이 확인할 수 있는 짧은 목록으로 출력한다."""
    for item in result.items:
        print(f"- {item.title}\n  {item.url}")
    print(f"\n수집 결과: {len(result.items)}건 / 페이지 {result.pages_fetched}개")
    if result.errors:
        print("오류:", *result.errors, sep="\n- ", file=sys.stderr)
        return 2
    return 0


def generate_vapid_keys() -> tuple[str, str]:
    """Web Push 표준 P-256 VAPID 공개·비밀 키를 URL-safe Base64로 만든다."""
    private_key = ec.generate_private_key(ec.SECP256R1())
    private_value = private_key.private_numbers().private_value.to_bytes(32, "big")
    public_value = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.X962,
        format=serialization.PublicFormat.UncompressedPoint,
    )
    return _urlsafe_b64(public_value), _urlsafe_b64(private_value)


def _urlsafe_b64(value: bytes) -> str:
    """`.env` 한 줄에 저장할 수 있도록 padding 없는 Base64URL로 인코딩한다."""
    return urlsafe_b64encode(value).decode().rstrip("=")


def _print_vapid_keys() -> int:
    """사용자가 `.env`에 직접 복사할 VAPID 키 쌍을 한 번만 출력한다."""
    public_key, private_key = generate_vapid_keys()
    print("VAPID_PUBLIC_KEY=" + public_key)
    print("VAPID_PRIVATE_KEY=" + private_key)
    return 0


def generate_fernet_key() -> str:
    """카카오 OAuth 토큰 암호화용 Fernet 키를 새로 만든다."""
    return Fernet.generate_key().decode()


def _print_fernet_key() -> int:
    """사용자가 `.env`에 직접 복사할 Fernet 키를 한 번만 출력한다."""
    print("FERNET_KEY=" + generate_fernet_key())
    return 0


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdout()
    parser = argparse.ArgumentParser(prog="app.cli", description="jobRadar 운영 CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check-keys", help="외부 API 키 설정 상태를 출력한다")
    sub.add_parser("generate-vapid", help="M9 Web Push VAPID 키 쌍을 생성한다")
    sub.add_parser("generate-fernet", help="M9 카카오 토큰 암호화용 Fernet 키를 생성한다")
    crawl_parser = sub.add_parser("crawl", help="등록 소스를 한 번 수집한다")
    crawl_parser.add_argument(
        "slug", choices=tuple(definition.slug for definition in BUILTIN_SOURCE_DEFINITIONS)
    )

    args = parser.parse_args(argv)
    if args.command == "check-keys":
        return _print_key_report(get_settings())
    if args.command == "generate-vapid":
        return _print_vapid_keys()
    if args.command == "generate-fernet":
        return _print_fernet_key()
    if args.command == "crawl":
        try:
            return _print_crawl_result(crawl_once(args.slug, get_settings()))
        except (LookupError, ValueError) as error:
            print(f"수집을 시작할 수 없습니다: {error}", file=sys.stderr)
            return 2
    return 1


if __name__ == "__main__":
    sys.exit(main())
