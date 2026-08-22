# Site Recon — 사람인 API (보류)

*확인일: 2026-08-22*

사람인은 [공식 채용공고 API](https://oapi.saramin.co.kr/guide/job-search)를 제공한다. 이 API는
`GET https://oapi.saramin.co.kr/job-search`와 `Accept: application/json`을 사용하며, 이용신청
승인과 앱 등록 뒤 발급된 `access-key`가 필요하다. 공식 안내의 일일 호출 한도는 500회다.

현재 `SARAMIN_ACCESS_KEY`는 미설정이므로 M0의 승인 전제는 충족되지 않았다. 키 없이 요청하거나
예제 키를 사용하지 않으며, `saramin_api.py`와 `sources` 등록도 만들지 않았다. 승인이 완료되면
실제 성공 응답을 골든 파일로 보관한 뒤 별도 변경으로 추가한다.
