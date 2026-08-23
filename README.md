# jobRadar

관심 채용 사이트를 주기적으로 확인해, **내 키워드와 일치하는 새 공고만** 골라 알려주는 개인용 채용공고 모니터링 서비스.

```text
채용 사이트 → 주기 수집 → 신규 탐지 → 키워드 매칭 → DB 저장 → 알림
```

`데이터`, `AI`, `개발`처럼 직무를 특정하는 관심 키워드가 일치한 공고만 저장한다. `신입`,
`인턴`은 보조 조건이므로 직무 관심 키워드와 함께 일치할 때만 저장한다. 마감일이 있는 공고는
KST 기준 마감일의 다음 날이 끝난 뒤 DB와 관리 화면에서 함께 제거한다.

- 상세 설계: [세부기획서.md](./세부기획서.md)
- 초기 기획: [기획.md](./기획.md)
- **현재 상태**: [memory/CHECKPOINT.md](./memory/CHECKPOINT.md)
- 작업 규칙 (에이전트용): [AGENTS.md](./AGENTS.md)

## 현재 상태

| 마일스톤 | 상태 |
|---|---|
| M0 사전 준비 | 진행 중 — [docs/M0-checklist.md](./docs/M0-checklist.md) (외부 키 발급 대기) |
| M1 프로젝트 기본 환경 | **완료** — GitHub Actions lint·format·PostgreSQL 마이그레이션·전체 테스트 통과 |
| M2 PostgreSQL · 데이터 모델 | **완료** |
| M3 첫 크롤러 2종 | **완료** — 공공데이터포털 API + 링크어리어 HTML |
| M4 신규 · 중복 · 변경 탐지 | **완료** — 정규화·UPSERT·변경 이력·3회 미노출 종료 |
| M5 키워드 매칭 | **완료** — include/exclude·매칭 근거·키워드 CRUD API |
| M6 스케줄러 자동 수집 | **완료** — APScheduler·실행 이력·advisory lock·하트비트 |
| M7 다중 사이트 확장 | **완료** — 인디스워크 JSON·금융투자협회 HTML·잡알리오 JSON, 기본 소스 5개 스케줄 |
| M8 웹 관리 UI | **완료** — argon2 로그인·공고/소스/키워드 관리·HTMX 수동 수집·운영 대시보드 |
| M9 알림 | **완료** — Web Push·카카오 실제 수신, 배치·중복 방지·방해금지·재인증 폴백 검증 |
| M10 장애 처리 · 테스트 | **완료** — 서킷브레이커·급감 감지·오류 분류·E2E·84.63% 커버리지·메모리·DB 복구 |
| M11 Azure VM 배포 | **완료** — HTTPS·systemd 자동 복구·백업 복원·외부 DB 차단·카카오·Web Push 실제 수신 |
| M12 운영 안정화 · 포트폴리오 마감 | **완료** — 운영/ADR/트러블슈팅 문서화·일일 알림 제어·배포 검증 완료 |

사람인 API는 승인 대기 중이며, 승인 후 실제 성공 응답 골든 파일을 확보한 뒤 별도 소스로
추가한다. 잡플래닛은 이용약관상 자동 수집 허용 범위가 확인되기 전까지 보류한다.

사이트 조사 결과와 추가 절차는 [docs/sources](./docs/sources/) 및
[docs/adding-a-source.md](./docs/adding-a-source.md)에 정리했다.

## 기술 스택

Python 3.12 · FastAPI · PostgreSQL 16 · SQLAlchemy 2.0 · Alembic · httpx · APScheduler · Nginx · systemd

## 아키텍처와 데이터 흐름

API 요청은 서비스 계층에서만 트랜잭션을 만들고, 크롤러와 알림 채널은 DB를 모른다. 이 경계를
지켜서 파서·전송 채널은 네트워크와 DB 없이 각각 검증할 수 있다.

