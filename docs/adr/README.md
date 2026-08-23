# Architecture Decision Records

프로젝트의 주요 선택과 그 이유를 짧게 남긴다. 형식은 `상태 → 맥락 → 결정 → 결과`로 통일한다.
나중에 기술 선택을 바꾸면 기존 기록을 고치기보다 새 ADR로 대체 관계를 남긴다.

| ADR | 결정 |
|---|---|
| [ADR-01](./0001-sync-and-worker-separation.md) | 동기 코드와 API·워커 프로세스 분리 |
| [ADR-02](./0002-systemd-over-containers.md) | 1GB VM에서 systemd 직접 배포 |
| [ADR-03](./0003-daily-digest-and-notification-control.md) | KST 09:00 일일 요약, 수동 즉시 발송, 전역 수신 제어 |
