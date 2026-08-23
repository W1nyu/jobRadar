# Site Recon — 인디스워크

*확인일: 2026-08-22*

## 수집 대상

- 서비스: [IN THIS WORK · 인디스워크](https://inthiswork.com/entry)
- 사용자용 채용 진입 화면은 `/entry`다. 크롤러는 같은 서비스가 공개한 WordPress 목록 API를
  사용해 브라우저 렌더링 없이 채용 분류만 가져온다.
- 목록 URL: `https://inthiswork.com/wp-json/wp/v2/posts`
- 방식: WordPress 공개 JSON API
- 크롤러 키: `inthiswork`
- 티어: 2 (공개 JSON)

일반 RSS(`feed/`)는 취업 토크도 포함하므로 사용하지 않는다. WordPress 분류 API에서 확인한
`신입/인턴`(191700167)과 `주니어경력`(191700168)만 `categories` 파라미터로 조회한다.
제목·본문·게시시각·상세 URL·분류를 `RawJob`으로 변환한다.

## robots·접근 결과

- `robots.txt`는 HTTP 200으로 응답했고 `User-agent: *`에 대해 `/wp-admin/`만 제한한다.
  사용 경로인 `/wp-json/`은 제한 대상이 아니다.
- 통합 식별 User-Agent와 `Accept: application/json`으로 루트, `feed/`, `wp-json/` 및
  채용 분류 목록을 각각 한 번씩 확인했다. 모두 HTTP 200이었다.
- 이전의 HTTP 403은 재현되지 않아 원인을 확정할 수 없다. User-Agent 로테이션·우회는 하지
  않았으며, 같은 경로가 다시 403을 내면 이 소스는 비활성화하고 원인을 다시 기록한다.

## 운영 제한과 검증

- 분당 10회, 최신 20건, 첫 페이지 1회로 제한한다.
- `tests/fixtures/inthiswork/posts_2026-08-22.json`은 실제 최신 공고 응답에서 파서 계약에
  필요한 필드만 남긴 골든 스냅샷이다.
- 2026-08-22 실제 단발 실행에서 HTTP 200, 20건을 수집했다.
