# Checkpoint — jobRadar 채용공고 모니터링 서비스 — 2026-08-22

## The story so far

Azure VM(2 vCPU / RAM 1GB)에서 24시간 돌릴 개인용 채용공고 모니터링 서비스다.
M0~M12 마일스톤 방식으로 진행하며, 현재 **M8(웹 관리 UI)까지 완료**했다.
M9(알림)는 코드·자동 테스트를 구현했고, 실제 Web Push·카카오 수신 DoD는 외부 설정 입력을 기다린다.

- 완료 커밋: `7b1efb5` (M1), `9f8d9b9` (M2), `093a3ca` (M3), `cc80637` (M4),
  `7fbfd65` (M5), `e8c0df9` (M6), `56ede96` (M7)
- 현재 검증: pytest **102개 통과**, `ruff check .` 및 `ruff format --check .` 통과
- 로컬 PostgreSQL은 `127.0.0.1:5432/jobradar`, Alembic revision `d5c91f86a4b2` (head)

### M8에서 실제로 만든 것

```
app/api/web/admin.py                Jinja2·HTMX 관리자 웹 라우트
app/services/admin_auth.py          단일 관리자 argon2 자격 증명 검증
app/services/admin.py               공고 조회·대시보드·소스 관리 서비스 경계
app/templates/                      로그인·대시보드·공고·소스·키워드 템플릿
app/static/admin.css                관리자 화면 스타일
tests/unit/test_admin_auth.py       비로그인 리다이렉트·로그인 세션 계약
tests/integration/test_admin_web.py DB 연동 UI 계약
```

- `/admin/*` 전체는 로그인 세션을 요구하며, 비로그인 요청은 원래 내부 경로를 보존해 `/login`으로
  303 리다이렉트한다. 세션은 `HttpOnly`, 운영 환경 `Secure`, `SameSite=Lax`로 설정했다.
- `ADMIN_PASSWORD_HASH`는 argon2 해시만 받는다. 해시가 비어 있으면 앱은 기동하지만 관리자 로그인은
  비활성화된다. 비밀을 기본값으로 넣지 않기 위한 결정이다.
- 공고 화면은 제목·회사명 검색과 소스·매칭 여부·기간·마감 임박·열림 상태 필터 및 페이지네이션을
  제공하고, 상세 화면은 `matched_snippet`을 포함한 키워드 매칭 근거를 표시한다.
- 소스 UI는 등록 크롤러와 수집 전략만 선택하게 하며 API 키·토큰·비밀번호 성격의 JSON 키를 차단한다.
  새 활성 소스는 기존 워커의 다음 소스 동기화 시 읽힌다. 수동 수집은 HTMX로 기존 M6 실행 서비스를
  호출한다.
- 대시보드는 마지막 성공 시각·연속 실패·최근 24시간 수집 건수·최근 실행 오류를 보이며,
  `worker_heartbeat`가 15분을 넘기면 경고 배너를 표시한다.

### M9에서 구현한 것 (외부 수신 검증 대기)

```
app/notifications/                  DB를 모르는 Web Push·카카오 채널 계약
app/services/dispatcher.py          배치·중복 방지·방해금지·재시도 디스패처
app/services/kakao.py               OAuth 교환·Fernet 암호화·매일/발송 직전 토큰 갱신
app/services/notification_runtime.py 워커용 실제 채널 조립·카카오 실패 Web Push 폴백
app/api/v1/push.py                  로그인 관리자 브라우저 구독 API
app/static/sw.js, push.js           Push 표시·클릭 공고 이동·구독 UI 동작
alembic/versions/d5c91f86a4b2...    OAuth 토큰 갱신 오류 보존 컬럼
```

- Web Push는 `POST /api/v1/push/subscribe`로 endpoint 키를 등록하고 404/410은 즉시 비활성화한다.
  그 밖의 실패는 5회 누적 시 비활성화한다.
- 워커는 매분 신규 매칭을 채널별 한 번의 배치로 발송한다. `notifications`의
  `(job_posting_id, channel)` 유일성 제약을 활용해 연속 실행에도 같은 공고를 중복 발송하지 않는다.
- 방해금지 시간(기본 KST 23:00~08:00)에는 `scheduled_at`으로 큐잉하며, 이후 한 배치로 발송한다.
- 카카오 access/refresh token은 Fernet으로 암호화해 저장한다. refresh 실패 시 오류를 DB와 UI에
  남기고, 가능한 경우 Web Push로 재인증 안내를 한 번 보낸다.

## Decided

- **웹 라우터도 서비스 계층만 호출** — 공고 조회, 대시보드, 소스 변경은 `app.services.admin`으로
  묶었다. API와 UI가 repository를 직접 호출하지 않아 트랜잭션과 검증 정책을 공유한다.
- **공개 소스 설정과 비밀 분리 유지** — UI로 저장할 수 있는 JSON에서 `password`, `secret`, `token`,
  `service_key`, `access_key` 계열 키를 거절한다. API 키는 계속 `.env`에서 실행 시점에만 주입한다.
- **세션은 Starlette 서명 쿠키** — 단일 사용자 서비스에는 별도 사용자 테이블·세션 저장소가 필요 없고,
  1GB VM의 상주 메모리와 운영 복잡도를 늘리지 않는다.
- **M9 채널은 DB를 모른다** — Web Push·카카오 구현은 페이로드를 받아 `SendResult`만 반환한다.
  이력 생성, 재시도, 구독 비활성화는 dispatcher/runtime 서비스가 맡아 채널 단위 HTTP 모킹 테스트가 가능하다.

## Waiting on the user

- **관리자 비밀번호 해시** — 실제 `/admin` 사용 전 `.env`에 `ADMIN_PASSWORD_HASH`를 설정한다.
  생성 명령은 README의 “관리자 로그인 (M8)” 절에 있다.
- **VAPID 키와 HTTPS** — `generate-vapid` 출력값과 메일 subject를 `.env`에 넣고, HTTPS로 `/admin`에서
  브라우저 알림을 연결해야 실제 Web Push DoD를 검증할 수 있다.
- **카카오 앱 설정** — Fernet 키, REST API 키, Redirect URI, 필요 시 Client Secret을 `.env`에 넣고
  Kakao Developers에 `talk_message` 동의와 Redirect URI를 등록해야 카카오 DoD를 검증할 수 있다.
- **사람인 API 승인 및 `SARAMIN_ACCESS_KEY`** — 승인 뒤 실제 성공 응답을 확보하면 추가 소스 작업을
  재개한다.
- **GitHub 원격 저장소** — 아직 없어 CI 원격 초록불은 확인하지 못했다.
- **카카오 앱 / 도메인 / Azure VM** — M9·M11 전까지 준비한다.

## Next first action

README의 “알림 설정 (M9)”에 따라 VAPID와 카카오 설정을 채운 뒤, HTTPS `/admin`에서 브라우저
구독·새 매칭 공고 수신·카카오 나에게 보내기·재인증 Web Push 폴백을 실제로 확인한다. 이 외부 DoD가
통과하기 전에는 M10으로 넘어가지 않는다.

## Archive

직전 M7 체크포인트는 `memory/checkpoints/2026-08-22-m7-complete.md`에 보관했다.
