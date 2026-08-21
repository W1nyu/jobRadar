"""운영용 CLI.

    uv run python -m app.cli check-keys

M3 이후 `crawl <slug>` 등이 여기에 추가된다.
"""

import argparse
import sys
from dataclasses import dataclass

from app.core.config import Settings, get_settings


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
            needed_by="M3",
            note="공공데이터포털 (워크넷·잡알리오) · 자동 승인",
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


def main(argv: list[str] | None = None) -> int:
    _force_utf8_stdout()
    parser = argparse.ArgumentParser(prog="app.cli", description="jobRadar 운영 CLI")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check-keys", help="외부 API 키 설정 상태를 출력한다")

    args = parser.parse_args(argv)
    if args.command == "check-keys":
        return _print_key_report(get_settings())
    return 1


if __name__ == "__main__":
    sys.exit(main())
