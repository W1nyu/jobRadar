# Site Recon — work24 (구 워크넷, 보류)

*확인일: 2026-08-22*

## 수집 대상

- 목록 URL: `https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo210L01.do`
- 방식: 고용24 공식 채용정보 API, XML 반환
- 필수 요청값: `authKey`, `callTp=L`, `returnType=XML`, `startPage`, `display`
- 티어: 1 (공식 API)

## 실제 호출 결과와 차단 요인

- `.env`의 `WORK24_SERVICE_KEY`를 사용해 목록 3건을 호출했다.
- HTTP 상태는 `200`이지만, 실제 XML은 `GO24/error`로
  `개인회원은 사용할 수 없는 OPEN-API입니다.`를 반환했다.
- 고용24 OPEN-API는 기업회원 전용이며, 서비스 이용허가 후 발급된 인증키가 필요하다.
  따라서 이는 URL·파라미터·키 이름 문제가 아니라 계정 유형/채용정보 API 승인 상태 문제다.

현재 M3에는 고용24 크롤러·골든 파일을 구현하지 않는다. `WORK24_SERVICE_KEY`는 유지하고,
기업회원용 인증키가 확보된 뒤 M7의 다중 소스 확장에서 목록 성공 응답을 골든 XML로 추가한다.
