# 에이전트 지침 누출 감사 — CLI 설정 소스·CLAUDE.md·자동 기억 (2026-10-20)

> 범위: ClaudeCode 공급자(`backend/providers/claude_code.py`, `cli_provider.py`)가 띄우는 CLI 턴에 **사용자 하네스 전용 파일**(상위 `CLAUDE.md`, Claude Code 자동 기억 `MEMORY.md`)이 실리는 경로·부류·비용을 확정하고 최소 수리안을 제안한다. **구현 0** — 판정은 사용자. 발단 = L84-3 추적(`docs/ANSWER_LANGUAGE_TRACE_2026_10_20.md` §7, `c2b3f600`).
> 증거 = 코드 + CLI 트랜스크립트(`~/.claude/projects/*/…jsonl` 의 `attachment` 기록) + 공식 문서(code.claude.com/docs memory·settings·cli-reference) + 도구 없는 haiku 탐침 4회(에이전트 턴 아님, 흔적 삭제). CLI 판 = 2.1.299(데스크톱 동봉 번들, `find_claude_binary` 2단계).

## 0. 요지

| 사실 | 근거 |
|---|---|
| EXECUTE 경로(프로젝트 에이전트·시스템 AI 실행 턴)는 `--setting-sources` 를 주지 않아 CLI 기본값(user,project,local)으로 돈다. cwd 조상의 `/Users/kangkukjin/Desktop/AI/CLAUDE.md`(5,070자)와 저장소 자동 기억 `~/.claude/projects/-Users-kangkukjin-Desktop-AI-indiebizOS/memory/MEMORY.md`(1,464자)가 첫 유저 턴에 `instructions` attachment 로 실린다. | §1·§2 |
| `--setting-sources ""`(원샷·의식·감독·평가·수리 실행자)는 **CLAUDE.md 는 막지만 자동 기억은 못 막는다.** 의식·평가·수리 트랜스크립트 전부 MEMORY.md(AutoMem) 가 실려 있다. | §2 표·탐침 A |
| 자동 기억은 적재만이 아니라 **쓰기 지시**도 따라온다: CLI 시스템 프롬프트 절 6("# Memory … write to it directly with the Write tool", 2,099자)이 프로젝트 에이전트에게 주인의 하네스 기억 폴더에 쓰라고 말한다. 현재까지 실제 쓰기 흔적은 없다(MEMORY.md mtime 09-06). | §1.3 |
| 차단 수단은 둘 다 실증됨: 환경변수 `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` 또는 `--settings` JSON 의 `"autoMemoryEnabled": false`. 둘 다 instructions attachment 와 시스템 프롬프트 Memory 절을 함께 없앤다. `--setting-sources ""` 아래서도 `--settings` 의 훅은 산다(SessionStart 훅 마커 3/3). | §4 탐침 |
| 회원 PC(`MemberClaudeProvider`)는 누출 0 — `CLAUDE_CONFIG_DIR` 를 턴 임시 폴더로 바꾸고 `--setting-sources ""`·cwd=임시 폴더. | §2 |
| 코딩: `execution_profile=coding` 은 ClaudeCode 에 연결된 호출자가 없다(`coding_profile.configure` 는 REPAIR/Codex 격리 전용, `docs/CODING_APP_ON_IBL_PLAN_2026_10_07.md` §몸). 코딩 앱의 실행자는 일반 EXECUTE(delegate role:coding)라 cwd=작업 폴더로 같은 누출을 받는다. "의도된 CLAUDE.md"는 작업 폴더 자신·하위의 것이지 작업 폴더 바깥 조상의 것이 아니다. | §3 |

## 1. EXECUTE 경로가 읽는 설정 소스·지침 파일 (확정)

### 1.1 코드 — `_build_command` 분기 (`backend/providers/claude_code.py:435-543`)

| 분기 | 조건 | 설정 소스 | `--settings`(훅) | 도구 |
|---|---|---|---|---|
| 원샷 | `tools_mode in ("none","read")` | `--setting-sources ""` (L494-497) | 없음 | `--tools ""`/`Read` |
| 의식(감독자) | `agent_role == "consciousness"` | `""` | 없음 | `Read`+supervision |
| 응답 수리 | `restricted_response_repair` | `""` | 없음 | supervision 만 |
| 연구 도서관 | `research_library` | `""` | 없음 | MCP 만 |
| 수리 실행자 | `repair_active()` | `""` | 없음 | MCP+repair command |
| **EXECUTE(평소)** | 위 전부 아님 | **지정 없음 → CLI 기본 user,project,local** | `native_hook_settings()` PreToolUse 감독 훅 (L507) | `EAGER_BUILTIN_TOOLS`+MCP |

