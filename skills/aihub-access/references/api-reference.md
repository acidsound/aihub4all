# AI Hub API 요약

이 문서는 AIHub4All Skill에서 사용하는 API의 요약이다. 경로는 제공된 aihubshell v0.6 소스에서 확인한 값이다.

기본 주소: https://api.aihub.or.kr

## API 목록

| 기능 | 요청 | 인증 | 입력 |
| --- | --- | --- | --- |
| 데이터셋 목록 | GET /info/dataset.do | 없음 | 없음 |
| 데이터셋 상세 | GET /info/{datasetKey}.do | 없음 | datasetKey |
| 데이터 패키지 목록 | GET /info/datapckage.do | 없음 | 없음 |
| 데이터 패키지 상세 | GET /info/pckage/{packageKey}.do | 없음 | packageKey |
| 데이터셋 다운로드 | GET /down/0.6/{datasetKey}.do | apikey 헤더 | datasetKey, fileSn |
| 데이터 패키지 다운로드 | GET /down/pckage/0.6/{packageKey}.do | apikey 헤더 | packageKey, fileSn |

메타데이터 조회는 Shell 소스에서 API 키 없이 호출한다. 다운로드는 apikey 헤더를 사용한다.

## 파일 선택

fileSn 쿼리 파라미터:

- 전체 파일: fileSn=all
- 특정 파일: fileSn=12345
- 여러 파일: fileSn=12345,67890

Shell 가이드의 사용자 인터페이스 용어는 filekey지만, 확인한 HTTP 요청 파라미터는 fileSn이다.

## 이용 신청과 승인 확인

AI Hub 데이터는 이용 목적을 적은 별도 신청이 필요할 수 있다. 신청·승인 상태 조회 API는 확인한 Shell 소스와 공식 안내에서 찾지 못했다. 다른 비공개·미문서화 API가 없다고 단정하는 것은 아니다.

다운로드가 거부되면 스크립트의 JSON 오류 결과를 확인한다.

- approval_check_recommended: true: 서버의 HTTP 403 또는 응답 문구가 승인·권한 문제를 시사한다. AI Hub 웹사이트에서 신청 상태를 확인하도록 사용자에게 안내한다. 승인 누락을 확정한 값은 아니다.
- api_key_check_recommended: true: API 키 설정과 유효성을 먼저 확인한다.

## 확인된 서버 동작

2026-11 실제 응답으로 확인한 내용이다.

- 메타데이터 GET 요청은 HTTP 502 상태 코드와 함께 완전한 텍스트 본문을 반환한다. 본문이 정상 응답과 동일하므로 도구는 생성된 오류 페이지가 아닌 502/503을 성공으로 처리한다. User-Agent, apikey, Referer와 무관하게 같은 동작이 관측되었다.
- 다운로드는 apikey 헤더 인증 후 `stream.aihub.or.kr`의 임시 UUID 경로로 302 리다이렉트되어 스트리밍된다. 인증 실패 시 502 상태 코드와 `인증실패, 권한이 거부되었습니다` 본문이 온다.
- HTTP Range는 지원하지 않는다. Range 헤더를 보내도 전체 본문을 스트리밍한다. HEAD 요청은 403을 반환한다.
- 다운로드로 받는 TAR에는 같은 경로의 바이트동일 파일이 중복해서 들어올 수 있다. 도구는 중복을 한 번만 추출하고 내용이 다른 중복은 오류로 처리한다.

## 근거와 한계

- 공식 안내: https://aihub.or.kr/devsport/apishell/list.do?currMenu=528&topMenu=100
- 메타데이터 응답의 전체 JSON 구조는 공개 명세로 확인되지 않았다.
- 오류 응답 본문과 Content-Type은 일부 확인되었다(Range 미지원, HEAD 403, 인증 실패 본문). 승인 상태 조회 기능은 확인하지 못했다.
