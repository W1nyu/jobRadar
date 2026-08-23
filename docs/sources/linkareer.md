# Site Recon — linkareer

*확인일: 2026-08-23*

## 수집 대상

- 목록 URL: `https://linkareer.com/list/recruit?filterBy_activityTypeID=5&filterBy_status=OPEN&orderBy_direction=DESC&orderBy_field=RECENT&page=1`
- 방식: SSR HTML의 `application/ld+json` `ItemList`와 `__NEXT_DATA__` 초기 상태
- 크롤러 키: `linkareer`
- 티어: 3 (HTTP + HTML 파싱)

## 준수 사항

- 2026-08-23 확인한 `robots.txt`에서 이 수집 경로를 제한하는 규칙은 확인되지 않았다.
- 차단된 `/stem/learn/...` 경로는 요청하지 않는다.
- 고정된 식별 User-Agent를 사용하고, 기본 제한인 분당 30회보다 훨씬 낮은 빈도로 수집한다.

## 관측 결과

- 목록 GET은 `200`을 반환했다.
- 채용 목록은 상세 URL이 `/activity/<id>` 형식이더라도 `activityTypeID=5`와 `OPEN` 필터로
  실제 채용공고만 선택한다. 이전 `/list/activity`는 서포터즈·자원봉사 등 대외활동을 섞어
  반환하므로 사용하지 않는다.
- JSON-LD `ItemList`에서 제목·절대 상세 URL을, 초기 상태의 숫자형 `recruitCloseAt`에서
  마감 시각을 얻는다. 채용 형태(`jobTypes`)도 보조 정보로 저장한다.
- 제목에 서포터즈·홍보단·자원봉사·대외활동·공모전 등 활동성 표현이 있으면 방어적으로
  제외한다.
- `ETag`는 제공하고 `Last-Modified`는 제공하지 않았다. `If-None-Match` 조건부 요청을 사용한다.
- 실제 응답을 줄인 골든 스냅샷은
  `tests/fixtures/linkareer/recruit_list_2026-08-23.html`에 보관한다.

## 페이지네이션

M3는 최신 목록 첫 페이지 1회만 수집한다. 페이지네이션 파라미터와 조기 종료 규칙은
스케줄러·다중 소스 작업이 생기는 M6/M7에서 실제 운영 데이터에 맞춰 확장한다.
