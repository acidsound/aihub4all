# AI Hub API 레퍼런스

이 문서는 AI Hub에서 제공하는 aihubshell v0.6 소스와 공식 사용 안내를 바탕으로 HTTP 요청을 정리한 것입니다. AI Hub의 전체 내부 API를 보장하거나 공식 API 계약을 대체하지 않습니다.

| 항목 | 값 |
| --- | --- |
| 기본 주소 | https://api.aihub.or.kr |
| 다운로드 경로 버전 | 0.6 |
| 공식 사용 안내 | [AI Hub API Shell](https://aihub.or.kr/devsport/apishell/list.do?currMenu=528&topMenu=100) |
| Shell 가이드 | [aihubshell 가이드 PDF](https://www.aihub.or.kr/static/pdf/aihubshell_%EA%B0%80%EC%9D%B4%EB%93%9C.pdf) |

## API 목록

| 구분 | 기능 | 방식 | 경로 | 인증 |
| --- | --- | --- | --- | --- |
| 데이터셋 | 목록 조회 | GET | /info/dataset.do | 없음 |
| 데이터셋 | 상세 및 파일 트리 조회 | GET | /info/{datasetKey}.do | 없음 |
| 데이터 패키지 | 목록 조회 | GET | /info/datapckage.do | 없음 |
| 데이터 패키지 | 상세 및 파일 트리 조회 | GET | /info/pckage/{packageKey}.do | 없음 |
| 다운로드 | 데이터셋 파일 | GET | /down/0.6/{datasetKey}.do | apikey 헤더 |
| 다운로드 | 데이터 패키지 파일 | GET | /down/pckage/0.6/{packageKey}.do | apikey 헤더 |

datapckage, pckage는 오타처럼 보이지만 확인된 서버 경로이므로 명세에서도 그대로 사용합니다.

## 인증

aihubshell은 다운로드 요청에만 다음 헤더를 붙입니다.

~~~http
apikey: 발급받은_API_키
~~~

목록 및 상세 조회 요청에는 이 헤더를 넣지 않습니다. 셸 소스에는 키 검증 URL 상수가 선언되어 있지만, 여기서 정리한 요청 흐름에서는 호출하지 않습니다. 확인되지 않은 키 검증 API를 별도로 가정하지 않았습니다.

실제 키는 AIHUB_API_KEY 환경변수에 설정합니다. 키를 URL, 소스 코드, 로그, Agent 대화에 기록하지 마세요.

## 데이터셋 조회

### 데이터셋 목록

~~~bash
curl --fail-with-body 'https://api.aihub.or.kr/info/dataset.do'
~~~

### 데이터셋 상세 및 파일 트리

~~~bash
curl --fail-with-body 'https://api.aihub.or.kr/info/593.do'
~~~

공식 Shell 안내는 데이터셋 정보에 파일명, 용량, 파일 식별자, 안내 정보 등이 포함된다고 설명합니다. 다만 전체 JSON 응답 스키마는 공개 문서에서 확인되지 않았습니다. 실제 응답을 수집하기 전까지 필드명과 중첩 구조를 추정하지 않습니다.

## 데이터 패키지 조회

### 데이터 패키지 목록

~~~bash
curl --fail-with-body 'https://api.aihub.or.kr/info/datapckage.do'
~~~

### 데이터 패키지 상세 및 파일 트리

~~~bash
curl --fail-with-body 'https://api.aihub.or.kr/info/pckage/1.do'
~~~

패키지 API도 응답 구조를 임의로 단정하지 않습니다.

## 다운로드

데이터셋과 패키지 다운로드 요청은 apikey 헤더와 fileSn 쿼리 파라미터를 사용합니다.

| 파라미터 | 위치 | 필수 여부 | 설명 | 예시 |
| --- | --- | --- | --- | --- |
| datasetKey | 경로 | 필수 | 데이터셋 식별자 | 593 |
| packageKey | 경로 | 필수 | 데이터 패키지 식별자 | 1 |
| fileSn | 쿼리 | 선택 | 쉼표로 구분한 파일 ID. 전체 파일은 all | 51937,51938 또는 all |
| apikey | 헤더 | 필수 | AI Hub에서 발급받은 API 키 | apikey: ... |

### 데이터셋 파일

~~~bash
curl --fail-with-body --location \
  --header "apikey: $AIHUB_API_KEY" \
  --output dataset-593.tar \
  'https://api.aihub.or.kr/down/0.6/593.do?fileSn=51937,51938'
~~~

전체 파일을 요청하려면 fileSn=all을 사용합니다.

### 데이터 패키지 파일

~~~bash
curl --fail-with-body --location \
  --header "apikey: $AIHUB_API_KEY" \
  --output package-1.tar \
  'https://api.aihub.or.kr/down/pckage/0.6/1.do?fileSn=all'
~~~

다운로드 응답은 aihubshell 흐름에서 TAR 아카이브로 처리됩니다. 다만 실제 응답의 Content-Type, 오류 응답 형식, Range 요청 지원 여부는 별도 검증이 필요합니다.

## 이용 신청 및 승인 상태

AI Hub 데이터는 이용 목적을 적어 별도 신청해야 하는 경우가 있습니다. 기존 AI Hub 이용 절차에 해당하는 내용이므로 다운로드 전에 필요한 신청을 진행해야 한다는 점을 전제로 합니다.

현재 확인한 aihubshell 소스와 공식 Shell 안내에서는 **신청·승인 상태를 조회하는 API를 확인하지 못했습니다.** 이것은 다른 문서화되지 않은 API가 존재하지 않는다는 뜻은 아닙니다.

AIHub4All 다운로더는 우선 실제 다운로드 요청을 보냅니다. 서버가 HTTP 403을 반환하거나 응답 본문에서 승인·권한 문제를 시사하면 다음 필드를 설정합니다.

- error.approval_check_recommended: true
- error.next_action: AI Hub 웹사이트에서 해당 데이터셋 또는 패키지의 신청 상태를 확인하라는 안내

이 값은 승인 누락을 판정한 결과가 아닙니다. API 키나 계정 권한 등 다른 원인일 수도 있으므로 서버 응답을 함께 확인해야 합니다. HTTP 401은 우선 API 키 확인 대상으로 분류합니다.

### Agent용 JSON 결과

~~~bash
python skills/aihub-access/scripts/aihub.py --json download dataset 593 \
  --file-ids 51937,51938 --output-dir ./aihub-data
~~~

승인 확인이 필요한 것으로 분류된 실패의 예시입니다. 아래 응답은 AI Hub의 실제 오류 응답을 재현한 것이 아니라 AIHub4All 도구의 출력 형식을 설명합니다.

~~~json
{
  "ok": false,
  "command": "download",
  "error": {
    "code": "download_access_denied",
    "message": "AI Hub 다운로드 요청이 거부되었습니다.",
    "http_status": 403,
    "approval_check_recommended": true,
    "api_key_check_recommended": false,
    "next_action": "AI Hub 계정에서 해당 데이터셋 또는 패키지의 신청·승인 상태를 확인하세요. AIHub4All은 현재 승인 상태를 API로 조회하지 않습니다."
  }
}
~~~

## MCP 메타데이터 API

AI Hub는 aihubshell 다운로드 API와 별도로, 데이터셋 메타데이터를 JSON으로 조회하는 MCP용 API를 운영합니다. AI Hub 공식 MCP 서버 구현(github.com/aihub-git/AIHub-MCP)에서 확인한 내용이며, 공식 안내 페이지도 같은 API key로 aihubShell과 MCP 모두 사용 가능하다고 안내합니다.

기본 주소: https://aihub.or.kr/mcp/

인증: 모든 요청에 `X-API-KEY` 헤더로 AI Hub API key를 전달합니다. key가 없으면 `{"result":"FAIL","message":"API 키가 없습니다. ..."}` 실패 응답이 옵니다.

### API 목록

| 기능 | 요청 | 입력 |
| --- | --- | --- |
| 데이터셋 검색 | GET /mcp/dataSetList.do | searchKeyword, srchDataRealmCode, srchdataClCode, srchDataClDetailCode, srchOneDataTy, srchOneDataCnstcYear, srchDetailCnd, firstIndex(오프셋), recordCountPerPage(페이지당 건수) |
| 데이터셋 건수 | GET /mcp/dataSetCnt.do | 검색과 동일한 필터(페이징 제외) |
| 데이터셋 상세 | GET /mcp/dataSetDetail.do | dataSetSn |
| 설명서·가이드 보유 목록 | GET /mcp/getDataSetsWithGuide.do | srchGuideFileSe(ANY, FILESE001=데이터 설명서, FILESE002=구축활용가이드), firstIndex, recordCountPerPage |

### 응답 형식

공통 envelope:

~~~json
{
  "result": "SUCCESS",
  "data": { ... },
  "totalCount": {"총 개수": 412}
}
~~~

실패 시 `result`가 `FAIL`이고 `message`가 들어옵니다. 일부 실패는 `guideUrl`을 함께 반환합니다.

데이터 필드는 `{value, label, description}` 래퍼로 감싸져 오며, AIHub4All 도구는 `value`만 풀어서 보여줍니다. 상세 응답의 단위 섹션은 한국어 키를 사용합니다(예: `주요 정보`, `데이터 개요`, `메타데이터 구조표`, `데이터 성능지표`, `어노테이션 포맷 및 데이터 구조`, `구축 업체`, `파일 목록(API 다운로드)`, `데이터 설명서`, `구축활용가이드`).

### CLI 사용

~~~bash
python skills/aihub-access/scripts/aihub.py --json search --keyword "감성" --limit 5
python skills/aihub-access/scripts/aihub.py --json count --keyword "음성"
python skills/aihub-access/scripts/aihub.py --json detail 71349
python skills/aihub-access/scripts/aihub.py --json describe "감성 및 발화 스타일 동시 고려 음성합성 데이터"
python skills/aihub-access/scripts/aihub.py --json guides --type manual --limit 10
~~~

### 확인 상태

| 항목 | 근거 | 상태 |
| --- | --- | --- |
| 경로·파라미터 | AIHub-MCP 서버 소스 | 확인 |
| X-API-KEY 인증 | AIHub-MCP 서버 소스 | 확인 |
| envelope·Field 래퍼 구조 | AIHub-MCP 서버 DTO | 확인 |
| 실제 성공 응답 | 라이브 검증 | 미확인 — aihubshell 용으로 발급받은 key로는 "잘못된 접근입니다" 실패만 관측됨(2026-11). 성공 응답 사례를 확보한 뒤 필드를 더 반영합니다. |

## 확인 상태

| 항목 | 근거 | 상태 |
| --- | --- | --- |
| 목록·상세·다운로드 경로 | 제공된 aihubshell v0.6 소스 | 확인 |
| 다운로드 apikey 헤더 | Shell 소스 및 공식 안내 | 확인 |
| 파일 선택 fileSn | Shell 소스 | 확인 |
| 전체 파일 선택 fileSn=all | Shell 동작 | 확인 |
| 데이터 이용 신청 절차 | AI Hub 사용자 안내 | 별도 절차 필요 |
| 승인 상태 조회 API | 확인한 Shell 소스·공식 안내 | 확인하지 못함 |
| 메타데이터 JSON 전체 구조 | 완전한 공개 스키마 미확인 | 미확인 |
| 오류 응답의 전체 구조 | 실제 응답 사례 미수집 | 미확인 |
| Content-Type 및 Range 지원 | 실응답 검증 전 | 미확인 |

확인되지 않은 항목은 응답 사례를 확보한 뒤 명세와 테스트에 추가합니다.
