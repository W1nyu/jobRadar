# Checkpoint — jobRadar 채용공고 모니터링 서비스 — 2026-08-22

## The story so far

Azure VM(2 vCPU / RAM 1GB)에서 24시간 돌릴 **개인용 채용공고 모니터링 서비스**를 만든다.
등록한 채용 사이트를 주기적으로 수집해, 신규 공고 중 관심 키워드와 맞는 것만 골라
카카오톡과 Web Push로 알린다. 개인용이자 **취업 포트폴리오**라, 단순 크롤링 스크립트가
아니라 설계 근거(ADR)를 남기는 형태로 만든다.

설계는 `세부기획서.md`(1,400행)에 확정돼 있다. **M0~M12 마일스톤 방식**으로 진행하며,
각 마일스톤은 검증 가능한 DoD를 만족해야 다음으로 넘어간다.

**현재: M3 완료. 다음 마일스톤은 M4(신규·중복·변경 탐지)다. 고용24는 개인회원 키로 목록
API를 쓸 수 없어 M7까지 보류한다.**

- 이전 커밋: `a9ec6bb` (docs), `7b1efb5` (M1) — 브랜치 `main`, 원격 없음
- 테스트 40개 통과 / ruff check·format 통과 / Python 3.12.14 (배포 대상과 일치)
- 앱 기동 확인: `GET /healthz` → `200 {"status":"ok","version":"0.1.0","env":"development"}`

### M1에서 실제로 만든 것

```
app/core/config.py     pydantic-settings. 별칭을 대문자로 생성해 검증 에러가
                       .env에 적을 이름 그대로(SECRET_KEY) 나온다
app/main.py            create_app(settings) 팩토리. 모듈 레벨 app 인스턴스 없음
app/api/health.py      /healthz (DB 미접근)
app/core/logging.py    structlog. 운영 JSON / 개발 콘솔
app/cli.py             check-keys 명령
.github/workflows/ci.yml   ruff → format → pytest
```

`app/{models,schemas,repositories,services,crawlers,notifications,worker}`는
`__init__.py`만 있던 상태에서 M2의 영속 계층을 채웠다.

### M2에서 실제로 만든 것

```
app/core/db.py                    지연 초기화 sync engine, SessionLocal, get_db
app/models/entities.py            SQLAlchemy 2.0 typed ORM 모델 10종과 enum
app/repositories/                 commit하지 않는 기본 CRUD와 모델별 저장소
alembic/versions/8c0076e38b48...  초기 스키마 + pg_trgm extension + clean downgrade
app/seed.py                       기본 키워드 8개를 중복 없이 넣는 시드 명령
tests/integration/test_database.py PostgreSQL UNIQUE·시드·CRUD 통합 테스트
```

- 로컬 PostgreSQL 16 Docker 컨테이너 `jobradar-postgres`를 `127.0.0.1:5432`에 준비했다.
  운영 배포에서는 기존 ADR-03대로 Docker를 사용하지 않는다.
- `alembic upgrade head` → 테이블 10개, `pg_trgm`, 공고 인덱스 생성 확인.
- `alembic downgrade base` → 프로젝트 테이블·`pg_trgm`·프로젝트 enum 0개 확인 후 다시 upgrade.
- `python -m app.seed` 후 `keywords` 8건 확인. 기본 `DATABASE_URL`은 Windows Docker의
  IPv6 `localhost` 우선 해석 지연을 피하도록 `127.0.0.1`을 쓴다.

### M3 진행 상황

```
app/crawlers/base.py             DB-독립 RawJob·RawPage·CrawlResult·BaseCrawler
app/crawlers/http.py             429/5xx 재시도, 5MB 상한, ETag 조건부 요청, rate limit
app/crawlers/registry.py         데코레이터 기반 크롤러 레지스트리
app/crawlers/datagokr_msit.py    공공데이터포털 모집채용 JSON 파서와 오류 응답 처리
app/crawlers/linkareer.py        SSR JSON-LD ItemList 파서
app/crawlers/sources.py          M3 단발 CLI용 최소 소스 설정
docs/sources/                    공공데이터포털·링커리어·고용24 Site Recon 결과
```

- `python -m app.cli crawl linkareer`는 실제 목록에서 RawJob 20건을 반환했다.
- 링크어리어 `robots.txt`는 `/list/activity`를 허용하고, 목록은 ETag를 제공한다.
- 고용24는 `WORK24_SERVICE_KEY` 설정과 조사 문서만 유지한다. 개인회원 키의 실제 응답은
  `GO24/error`이며, 수집 구현·골든 파일은 M7까지 보류했다.
- 공공데이터포털 과기정통부 모집채용 API형 크롤러와 실제 성공·403 오류 골든 파일을
  추가했다. `MSIT_RECRUITMENT_SERVICE_KEY`는 URL 디코딩 후 요청해 이중 인코딩을 피한다.
- `crawl datagokr-msit-recruitment`는 실제 공고 10건, `crawl linkareer`는 실제 공고 20건을
  반환했다. M3 DoD 5개를 모두 확인했다.

## Decided

- **PostgreSQL 채택** — API·워커 두 프로세스가 동시에 쓰므로 SQLite writer lock이 병목.
  JSONB 원본 보관으로 파서 개선 시 재파싱 가능, pg_trgm으로 한글 부분일치 (세부기획서 §5)
- **ADR-01 전면 동기(sync) 구조** — 사용자 1명·소스 10개 미만에서 async 이점 없음.
  동시성은 사이트 단위 `ThreadPoolExecutor(max_workers=3)`
