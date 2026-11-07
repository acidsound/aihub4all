# AIHub4All

**AI Hub를 사람과 AI Agent 모두가 쉽게 이용하도록.**

AIHub4All은 [AI Hub](https://aihub.or.kr)의 데이터셋을 더 쉽게 찾고, 내려받고, 연구에 활용할 수 있도록 돕는 커뮤니티 프로젝트입니다.

사람을 위한 한국어 문서, OpenAPI 3.1 명세, OpenAI·Claude 등에서 사용할 수 있는 Agent Skill, 데이터 다운로드와 파일 가공 도구를 함께 제공합니다.

> AIHub4All은 AI Hub와 별개로 운영되는 비공식 프로젝트입니다. API 키 발급, 데이터 이용 신청과 승인, 데이터별 이용 조건은 AI Hub의 공식 절차를 따릅니다.

## 제공 기능

| 구성 요소 | 내용 |
| --- | --- |
| 한국어 문서 | API 사용법, 데이터 탐색, 다운로드, 파일 처리 안내 |
| OpenAPI 3.1 | AI Hub 공개 Shell에서 사용하는 HTTP API 명세 |
| Agent Skill | 데이터 탐색부터 다운로드와 파일 처리까지 수행하는 공통 Skill |
| Python 도구 | API 조회, TAR 다운로드, 안전한 압축 해제, 분할 파일 병합 |
| 예제와 테스트 | curl 예제, 오프라인 단위 테스트, OpenAPI 검증 |

## API 목록

현재 명세에 포함한 API는 aihubshell v0.6 소스에서 확인한 6개입니다.

| 기능 | 방식 | 경로 | API 키 | 주요 입력 |
| --- | --- | --- | --- | --- |
| 데이터셋 목록 | GET | /info/dataset.do | 불필요 | 없음 |
| 데이터셋 상세·파일 목록 | GET | /info/{datasetKey}.do | 불필요 | datasetKey |
| 데이터 패키지 목록 | GET | /info/datapckage.do | 불필요 | 없음 |
| 데이터 패키지 상세·파일 목록 | GET | /info/pckage/{packageKey}.do | 불필요 | packageKey |
| 데이터셋 파일 다운로드 | GET | /down/0.6/{datasetKey}.do | apikey 헤더 | datasetKey, fileSn |
| 데이터 패키지 파일 다운로드 | GET | /down/pckage/0.6/{packageKey}.do | apikey 헤더 | packageKey, fileSn |

- 서버가 실제로 사용하는 datapckage, pckage 표기는 원래 경로 그대로 유지했습니다.
- fileSn에는 파일 ID를 쉼표로 구분해 전달합니다. 전체 파일을 요청할 때는 all을 사용합니다.
- 메타데이터 응답 필드는 공식 문서에 완전한 JSON Schema가 공개되어 있지 않아, 확인되지 않은 필드를 명세에 임의로 추가하지 않았습니다.
- 승인 상태를 조회하는 API는 확인하지 못했습니다. 다운로드가 거부되면 도구가 AI Hub 웹사이트에서 신청·승인 상태를 확인할 필요가 있다는 힌트를 반환합니다.

자세한 내용은 [API 레퍼런스](docs/api-reference.md)와 [OpenAPI 명세](openapi/aihub.openapi.yaml)를 참고하세요.

## 시작하기

### 1. API 키 준비

[AI Hub](https://aihub.or.kr)에 로그인한 뒤 Open API 안내에 따라 API 키를 발급받습니다. 발급 과정과 키 전달 방식은 AI Hub의 현재 안내를 따릅니다.

데이터셋에 따라 이용 목적을 기재한 별도 신청 절차가 필요할 수 있습니다. AIHub4All은 신청을 대신 제출하거나 승인 상태를 조회하지 않습니다. 실제 다운로드 요청이 거부되면 오류 결과의 안내에 따라 AI Hub 웹사이트에서 해당 데이터의 신청 상태를 확인하면 됩니다.

### 2. API 키 설정

API 키는 환경변수로 전달합니다. 저장소, 스크립트, 명령 기록, Agent 대화에 실제 키를 남기지 마세요.

macOS / Linux:

~~~bash
export AIHUB_API_KEY='발급받은_API_키'
~~~

PowerShell:

~~~powershell
$env:AIHUB_API_KEY = '발급받은_API_키'
~~~

### 3. 데이터 탐색과 다운로드

Python 3.10 이상이 필요하며 외부 패키지는 사용하지 않습니다.

~~~bash
# 데이터셋 목록과 특정 데이터셋의 파일 정보
python skills/aihub-access/scripts/aihub.py datasets
python skills/aihub-access/scripts/aihub.py dataset 593

# 데이터 패키지 목록과 특정 패키지의 파일 정보
python skills/aihub-access/scripts/aihub.py packages
python skills/aihub-access/scripts/aihub.py package 1

# 지정한 파일만 다운로드
python skills/aihub-access/scripts/aihub.py download dataset 593 \
  --file-ids 51937,51938 --output-dir ./aihub-data

# 해당 데이터셋의 전체 파일 다운로드
python skills/aihub-access/scripts/aihub.py download dataset 593 \
  --output-dir ./aihub-data
~~~

파일 ID를 지정하지 않으면 전체 파일을 요청합니다. 실제 다운로드 전에 상세 조회로 파일 ID와 용량을 확인하세요. 대용량 데이터를 처리할 때는 다운로드 크기의 약 2~3배에 해당하는 작업 공간을 확보하는 것이 좋습니다.

기본 동작은 TAR 다운로드 후 압축 해제와 분할 파일 병합까지 수행하는 것입니다. --archive-only를 지정하면 TAR만 저장하고, --keep-archive를 지정하면 처리 후에도 TAR를 남깁니다. 기존 파일은 덮어쓰지 않습니다.

### 4. Agent에서 사용

공통 Agent Skill은 skills/aihub-access에 있습니다. Codex와 Claude Code에 설치하려면 저장소 루트에서 실행합니다.

~~~bash
# 사용자 계정에 두 환경 모두 설치
python scripts/install_skill.py

# 프로젝트 단위로 설치
python scripts/install_skill.py --scope project

# 특정 환경만 설치
python scripts/install_skill.py --targets codex
python scripts/install_skill.py --targets claude
~~~

기본 설치 위치:

| 도구 | 사용자 단위 설치 경로 |
| --- | --- |
| OpenAI Codex | ~/.agents/skills/aihub-access |
| Claude Code | ~/.claude/skills/aihub-access |

다른 Agent Skills 호환 도구에서는 해당 도구의 Skill 검색 경로에 skills/aihub-access를 배치해 사용할 수 있습니다.

Agent가 결과를 안정적으로 해석할 수 있도록 다운로더는 --json 모드를 제공합니다. 이 옵션은 하위 명령보다 앞에 둡니다.

~~~bash
python skills/aihub-access/scripts/aihub.py --json download dataset 593 \
  --file-ids 51937,51938 --output-dir ./aihub-data
~~~

성공 여부는 ok로, 실패 원인은 error.code로 확인합니다. 권한 문제 가능성이 있으면 error.approval_check_recommended가 true로 설정됩니다. 이는 승인 누락을 확정하는 값이 아니라, 사용자가 AI Hub 웹사이트에서 신청 상태를 확인할 필요가 있다는 안내입니다.

## 문서와 명세

| 문서 | 설명 |
| --- | --- |
| [API 레퍼런스](docs/api-reference.md) | API 목록, 인증, 파라미터, 오류 처리 |
| [파일 처리 안내](docs/data-processing.md) | TAR 압축 해제와 .part 파일 병합 |
| [Agent Skill](skills/aihub-access/SKILL.md) | Agent 작업 절차와 안전 조건 |
| [OpenAPI 3.1](openapi/aihub.openapi.yaml) | 도구 연동과 클라이언트 생성용 명세 |
| [기여 안내](CONTRIBUTING.md) | 응답 사례 제공과 문서·코드 기여 방법 |

## 검증 범위

현재 자동 검사는 Python 문법, 오프라인 단위 테스트, OpenAPI 3.1 명세 유효성, CLI 실행 여부를 확인합니다. 실제 AI Hub 계정으로 수행하는 다운로드와 서버 오류 응답 검증은 별도 작업입니다.

메타데이터 응답의 전체 구조, 다운로드 오류의 세부 형식, HTTP Range 지원 여부, 승인 상태 조회 기능은 아직 확인되지 않았습니다. 이 항목들은 실제 응답과 공식 자료를 확보한 뒤 반영합니다.

## 라이선스와 데이터 이용

저장소의 코드와 문서는 MIT License로 배포합니다. 이 라이선스는 AI Hub 데이터셋의 이용·재배포 권한을 부여하지 않습니다. 데이터 이용은 AI Hub의 약관과 데이터셋별 조건을 따릅니다.