주석(L495-496)의 근거는 "원샷은 CLAUDE.md·settings 도 안 읽는다(실측 8.5K→5.1K)". 이 주석은 CLAUDE.md 에 대해서만 맞다(§4 탐침 A: 자동 기억은 남는다).

cwd 결정 = `cli_provider._prepare_launch_context` (L514-543): `project_path`(프로젝트 에이전트 = `projects/<id>`, 시스템 AI = `data/` 또는 work_dir, 의식·원샷 = None → 백엔드 프로세스 cwd `backend/`, 수리 = `.worktrees/<task>`). env = `os.environ` 상속 + 신원(`_build_env` L1389) — 자동 기억 관련 변수 없음.

### 1.2 트랜스크립트 — 실제로 실린 것 (L84_training, `3839d4b6…jsonl`·`6c125a1a…jsonl`)

| 줄 | attachment | 내용 |
|---|---|---|
| 4 | `environment` | `workingDirectory=…/indiebizOS/projects/L84_training`, `isGitRepo: true`, `isWorktree: false` |
| 9 | `instructions` | `files[0] = /Users/kangkukjin/Desktop/AI/CLAUDE.md` type **Project** 5,069자 · `files[1] = ~/.claude/projects/-Users-kangkukjin-Desktop-AI-indiebizOS/memory/MEMORY.md` type **AutoMem** 1,463자 |
| 10 | `session_context` | `userEmail`(사용자 이메일 문장), `gitStatus`(indiebizOS 브랜치·변경 파일 목록) |
| 13 | `prompt_snapshot` | CLI 시스템 프롬프트 12절, 우리 49.6K 프롬프트는 마지막 절. **절 6 = "# Memory" 2,099자**: 위 memory 폴더에 Write 도구로 직접 쓰라는 지시 |
| 16 | 첫 assistant | `cache_creation_input_tokens 55,803`, `cache_read 11,833`, `input 2` |

지침 파일 탐색 경로(cwd → `/`)에 존재하는 후보는 `/Users/kangkukjin/Desktop/AI/CLAUDE.md` 하나뿐이다 — `indiebizOS/CLAUDE.md`·`projects/CLAUDE.md`·`projects/L84_training/CLAUDE.md`·`~/.claude/CLAUDE.md`·`CLAUDE.local.md`·`.claude/rules/` 전부 없음. `/Users/kangkukjin/Desktop/AI/AGENTS.md`(6,866B, "Codex 하네스 전용 뷰")는 CLAUDE.md 가 있어 기본값 `claude-md-or-agents-md` 에서 읽히지 않는다.

자동 기억 폴더는 **git 저장소 단위**(문서: "derived from the git repository, so all worktrees and subdirectories within the same repo share one auto memory directory")라 cwd 가 `projects/<id>`·`data/`·`backend/`·`.worktrees/<task>` 어디든 indiebizOS 저장소의 같은 MEMORY.md 가 실린다. 이 파일은 **Claude Code 하네스 세션(사용자와 나)의 기억 색인**이다 — 사용자 Nostr 주소·투자 철학·설계 취향 줄이 들어 있다.

설정 파일 쪽: `~/.claude/settings.json`(`skipWorkflowUsageWarning` 하나)·`indiebizOS/.claude/settings.local.json`(permissions allow 20줄, gitignore)만 저장소 안에 있고 프롬프트에는 실리지 않는다(권한은 `bypassPermissions` 라 무의미). `Desktop/AI/.claude/settings.local.json`(allow 987줄, 저장소 밖)은 CLI 프로젝트 루트(git 루트) 위라 적재 대상이 아니다 — 다만 그 allow 규칙 2건에 외부 API 키 문자열이 박혀 있어 별건 정리 후보(저장소 밖, 이 문서 범위 밖).

### 1.3 상위 CLAUDE.md 가 걸리는 이유·의도 여부

- 걸리는 이유 = 순수 위치: 프로젝트 폴더가 `Desktop/AI/indiebizOS/projects/<id>` 라 CLI 의 조상 탐색이 `Desktop/AI/CLAUDE.md` 까지 올라간다. 문서 기준으로 프로젝트 지침은 cwd 에서 `/` 직전까지 재귀한다(git 루트에서 멈추지 않는다 — cwd=`data/`·`projects/*` 트랜스크립트 전부 동일).
- 의도 여부: **아니오.** 그 파일 머리글이 스스로 "Claude Code 하네스 전용 뷰 — 시스템 바깥"이라 선언한다. 프로젝트 에이전트(훈련 프로젝트)·시스템 AI 실행 턴에 사용자 워크스페이스 규칙(커밋 규약·백업 규약·재기동 제어자 규약)이 들어가는 것은 몸의 프롬프트 설계(`prompt_composition`) 바깥에서 들어온 셋째 지침원이다. 두 파일 다 한국어라 L84-3 언어 원인은 아니다(L84-3 §5 기각 유지).
- 코딩 프로젝트에서의 의도: §3.

