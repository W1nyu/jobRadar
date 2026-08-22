# Checkpoint Archive — M3 진행 중 — 2026-08-22

M3 완료 직전의 상태를 보관한다.

- 공통 크롤링 기반(`RawJob`, `CrawlResult`, `BaseCrawler`, 레지스트리, `HttpClient`)과
  링크어리어 HTML 크롤러를 구현했다.
- 고용24는 개인회원 키로 목록 API를 사용할 수 없어 M7까지 보류했다.
- 과기정통부 모집채용 API를 M3의 티어 1 소스로 선정하고,
  `MSIT_RECRUITMENT_SERVICE_KEY`를 별도 설정으로 분리했다.
- 일반 공공데이터포털 키를 그대로 요청에 전달하면 403 코드 30이 발생했다. 이후 전용 키가
  URL-인코딩 형태임을 확인해 디코딩 호출 검증을 진행 중이었다.
- 이 시점까지 테스트 39개와 Ruff 검사·포맷은 통과했다.
