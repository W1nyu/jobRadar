# ADR-02 — 1GB VM에서 systemd 직접 배포

- 상태: 채택
- 날짜: 2026-08-23

## 맥락

운영 VM은 2 vCPU, RAM 1GB다. 서비스는 API·워커·PostgreSQL·Nginx 네 프로세스로 충분하며,
클러스터 오케스트레이션이나 메시지 브로커가 필요한 작업량이 아니다.

## 결정

Docker, Kubernetes, Redis, Celery를 도입하지 않는다. systemd 유닛으로 API·워커·백업을 관리하고,
Nginx와 Let's Encrypt를 운영체제 수준에서 사용한다. PostgreSQL은 Unix socket만 사용하고 UFW와
Azure NSG에서는 22/80/443만 허용한다.

## 결과

이미지·데몬 오버헤드 없이 메모리 예산을 지키며, `systemctl`과 journald만으로 재시작과 로그 조사가
가능하다. 환경 재현은 배포 스크립트와 `.env.example`로 보장한다.