```text
채용 사이트/API
    │  (최대 3개 병렬, 응답 5MB 상한, robots/ToS 준수)
    ▼
워커 ──> 크롤러 ──> 수집 서비스 ──> PostgreSQL
  │                                      │
  │ 매일 KST 09:00                       ├── 신규·변경 탐지
  └──────────> 알림 서비스 <─────────────┴── 키워드 매칭 근거
                     │
          ┌──────────┴──────────┐
          ▼                     ▼
   카카오톡 나에게 보내기      Web Push

브라우저 관리 UI ──> FastAPI API ──> 서비스 ──> 저장소 ──> PostgreSQL
```

운영에는 API와 워커를 분리한 systemd 서비스로 두고, Nginx가 HTTPS를 종료한다. PostgreSQL은
VM 내부 Unix socket으로만 접근하며 외부 5432 포트는 열지 않는다. 자세한 운영 절차는
[docs/operations.md](./docs/operations.md), 기술 결정은 [docs/adr](./docs/adr/)에서 확인할 수 있다.

## 개발 환경 설정

Python 버전과 의존성은 [uv](https://docs.astral.sh/uv/)가 관리한다. `.python-version`에 3.12가 고정되어 있어 별도 설치 없이 uv가 맞춰준다.

```bash
uv sync                 # 가상환경 생성 + 의존성 설치
cp .env.example .env    # 값을 채운다
uv run uvicorn app.main:create_app --factory --reload
```

`uv`가 PATH에 없으면 `py -3 -m uv`로 호출한다.

### 관리자 로그인 (M8)

관리 화면은 `/admin`이며 `ADMIN_PASSWORD_HASH`가 설정된 경우에만 로그인할 수 있다. 평문
비밀번호는 저장하지 말고 아래 명령으로 생성한 argon2 해시를 `.env`에 복사한다.

```bash
uv run python -m app.cli generate-password-hash
```

```dotenv
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=<위 명령의 출력값>
ADMIN_SESSION_MAX_AGE_SECONDS=43200
```

### 알림 설정 (M9)

Web Push와 카카오톡은 둘 다 선택 기능이다. 관련 값이 비어 있어도 앱과 워커는 정상 기동하며,
해당 채널만 비활성화된다. 키는 아래 명령으로 **사용자 터미널에서** 생성한 뒤 `.env`에만 넣는다.

```bash
uv run python -m app.cli generate-vapid
uv run python -m app.cli generate-fernet
```

Web Push는 HTTPS 환경에서 `/admin`의 “브라우저 알림 연결”을 눌러 구독한다. 카카오는 개발자
콘솔에 `KAKAO_REDIRECT_URI`를 정확히 등록하고 `talk_message` 동의를 활성화한 뒤,
`/admin/notifications`의 “카카오 연결”을 사용한다. 토큰 갱신이 실패하면 Web Push와 관리 화면에
재인증 안내가 표시된다.

### 알림 운영 정책 (M12)

신규 매칭 공고의 자동 알림은 **매일 KST 09:00에 한 번만** 카카오톡과 Web Push로 요약 발송한다.
관리자 `/admin/notifications`에서 “지금 수동 발송”을 누르면 예약·방해금지 시간을 건너뛰고 즉시
발송할 수 있다. 같은 화면의 “알림 끄기/켜기”는 두 채널의 채용공고 자동·수동 알림을 함께 제어한다.
알림을 껐을 때는 전송을 시도하지 않는다.

### 데이터베이스 (M2)

개발용 PostgreSQL 16이 준비된 뒤 아래 명령으로 스키마와 기본 키워드 8개를 만든다.

```bash
uv run alembic upgrade head
uv run python -m app.seed
```

롤백 검증은 `uv run alembic downgrade base`로 할 수 있다. 기본 `DATABASE_URL`은 Windows에서
Docker의 IPv6 `localhost` 우선 해석으로 인한 연결 지연을 피하도록 `127.0.0.1`을 사용한다.
운영 환경에서는 `.env`의 `DATABASE_URL`로 PostgreSQL 주소와 자격 증명을 명시한다.

### 확인

```bash
curl http://127.0.0.1:8000/healthz
```

### 테스트 · 린트

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

## 라이선스

개인 프로젝트. 수집한 채용 데이터는 재배포하지 않는다.