## 2. 누출 범위 — 에이전트 부류 × 받는 파일

트랜스크립트 디렉터리별 최근 12건 전수(10-19~20)·수리 워크트리 7개 디렉터리 최신 1건.

| 부류 | cwd | 분기 | CLAUDE.md(Project) | MEMORY.md(AutoMem) | Memory 절(쓰기 지시) | userEmail/gitStatus | 첫 턴 cache_create(실측) |
|---|---|---|---|---|---|---|---|
| 프로젝트 에이전트 EXECUTE(L81·L83·L84·연구1·study) | `projects/<id>` | 평소 | **있음** 5,069자 | **있음** 1,463자 | 있음 | 있음 | 54–66K(L81/83/84 fresh), 92–110K(연구1 긴 프롬프트) |
| 시스템 AI EXECUTE | `data/` | 평소 | **있음** | **있음** | 있음 | 있음 | 16–33K (+cache_read 55.9K) |
| 의식·평가자·기억 선별(원샷)·감독 | `backend/`(cwd None) 또는 `projects/<id>` | `""` | 없음 | **있음** | 있음 | 있음 | 3–33K |
| 수리 실행자 | `.worktrees/repair-task_*` | `""` | 없음 | **있음**(같은 저장소) | 있음 | 있음 | — |
| 회원 PC(`MemberClaudeProvider`) | 턴 임시 폴더 | 전용 명령 | 없음 | 없음(`CLAUDE_CONFIG_DIR` 임시) | 없음 | 임시 config → 계정 없음 | — |
| 코딩 앱 실행자(delegate role:coding) | 코딩 작업 폴더 | 평소 | 조상에 있으면 있음 | 저장소 안 폴더면 있음 | 있음 | 있음 | — |

예외 1건: `-worktrees-repair-task-sysai-bfcb2d55`(10-11, cwd=`data/`, 수리 활성화 전용 턴)는 CLAUDE.md 만 있고 AutoMem 이 없다 — 당시 CLI 판(2.1.295 이전) 차이로 추정, 현재 판에서는 재현 안 됨.

### 토큰 비용

Claude 토크나이저로 직접 셀 수 없어(tiktoken 미설치, API 호출 안 함) 추정 범위로 적는다. 한국어 밀도 문서는 코드 주석의 선례(3.4K자 → 8.5K→5.1K, ≈1토큰/자)를 상한으로 본다.

| 항목 | 크기 | 토큰(추정) | 실측 근거 |
|---|---|---|---|
| `Desktop/AI/CLAUDE.md` | 5,070자 / 7,807B | 3.5–5K | — |
| `MEMORY.md`(AutoMem) | 1,464자 / 2,233B | 1–1.5K | — |
| CLI "# Memory" 절(쓰기 지시) | 2,099자 영어 | ≈0.95K | 탐침 A−B cache_create 3,437−2,479 = 958 (MEMORY.md 47자 포함) |
| 합계 / 세션 1회 | | **≈5.5–7.5K** | 프로젝트 에이전트 첫 턴 55.8K 의 10–13%; 이후 턴은 매번 cache_read 로 재지불, 세션 리셋마다 재작성 |

## 3. 코딩 프로젝트 — 보존해야 할 CLAUDE.md 의 조건

- 현재 ClaudeCode 에는 `execution_profile=coding` 경로가 없다. `coding_profile.configure` 호출자는 없고(`grep` 0건), 계획 문서가 명시하듯 `coding_profile.py`·cli_provider 의 coding 분기는 REPAIR 경로의 Codex 격리가 쓴다. 코딩 앱(`services/coding_projects.py`)의 실행은 일반 EXECUTE 위임(`delegate role:coding`) → cwd = 코딩 작업 폴더.
- 거기서 **의도된** 지침 = 작업 폴더 자신의 `CLAUDE.md`·`.claude/rules/`·하위 폴더 CLAUDE.md(사용자가 그 코드베이스를 위해 쓴 것). **의도되지 않은** 것 = 작업 폴더 **바깥 조상**의 CLAUDE.md(`Desktop/AI/CLAUDE.md` 같은 하네스 뷰)와 indiebizOS 저장소 자동 기억.
- 따라서 보존 조건은 역할이 아니라 **경계**로 적는다: "cwd(작업 폴더) 안에서 시작하는 지침만 읽고, cwd 위 조상·주인의 하네스 기억은 읽지 않는다."