- **ADR-02 API·워커 프로세스 분리** — systemd 유닛 2개. 유닛별 `MemoryMax`로 장애 격리
- **ADR-03 Docker 미사용** — 1GB RAM에서 오버헤드 회피. systemd + venv 직접 배포
- **알림 채널 2개** — 카카오톡 나에게 보내기 + Web Push (Telegram/Discord 제외)
- **M3에 크롤러 2개** — API형(공공데이터포털) + HTML형(링커리어). 하나만 만들면
  `BaseCrawler` 추상화가 그것에 과적합된다
- **uvicorn 팩토리 모드** — 모듈 레벨 `app = create_app()`을 두면 임포트만으로 설정
  검증이 돌아 `.env` 없는 CI에서 테스트 수집이 실패한다
- **외부 API 키는 전부 선택값** — 승인 대기 중인 사람인 API 때문에 앱 전체가 못 뜨면 안 됨
- **개행 LF 고정** (`.gitattributes`) — 배포가 Linux. CRLF로 체크아웃된 셸 스크립트는 깨진다
- **DB 트랜잭션은 저장소가 commit하지 않는다** — 여러 저장소 변경을 M4 이후 서비스 계층에서
  하나의 트랜잭션으로 묶을 수 있도록, 저장소는 `flush`까지만 수행한다.

## Waiting on the user

- **잡알리오 API 경로·활용신청 재확인 필요** — `ALIO_SERVICE_KEY`는 설정됐으나 이전
  `apis.data.go.kr/1051000/recruitment/list` 경로에서 403 코드 30을 반환했다. 이 소스는
  M7에서 별도 크롤러로 추가한다.
- **사람인 API 승인 대기** — M7까지 되면 된다. 승인 후 `.env`에 `SARAMIN_ACCESS_KEY`만 채우면 켜짐
- **GitHub 원격 저장소** — 없어서 CI 초록불을 확인하지 못했다. 워크플로 파일은 커밋돼 있음
- **카카오 앱 / 도메인 / Azure VM** — M9·M11 전까지만 준비되면 된다

## Next first action

`세부기획서.md` §10의 M4 구간만 발췌해 읽고, `RawJob`을 `JobPostingDTO`로 정규화하는
`normalizer.py`와 중복·변경 탐지 테스트를 TDD로 시작한다. M3의 소스별 원본 응답·크롤러는
DB를 모르는 현재 계층 경계를 유지한다.

## Tried

- **공공데이터포털 잡알리오 API(`apis.data.go.kr/1051000/recruitment/list`) 호출 → 403
  `SERVICE_KEY_IS_NOT_REGISTERED_ERROR`(returnReasonCode 30).**
  키를 원문 그대로 붙인 경우와 URL 디코딩 후 재인코딩한 경우 **둘 다 동일 에러** — 따라서
  Encoding/Decoding 혼동 문제가 **아니다**. 남은 원인은 (a) 이 API를 활용신청하지 않았거나
  (b) 발급/신청 직후라 반영 전(보통 1시간, 최대 1일). 다시 시도하기 전에 마이페이지에서
  **해당 API가 활용신청 목록에 있는지 먼저 확인할 것**
- **구 워크넷 LINK API(`openapi.work.go.kr/opi/opi/opia/wantedApi.do`) 호출 → HTTP 200,
  XML 오류 코드 `002`.** `DATA_GO_KR_SERVICE_KEY`를 `authKey`로 전달했으나 유효하지 않았다.
  고용24 전환에 따라 이 엔드포인트·대체 키 로직은 M3에서 제거했다.
- **고용24 채용정보 API(`www.work24.go.kr/.../callOpenApiSvcInfo210L01.do`) 호출 → HTTP 200,
  `GO24/error`: `개인회원은 사용할 수 없는 OPEN-API입니다.`** 현재 `WORK24_SERVICE_KEY`는
  개인회원 키이거나 채용정보 API 서비스 승인이 연결되지 않은 상태다. M3 구현에서는 제외하고
  설정·조사만 남긴다.
- **공공데이터포털 과기정통부 모집채용 API
  (`apis.data.go.kr/1721000/msitrecruitinfo/recruitList`)에 URL-인코딩 키를 그대로 전달 →
  HTTP 403, `SERVICE_KEY_IS_NOT_REGISTERED_ERROR`(코드 30).** `httpx`가 `%`를 다시 인코딩한
  결과다. 전용 키를 `urllib.parse.unquote()`한 뒤 전달하면 HTTP 200과 실제 공고 10건을
  반환했다. 두 응답 형태를 골든 파일 테스트로 고정했다.
- **`starlette.testclient` + `httpx`** → `StarletteDeprecationWarning`. Starlette 1.6부터
  `httpx2`를 요구한다. dev 의존성을 `httpx2`로 교체해 해결
- **ruff format이 `세부기획서.md`를 대상으로 잡음** — ruff 0.16이 마크다운 내 Python 코드
  블록을 포맷한다. 문서의 코드는 설명용 발췌라 `extend-exclude = ["*.md"]`로 제외
- **`uv`가 PATH에 없음** — `py -3 -m uv`로 호출한다. 실제 경로는
  `C:\Users\Winyu\AppData\Roaming\Python\Python314\Scripts\uv.exe`
- **Windows 콘솔(cp949)에서 CLI 한글 깨짐** — `app/cli.py`의 `_force_utf8_stdout()`으로 해결
