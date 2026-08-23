# Checkpoint — jobRadar 채용공고 모니터링 서비스 — 2026-08-23

## 완료 상태

사용자가 요청한 범위에서 **M1~M12 개발·배포 작업이 완료**됐다. 개인 단독 사용이라 M12의 30일
운영 관측은 완료 조건에서 제외했다. M0의 사람인 API 승인은 선택 소스의 외부 절차로 별도 보류다.

- GitHub 원격: `https://github.com/W1nyu/jobRadar.git`
- 운영 주소: `https://jobradar.my`
- 최신 로컬 검증: `pytest` **132개 통과**, `ruff check .`, `ruff format --check .` 통과
- GitHub Actions: 실행 `32621411424`에서 PostgreSQL 16·마이그레이션·lint·format·전체 테스트 통과
- 운영 VM: API·워커 `active`, `/readyz` 정상, 자동 채용공고 알림 `KST 09:00` cron 확인

## 완성된 알림 정책

- 자동 채용공고 알림은 카카오톡·Web Push로 매일 KST 09:00 한 번만 요약 발송한다.
- 수동 발송은 `/admin/notifications`에서 예약 시각과 방해금지를 우회해 즉시 실행한다.
- 같은 화면에서 두 채널의 채용공고 알림을 함께 켜고 끈다. 꺼진 상태에서는 자동·수동 전송을
  모두 생략한다.

## 문서

- 아키텍처·실행 방법: `README.md`
- 운영 절차·실제 장애 해결 기록: `docs/operations.md`
- 기술 결정: `docs/adr/`

## 선택적 후속 작업

사람인 API 승인은 외부 서비스 절차라 계속 대기 상태다. 승인이 나면 성공 응답 골든 파일을 확보해
별도 소스로 추가할 수 있지만, 현재 운영 기능과 완료 기준에는 포함하지 않는다.

## Archive

M12 진행 시점은 `memory/checkpoints/2026-08-23-m12-in-progress.md`에 보관했다.