## 4. 탐침 (haiku, `--tools ""`, 도구 없는 1턴, cwd=스크래치 `probe/`에 CLAUDE.md 56자 심고 그 슬러그 memory/ 에 MEMORY.md 47자 심음, `--settings` 에 SessionStart 훅 `touch marker`)

| 탐침 | 인자 | instructions attachment | 시스템 프롬프트 Memory 절 | 훅 | cache_create / read |
|---|---|---|---|---|---|
| D 기본 | (없음) | CLAUDE.md(Project)+MEMORY.md(AutoMem) | 있음 | — | 1,128 / 2,973 |
| A | `--setting-sources "" --settings {hooks}` | **MEMORY.md 만** | 있음 | 발화 | 3,437 / 535 |
| B | A + env `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1` | **없음** | 없음 | 발화 | 2,479 / 535 |
| C | `--setting-sources "" --settings {"autoMemoryEnabled":false, hooks}` | **없음** | 없음 | 발화 | 599 / 2,420 |

확정: ① `--setting-sources ""` = CLAUDE.md 차단, 자동 기억 미차단. ② 자동 기억 차단은 env 또는 `--settings` 키 둘 다 적재·쓰기 지시 절까지 없앤다. ③ `--settings` 는 설정 소스 목록과 별개 층(문서 우선순위: 관리 > **명령줄 `--settings`** > local > project > user; `--restricted` 설명 "loads only managed settings and `--settings`")이라 `--setting-sources ""` 와 양립한다 — 감독 훅이 그대로 산다. 탐침 흔적(슬러그 폴더·마커)은 삭제했다.

## 5. 수리안 (제안만 — 구현은 판정 뒤)

### R1. 자동 기억 차단 — 전 역할 공통, 한 곳
`ClaudeCodeProvider._build_env` 에 `env["CLAUDE_CODE_DISABLE_AUTO_MEMORY"] = "1"`.
- 효과: EXECUTE·의식·원샷·수리·회원 전부에서 MEMORY.md 적재 + "# Memory" 쓰기 지시 절 소멸(탐침 B). 프로젝트 에이전트가 주인의 하네스 기억 폴더에 쓸 통로도 닫힌다.
- 왜 env 이고 `--settings` 키가 아닌가: `--settings` 는 EXECUTE 분기에만 있고 의식·원샷·수리 분기에는 없다(§1.1). env 한 줄이 분기 수와 무관하게 전수를 덮는다. 문서화된 공개 변수라 모델 교체·CLI 갱신을 살아남는다. 대안 = `native_hook_settings()` 에 `"autoMemoryEnabled": false` 를 넣고 나머지 분기에도 `--settings` 를 주는 것(탐침 C) — 분기 다섯 곳을 건드려 더 넓다.
- 회원 경로(`MemberClaudeProvider._build_env`)는 env 를 화이트리스트로 거른다 — 이미 `CLAUDE_CONFIG_DIR` 임시라 누출 0, 변경 불필요.

### R2. EXECUTE 에 `--setting-sources` 주기 — 기본은 `""`
`_build_command` 의 else 분기(평소 EXECUTE)에도 `cmd += ["--setting-sources", ""]`.
- 효과: 조상 CLAUDE.md(Project)·`.claude/rules/`·`CLAUDE.local.md` 전부 미적재(탐침 A, 의식 트랜스크립트 전수). `--settings` 의 PreToolUse 감독 훅은 그대로(탐침 A/B/C).
- 잃는 것: `~/.claude/settings.json`(`skipWorkflowUsageWarning` 하나)·`indiebizOS/.claude/settings.local.json`(permissions allow) — 둘 다 EXECUTE 에 무의미(모델·권한·도구는 인자로 명시, `bypassPermissions`). 즉 원샷 다이어트(2026-08-21) 때 세운 같은 전제가 EXECUTE 에도 성립한다.
- 세션 키: 설정 소스가 바뀌어도 `tool_policy_fingerprint` 는 그대로다. resume 세션은 첫 요청의 시스템 프롬프트 기록본을 압축 전까지 재사용하므로(`pitfall_claude_code_resume_system_prompt_snapshot`) 옛 세션은 Memory 절·instructions 를 기억한 채 이어질 수 있다 — 지문 blob 에 `"||settings:none"` 같은 표식을 더해 옛 세션을 자연 폐기시키는 것이 깨끗하다(선택).

