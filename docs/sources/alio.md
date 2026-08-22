# Site Recon — 잡알리오 공공기관 채용정보

*확인일: 2026-08-22*

## 수집 대상

- 서비스: [잡알리오 채용정보](https://opendata.alio.go.kr/new/odaApiMng/recrutInquiryList.do)
- 목록 URL: `https://opendata.alio.go.kr/new/odaApiMng/recrutInquiryAjaxList.do`
- 방식: 공개 채용정보 화면이 사용하는 JSON 목록
- 크롤러 키: `alio-recruitment`
- 티어: 2 (공개 JSON)

목록은 공시기관, 제목, 공고번호, 시작·종료일, 고용형태, 경력구분, 근무지, 원문 지원 URL을
제공한다. 현재 확인한 경로는 GET 조회도 HTTP 200으로 지원하며, 진행 중 공고(`ongoingYn=Y`)
20건만 요청한다.

## 키·경로 결정

- 이전 `apis.data.go.kr/1051000/recruitment/list`의 403 코드 30은 공공데이터포털 키가
  해당 경로에 등록되지 않았다는 응답이었다. 잡알리오 공식 포털의 공개 채용목록 경로와는
  다른 경로다.
- 이 크롤러는 공개 목록 요청에 `ALIO_SERVICE_KEY`를 보내지 않는다. DB의 `sources.config`에도
  키를 저장하지 않는다.
- 로그인 뒤 발급·활용신청하는 별도 Open API의 정확한 호출 명세는 확인하지 못했으므로, 그
  인증 API는 추측해 구현하지 않는다. 현재 `.env`의 `ALIO_SERVICE_KEY` 필드는 보존한다.

## robots·접근 결과

- `https://opendata.alio.go.kr/robots.txt`는 robots 지시문이 아닌 서비스 HTML을 반환했다.
  따라서 그 경로에서 별도 robots 정책을 확인할 수 없었다.
- 공개 채용 조회 화면과 목록 JSON 모두 식별 User-Agent로 HTTP 200이었다. 로그인, 상세
  API 신청 화면, 차단 우회는 사용하지 않는다.

## 운영 제한과 검증

- 분당 10회, 진행 중 최신 20건, 첫 페이지 1회로 제한한다.
- `tests/fixtures/alio/recruit_list_2026-08-22.json`은 실제 목록 첫 공고에서 파서 계약에
  필요한 필드만 남긴 골든 스냅샷이다.
- 2026-08-22 실제 단발 실행에서 HTTP 200, 20건을 수집했다.
