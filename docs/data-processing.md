# 다운로드 파일 처리

AI Hub 다운로드 API는 aihubshell에서 TAR 아카이브로 처리됩니다. 압축 안에는 원래 디렉터리 구조가 들어 있으며, 큰 파일은 바이트 오프셋을 붙인 여러 조각으로 나뉠 수 있습니다.

~~~text
dataset/
  training/
    source.zip.part0
    source.zip.part1073741824
    source.zip.part2147483648
~~~

AIHub4All은 다음 순서로 처리합니다.

1. TAR 아카이브를 다운로드합니다.
2. 임시 디렉터리에 압축을 풉니다.
3. 같은 파일명에 속한 .part 조각을 찾습니다.
4. 파일명 끝의 숫자를 바이트 오프셋으로 해석해 순서대로 연결합니다.
5. 병합 결과를 정상적으로 기록한 뒤 원본 조각을 삭제합니다.

## 저장 공간

AI Hub 가이드는 다운로드 파일과 압축 해제 결과가 함께 존재할 수 있으므로 데이터 크기의 약 2~3배에 해당하는 여유 공간을 확보하도록 안내합니다. 실제 필요 용량은 데이터 구성과 선택한 파일에 따라 달라집니다.

전체 데이터셋을 받기 전에 상세 조회로 파일 목록과 용량을 확인하세요. 연구에 필요한 파일만 선택할 수 있다면 fileSn에 해당 파일 ID를 지정하는 편이 낫습니다.

## 분할 파일 병합 규칙

.part 뒤에 붙는 숫자는 단순한 조각 순번이 아니라 바이트 오프셋으로 취급합니다.

예를 들어 다음 파일은 순서대로 연결합니다.

~~~text
sample.zip.part0
sample.zip.part1048576
sample.zip.part2097152
~~~

병합 과정에서는 다음을 확인합니다.

- 첫 조각의 오프셋은 0이어야 합니다.
- 다음 조각의 오프셋은 앞 조각까지 기록한 전체 바이트 수와 일치해야 합니다.
- 병합 대상 파일이 이미 있으면 덮어쓰지 않습니다.
- 오프셋이 빠졌거나 중복·불일치하면 병합을 중단하고 원본 조각을 보존합니다.
- 임시 파일에 병합한 뒤 결과 파일로 이동합니다. 성공한 경우에만 원본 조각을 삭제합니다.

## 안전한 압축 해제

다운로드한 TAR를 바로 현재 디렉터리에 풀지 않고 임시 디렉터리에서 검사·압축 해제합니다.

다음 항목은 거부합니다.

- 절대 경로 또는 상위 디렉터리로 벗어나는 경로
- 심볼릭 링크와 하드 링크
- 일반 파일·디렉터리가 아닌 특수 TAR 항목
- 동일 경로에 대한 중복 파일

압축 형식이 바뀌어 링크나 특수 항목이 필요해지면 검증을 거쳐 처리 정책을 수정해야 합니다.

## 사용 방법

### 다운로드와 동시에 처리

~~~bash
python skills/aihub-access/scripts/aihub.py download dataset 593 \
  --file-ids 51937,51938 --output-dir ./aihub-data
~~~

### TAR만 다운로드

~~~bash
python skills/aihub-access/scripts/aihub.py download dataset 593 \
  --archive-only --output-dir ./archives
~~~

### 기존 TAR 처리

~~~bash
python skills/aihub-access/scripts/aihub.py process ./archives/dataset.tar \
  --output-dir ./aihub-data
~~~

process 명령은 기본적으로 원본 TAR를 보존합니다. 처리가 끝난 뒤 TAR를 삭제하려는 경우에만 --remove-archive를 명시합니다.

### 이미 압축을 푼 디렉터리의 조각 병합

~~~bash
python skills/aihub-access/scripts/aihub.py merge ./aihub-data
~~~

기존 파일과 충돌하면 자동으로 덮어쓰지 않습니다. 기존 파일 내용을 확인한 뒤 직접 이름을 변경하거나 다른 출력 디렉터리를 지정하세요.
