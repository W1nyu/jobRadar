# 운영 관측 및 트러블슈팅

개인 단독 사용 범위에서는 30일 관측을 출시 조건으로 두지 않는다. 다만 문제가 생겼을 때 원인을
빠르게 좁힐 수 있도록 아래 확인 절차와 기록 표를 유지한다.

## 매일 확인할 항목

운영 VM에서 다음 명령을 실행해 기록한다. 비밀값과 토큰은 출력하지 않는다.

```bash
systemctl is-active jobradar-api jobradar-worker
free -m
curl --fail https://jobradar.my/readyz
sudo -u postgres psql -d jobradar -c "
  SELECT status, count(*)
  FROM crawl_runs
  WHERE started_at >= now() - interval '24 hours'
  GROUP BY status ORDER BY status;"
journalctl -u jobradar-worker --since '24 hours ago' -p warning --no-pager
```

알림은 매일 KST 09:00에 카카오톡과 Web Push로 각각 한 번의 채용공고 요약만 도착하는지 기록한다.
수동 발송은 `/admin/notifications`에서 즉시 실행하며, 알림이 꺼진 상태에서는 발송되지 않아야 한다.

## 관측 기록

| 날짜(KST) | API/워커 | 메모리 | 24h 수집 실패 | 09:00 카카오 | 09:00 Push | 수동 개입·사유 |
|---|---|---:|---:|---|---|---|
| 2026-08-23 | 정상 (`/readyz` 확인) | 357 MiB 사용, Swap 0 | 관측 시작 전 | 기능 검증 완료 | 기능 검증 완료 | M12 배포·일일 요약 정책 적용, 워커 오류 없음 |

메모리 예산은 PostgreSQL 250MB, API 120MB, 워커 150MB, Nginx 15MB, OS 200MB 및 여유
250MB를 기준으로 한다. `MemoryMax` 또는 OOM, 워커 하트비트 15분 초과, 수집 실패율 급증은
개입 사유로 바로 기록한다.

## 확인 절차

| 증상 | 먼저 확인할 것 | 조치 |
|---|---|---|
| 관리 화면이 열리지 않음 | `systemctl status jobradar-api`, `/readyz`, Nginx error log | API 로그를 확인하고 원인을 수정한 뒤 `sudo systemctl restart jobradar-api` |
| 수집이 멈춘 것 같음 | 대시보드 하트비트, `jobradar-worker` 상태, 최근 `crawl_runs` | 단일 소스 실패면 해당 소스·골든 파일을 확인하고, 워커 자체 실패면 재시작 후 원인을 기록 |
| 카카오 전송 실패 | 알림 화면의 재인증 배너, 워커 로그 | 카카오 개발자 콘솔 URI와 Client Secret을 확인하고 “카카오 다시 연결” 수행 |
| Web Push가 도착하지 않음 | 브라우저 권한·구독 상태·HTTPS 인증서 | `/admin`에서 브라우저 알림을 다시 연결하고 만료된 구독을 교체 |
| 09:00 자동 알림이 없음 | `systemctl status jobradar-worker`, 알림 활성 상태, 신규 매칭 유무 | 알림이 켜져 있고 매칭이 있는데도 없으면 worker 로그와 `notifications` 이력을 보존한 채 조사 |

## 공고 보존·관심도 정책

- 활성 include 키워드가 설정된 경우, 직무를 특정하는 키워드가 하나 이상 일치하고 exclude
  키워드가 없는 공고만 저장한다. `신입`, `인턴`은 보조 조건이므로 단독 일치로는 저장하지
  않는다. include 키워드가 전혀 없는 초기 상태에서만 기존처럼 필터 없이 저장한다.
- 마감일이 있는 공고는 KST 기준으로 **마감일 다음 날 24:00**이 지난 뒤, 매일 00:05 보존
  작업에서 행 자체와 매칭 근거·알림·변경 이력을 함께 삭제한다. 따라서 관리 화면에도 표시되지
  않는다.
- 마감일을 제공하지 않는 소스는 즉시 삭제 시점을 추측하지 않으며, 기존의 3회 연속 미노출 마감
  판정을 적용한다.

## 실제 해결 기록

### 2026-08-23 — 카카오 KOE006 Redirect URI 불일치

카카오 OAuth가 `KOE006`을 반환했다. 카카오 개발자 콘솔의 Redirect URI를 애플리케이션이 실제로
사용한 `https://jobradar.my/oauth/kakao/callback`과 완전히 동일하게 등록해 해결했다. 스킴, 도메인,
경로, 후행 슬래시 중 하나라도 다르면 재발한다.

### 2026-08-23 — 카카오 토큰 발행 실패

카카오 앱에서 Client Secret을 사용하는 상태였지만 서버 환경변수에 없어서 토큰 발행에 실패했다.
`KAKAO_CLIENT_SECRET`을 서버 `.env`에 넣고 API를 재기동한 뒤 연결을 다시 수행해 해결했다. 시크릿은
로그와 저장소에 남기지 않는다.
