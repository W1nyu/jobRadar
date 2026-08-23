# Checkpoint — jobRadar 채용공고 모니터링 서비스 — 2026-08-23

## The story so far

Azure VM(2 vCPU / RAM 1GB)에서 24시간 돌릴 개인용 채용공고 모니터링 서비스다.
M0~M12 마일스톤 방식으로 진행하며, 현재 **M9(알림)까지 완료**했다. 다음 작업은
M10(장애 처리 · 테스트)이다.

- 완료 커밋: `7b1efb5` (M1), `9f8d9b9` (M2), `093a3ca` (M3), `cc80637` (M4),
  `7fbfd65` (M5), `e8c0df9` (M6), `56ede96` (M7), `575bb71` (M8), M9 관련 후속 커밋
  `6e1a6e6`~`e8cf85a`, `f130302` (관리 화면 KST 표시)
- 현재 검증: 전체 `pytest`, `ruff check .`, `ruff format --check .` 통과
- 로컬 PostgreSQL은 `127.0.0.1:5432/jobradar`, Alembic revision `d5c91f86a4b2` (head)
- 로컬 API는 `http://127.0.0.1:8000/admin`에서 실행 중이다.

### M9에서 실제로 검증한 것

- 새 매칭 공고의 Web Push를 브라우저에서 수신하고, 알림 클릭으로 공고 화면 이동을 확인했다.
- 카카오 OAuth를 연결한 뒤 “나와의 채팅” 메시지 수신을 확인했다.
- 활성 소스 5개를 수동 수집해 신규 매칭 20건을 채널별 1건의 배치로 전송했다. 직후 재실행은
  신규 발송 0건으로, `(job_posting_id, channel)` 중복 방지가 동작함을 확인했다.
- 방해금지 시간(KST 23:00~08:00) 큐잉과 종료 뒤 발송은 통합 테스트로 검증했다.
- 카카오 refresh token을 의도적으로 무효화해 Web Push 재인증 안내와 관리자 배너를 확인한 뒤,
  카카오를 다시 연결했다. 현재 토큰 연결 상태이며 재인증 플래그는 해제되어 있다.

### M9 구현과 운영 결정

```
app/notifications/                  DB를 모르는 Web Push·카카오 채널 계약
app/services/dispatcher.py          배치·중복 방지·방해금지·재시도 디스패처
app/services/kakao.py               OAuth 교환·Fernet 암호화·토큰 갱신
app/services/notification_runtime.py 워커용 실제 채널 조립·카카오 실패 Web Push 폴백
app/api/v1/push.py                  로그인 관리자 브라우저 구독 API
app/static/sw.js, push.js           Push 표시·클릭 공고 이동·구독 UI 동작
```

- 채널은 `send(payload) -> SendResult`만 알고 DB를 직접 다루지 않는다. 이력 기록, 재시도,
  구독 비활성화는 dispatcher/runtime 서비스가 담당한다.
- Web Push endpoint는 404/410에서 즉시 비활성화하며, 그 밖의 실패는 5회 누적 때 비활성화한다.
- 카카오 access/refresh token은 Fernet 암호문으로만 저장한다. 갱신 실패 시 재인증 상태를 보존하고,
  가능하면 Web Push로 한 번만 안내한다.
- DB의 모든 시각은 UTC로 유지하고, 관리자 화면은 `Asia/Seoul`로 변환해 `KST (UTC+9)`로 표시한다.

## Open items

- 사람인 API 승인과 `SARAMIN_ACCESS_KEY`는 계속 대기 상태다. 승인 뒤 실제 성공 응답 골든 파일을
  확보한 후 소스로 추가한다.
- GitHub 원격 저장소가 아직 없어 원격 CI 초록불은 확인하지 못했다.
- Azure VM 공개 배포·HTTPS·systemd·백업은 M11 범위다. 로컬 Web Push 검증은 완료했지만 휴대폰용
  Push는 공개 HTTPS 배포 후 실제 기기에서 다시 확인한다.

## Next first action

M10의 첫 DoD인 소스 5회 연속 실패 자동 비활성·운영 알림을 테스트부터 구현한다. 이어서 수집 급감,
오류 분류, 서비스 계층 커버리지, 워커 메모리, DB 자동 복구를 각각 측정·검증한다.

## Archive

M9 완료 전 체크포인트는 `memory/checkpoints/2026-08-23-pre-m9-complete.md`에 보관했다.
