# HANDOFF — M2 착수

> 이 파일은 **한 번만 읽는다.** 읽고 지시를 흡수한 뒤 **즉시 삭제**한다.
> 지시가 살아남으면 오래된 명령이 현재 명령의 권위를 갖게 된다.

## 상황

M1(프로젝트 기본 환경)까지 Claude Code에서 완료했다. **M2부터 Codex에서 진행한다.**
현재 상태는 `memory/CHECKPOINT.md`, 작업 규칙은 `AGENTS.md`에 있다.

## 지금 할 일 — M2: PostgreSQL · 데이터 모델

`세부기획서.md` **§6 데이터베이스 설계**(405~640행)만 읽으면 된다. 그 앞뒤는 지금 불필요하다.

1. 로컬 PostgreSQL 16 준비 (개발용은 Docker 허용 — 운영만 Docker 미사용이다)
2. `app/core/db.py` — engine, `SessionLocal`, `get_db` 의존성
   - `pool_size=5, max_overflow=2, pool_pre_ping=True, pool_recycle=1800`
3. SQLAlchemy 2.0 typed 모델 **10종** (§6.1 ERD, §6.2 설계 포인트)
   - `sources`, `job_postings`, `job_posting_revisions`, `keywords`,
     `job_keyword_matches`, `crawl_runs`, `notifications`,
     `push_subscriptions`, `oauth_tokens`, `app_settings`
4. Alembic 초기화 + 첫 마이그레이션 — **`pg_trgm` 확장 생성 포함**
5. `app/repositories/` 기본 CRUD
6. 시드 스크립트 — 기본 키워드 8개 등록
   (`데이터`, `데이터분석`, `IT`, `디지털`, `AI`, `개발`, `신입`, `인턴`)

`Settings`에 `DATABASE_URL`, `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`를 추가해야 한다.
`.env.example`에 주석 처리된 채로 이미 자리가 잡혀 있으니 주석만 풀면 된다.

### M2 DoD (세부기획서 §10)

- [ ] `alembic upgrade head` → 테이블 10종 + 인덱스 생성
- [ ] `alembic downgrade base` → 깨끗이 롤백
- [ ] 시드 실행 후 `keywords` 8건 조회
- [ ] UNIQUE 제약 위반 시 `IntegrityError`가 나는 테스트 통과

## 놓치기 쉬운 것

- **중복 방지 제약이 이 마일스톤의 핵심이다.** `job_postings`에 UNIQUE 두 개
  (`source_id, external_id`)와 (`source_id, fingerprint`), `notifications`에
  UNIQUE (`job_posting_id, channel`). 이 제약들이 M4·M9의 중복 방지를
  애플리케이션 코드가 아니라 DB 레벨에서 보장한다
- **인덱스를 빠뜨리지 말 것.** `GIN (title gin_trgm_ops)`, `(deadline_at) WHERE is_open`
  같은 부분 인덱스가 M5·M8 성능의 전제다
- 테스트는 `filterwarnings = ["error"]` 아래서 돈다. SQLAlchemy 2.0 경고가 뜨면 실패한다
- DB가 필요한 테스트에는 `@pytest.mark.integration`을 붙인다 (마커는 이미 등록돼 있다)

## 사용자에게 확인이 필요한 것 (막히면 물어볼 것)

**공공데이터포털 키가 아직 안 통한다.** `.env`에 설정은 됐지만 잡알리오 API 호출이
403 `SERVICE_KEY_IS_NOT_REGISTERED_ERROR`다. **인코딩/디코딩 혼동이 아니다** —
두 방식 다 같은 에러였다. 남은 원인은 해당 API 활용신청 미완료이거나 발급 직후 미반영이다.

**M2에는 이 키가 필요 없다.** M3 착수 전까지만 해결되면 된다. 지금 붙잡지 말 것.

## M2를 끝내면

`AGENTS.md`의 "마일스톤을 끝낼 때" 절차를 따른다 — DoD 실행 확인 → 세부기획서 갱신 →
README 갱신 → CHECKPOINT 갱신 → 커밋.

---

**이 파일을 삭제하는 것을 잊지 말 것.**
