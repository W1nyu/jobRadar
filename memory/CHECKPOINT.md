# Checkpoint — jobRadar 채용공고 모니터링 서비스 — 2026-08-22

## The story so far

Azure VM(2 vCPU / RAM 1GB)에서 24시간 돌릴 개인용 채용공고 모니터링 서비스다.
M0~M12 마일스톤 방식으로 진행하며, 현재 **M7(다중 사이트 확장)까지 완료**했다.
다음 마일스톤은 M8(웹 관리 UI)이다.

- 완료 커밋: `7b1efb5` (M1), `9f8d9b9` (M2), `093a3ca` (M3), `cc80637` (M4),
  `7fbfd65` (M5), `e8c0df9` (M6)
- 현재 검증: pytest **77개 통과**, `ruff check .` 및 `ruff format --check .` 통과
- 로컬 PostgreSQL은 `127.0.0.1:5432/jobradar`, Alembic revision `b24a4f6d9c1e` (head)

### M7에서 실제로 만든 것

```
app/crawlers/inthiswork.py           WordPress 채용 분류 JSON 크롤러
app/crawlers/kofia.py                금융투자협회 회원사 채용안내 HTML 크롤러
app/crawlers/alio.py                 잡알리오 공개 채용목록 JSON 크롤러
app/source_catalog.py                비밀 없는 기본 소스 5개 정의
app/crawlers/sources.py              실행 시점 API 키 주입
app/seed.py                          기본 소스 최초 시드
docs/adding-a-source.md              새 소스 추가 절차
docs/sources/*.md                    소스별 robots·경로·보류 근거
```

- 실제 DB에 기본 소스 5개를 시드했고, 워커에는 `crawl-source-218`~`crawl-source-222`의
  개별 잡으로 등록됨을 확인했다. 워커 풀은 기존대로 `max_workers=3`이므로 순간 동시 요청은
  세 개로 제한된다.
- 2026-08-22 단발 검증 결과: 인디스워크 20건, 금융투자협회 10건, 잡알리오 20건을 수집했다.
- 인디스워크는 일반 RSS 대신 `신입/인턴`·`주니어경력` WordPress 분류만 요청한다. 이전 403은
  동일 식별 User-Agent로 재현되지 않았고, 우회·로테이션은 하지 않았다.
- 잡알리오는 이전 공공데이터포털 403 경로가 아닌 공식 포털의 공개 채용목록 JSON을 사용한다.
  `ALIO_SERVICE_KEY`는 저장하거나 전송하지 않는다. 로그인 뒤 사용하는 별도 인증 Open API는
  정확한 명세를 확인할 때까지 구현하지 않는다.
- 키가 필요한 과기정통부 소스는 `sources.config`에 키를 쓰지 않고 실행 객체에만 주입한다.
  수동 API 트리거와 워커 모두 같은 주입 경로를 사용한다.
- `collector.py`, `normalizer.py`, `deduplicator.py`, `keyword_matcher.py`는 M7에서 변경하지
  않았다. 새 파서는 모두 DB를 모르고 `RawJob`만 반환한다.

### 보류한 소스

- **사람인**: `SARAMIN_ACCESS_KEY`가 미설정이며 공식 API는 승인·앱 등록이 전제다. 성공 응답
  골든 파일을 확보한 뒤 별도 변경으로 추가한다.
- **잡플래닛**: 이용약관상 자동 수집 허용 범위가 명확하지 않아 구현하지 않았다.
- **고용24**: 개인회원 `WORK24_SERVICE_KEY`로는 채용정보 목록 Open API를 사용할 수 없어
  기존 결정대로 보류한다.

## Decided

- **소스 카탈로그와 비밀 분리** — `app/source_catalog.py`에는 URL·빈도·필터만 두고, 키는
  `Settings`에서 실행 시점에만 복사한다. DB 백업·로그·관리 UI에 API 키가 새지 않게 하기 위해서다.
- **시드로 M7 소스 등록** — M8의 소스 관리 UI 전에도 실제 워커가 소스를 실행해야 하므로,
  `app.seed`는 없는 기본 소스만 추가하고 기존 운영 설정은 덮어쓰지 않는다.
- **공개 JSON 우선** — 인디스워크와 잡알리오는 목록 화면이 제공하는 공개 JSON을 사용한다.
  상세 페이지·첨부 파일은 요청하지 않아 트래픽과 약관 리스크를 낮춘다.

## Waiting on the user

- **사람인 API 승인 및 `SARAMIN_ACCESS_KEY`** — 승인 뒤 실제 성공 응답을 확보하면 추가 소스
  작업을 재개한다.
- **GitHub 원격 저장소** — 아직 없어 CI 원격 초록불은 확인하지 못했다.
- **카카오 앱 / 도메인 / Azure VM** — M9·M11 전까지 준비한다.

## Next first action

`세부기획서.md` §10의 M8 구간만 읽고, 로그인·소스/키워드 관리·공고 조회 웹 UI를 순서대로
구현한다. M7의 `sources` 행과 수동 수집 API를 재사용하되, API가 repository를 직접 호출하지
않는 계층 경계를 유지한다.

## Archive

직전 M6 체크포인트는 `memory/checkpoints/2026-08-22-m6-complete.md`에 보관했다.
