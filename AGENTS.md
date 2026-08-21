# AGENTS.md — jobRadar 작업 규칙

개인용 채용공고 모니터링 서비스. 취업 포트폴리오 겸용이라 **설계 근거를 남기는 것**이
동작하는 코드만큼 중요하다.

## 시작하기 전에 읽을 것

1. `memory/HANDOFF.md` — 있으면 읽고 실행한 뒤 **삭제한다** (단발성 지시)
2. `memory/CHECKPOINT.md` — 현재 상태, 결정 사항, 막힌 것, 시도했다 실패한 것
3. `세부기획서.md` — 설계 원본. **1,400행이므로 통독하지 말고** 지금 할 마일스톤 구간만 발췌해 읽는다

## 가장 중요한 규칙

**마일스톤 순서를 지킨다.** M0 → M1 → ... → M12. 각 마일스톤의 DoD를 만족하기 전에
다음으로 넘어가지 않는다. DoD는 `세부기획서.md` §10에 체크박스로 있다.

**앞선 마일스톤의 기능을 미리 만들지 않는다.** M2에서 크롤러를 만들지 않고,
M5에서 알림을 붙이지 않는다. 스코프를 넓히면 마일스톤 방식이 의미를 잃는다.

## 개발 명령

```bash
uv sync                                              # 의존성 설치
uv run uvicorn app.main:create_app --factory --reload
uv run pytest
uv run ruff check . && uv run ruff format --check .
uv run python -m app.cli check-keys                  # 외부 API 키 상태
```

- `uv`가 PATH에 없으면 `py -3 -m uv`로 호출한다
  (실제 경로: `C:\Users\Winyu\AppData\Roaming\Python\Python314\Scripts\uv.exe`)
- **`app.main:app`은 없다.** 모듈 레벨 인스턴스를 두면 임포트만으로 설정 검증이 돌아
  `.env` 없는 CI에서 테스트 수집이 실패한다. 반드시 `--factory`를 쓴다

## 코드 규약

**계층 의존은 한 방향으로만 흐른다.**

```
api  →  services  →  repositories  →  models
            ↘  crawlers        (DB를 모른다)
            ↘  notifications   (DB를 모른다)
```

- **크롤러는 DB를 모른다.** `RawJob` 리스트만 반환한다. 그래서 파서 테스트가 DB 없이 돈다
- **알림 채널은 DB를 모른다.** `send(payload) -> SendResult`만 안다. 이력 기록은 dispatcher 책임
- **API는 repository를 직접 호출하지 않는다.** 트랜잭션 경계는 service에 고정
- **크롤러의 `parse()`는 순수 함수다.** 네트워크·DB를 건드리지 않는다

**동기(sync) 코드로 쓴다.** async를 도입하지 않는다 (ADR-01). 동시성이 필요하면
`ThreadPoolExecutor(max_workers=3)`.

**외부 API 키는 전부 선택값이다.** 키가 없으면 해당 소스만 비활성화되고 앱은 정상 기동한다.
승인 대기 중인 API 때문에 전체가 멈추면 안 된다. `Settings`에 `*_enabled` 프로퍼티로 노출한다.

**주석과 문서는 한국어로 쓴다.** 코드 식별자는 영어.

## 테스트

**TDD로 작업한다.** 테스트를 먼저 쓰고, 실패를 눈으로 확인한 뒤, 통과할 만큼만 구현한다.
테스트가 먼저 실패하는 것을 보지 않았다면 그 테스트가 무엇을 검증하는지 알 수 없다.

- 설정 파일(`pyproject.toml`, systemd 유닛, Nginx conf)은 예외
- 테스트는 `.env`나 OS 환경변수에 의존하면 안 된다 → `Settings(_env_file=None, ...)`로 주입
- DB가 필요한 테스트는 `@pytest.mark.integration`
- `filterwarnings = ["error"]`다. 경고가 뜨면 테스트가 실패한다 — 무시하지 말고 원인을 고친다
- 크롤러 파서는 **골든 파일 테스트**로 쓴다: `tests/fixtures/<site>/`에 실제 응답 스냅샷을
  저장하고 기대 결과와 대조한다. 사이트 마크업이 바뀌면 운영에서 조용히 0건을 수집하기 전에
  CI가 먼저 깨진다

## 하지 말 것

- Kubernetes, Microservices, Kafka, RabbitMQ, Redis, Celery, Elasticsearch, Docker
  (사유는 `세부기획서.md` §1.5)
- Telegram / Discord 알림
- `.env` 커밋 (`.gitignore`에 있음). 시크릿을 로그·터미널에 출력하지 않는다
- 봇 차단을 우회하는 크롤링. 막히면 **보류하고 문서에 사유를 남긴다**
  (User-Agent 위장·로테이션 금지, robots.txt 준수)
- 상시 Playwright 기동. 필요하면 별도 systemd oneshot으로 격리 실행 (RAM 1GB)

## 운영 제약을 항상 염두에 둘 것

**RAM 1GB.** 메모리 예산은 PostgreSQL 250MB / API 120MB / Worker 150MB / Nginx 15MB /
OS 200MB, 여유 250MB다. 응답 크기 상한 5MB, 사이트 병렬 3, `MAX_ITEMS_PER_RUN` 500 같은
상한이 장식이 아니라 이 예산에서 나온 것이다.

**배포는 Linux.** 개행은 LF로 고정돼 있다(`.gitattributes`). 개발이 Windows여도
셸 스크립트나 systemd 유닛에 CRLF가 섞이면 서버에서 깨진다.

## 마일스톤을 끝낼 때

1. DoD 체크박스를 **실제로 실행해서** 확인한다 (통과했다고 쓰기 전에 명령을 돌린다)
2. `세부기획서.md` §10의 해당 DoD를 `[x]`로 갱신한다.
   설계와 다르게 구현했으면 **그 사유를 문서에 남긴다**
3. `README.md`의 마일스톤 상태 표를 갱신한다
4. `memory/CHECKPOINT.md`를 갱신한다 (이전 버전은 `memory/checkpoints/`로 아카이브)
5. 커밋한다. 메시지는 `M<n>: <제목>` 형식, 본문에 설계 결정과 그 이유를 적는다
