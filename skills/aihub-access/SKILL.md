---
name: aihub-access
description: AI Hub 데이터셋과 데이터 패키지를 검색하고, 파일 목록을 확인하고, 데이터를 다운로드하거나 TAR 압축 해제·분할 파일 병합을 수행할 때 사용한다.
license: MIT
compatibility: Python 3.10 이상. 다운로드에는 AI Hub API 키가 필요하다.
metadata:
  author: AIHub4All
  version: "0.1.0"
---

# AI Hub 데이터 이용

이 Skill은 [AI Hub](https://aihub.or.kr) 데이터셋과 데이터 패키지를 찾고, 필요한 파일을 내려받아 연구에 사용할 수 있는 상태로 준비하는 작업에 사용한다.

API 조회, 다운로드, 압축 해제, 분할 파일 병합은 Skill에 포함된 Python 도구로 실행한다. 명령 실행 결과를 확인하지 않은 상태에서 다운로드나 처리가 끝났다고 말하지 않는다.

## 기본 원칙

1. **이용 신청 절차를 존중한다.** AI Hub 데이터는 이용 목적을 적은 별도 신청이 필요한 경우가 있다. 이 도구는 신청을 제출하지 않으며, 승인 상태를 조회하지도 않는다. 확인한 Shell 문서에서는 승인 상태 조회 API를 찾지 못했다. 승인 여부를 알고 있다고 가정하지 않는다.
2. **다운로드 거부 결과를 구분한다.** 실제 다운로드가 HTTP 403으로 거부되거나 응답이 승인·권한 문제를 시사하면 도구가 approval_check_recommended를 반환한다. 이는 승인 누락을 확정한 결과가 아니다. 사용자가 AI Hub 웹사이트에서 해당 데이터의 신청 상태를 확인하도록 안내한다. HTTP 401은 우선 API 키 확인 대상으로 본다.
3. **API 키를 보호한다.** AIHUB_API_KEY 환경변수만 사용한다. 사용자에게 채팅으로 키를 붙여 넣도록 요구하거나 키 값을 출력·기록하지 않는다.
4. **대용량 다운로드를 임의로 시작하지 않는다.** 파일 목록과 용량, 출력 위치를 먼저 확인한다. 전체 데이터셋이나 대용량 전송은 사용자의 요청이 명확하지 않으면 시작 전에 범위와 예상 용량을 설명하고 확인을 받는다.
5. **기존 파일을 보존한다.** 도구는 기존 결과를 덮어쓰지 않는다. 압축을 임시 디렉터리에 풀고, 경로 이탈과 특수 TAR 항목을 거부한다. AI Hub가 만든 TAR에는 같은 경로의 바이트동일 파일이 중복해서 들어올 수 있으며, 이 경우 한 번만 추출하고 내용이 다른 중복은 거부한다. 분할 파일은 병합 결과가 정상적으로 만들어진 뒤에만 삭제한다.
6. **모르는 응답 필드를 만들지 않는다.** 메타데이터 API의 완전한 JSON Schema는 확인되지 않았다. 실제 응답에 없는 필드명이나 파일 ID를 추정하지 않는다.

## 작업 절차

### 1. 데이터 탐색

Skill 디렉터리를 기준으로 scripts/aihub.py를 실행한다.

~~~bash
python <skill-directory>/scripts/aihub.py datasets
python <skill-directory>/scripts/aihub.py dataset DATASET_KEY
python <skill-directory>/scripts/aihub.py packages
python <skill-directory>/scripts/aihub.py package PACKAGE_KEY
~~~

사용자가 데이터셋 ID를 주지 않았다면 목록을 조회한다. 목록에서 후보를 좁힌 다음 상세 조회로 파일 ID와 용량을 확인한다. 응답에서 실제로 확인한 식별자만 사용한다.

### 2. 다운로드 범위 정리

다운로드 전에 다음 항목을 확인한다.

- 데이터셋 또는 패키지 ID
- 선택한 파일 ID 또는 전체 파일 여부
- API 응답에 표시된 파일 크기
- 저장 위치
- 예상 전송량과 필요한 저장 공간

용량 정보가 없으면 예상 크기를 알 수 없다고 밝힌다. AI Hub 가이드는 다운로드와 압축 해제 공간을 고려해 데이터 크기의 약 2~3배를 확보하도록 안내한다.

AI Hub의 별도 이용 신청은 사용자 측 절차다. 이 Skill은 승인 상태를 사전 조회하지 않는다. 모든 다운로드 전에 승인 완료 여부를 다시 질문하지 말고, 실제 요청 결과를 확인한다.

### 3. 다운로드

실행 환경에 AIHUB_API_KEY가 설정되어 있는지 확인하되 키 값을 읽거나 출력하지 않는다.

~~~bash
python <skill-directory>/scripts/aihub.py --json download dataset DATASET_KEY \
  --file-ids 123,456 --output-dir ./aihub-data
~~~

- --file-ids를 생략하면 전체 파일을 요청한다.
- 데이터 패키지는 dataset 대신 package를 사용한다.
- --archive-only는 TAR만 다운로드한다.
- --keep-archive는 압축 해제와 병합 후에도 TAR를 보존한다.
- 이미 존재하는 파일은 덮어쓰지 않는다.

--json은 반드시 하위 명령보다 앞에 둔다. 진행 메시지는 표준 오류로, 최종 결과는 표준 출력으로 JSON 한 건을 반환한다.

성공 결과는 ok: true다. 실패하면 종료 코드 1과 함께 ok: false 및 error 객체를 반환한다.

#### 다운로드 실패 처리

오류 객체의 다음 필드를 확인한다.

| 필드 | 의미 | Agent의 다음 조치 |
| --- | --- | --- |
| error.code | 오류 분류 | 오류 종류에 맞춰 안내 |
| error.http_status | HTTP 상태 코드 | 서버 응답과 함께 해석 |
| error.approval_check_recommended | 승인·권한 문제를 의심할 근거가 있음 | AI Hub 웹사이트에서 신청 상태 확인을 요청 |
| error.api_key_check_recommended | API 키 확인 필요 | 환경변수와 키 유효성 확인 |
| error.next_action | 도구가 제안하는 다음 조치 | 사용자에게 구체적으로 안내 |
| error.response_excerpt | 서버 응답 일부 | 민감 정보가 없는지 확인한 뒤 참고 |

approval_check_recommended가 true여도 승인이 없다고 단정하지 않는다. 승인 상태를 조회한 결과가 아니며, AIHub4All은 현재 승인 상태를 API로 확인하지 않는다. 무조건 재시도하지 말고 사용자에게 AI Hub 계정에서 해당 데이터셋 또는 패키지의 신청 상태를 확인하도록 안내한다.

오류가 네트워크 단절이나 일반 서버 오류라면 승인 문제로 몰아가지 않는다. HTTP 401에서는 먼저 API 키를 확인한다.

셸 실행이 불가능하면 사용자가 직접 실행할 수 있도록 명령을 제공한다. 명령의 성공 결과와 실제 파일을 확인하지 않았다면 다운로드가 완료되었다고 말하지 않는다.

### 4. 기존 파일 처리

별도로 받은 TAR 파일:

~~~bash
python <skill-directory>/scripts/aihub.py process /path/to/archive.tar \
  --output-dir ./aihub-data
~~~

이미 압축을 푼 디렉터리의 분할 파일:

~~~bash
python <skill-directory>/scripts/aihub.py merge ./aihub-data
~~~

filename.zip.part0, filename.zip.part1073741824 같은 이름을 처리한다. 숫자는 바이트 오프셋으로 해석한다. 조각의 오프셋이 이어지지 않으면 중단하고 원본 조각을 보존한다.

process 명령은 기본적으로 원본 TAR를 보존한다. 성공 후 삭제가 명시적으로 필요한 경우에만 --remove-archive를 사용한다.

### 5. 결과 보고

작업 후 다음을 구분해 보고한다.

- 다운로드 성공 여부와 파일 크기
- TAR 보존 또는 삭제 여부
- 압축 해제된 출력 디렉터리
- 병합한 파일 목록
- 실패한 단계와 오류 코드
- 사용자가 추가로 확인해야 할 사항

데이터 내부를 실제로 열어보지 않았다면 데이터 내용을 확인했다고 말하지 않는다. 데이터셋별 이용 조건도 그대로 적용된다.

## 참고 자료

- references/api-reference.md: 확인된 API 경로, 인증 방식, 파일 선택 파라미터, 미확인 사항
- 저장소의 openapi/aihub.openapi.yaml: OpenAPI 3.1 명세
- docs/data-processing.md: TAR와 분할 파일 처리 설명
