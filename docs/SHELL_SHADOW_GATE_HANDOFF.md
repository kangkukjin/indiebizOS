# 셸 그림자 관문 — 설계 핸드오프 (2026-09-05)

## 뿌리

ep2862·ep2866(`#repair` 두 주행) 실측: execute_ibl 9·11건 대 Bash 23·27건. Bash 의 3분의 2가
grep·sed -n·cat 이었고(전부 `[self:grep]`·`[self:read]` 로 표현되는 일), 127줄 블록 제거는 `/tmp` 파이썬
스크립트로 갔다(쓰기 원장·RED 격리·해마 밖 — 증류가 "실행에 없던 합성"으로 스킵). 절단 표지(truncated)
직후 셸로 갈아타는 것도 두 주행 공통.

규칙은 있었다 — `claude_code.TOOL_POLICY` 산문 "IBL 등가물이 있는 일을 Bash 로 하지 마라". 산문은 실측으로
무효였다. Read·Grep 네이티브를 **이름 골라** 하드 차단했더니 물이 Bash 로 옮겨간 것뿐(손으로 고른 스윕은 샌다).
선택 순간에 Bash 가 IBL 의 상위집합(앞뒤 줄·줄번호·꼬리·줄범위 편집)이고 결과는 봉투 없이 원문으로 오는데,
IBL 의 이득(해마·타입검사·원장)은 그 순간에 보이지 않는다.

## 처방 세 갈래 (전부 집행)

### 1. 관문 — 어휘에서 파생
- 낱말 yaml 에 `shell_shadow:` 블록: `heads`(`"명령 [필수 flag]"`), `argmap`(셸 인자→param: positional·flags·
  flags_by_head·positional_by_head·range_script·path_params·skeleton·cwd_default[_heads]), `native`(같은 일을 하는
  네이티브 도구), `redirect`(`>` 리다이렉션), `python_write`(파일을 쓰는 인라인 파이썬·임시 스크립트).
- 빌드가 `data/shell_shadow.json` 으로 파생(`--check` 가 신선도 대조). 낱말이 은퇴하면 그림자도 빠진다.
- 판정기 `backend/base/shell_shadow_gate.py`(표준 라이브러리만 — 훅은 Bash 호출마다 새 프로세스):
  - Claude Code 실행기: `--settings` 인라인 JSON 으로 PreToolUse 훅(`Bash|Write|Edit|MultiEdit|NotebookEdit`).
    거절 = exit 2 + stderr 사유(실측 CLI 2.1.260, bypassPermissions 아래서도 막힌다). 정책 지문에 훅 포함 → 옛 세션 fresh.
  - in-process 프로바이더: `handler.run_command` 가 같은 `judge_shell` 로 거절(`error_type: shell_shadow`).
- 거절문 = **그 명령을 옮긴 IBL 문장** + 다른 param 목록 + "셸은 낱말 없는 일에만". 다음 걸음이 IBL 안에 있게.
- 셸의 몫(통과): git·pytest·빌드·등록 스크립트·프로세스 조회·파이프 안의 필터(stdin 을 받는 grep/head)·
  임시 폴더(/tmp·$TMPDIR)의 읽기/쓰기·파일을 쓰지 않는 인라인 파이썬.
- 관문 코드에 낱말 이름이 없다(헌법 '표준/사전 경계' — 내용어는 데이터로만). 시험 S1 이 이를 고정.

### 2. 낱말을 상위집합으로 — 도망갈 이유 제거
- `[self:grep]{context: N, ignore_case: true}` — grep -A/-B/-C·-i 의 자리(items `문맥` 필드, text 는 grep -C 모양).
- `[self:read]{numbered: true, tail: N}` — cat -n·tail -n 의 자리.
- `[self:edit]{start_line, end_line, new_string}` — 줄 범위 교체·삭제(old_string 불요, 함께 주면 자리 확인).
  ep2862 가 /tmp 스크립트를 짠 이유(127줄 되타이핑)를 없앤다. 구현 `fs_edit.replace_line_range`.

### 3. 절단 표지에 다음 걸음
- `ibl_honesty.TRUNCATED_NEXT_STEP` 한 줄을 승격 경고(`describe_promoted`)·병렬 가지 경고·MCP 경계 꼬리 절단·
  grep 자체 절단문이 함께 쓴다 — "같은 낱말 안에서 좁혀라, 셸로 갈아타지 말 것".

## 하지 않은 것
- 지표·카운터 추가(seam/carried 는 값 되찍기 왕복만 잡는 하한 — 이 두 주행의 우회는 그물 밖).
- 셸 낱말 재도입·Bash 제거(두 실행기 구조는 맞다는 판정 유지). Write/Edit 네이티브는 남기되 경로로 관문.

## 판정 기준(⏳)
- 다음 세 주행: 거절 뒤 재시도가 IBL 로 가는 비율, Bash 중 그림자 비율, 증류 접지 스킵 0.
- 오거절이 보이면 argmap/예외(임시 폴더·파이프)를 데이터로 고친다 — 관문 코드에 낱말을 넣지 말 것.

## 시험
`backend/test_shell_shadow_gate.py` (S1~S9). 실측 스모크: claude CLI haiku 로 grep 거절·git 통과·Write 거절 확인.
