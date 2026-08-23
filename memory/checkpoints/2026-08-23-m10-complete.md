# Checkpoint — jobRadar 채용공고 모니터링 서비스 — 2026-08-23

## The story so far

Azure VM(2 vCPU / RAM 1GB)에서 24시간 돌릴 개인용 채용공고 모니터링 서비스다.
M0~M12 마일스톤 방식으로 진행하며, 현재 **M10(장애 처리 · 테스트)까지 완료**했다.
다음 작업은 M11(Azure VM 배포)이다.

- 완료 커밋: `7b1efb5` (M1), `9f8d9b9` (M2), `093a3ca` (M3), `cc80637` (M4),
  `7fbfd65` (M5), `e8c0df9` (M6), `56ede96` (M7), `575bb71` (M8), `8bd2527` (M9)
- 현재 검증: `pytest` **125개 통과**, 서비스 계층 커버리지 **84.63%**,
  `ruff check .` 및 `ruff format --check .` 통과
- 워커 수집·저장 한 사이클의 `tracemalloc` Python 피크는 로컬 PostgreSQL E2E에서 **0.67MiB**였다.
  M10 기준 150MiB 이하다.
- 로컬 PostgreSQL은 `127.0.0.1:5432/jobradar`, Alembic revision `d5c91f86a4b2` (head)

### M10에서 실제로 만든 것

```
app/services/crawl_health.py         실패 유형·서킷브레이커·급감 운영 알림 계약
app/services/crawl_runner.py         실패 누적·자동 중지·급감 partial·원자적 실행 이력
app/services/notification_runtime.py Web Push 운영 알림 조립
app/worker/diagnostics.py            tracemalloc 워커 사이클 측정
tests/integration/test_pipeline_e2e.py 수집→매칭→알림 E2E
tests/integration/test_database_recovery.py 끊긴 풀 연결 복구
```

- 연속 실패는 `network`, `rate_limit`, `parser`, `schema`, `authentication`, `unknown`으로
  분류해 `crawl_runs.error_type`에 기록한다. timeout·429·파싱 오류의 서로 다른 기록을 검증했다.
- 한 소스가 5회 연속 실패하면 한 번만 자동 비활성화하고 Web Push 운영 알림을 보낸다. 완전 성공은
  실패 카운터를 0으로 되돌린다.
- 직전 완전 성공보다 수집 건수가 80% 이상 감소하면 공고 종료 처리를 하지 않고 `partial`로 남기며,
  운영 알림을 보낸다.
- `pool_pre_ping=True` 풀에서 끊긴 DBAPI 연결을 재현해 다음 `SELECT 1`이 새 연결로 정상 복구됨을
  로컬 PostgreSQL에서 확인했다.

## Open items

- 사람인 API 승인과 `SARAMIN_ACCESS_KEY`는 계속 대기 상태다. 승인 뒤 실제 성공 응답 골든 파일을
  확보한 후 소스로 추가한다.
- GitHub 원격 저장소가 아직 없어 원격 CI 초록불은 확인하지 못했다.
- 휴대폰 Web Push는 M11에서 `https://jobradar.my` 공개 배포와 인증서 설정 뒤 실제 기기에서
  다시 검증한다.

## Next first action

M11 Azure VM 배포를 시작한다. Ubuntu 보안 초기화, PostgreSQL 튜닝, systemd API·워커 유닛,
Nginx·Let's Encrypt, 백업·복구 리허설, 재부팅 복구와 외부 포트 차단을 DoD 순서대로 검증한다.

## Archive

M10 시작 전 M9 완료 체크포인트는 `memory/checkpoints/2026-08-23-m9-complete.md`에 보관했다.
