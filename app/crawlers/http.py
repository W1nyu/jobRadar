"""크롤러가 공통으로 사용하는 동기 HTTP 클라이언트."""

from __future__ import annotations

import threading
import time
from collections.abc import Mapping

import httpx
from charset_normalizer import from_bytes
from tenacity import (
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_none,
    wait_random_exponential,
)

from app.crawlers.base import RawPage

MAX_RESPONSE_BYTES = 5 * 1024 * 1024


class HttpClientError(RuntimeError):
    """수집 정책을 지키지 못한 HTTP 요청 오류."""


class HttpStatusError(HttpClientError):
    """재시도하지 않는 HTTP 상태 코드 오류."""


class ResponseTooLargeError(HttpClientError):
    """응답이 메모리 예산 상한을 넘은 경우."""


class _RetryableHttpStatusError(HttpClientError):
    """429와 5xx를 tenacity 재시도 대상으로 바꾸는 내부 오류."""


class HttpClient:
    """타임아웃·재시도·저빈도 요청·조건부 요청을 한 곳에 모은 클라이언트."""

    def __init__(
        self,
        *,
        rate_limit_per_min: int,
        user_agent: str = "jobRadar/1.0 (personal job monitor; contact@example.com)",
        max_response_bytes: int = MAX_RESPONSE_BYTES,
        retry_wait_seconds: float | None = None,
    ) -> None:
        if rate_limit_per_min < 1:
            raise ValueError("rate_limit_per_min은 1 이상이어야 합니다.")

        self.max_response_bytes = max_response_bytes
        self._minimum_interval = 60 / rate_limit_per_min
        self._last_request_at: float | None = None
        self._rate_limit_lock = threading.Lock()
        self._client = httpx.Client(
            follow_redirects=True,
            headers={"User-Agent": user_agent},
            timeout=httpx.Timeout(connect=5, read=15, write=15, pool=30),
        )
        self._wait = (
            wait_none()
            if retry_wait_seconds == 0
            else wait_random_exponential(multiplier=0.5, max=4)
        )

    def __enter__(self) -> HttpClient:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def close(self) -> None:
        """보유한 HTTP 연결을 닫는다."""
        self._client.close()

    def get(
        self,
        url: str,
        *,
        params: Mapping[str, str | int] | None = None,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> RawPage | None:
        """GET 한 번을 수행한다. 304면 파싱할 내용이 없으므로 None을 반환한다."""
        headers: dict[str, str] = {}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified

        retrying = Retrying(
            retry=retry_if_exception_type((_RetryableHttpStatusError, httpx.TransportError)),
            stop=stop_after_attempt(3),
            wait=self._wait,
            reraise=True,
        )
        return retrying(self._get_once, url, params, headers)

    def _get_once(
        self,
        url: str,
        params: Mapping[str, str | int] | None,
        headers: Mapping[str, str],
    ) -> RawPage | None:
        self._wait_for_rate_limit()
        with self._client.stream("GET", url, params=params, headers=headers) as response:
            if response.status_code == 304:
                return None
            if response.status_code == 429 or response.status_code >= 500:
                raise _RetryableHttpStatusError(f"HTTP {response.status_code}")
            if response.status_code >= 400:
                raise HttpStatusError(f"HTTP {response.status_code}")

            content_length = response.headers.get("Content-Length")
            if content_length is not None and int(content_length) > self.max_response_bytes:
                raise ResponseTooLargeError(
                    f"응답이 {self.max_response_bytes}바이트 상한을 넘었습니다."
                )

            body = self._read_with_limit(response)
            return RawPage(
                url=str(response.url),
                body=body,
                status_code=response.status_code,
                headers=dict(response.headers),
            )

    def _wait_for_rate_limit(self) -> None:
        """클라이언트 하나가 소스 하나를 담당한다는 전제로 최소 요청 간격을 지킨다."""
        with self._rate_limit_lock:
            now = time.monotonic()
            if self._last_request_at is not None:
                remaining = self._minimum_interval - (now - self._last_request_at)
                if remaining > 0:
                    time.sleep(remaining)
            self._last_request_at = time.monotonic()

    def _read_with_limit(self, response: httpx.Response) -> bytes:
        chunks: list[bytes] = []
        size = 0
        for chunk in response.iter_bytes():
            size += len(chunk)
            if size > self.max_response_bytes:
                raise ResponseTooLargeError(
                    f"응답이 {self.max_response_bytes}바이트 상한을 넘었습니다."
                )
            chunks.append(chunk)
        return b"".join(chunks)


def decode_html(body: bytes) -> str:
    """응답 헤더가 부정확한 한국 사이트도 처리할 수 있게 문자 인코딩을 추정한다."""
    match = from_bytes(body).best()
    if match is None:
        return body.decode("utf-8", errors="replace")
    return str(match)
