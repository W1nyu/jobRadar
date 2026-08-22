# Site Recon — linkareer

*확인일: 2026-08-22*

## 수집 대상

- 목록 URL: `https://linkareer.com/list/activity`
- 방식: SSR HTML의 `application/ld+json` `ItemList`
- 크롤러 키: `linkareer`
- 티어: 3 (HTTP + HTML 파싱)

## 준수 사항

- `robots.txt`는 `User-agent: *`에 대해 `/list/activity`를 허용한다.
- 차단된 `/stem/learn/...` 경로는 요청하지 않는다.
- 고정된 식별 User-Agent를 사용하고, 기본 제한인 분당 30회보다 훨씬 낮은 빈도로 수집한다.

## 관측 결과

- 목록 GET은 `200`, 약 224KB를 반환했다.
- 목록에 JSON-LD `ItemList`가 포함돼 제목·절대 상세 URL을 SSR 상태에서 얻을 수 있다.
- `ETag`는 제공하고 `Last-Modified`는 제공하지 않았다. `If-None-Match` 조건부 요청을 사용한다.
- 페이지별 상세 메타데이터는 선택 사항이므로, M3에서는 URL·제목·상세 ID만 `RawJob`으로 반환한다.
- 실제 응답의 JSON-LD 일부를 줄인 골든 스냅샷은
  `tests/fixtures/linkareer/list_2026-08-22.html`에 보관한다.

## 페이지네이션

M3는 최신 목록 첫 페이지 1회만 수집한다. 페이지네이션 파라미터와 조기 종료 규칙은
스케줄러·다중 소스 작업이 생기는 M6/M7에서 실제 운영 데이터에 맞춰 확장한다.
