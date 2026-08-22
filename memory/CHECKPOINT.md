# Checkpoint — jobRadar 채용공고 모니터링 서비스 — 2026-08-22

## The story so far

Azure VM(2 vCPU / RAM 1GB)에서 24시간 돌릴 개인용 채용공고 모니터링 서비스다.
M0~M12 마일스톤 방식으로 진행하며, 현재 **M4(신규·중복·변경 탐지)까지 완료**했다.
다음 마일스톤은 M5(키워드 매칭)다.

- 완료 커밋: `7b1efb5` (M1), `9f8d9b9` (M2), `093a3ca` (M3)
- 현재 검증: pytest 47개 통과, `ruff check .` 및 `ruff format --check .` 통과
- 로컬 PostgreSQL은 `127.0.0.1:5432/jobradar`, Alembic revision `b24a4f6d9c1e` (head)

### M4에서 실제로 만든 것

```
app/schemas/job_posting.py              RawJob과 ORM 사이의 JobPostingDTO
app/services/normalizer.py              NFKC·공백·접두 태그 정리, fingerprint/content_hash
app/services/deduplicator.py            PostgreSQL ON CONFLICT 기반 신규/기존 판정
app/services/change_detector.py         내용 해시 대상 필드의 old/new JSONB diff
app/services/collector.py               정규화·UPSERT·이력·종료를 묶는 서비스 트랜잭션
app/repositories/models.py              공고 UPSERT, 관측 갱신, 미관측 종료 저장소 연산
alembic/versions/b24a4f6d9c1e_...       consecutive_missing_runs 컬럼 추가
tests/unit/test_job_normalizer.py       DB 없이 정규화·동적 raw 값 제외 계약 검증
tests/integration/test_collector.py     M4 DoD 5개를 PostgreSQL에서 검증
```

- 외부 ID가 있으면 `(source_id, external_id)`, 없으면 `(source_id, fingerprint)`로 식별한다.
- fingerprint는 source, 정규화 제목·회사명, URL path만 해시한다. URL query와 `[신입]`·`(채용)`
  같은 선행 태그 변동은 중복을 만들지 않는다.
- content_hash는 제목·마감일·설명 앞 2,000자만 사용한다. 조회수·스크랩 같은 `raw` 동적 값은
  갱신되더라도 revision을 만들지 않는다.
- 완전 수집에서만 열린 공고의 `consecutive_missing_runs`를 늘린다. 3회째에
  `is_open=false`, `closed_at`을 설정한다. `complete=False` 수집은 장애로 인한 오종료를 막기
  위해 이 판정을 건너뛴다.
- `CollectorService`는 중첩 트랜잭션으로 원자성을 보장하되 commit은 상위 호출자에게 맡긴다.
  따라서 M6 워커가 한 수집 실행을 자기 트랜잭션으로 관리할 수 있고, 통합 테스트도 rollback
  으로 격리된다.

### 이전 마일스톤 핵심 상태

- M1: FastAPI 팩토리, 설정, 구조화 로깅, `/healthz`, CI 골격.
- M2: PostgreSQL 10개 테이블, pg_trgm, Alembic, 기본 CRUD와 키워드 시드.
- M3: 공공데이터포털 과기정통부 API와 링크어리어 HTML 크롤러. 둘 다 DB와 독립적으로
  `list[RawJob]`을 반환한다. 과기정통부는 전용 키를 URL 디코딩한 뒤 전달해 이중 인코딩을
  피한다.

## Decided

- **동기 구조** — 사용자 1명·소스 10개 미만에서는 async가 불필요하다. 병렬은 M6에서
  `ThreadPoolExecutor(max_workers=3)`만 사용한다.
- **계층 경계** — 크롤러는 `RawJob`까지만 알고 DB를 모르며, `CollectorService`가 DTO와
  저장소를 연결한다. 저장소는 commit하지 않는다.
- **외부 키 선택값** — 키/승인 문제는 해당 소스만 비활성화하고 앱 기동을 막지 않는다.
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

`세부기획서.md` §10의 M5 구간만 읽고, include/exclude·세 가지 match_mode·가중치·
`job_keyword_matches` 근거를 TDD로 구현한다. M6 스케줄러와 API/UI는 아직 만들지 않는다.

## Tried

- **잡알리오 API** `apis.data.go.kr/1051000/recruitment/list`는 키 원문/디코딩 모두
  `SERVICE_KEY_IS_NOT_REGISTERED_ERROR`(403 코드 30)를 반환했다. 인코딩 문제가 아니라
  활용신청 또는 반영 상태 문제로 보고 M7까지 보류한다.
- **구 워크넷 LINK API**는 XML 오류 코드 `002`, **고용24 채용정보 API**는
  `GO24/error`(개인회원은 사용할 수 없는 OPEN-API)를 반환했다. 구현하지 않는다.
- **과기정통부 모집채용 API**는 URL-인코딩 키를 그대로 전달하면 httpx가 `%`를 다시
  인코딩해 403이 났다. `urllib.parse.unquote()` 후 전달하면 실제 공고를 정상 수집한다.
- `uv`가 PATH에 없어 개발 명령은 `py -3 -m uv`를 사용한다.