### R3. 코딩 작업 폴더 보존 조건 — 경계로, 역할로 말고
코딩 앱 실행자처럼 cwd 가 **사용자 코드베이스**인 턴에만 `project` 소스를 살리고 조상은 잘라낸다.
- 조건 판정은 데이터로: cwd 가 `services/coding_projects.py` 의 등록 프로젝트(또는 `outputs/coding/*`)일 때. 역할 이름(`role:coding`)으로 스위치하지 않는다(사용 빈도·역할명 스위치화 금지 원칙).
- 조상 절단 수단 후보 = `--settings` JSON 의 `claudeMdExcludes`(문서: "Skip specific CLAUDE.md files when memory loads", 모든 범위에서 읽힘): spawn 직전 cwd 의 조상 경로를 훑어 **존재하는** `CLAUDE.md`·`.claude/CLAUDE.md`·`CLAUDE.local.md` 절대 경로를 목록에 넣는다. 작업 폴더 자신·하위는 남는다. ★패턴 문법(절대 경로/글롭)은 미실측 — 구현 때 탐침 1회 필요.
- 더 단순한 대안: 코딩 턴도 R2 와 같이 `""` 로 두고, 작업 폴더의 CLAUDE.md 는 몸이 읽어 프롬프트에 싣는다(`[self:read]` 또는 prompt_composition 절). 지침원이 하나(몸)로 모이므로 IBL 우선 원칙에 더 맞지만, `.claude/rules/`·경로 범위 규칙·하위 CLAUDE.md 온디맨드 적재 같은 CLI 기능을 잃는다. **판정 사항.**
- 주의: `project` 소스를 살리면 작업 폴더의 `.claude/settings.json` 훅도 실행 대상이 된다(사용자 코드베이스의 훅이 `bypassPermissions` 로 돈다). `-p` 모드의 작업 공간 신뢰 규칙은 미확인 — R3 를 택하면 함께 실측.

### 손대지 않는 것·남는 것
- `session_context`(userEmail·gitStatus)는 CLI 가 계정·저장소에서 스스로 넣는 것으로 위 플래그로 안 빠진다(탐침 B/C 에도 있음). 회원 경로만 임시 config 로 없다. 필요하면 `--bare`(자동 기억·CLAUDE.md·훅 발견·MCP 발견 전부 생략) 또는 `--exclude-dynamic-system-prompt-sections` 가 후보지만 둘 다 감독 훅·MCP 브리지와의 양립이 미실측이라 이번 범위 밖.
- `Desktop/AI/.claude/settings.local.json` 의 allow 규칙 안 키 문자열 — 저장소 밖, 사용자 정리.

### 구현 때 검증 절차(기록만으로)
1. R1·R2 적용 뒤 프로젝트 에이전트 fresh 턴 1회 → 트랜스크립트 `attachment.type=instructions` 부재, `prompt_snapshot` 에 "# Memory" 절 부재, PreToolUse 훅 발화(`hook_started`) 확인.
2. 첫 턴 `cache_creation_input_tokens` 를 L84 55,803 과 비교(기대 −5.5~7.5K).
3. 의식 턴 1회 → instructions 부재 확인(현재는 AutoMem 만 실림).

## 6. 참조
- 코드: `backend/providers/claude_code.py:401-408`(훅 설정)·`:435-543`(`_build_command`)·`:220`(`_build_env`), `backend/providers/cli_provider.py:514-543`(cwd/env), `backend/cognition/member_cli.py:160-190`(회원 명령·env 화이트리스트).
- 기록: `~/.claude/projects/-Users-kangkukjin-Desktop-AI-indiebizOS-projects-L84-training/{3839d4b6…,6c125a1a…}.jsonl`, `…-indiebizOS-backend/ecc40da2….jsonl`(기억 선별 원샷)·`ceb0a60e….jsonl`(평가자), `…-projects-study/29ec7378….jsonl`(의식), `…--worktrees-repair-task-*` 최신 1건씩.
- 문서: memory(Auto memory → Enable or disable, Storage location), settings(Settings precedence), cli-reference(`--setting-sources`·`--settings`·`--bare`·`--restricted`·`--exclude-dynamic-system-prompt-sections`).
- 선행: `docs/ANSWER_LANGUAGE_TRACE_2026_10_20.md` §7, 원샷 다이어트 2026-08-21(`_build_command` 주석).
