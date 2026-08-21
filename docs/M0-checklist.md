# M0 — 사전 준비 체크리스트

외부 계정·키 발급은 **승인 대기 시간**이 있어서 가장 먼저 처리한다. 코드 작업(M1~)과 병행 가능하다.

> 진행 상황을 이 파일에서 직접 체크하며 갱신한다.

---

## 1. 공공데이터포털 — 워크넷 · 잡알리오 API

**M3의 첫 크롤러가 이 키를 쓴다. 자동 승인이라 가장 빠르다.**

- [ ] [공공데이터포털](https://www.data.go.kr/) 회원가입
- [ ] [한국고용정보원 워크넷 채용정보 API](https://www.data.go.kr/data/3038225/openapi.do) → **활용신청**
- [ ] [공공기관 채용정보 (잡알리오)](https://opendata.alio.go.kr/recruit/list) 확인
- [ ] 마이페이지 → 개발계정 → **일반 인증키(Encoding/Decoding)** 복사
- [ ] `.env`의 `DATA_GO_KR_SERVICE_KEY`에 붙여넣기

**한도**: 개발계정 일 1,000건 (운영계정 신청 시 증량 가능)

**검증** — 키 발급 후 실제 호출이 되는지 확인한다:

```bash
curl -sS "https://apis.data.go.kr/1051000/recruitment/list?serviceKey=<인코딩키>&numOfRows=3&pageNo=1&resultType=json" | head -c 500
```

> 인증키는 Encoding/Decoding 두 종류가 나온다. `curl`에 그대로 붙일 때는 **Encoding 키**를 쓰고, 코드에서 파라미터로 넘길 때는 **Decoding 키**를 쓴다. 이걸 바꿔 넣으면 `SERVICE_KEY_IS_NOT_REGISTERED_ERROR`가 나온다 — M3에서 가장 흔한 삽질 지점이다.

---

## 2. 사람인 채용정보 API — **승인 대기 중**

**M7에서 사용한다. 승인에 수일 걸리므로 지금 신청만 해둔다.**

- [ ] [사람인 API 소개](https://oapi.saramin.co.kr/introduce) → 이용 신청
- [ ] 승인 대기
- [ ] **승인 후**: `.env`의 `SARAMIN_ACCESS_KEY`에 키를 넣는다

**한도**: 일 500건

### 승인이 나면 무엇을 하면 되나

이미 자리를 비워뒀다. **키만 넣으면 된다.**

```bash
# 1. .env에 키 입력
#    SARAMIN_ACCESS_KEY=발급받은키

# 2. 인식됐는지 확인
uv run python -m app.cli check-keys
```

출력이 이렇게 바뀌면 성공이다:

```text
  [설정됨  ] SARAMIN_ACCESS_KEY
              필요 시점: M7 · 사람인 채용정보 API · 승인 절차 필요
```

M7에서 크롤러 파일(`app/crawlers/saramin_api.py`) 1개와 소스 row 1개를 추가하면 붙는다.
**핵심 로직은 건드리지 않는다.**

> 승인 전까지 `SARAMIN_ACCESS_KEY`는 비워둔다. 앱은 정상 기동하고, 사람인 소스만 비활성 상태로 남는다.

---

## 3. 카카오 개발자 앱

**M9의 "나에게 보내기" 알림에 필요하다.**

- [ ] [Kakao Developers](https://developers.kakao.com/) 로그인 → **내 애플리케이션 → 애플리케이션 추가하기**
- [ ] 앱 설정 → 앱 키 → **REST API 키** 복사
- [ ] 제품 설정 → **카카오 로그인 → 활성화 ON**
- [ ] 카카오 로그인 → Redirect URI 등록: `https://<도메인>/oauth/kakao/callback`
- [ ] 카카오 로그인 → **동의항목 → `talk_message`(카카오톡 메시지 전송) 설정**
- [ ] 앱 설정 → 플랫폼 → Web 사이트 도메인 등록: `https://<도메인>`

> 도메인이 아직 없으면 이 항목은 M11 배포 시점에 마무리해도 된다. 앱 생성과 REST API 키 확보까지만 지금 한다.

**참고**: [카카오톡 메시지 REST API](https://developers.kakao.com/docs/latest/ko/kakaotalk-message/rest-api)

---

## 4. 도메인 · DNS

**Web Push는 HTTPS가 필수라서 도메인이 있어야 한다.**

- [ ] 도메인 확보
- [ ] Azure VM 공인 IP에 **A 레코드** 연결
- [ ] `nslookup <도메인>` 으로 해석 확인

---

## 5. Azure VM

- [ ] Ubuntu 24.04 LTS VM 생성 (2 vCPU / RAM 1GB — B1s급)
- [ ] SSH 공개키 등록
- [ ] NSG 인바운드: **22 / 80 / 443만** 허용
- [ ] 공인 IP 고정(Static) 설정 — 동적이면 재부팅 시 DNS가 깨진다
- [ ] `ssh <user>@<IP>` 접속 확인

> 실제 서버 세팅(PostgreSQL, systemd, Nginx)은 **M11**에서 한다. M0에서는 접속만 되면 된다.

---

## M0 완료 기준 (DoD)

- [ ] 공공데이터포털 인증키로 `curl` 호출 시 채용 목록이 반환된다
- [ ] 사람인 API 신청이 **접수 상태**다 (승인 완료는 M7까지 되면 된다)
- [ ] 카카오 앱 REST API 키를 확보했다
- [ ] `https://<도메인>`이 VM IP로 해석된다
- [ ] VM에 SSH 접속된다

---

## 현재 상태

| 항목 | 상태 | 비고 |
|---|---|---|
| 공공데이터포털 키 | ⬜ 대기 | 자동 승인 — 가장 먼저 처리 권장 |
| 사람인 API | ⬜ 신청 필요 | **승인 대기 예정.** 승인 후 `.env`에 키만 넣으면 됨 |
| 카카오 앱 | ⬜ 대기 | M9에서 필요 |
| 도메인 · DNS | ⬜ 대기 | M11에서 필요 |
| Azure VM | ⬜ 대기 | M11에서 필요 |

> M1~M6은 위 항목 중 **공공데이터포털 키만** 있으면 진행된다(M3부터). 나머지는 해당 마일스톤 전까지만 준비되면 된다.
