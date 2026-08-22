# Checkpoint — jobRadar 채용공고 모니터링 서비스 — 2026-08-22

## The story so far

Azure VM(2 vCPU / RAM 1GB)에서 24시간 돌릴 개인용 채용공고 모니터링 서비스다.
M0~M12 마일스톤 방식으로 진행하며, 현재 **M5(키워드 매칭)까지 완료**했다.
다음 마일스톤은 M6(스케줄러 자동 수집)다.

- 완료 커밋: `7b1efb5` (M1), `9f8d9b9` (M2), `093a3ca` (M3), `cc80637` (M4)
- 현재 검증: pytest 59개 통과, `ruff check .` 및 `ruff format --check .` 통과
- 로컬 PostgreSQL은 `127.0.0.1:5432/jobradar`, Alembic revision `b24a4f6d9c1e` (head)

### M5에서 실제로 만든 것

```
app/services/keyword_matcher.py          순수 include/exclude 판정 + 근거 저장 서비스
app/services/keywords.py                 키워드 CRUD 트랜잭션 서비스
app/schemas/keyword.py                   CRUD API 입력/출력·정규식·대상 필드 검증
app/api/v1/keywords.py                   GET/POST/PATCH/DELETE /api/v1/keywords
app/repositories/models.py               활성 키워드 조회·공고별 매칭 근거 교체
app/services/collector.py                신규 공고 저장 직후 키워드 매칭 연결
tests/unit/test_keyword_matcher.py       substring/word/regex·대상 필드·정렬 순수 테스트
tests/integration/test_keyword_matcher.py 근거 저장·제외·GIN 계획·수집기 연결 테스트
tests/integration/test_keywords_api.py   키워드 CRUD API와 입력 검증 테스트
```

- include 키워드가 하나 이상이고 exclude 키워드가 없을 때만 관심 공고다.
- `substring`, `word`, `regex` 세 모드를 대소문자 무시로 적용한다. API는 잘못된 regex와
  title/description 외의 대상 필드를 422로 거절한다. 이미 DB에 잘못 저장된 regex는 한 키워드만
  건너뛰어 수집 전체를 실패시키지 않는다.
- 각 키워드는 지정한 첫 매칭 필드와 주변 `matched_snippet`, 가중치를 `job_keyword_matches`에
  기록한다. exclude 근거도 보존해 UI에서 제외 사유를 확인할 수 있다.
- 재매칭하면 그 공고의 근거를 현재 활성 키워드 결과로 교체한다. include 결과는 가중치 내림차순,
  동점이면 키워드 ID 순으로 고정한다.
- 신규 공고만 `CollectorService`에서 즉시 매칭하고 `items_matched`로 집계한다. 변경·기존 공고의
  재매칭 정책과 주기 실행은 M6 워커에서 명시적으로 확장한다.
- M2에서 만든 `ix_job_postings_title_trgm` GIN 인덱스를 유지하고, `EXPLAIN ANALYZE` 테스트로
  title `ILIKE '%데이터%'`가 해당 인덱스를 타는 것을 확인했다. M5에는 새 마이그레이션이 없다.

### 이전 마일스톤 핵심 상태

- M1: FastAPI 팩토리, 설정, 구조화 로깅, `/healthz`, CI 골격.
- M2: PostgreSQL 10개 테이블, pg_trgm, Alembic, 기본 CRUD와 키워드 시드.
- M3: 공공데이터포털 과기정통부 API와 링크어리어 HTML 크롤러가 DB 독립적으로 `RawJob`을 반환.
- M4: DTO 정규화, ON CONFLICT 중복 방지, 변경 이력, 3회 미관측 종료.

## Decided

- **동기 구조** — 사용자 1명·소스 10개 미만에서는 async가 불필요하다. 병렬은 M6에서
  `ThreadPoolExecutor(max_workers=3)`만 사용한다.
- **계층 경계** — API는 `KeywordService`만 호출하고, 서비스가 저장소를 조합한다. 크롤러는
  `RawJob`까지만 알고 DB를 모르며, 저장소는 commit하지 않는다.
- **키워드 근거 보존** — exclude를 포함한 모든 매칭을 저장해야 키워드 튜닝과 M8 UI에서
  "왜 제외됐는지"를 확인할 수 있다.
- **고용24 보류** — 현재 `WORK24_SERVICE_KEY`는 개인회원 키라 채용정보 목록을 이용할 수 없어,
  구현은 M7까지 보류한다.

## Waiting on the user

- **잡알리오 API 경로·활용신청 재확인** — `ALIO_SERVICE_KEY`는 설정됐으나 이전
  `apis.data.go.kr/1051000/recruitment/list` 호출은 403 코드 30이었다. M7에서 해당 API의
  활용신청 상태와 정확한 경로를 재확인한 뒤 추가한다.
- **사람인 API 승인 대기** — M7 전까지 승인되면 된다.
- **GitHub 원격 저장소** — 아직 없어 CI 원격 초록불은 확인하지 못했다.
- **카카오 앱 / 도메인 / Azure VM** — M9·M11 전까지 준비한다.

## Next first action

`세부기획서.md` §10의 M6 구간만 읽고, APScheduler 워커·`crawl_runs`·advisory lock·
수동 수집 API·하트비트를 TDD로 구현한다. M7 소스 확장과 M8 UI는 아직 만들지 않는다.

## Tried

- **잡알리오 API** `apis.data.go.kr/1051000/recruitment/list`는 키 원문/디코딩 모두
  `SERVICE_KEY_IS_NOT_REGISTERED_ERROR`(403 코드 30)를 반환했다. 인코딩 문제가 아니라
  활용신청 또는 반영 상태 문제로 보고 M7까지 보류한다.
- **구 워크넷 LINK API**는 XML 오류 코드 `002`, **고용24 채용정보 API**는
  `GO24/error`(개인회원은 사용할 수 없는 OPEN-API)를 반환했다. 구현하지 않는다.
- **과기정통부 모집채용 API**는 URL-인코딩 키를 그대로 전달하면 httpx가 `%`를 다시
  인코딩해 403이 났다. `urllib.parse.unquote()` 후 전달하면 실제 공고를 정상 수집한다.
- `uv`가 PATH에 없어 개발 명령은 `py -3 -m uv`를 사용한다.
