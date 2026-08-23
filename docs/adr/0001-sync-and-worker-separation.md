# ADR-01 — 동기 코드와 API·워커 프로세스 분리

- 상태: 채택
- 날짜: 2026-08-22

## 맥락

사용자는 한 명이고 수집 소스는 10개 미만이며 VM 메모리는 1GB다. 웹 요청 처리와 주기 수집을
하나의 프로세스에 섞으면 긴 수집 요청이 관리 UI 응답을 지연시키고, 장애 원인을 분리하기 어렵다.

## 결정

코드는 `async` 대신 동기 SQLAlchemy·httpx 호출로 작성한다. APScheduler와
`ThreadPoolExecutor(max_workers=3)`는 별도 `jobradar-worker` systemd 프로세스에서 실행하고,
FastAPI는 `jobradar-api`로 분리한다.

## 결과

구현과 테스트의 복잡도가 낮고, API와 워커에 메모리 상한을 각각 적용해 장애를 격리할 수 있다.
소스가 크게 늘거나 높은 동시 접속이 필요한 시점에는 비동기 전환을 다시 평가한다.
