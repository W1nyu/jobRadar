# 새 채용 소스 추가 가이드

새 소스는 **공식 API → 공개 RSS/JSON → 공개 HTML** 순으로 선택한다. 로그인·봇 차단 우회,
User-Agent 로테이션, 비공개 API 추측은 허용하지 않는다.

## 1. 조사 기록부터 만든다

`docs/sources/<slug>.md`에 다음을 적는다.

- 서비스·목록 URL·수집 방식·크롤러 키
- robots.txt와 이용약관 확인 결과, 확인일, 허용하지 않은 경로
- 실제 HTTP 상태와 제한(페이지·건수·요청 빈도)
- 키/승인 필요 여부와 보류 사유

robots 정책이 명시적으로 수집을 금지하거나 약관이 불명확하면 구현하지 않고 보류한다.

## 2. DB와 분리된 크롤러를 작성한다

- `app/crawlers/<slug>.py`는 `BaseCrawler`를 상속하고 `fetch()`와 순수 `parse()`만 구현한다.
- `parse()`는 네트워크·세션·ORM을 건드리지 않고 `RawJob` 목록만 반환한다.
- 실제 성공 응답을 축소·비식별화한 스냅샷을 `tests/fixtures/<slug>/`에 저장하고 골든 테스트를
  먼저 실패시킨 뒤 통과시킨다.
- `app/crawlers/__init__.py`에서 구현체를 import해 레지스트리에 등록한다.

## 3. 공개 설정과 비밀을 분리한다

- `app/source_catalog.py`에 slug, URL, 속도, 간격, 공개 필터만 넣는다.
- API 키는 `.env`의 `Settings`에서만 읽고, `with_runtime_credentials()`가 실행 객체에만 복사한다.
  DB `sources.config`, 로그, 테스트 픽스처에는 저장하지 않는다.
- `app.seed.seed_builtin_sources()`는 신규 기본 소스만 추가하며 기존 운영 설정은 덮어쓰지 않는다.

## 4. 검증하고 등록한다

1. 파서 골든 테스트와 키 비영속화 테스트를 실행한다.
2. `uv run python -m app.seed`로 실제 DB에 기본 소스를 등록한다.
3. `uv run python -m app.cli crawl <slug>`로 한 번만 실제 호출한다.
4. 워커의 활성 소스 잡과 전체 테스트·Ruff를 확인한다.

새 크롤러를 추가할 때 `collector.py`, `normalizer.py`, `deduplicator.py`,
`keyword_matcher.py`를 변경하지 않는다. 공통 계약 변경이 정말 필요하면 독립적인 설계 결정과
회귀 테스트를 먼저 남긴다.
