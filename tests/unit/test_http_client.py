"""HTTP 공통 정책은 네트워크 없이 모의 응답으로 검증한다."""

import httpx
import pytest
import respx

from app.crawlers.http import HttpClient, ResponseTooLargeError


def test_429는_성공할_때까지_최대_3회_재시도한다() -> None:
    url = "https://example.com/jobs"
    with respx.mock(assert_all_called=True) as router:
        route = router.get(url).mock(
            side_effect=[httpx.Response(429), httpx.Response(200, content=b"ok")]
        )
        with HttpClient(rate_limit_per_min=60_000, retry_wait_seconds=0) as client:
            page = client.get(url)

    assert page is not None
    assert page.body == b"ok"
    assert route.call_count == 2


def test_5mb를_넘는_응답은_메모리에_쌓지_않고_중단한다() -> None:
    url = "https://example.com/large"
    with respx.mock(assert_all_called=True) as router:
        router.get(url).mock(
            httpx.Response(200, headers={"Content-Length": str(5 * 1024 * 1024 + 1)})
        )
        with (
            HttpClient(rate_limit_per_min=60_000, retry_wait_seconds=0) as client,
            pytest.raises(ResponseTooLargeError),
        ):
            client.get(url)


def test_304는_조건부_요청_후_파싱할_페이지를_반환하지_않는다() -> None:
    url = "https://example.com/cached"
    with respx.mock(assert_all_called=True) as router:
        route = router.get(url).mock(httpx.Response(304))
        with HttpClient(rate_limit_per_min=60_000, retry_wait_seconds=0) as client:
            page = client.get(url, etag='"v1"', last_modified="Mon, 01 Jan 2026 00:00:00 GMT")

    assert page is None
    assert route.calls[0].request.headers["If-None-Match"] == '"v1"'
    assert route.calls[0].request.headers["If-Modified-Since"] == "Mon, 01 Jan 2026 00:00:00 GMT"
