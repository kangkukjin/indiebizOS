# 39회차 사전 과제 — 문서 묶음 용어 개정 (2026-10-09)

## 자연어 요구 원문 (훈련자·독립 AI 공통)

docs 폴더에 있는 마크다운 안내 문서 묶음의 용어를 바꿔 줘. 바꿀 용어는 "구독 플랜"→"요금제", "워크스페이스"→"작업 공간" 두 가지고,
단순 부분 문자열 치환이다(예: "워크스페이스들"→"작업 공간들"). 다만 **코드 펜스(```) 안과 인라인 코드(백틱) 안, 링크 대상(`](...)` 괄호 안)은
절대 바꾸지 마**. 제목 줄(#로 시작)도 산문이므로 바뀐다. 제목이 바뀌면 그 제목의 앵커도 바뀌니, 그 앵커를 가리키는 모든 링크
(`파일.md#앵커`, 같은 파일 안의 `#앵커`)의 대상을 새 앵커로 고쳐 줘. 앵커 규칙은: 제목 텍스트를 소문자로 하고, 문자 `. , : ( ) ! ? `` ` `` 를 지운 뒤,
앞뒤 공백을 떼고 공백을 `-`로 바꾼 것. 문서는 전부 같은 폴더에 있고 링크 대상은 `이름.md`, `이름.md#앵커`, `#앵커` 세 모양뿐이다.
바꾸기 전 기준으로 **깨진 링크**(없는 파일, 또는 그 파일에 없는 앵커를 가리키는 것)를 파일·줄 번호·대상과 함께 보고하고, 바꾼 뒤에도
깨진 링크가 늘지 않았는지 확인해 줘. 바뀐 파일만 제자리에 덮어쓰고, 안 바뀐 파일은 건드리지 마.
읽기에 실패한 파일이 하나라도 있으면 **어떤 문서도 쓰지 말고** 실패 파일과 이유만 보고해. apply 가 false 면 계산만 하고 문서는 쓰지 마.
결과는 out 폴더에 report.json(applied, files_total, files_changed 이름 목록, lines_changed_by_file, replacements=산문에서 바꾼 용어 출현 수,
headings_changed=[{file,old,new}], anchors_remapped=대상을 고친 링크 수, broken_links=[{file,line,target}], failed=[{file,reason}],
sha256=쓰기 뒤 파일별 지문)과 summary.md(한 일 요약·깨진 링크 목록)로 저장해. 같은 요청을 다시 실행하면 바뀔 것이 없어야 하고
그때는 파일을 하나도 쓰지 말고 files_changed 가 빈 목록이어야 해. 자료 생성기·oracle·다른 실행자의 코드·결과는 열지 마.

## 선정 이유
이전 38회차까지 다중 파일 **구조 인식 재작성**(코드 보존·앵커 파급·트랜잭션 쓰기·멱등)은 없었다. 데이터 대사·집계가 아닌 "제작·편집" 분야.
정규식 없는 문자열 어휘(split/replace/strip/slicing)로 펜스·인라인 코드·링크 대상을 구분해야 하므로 값 어휘의 표현력을 시험한다.
읽기 실패 변형은 self:read 가 무효 UTF-8 을 실패로 알리는지, 조용히 대체 문자로 읽어 손상된 본문을 쓰는지를 본다(정직성 축).

## 입력 (합성, 생성기 harness/prepare.py — 시드 39)
- `outputs/long_sentence_imagination/2026-10-09_39회차/source/docs/` 36 파일 1,154줄(원본, 불변).
- 훈련자 작업 사본 `trainer/docs`, 변형 사본 `trainer/docs_bad`(guide_07.md 를 무효 UTF-8 바이트로 교체). 독립 AI 는 `agent/docs`·`agent/docs_bad`.
- 함정: api_03.md 의 제목 `` ### `구독 플랜` 객체 `` (인라인 코드 → 제목·앵커 불변), 코드 펜스 안의 링크 모양 텍스트, 산문 안의 "플랜"(단독, 불변),
  깨진 링크 5개(missing.md ×2, old_notes.md, plans.md#없는-절, workspace.md#없는-절).

## 완료 조건·기대값 (oracle/report.json, 독립 Python 구현)
| 항목 | 기대 |
|---|---|
| files_changed | 36 전부 |
| replacements | 329 |
| headings_changed | 45 |
| anchors_remapped | 55 |
| broken_links | 5 (위 목록, 줄 번호 일치) |
| 산출 파일 | oracle/expected_docs 와 36 파일 바이트 동일(sha256) |
| 2차 실행(멱등) | files_changed [], 쓰기 0, sha256 불변, broken_links 는 새 앵커 기준으로 같은 5개 |
| 변형 docs_bad | applied:false, failed=[guide_07.md], 36 파일 sha256 전부 원본과 동일(쓰기 0) |
| apply:false | 문서 sha256 불변, report.json 은 전체 수치 보고 |

작성 조건: 공개 교재(ibl_composition·tools)·문법 전문·describe 만. 상한 60분(01:08 KST 시작), 수정 주기는 횟수·이유 기록.
실행: HTTP `/ibl/execute`, `origin:"training"`, `project_id:"수동모드"`, 입력은 절대 경로. 독립 AI: `/system-ai/chat` background, 같은 대화에 변형 후속.
