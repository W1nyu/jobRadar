# Site Recon — data.go.kr / 과기정통부 모집채용

*확인일: 2026-08-22*

## 수집 대상

- 서비스: [과학기술정보통신부_모집채용](https://www.data.go.kr/data/15074635/openapi.do)
- 목록 URL: `https://apis.data.go.kr/1721000/msitrecruitinfo/recruitList`
- 방식: 공공데이터포털 공식 REST API, JSON 또는 XML 반환
- 크롤러 키: `datagokr-msit-recruitment`
- 티어: 1 (공식 API)

필수 요청값은 `ServiceKey`, `pageNo`, `numOfRows`이고, M3에서는 `returnType=json`으로
호출한다. 목록은 `subject`, `viewUrl`, `deptName`, `pressDt`, 첨부파일 정보를 제공한다.

## 실제 호출 결과와 차단 요인

- M3 크롤러는 `.env`의 `MSIT_RECRUITMENT_SERVICE_KEY`만 읽는다. 기존
  `DATA_GO_KR_SERVICE_KEY`와 분리해 다른 공공데이터포털 소스의 권한을 섞지 않는다.
- 공공데이터포털의 Encoding 키는 HTTP 클라이언트가 다시 인코딩하기 전에 URL 디코딩한다.
  인코딩된 값을 그대로 넘기면 HTTP `403`, `SERVICE_KEY_IS_NOT_REGISTERED_ERROR`
  (사유 코드 `30`)가 발생한다.
- 디코딩한 전용 키로 실제 목록을 호출해 HTTP `200`, 공고 10건을 확인했다. 응답은
  `response` 배열 안의 `header`·`body`와, `items[].item`·`files[].file` 중첩 구조다.

## robots·접근 결과

- 공공데이터포털의 인증된 공식 REST API만 사용하므로 HTML 경로에 대한 robots 규칙을
  적용하지 않는다. 목록·상세 웹페이지를 크롤링하지 않는다.
- 키가 없거나 활용 권한이 없으면 이 소스만 비활성화한다. 키를 바꿔가며 재시도하지 않는다.

## 골든 파일

- `tests/fixtures/datagokr_msit/recruit_list_contract.json`: 2026-08-22 실제 성공 응답의
  앞 두 공고를 보관한 축소 골든 스냅샷
- `tests/fixtures/datagokr_msit/service_key_not_registered_2026-08-22.json`: 이중 인코딩 시의
  실제 403 오류 응답
