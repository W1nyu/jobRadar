# Checkpoint — jobRadar 채용공고 모니터링 서비스 — 2026-08-23

## The story so far

Azure VM(2 vCPU / RAM 1GB)에서 24시간 돌리는 개인용 채용공고 모니터링 서비스다.
M0~M12 마일스톤 방식으로 진행하며, 현재 **M11(Azure VM 배포)까지 완료**했다.
다음 작업은 M12(운영 안정화 · 포트폴리오 마감)다.

- GitHub 원격: `https://github.com/W1nyu/jobRadar.git`
- 최신 코드 검증: `pytest` **128개 통과**, `ruff check .`, `ruff format --check .` 통과
- 운영 주소: `https://jobradar.my` (Let's Encrypt 인증서, 자동 갱신 리허설 성공)
- 운영 워커: 기본 키워드 8개와 활성 수집 소스 5개가 시드됐고, 과기정통부 공식 API 수동 수집에서
  공고 10건 저장을 확인했다.

### M11에서 실제로 만든 것과 검증한 것

```
deploy/bootstrap-server.sh            Ubuntu 보안 초기화·Swap·PostgreSQL·UFW·journald
deploy/deploy.sh                      pull·uv sync·마이그레이션·멱등 시드·Nginx·유닛 갱신
deploy/jobradar-*.service             API·워커·PostgreSQL 백업 systemd 유닛
deploy/jobradar-backup.timer          매일 03:00 UTC 백업 타이머
deploy/nginx-jobradar*.conf           TLS·ACME·보안 헤더·로그인 rate limit
deploy/backup.sh                      7일 보존 PostgreSQL custom-format 덤프
deploy/restore-verify.sh              임시 DB 복원·공고 수 대조
app/services/retention.py             종료 공고·변경 이력의 일일 보존 정책
app/api/health.py                     DB까지 확인하는 /readyz
```

- API·워커는 systemd `enabled`이며, VM 재부팅 뒤 1분 이내 두 유닛과 워커 스케줄러가 자동 복구됐다.
- `free -h`에서 사용 메모리 357MiB, Swap 2GiB(미사용)를 확인했다.
- 백업 덤프를 `jobradar_restore_verify` 임시 DB에 복원해 `job_postings` 0건이 원본과 일치함을 확인했다.
- 외부 TCP 연결 검사에서 PostgreSQL 5432 포트는 닫혀 있었고, Azure NSG·UFW는 22·80·443만 허용한다.
- Let’s Encrypt 인증서 발급과 `certbot renew --dry-run`이 성공했다.
- 운영 카카오 OAuth 토큰 저장, 카카오톡 테스트 메시지 실제 수신, Web Push 구독과 실제 휴대폰 수신을
  사용자와 함께 확인했다.

## Open items

- 사람인 API 승인과 `SARAMIN_ACCESS_KEY`는 계속 대기 상태다. 승인 뒤 실제 성공 응답 골든 파일을
  확보한 후 소스로 추가한다.
- M12의 30일 운영 관측은 아직 시작 단계다. 메모리·수집 실패율·알림 정확도를 주기적으로 기록한다.
- M1의 GitHub Actions 초록불은 원격 Actions 실행 결과를 별도 확인해 기획서의 미완료 DoD를 갱신한다.

## Next first action

M12 운영 관측 기준을 정하고, README 아키텍처·데이터 흐름·운영 트러블슈팅 문서를 포트폴리오 수준으로
마감한다. 30일 동안에는 수동 개입과 원인을 모두 기록한다.

## Archive

M11 시작 전 M10 완료 체크포인트는 `memory/checkpoints/2026-08-23-m10-complete.md`에 보관했다.
