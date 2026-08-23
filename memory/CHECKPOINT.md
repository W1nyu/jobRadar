# Checkpoint — jobRadar 채용공고 모니터링 서비스 — 2026-08-23

## Current status

현재 **M12(운영 안정화 · 포트폴리오 마감)를 진행 중**이다. M0~M11은 완료했고, 30일 운영
관측의 시작일은 2026-08-23, 종료 확인일은 2026-09-21이다.

- GitHub 원격: `https://github.com/W1nyu/jobRadar.git`
- 운영 주소: `https://jobradar.my`
- 최신 로컬 검증: `pytest` **132개 통과**, `ruff check .`, `ruff format --check .` 통과
- 아직 남은 M12 DoD: 30일 수동 개입/메모리 관측. README 아키텍처와 ADR 문서 DoD는 완료했다.

## M12에서 추가한 운영 정책

- 채용공고 자동 알림은 APScheduler cron으로 매일 **KST 09:00 한 번**만 발송한다.
- 최근 24시간 신규 매칭을 카카오톡과 Web Push 각각 한 번의 요약으로 보낸다.
- `/admin/notifications`의 수동 발송은 예약 시각과 방해금지 시간을 우회한다.
- 같은 화면에서 카카오·Web Push 채용공고 알림을 함께 켜고 끌 수 있다. 꺼진 상태에서는 자동·수동
  전송 모두 생략된다.
- `docs/operations.md`에 관측 표와 실제 카카오 OAuth 장애 해결 기록을 시작했고,
  `docs/adr/`에 ADR-01~03을 정리했다.

## 운영 반영 전 확인 사항

1. 이 변경을 커밋·push한 뒤 Azure VM에서 `sudo /opt/jobradar/deploy/deploy.sh`를 실행한다.
2. 운영 `.env`에 `NOTIFICATION_LOOKBACK_MINUTES`가 있다면 `1440`으로 바꾼다. 없다면 새 코드의
   기본값(1440)이 적용된다.
3. `systemctl status jobradar-worker`와 `/admin/notifications`에서 알림 상태·수동 버튼을 확인한다.

## Open items

- 사람인 API 승인과 `SARAMIN_ACCESS_KEY`는 계속 대기 상태다. 승인 뒤 실제 성공 응답 골든 파일을
  확보한 후 소스로 추가한다.
- M1의 GitHub Actions 초록불은 원격 Actions 실행 결과를 별도 확인해 기획서의 미완료 DoD를 갱신한다.
- 2026-09-21까지 운영 관측 표에 메모리·수집 실패율·알림 정확도와 모든 수동 개입 사유를 기록한다.

## Archive

M11 완료 시점은 `memory/checkpoints/2026-08-23-m11-complete.md`에 보관했다.
