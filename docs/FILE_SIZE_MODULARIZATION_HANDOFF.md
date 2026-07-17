# 파일 크기 모듈화 핸드오프 (1500줄 규칙)

> 2026-07-17~18 세션. **9개 완료**(①~④·⑧·⑩·⑪ + 인지·제네릭), 잔여 4개
> (⑤ LectureWorkspace 2706 / ⑥ shadcn_slides 1955 / ⑦ indienet 1781 / ⑨ media_producer/handler 1643 —
> 전부 AI 저빈도). §3 방법론(+§3-6 AST 미해소 검사) 그대로.

## 1. 왜 (동기 — 측정 근거)

CLAUDE.md 개발 규칙에 원래 "각 파일 1500줄 이하로 모듈화"가 있었으나 13개 파일이 초과.
문제가 실측으로 확인됨 (최근 120 에피소드, `self:read` 60회):

- **70%가 통파일 읽기** — 30%는 `start`/`end` 잘못된 param이 조용히 무시된 결과
  (올바른 param은 `offset`/`limit`. → §6 후속 항목).
- 상한 방어는 있음: MCP relay `_trim_for_agent` 24K자 / in-process(gemini.py) 16KB×액션수 /
  핸들러 1MB. **그래서 회당 피해는 유한하지만, 큰 파일은 앞 24K만 잘려 와서
  "토큰 쓰고 목적도 못 이루고 grep 재탐색"하는 이중 낭비**가 로그에 반복 관찰됨.
- 모듈화하면 통파일 읽기가 예산 안에 들어오고, 읽기 자체가 표적화된다.

우선순위 = **AI 읽기 빈도 × 크기** (그냥 큰 파일이 아니라 실제 토큰이 새는 파일부터).
※ `ibl_nodes.yaml`(5547줄)은 빌드 산출물이라 분할 대상 아님 — AI가 읽으면 src를 읽도록 유도가 맞음.

## 2. 완료 (커밋 기준)

### 2-1. agent_cognitive.py 2455줄 → 6파일 (`dcb6410`)

| 파일 | 내용 | 줄수 |
|---|---|---|
| `backend/cognitive_trace.py` | 도구 trace 직렬화·액션 원장·자기반성 메시지 (모듈 순수함수) | 335 |
| `backend/cognitive_recall.py` | 0단계 연상 회상 (해마+심층+포식+디스크골격). ★`_FORAGE_CUES` 여기 정의 | 253 |
| `backend/cognitive_consciousness.py` | 의식·무의식 분류·framing 캐시·SESSION_RESET | 380 |
| `backend/cognitive_distill.py` | 증류 (심층+포식+`_after_response`)+포식 공간 헬퍼 | 542 |
| `backend/cognitive_eval.py` | Goal 평가 루프 | 557 |
| `backend/agent_cognitive.py` | 코어(초기화·프롬프트·IBL 도구)+**4믹스인 합성+재수출** | 515 |

- 구조 = `AgentCognitiveMixin(CognitiveRecallMixin, CognitiveConsciousnessMixin,
  CognitiveDistillMixin, CognitiveEvalMixin)`. 메서드 정의 파일이 바뀌어도 `self.` 호출 전부 무변경.
- **기존 import 경로 전부 호환**: 외부(agent_pipeline·test_evaluator_trace 등)는 계속
  `from agent_cognitive import ...` — 슬림판이 재수출한다.
- 갱신한 가드: `scripts/consciousness_schema_check.py` CONSUMER_FILES 에
  cognitive_consciousness/eval 추가(의식 출력 키 소비 코드가 이동했으므로).
- 폰 번들: backend 전 모듈 자동 번들이라 코드 조치 불필요 — 단 **pre-commit 훅이
  `data/bodies/android.engine.json` 재파생을 요구**함 (`python3 scripts/build_body_bundle.py android`
  재실행 후 함께 커밋. 새 backend 파일 추가 시 항상 이 순서).
- 검증: py_compile 6파일 · 합성 클래스 메서드 42/42 전수 · 의존자 임포트 ·
  `test_evaluator_trace.py` 통과 · consciousness_schema_check OK · build --check ·
  **실 에이전트 턴 종단**(연상→분류→실행→증류, 지도 재주입 회귀 무손상).

### 2-2. GenericInstrument.tsx 1784줄 → 5파일 (`87a5c11`)

| 파일 | 내용 | 줄수 |
|---|---|---|
| `frontend/src/components/generic/manifest.ts` | 타입·runIBL·템플릿 엔진·URL 헬퍼 (비-JSX 공용층) | 257 |
| `generic/prims-basic.tsx` | Card·KvRow·Sparkline·linkify·DocBlock | 216 |
| `generic/prims-edit.tsx` | FormPrim·EditableListPrim·이미지/폴더/AI독 필드 | 272 |
| `generic/prims-map-calendar.tsx` | MapPrim(leaflet)·CalendarPrim·CalField | 320 |
| `GenericInstrument.tsx` (본체) | **ViewPrim(p.type 디스패치 정본)**·ViewRenderer·ModePane·계기 본체 + 타입 재수출 | 792 |

- ★★핵심 제약: **`p.type ===` 디스패치 체인(ViewPrim)은 본체에 남겨야 한다** —
  `build_ibl_nodes.py` 뷰-어휘 가드가 `GenericInstrument.tsx` *경로명*을 정규식 스캔한다
  (추출량이 기대치 70% 미만이면 graceful skip = 가드 무력화가 조용히 일어남).
  디스패치를 다른 파일로 옮기려면 가드의 `desktop` 경로도 같이 고칠 것.
- 타입 재수출로 의존 4곳(ActionDesktop·Messenger/Community/BusinessInstrumentView) 무수정.
- 검증: tsc(분할 파일 오류 0) · build --check 전 가드(뷰-어휘 가드 포함) ·
  실브라우저(5173 HMR, `#/messenger`: card_list·master_detail·드릴 thread/compose/form·필터칩, 콘솔 에러 0).

### 2-3. build_ibl_nodes.py 2772줄 → 6파일 (2026-07-18)

| 파일 | 내용 | 줄수 |
|---|---|---|
| `scripts/iblbuild_common.py` | 공유 상수(NODE_ORDER·PACKAGE_DIRS·PHONE_VERIFIED_PACKAGES·CORPUS_FILES)+repo_root+ibl_param_vocab 재수출+_extract_action_param_aliases | 128 |
| `scripts/iblbuild_guards.py` | 소스-스캔 가드: 포크(INDIEBIZ_PROFILE)·OS·launcher·교재 | 236 |
| `scripts/iblbuild_derive.py` | build_tool_index+파생(fragments·tool.json·package_meta·phone_manifest·fixtures)+병합·직렬화 | 527 |
| `scripts/iblbuild_appview.py` | APP_* 뷰 어휘 선언+앱 블록/standalone/템플릿 param 검증+뷰-어휘·뷰-렌더러 가드 | 858 |
| `scripts/iblbuild_validators.py` | _check_action(op 삼각 AST)·코퍼스 param·runs_on류·표준-코어·validate() | 589 |
| `build_ibl_nodes.py` (본체) | 진입점 build()+main()+**91개 공개 이름 전부 재수출** | 613 |

- 의존 방향(순환 0): common ← guards / derive ← appview ← validators ← 본체.
  STANDARD_CORE_NODES 는 validators, PHONE_VERIFIED_PACKAGES 는 common 에 산다(grep 로 발견).
- **spec-load 호환**: migrate_package_vocab/migrate_tool_schema/apply_edition 이
  importlib spec 으로 이 파일을 로드해 `build_tool_index/derive_tool_json_docs/
  derive_package_meta/build` 를 쓴다 — 본체 상단이 `_SCRIPTS_DIR` 를 sys.path 에 넣어
  형제 모듈 import 가 CWD 무관하게 성립. 재수출로 `build_ibl_nodes.<이름>` 전부 불변.
- 검증: py_compile 6파일 · spec-load 후 old-vs-new 심볼 91/91 보존 ·
  `--check` 전 가드 통과+파생물 5종 바이트 일치 · 실제 빌드 실행 후 git diff 에
  data/ 변경 0(산출물 byte-identical) · consciousness_schema_check OK.
- scripts/ 파일이라 폰 번들(backend 전용)·Electron 재빌드 무관. pre-commit 은
  scripts/build_ibl_nodes.py 스테이징 시 --check 를 돌리므로 그대로 게이트.

### 2-4. Launcher.tsx 1596줄 → 2파일 (2026-07-18)

| 파일 | 내용 | 줄수 |
|---|---|---|
| `launcher-components/useLauncherDesktop.ts` | 데스크탑 아이콘 상호작용 훅 — 다중채팅방·휴지통·드래그/폴더드롭·복사/이름변경·컨텍스트 메뉴·키보드 단축키의 상태+핸들러+이펙트 (verbatim 이동) | 560 |
| `Launcher.tsx` (본체) | 모드 셸(5표면 선택기·승격앱·폰클립보드·폴링·다이얼로그)+JSX 전부 | 1165 |

- ★단일 거대 컴포넌트(40여 useState 한 클로저)라 **커스텀 훅 추출**이 유일한
  동작-보존 이음매 (백엔드 믹스인 합성의 React 대응물). 훅 반환값을 **구조분해**해
  JSX 식별자는 전부 무변경 — 이 패턴이 이런 모놀리식 컴포넌트 분할의 정석.
- 훅 파라미터 = 클로저 밖에서 오던 4개만: launcherTab(컨텍스트 메뉴 autopilot 게이트),
  showNewProjectDialog/showNewFolderDialog/showSchedulerDialog(키보드 단축키 억제).
  훅이 useAppStore 를 자체 구독(zustand 다중 구독 무해).
- 검증: tsc 0오류 · 실브라우저(5173 HMR — 데스크탑 아이콘 렌더·우클릭 컨텍스트 메뉴
  열림/외부클릭 닫힘·휴지통 더블클릭 다이얼로그·아이콘 선택 하이라이트·
  자율주행↔앱 모드 왕복, 콘솔 에러 0) · build --check 회귀 무손상.

### 2-5. ForageBrowser.tsx 1569줄 → 3파일 (2026-07-18)

| 파일 | 내용 | 줄수 |
|---|---|---|
| `forage/support.ts` | 비-JSX 지원층: API·webview escape-hatch·인라인 번역 JS 조각·PoolItem/Hunt/Tab 타입·후보 파서·비밀번호 금고 IPC·목적지 추출 | 177 |
| `forage/views.tsx` | 서브컴포넌트 10종: BrowserTabView(webview)·Favorites/History/BoardsPage·PoolRow/PoolCard·CardThumb·TabFav·FavIcon·NavBtn | 352 |
| `ForageBrowser.tsx` (본체) | 메인 컴포넌트(검색홈+사냥판+탭 브라우저 상태) | 1067 |

- GenericInstrument 패턴 그대로(JSX/비-JSX 층 분리) — 서브컴포넌트가 전부
  props 만 받는 독립 함수라 verbatim 이동, 훅 추출 불필요.
- 검증: tsc 0오류 · 실브라우저(5173 — 검색홈, 즐겨찾기 그리드(FavIcon),
  방문기록(실데이터), 판 도서관 → 판 펼치기(PoolCard 썸네일·다녀옴 배지·파비콘 폴백),
  탭 열기/닫기, 콘솔 에러 0). BrowserTabView(webview)는 Electron 전용이라
  브라우저에선 미노출 — verbatim 이동+tsc 로 커버.

### 2-6. api_launcher_web.py 2928줄 → 4파일 (2026-07-18)

| 파일 | 내용 | 줄수 |
|---|---|---|
| `backend/launcher_web_shell.py` | 원격 웹앱 문서 셸(head·CSS·body 골격) 문자열 | 466 |
| `backend/launcher_web_app.py` | 앱 셸 JS(로그인·표면 토글·계기 로직·portalBoot) 문자열 | 990 |
| `backend/launcher_web_render.py` | **뷰 렌더 JS(renderPrim p.type 디스패치 정본)** 문자열 | 936 |
| `api_launcher_web.py` (본체) | 파이썬 로직(라우터·인증·계기 파생) + 세 조각 연결 | 568 |

- 파일의 82%가 `get_launcher_webapp_html()` 의 단일 삼중따옴표 문자열(HTML/JS)이었음
  → 줄 경계에서 3분할해 모듈 상수로, 함수는 `SHELL + APP_JS + RENDER_JS` 연결만.
  **바이트 동일 조립**을 리팩터 전 캡처와 대조로 증명(파이썬 재조립 + 라이브 HTTP 응답 diff).
- ★뷰-렌더러 가드 remote 경로 갱신: `iblbuild_appview.check_view_renderers` 가
  `backend/api_launcher_web.py` → `backend/launcher_web_render.py` 를 스캔하도록 변경
  (안 고치면 70% 문턱 미달로 graceful skip = 가드 침묵 무력화). 새 파일에서 15/15
  view type 추출 확인.
- api_portal.py 의 `get_launcher_webapp_html()` 재사용(포털 셸 주입)은 함수 시그니처·
  출력 불변이라 무수정. INDIEBIZ_PROFILE 분기(_phone_runnable_actions)는 본체 파이썬
  구간에 잔류 — 포크-가드 allowlist 그대로.
- 검증: py_compile 4파일 · 재조립 byte-identical · `--check` 전 가드(뷰-렌더러 15/15
  실스캔 포함) · **라이브 백엔드(auto-reload) GET /launcher/app 200 + 리팩터 전
  캡처와 바이트 동일** · build_body_bundle android 재파생.

### 2-7. system_essentials/handler.py 1659줄 → 2파일 (2026-07-18)

| 파일 | 내용 | 줄수 |
|---|---|---|
| `office_ops.py` | 오피스/문서 op 5종의 분기 몸통 verbatim: fill_op(PDF 폼/DOCX 자리표시자)·read_pdf·read_docx·read_xlsx·spreadsheet + 전용 헬퍼(_fill_pdf/_fill_docx/_truthy) + **_get_path 정의처** | 673 |
| `handler.py` (본체) | execute() if/elif 체인 — 5개 분기는 `_office.X(tool_input, project_path)` 위임 | 1036 |

- 형제 로드 = real-estate `load_module` 선례(`_load_sibling` spec-load). 의존 방향
  handler→office_ops 단방향: `_get_path` 는 office_ops 가 정의하고 handler 가 별칭
  (다른 분기 계속 사용), `_validate_path_in_scope` 는 handler 소유라 spreadsheet 에 인자 주입.
- 이 핸들러엔 `_OP_DISPATCHERS` 없음(if/elif 체인) — 삼각검증 무관. 코퍼스 param
  검사는 pkg rglob(*.py)라 이동해도 키 발견 ✓.
- 검증: py_compile · `--check`(코퍼스 param 포함) · `/packages/reload` 후 라이브
  /ibl/execute 종단 4종(read_pdf 실PDF·spreadsheet 쓰기→read_xlsx 왕복 table 통화
  일치·fill PDF 인트로스펙션) + 테스트 산출물 정리. read_docx 는 동일 패턴(컴파일 검증).

### 2-8. system_tools.py 1526줄 → 3파일 (2026-07-18)

| 파일 | 내용 | 줄수 |
|---|---|---|
| `backend/system_tools_delegate.py` | 위임 계층: execute_call_agent(직송/자식 태스크·위임 체인)·execute_list_agents | 322 |
| `backend/system_tools_ibl.py` | IBL 통합 실행 본체: _execute_ibl_unified(파일참조 치환·param 힌트) + **서킷 브레이커·로그 상태**(reset/get 포함) | 354 |
| `backend/system_tools.py` (본체) | SYSTEM_TOOLS 정의·trace 표기·execute_tool 디스패치·지도 봉투 수확 + 재수출 | 900 |

- ★교훈(이번에 실제로 밟은 함정): 이동 구간의 **모듈 전역(가변 상태) 참조를 특정
  심볼 grep 만으로 검사하면 놓친다** — `_ibl_log_seen` NameError 가 라이브에서 발생.
  이후 **AST 미해소-이름 전수 검사**(Load−{정의∪import∪인자∪builtins})로 잡음. 다음
  분할부터 이 검사를 표준 절차에 포함(§3-6).
- ★가변 전역 소유권: `_action_fail_counter` 는 reset 시 **rebind** 되므로
  `from x import` 별칭 공유 불가 — 상태+reset/get 함수를 hot-path(_execute_ibl_unified)와
  같은 모듈(system_tools_ibl)로 함께 이동, 본체는 함수만 재수출. 사적 상태 5개는
  외부 사용자 0 확인 후 재수출 안 함(별칭 함정 방지).
- 검증: py_compile · AST 미해소 0 · 구버전 대비 심볼 파리티(공개 36/36, 사적 상태 5 의도 이동) ·
  라이브 /ibl/execute(self:time + weather 파이프 2/2 스텝 — api_ibl 이 _execute_ibl_unified 직결) ·
  브레이커 재수출 상태 공유 검사 · body bundle 재파생.

### 2-9. ibl_parser.py 1522줄 → 3파일 (2026-07-18)

| 파일 | 내용 | 줄수 |
|---|---|---|
| `backend/ibl_parser_values.py` | 리프: **IBLSyntaxError**(공유 최하층)·{params} 파서·값 추출기(문자열/괄호/숫자/비인용) | 240 |
| `backend/ibl_parser_blocks.py` | 제어 블록: goal/if·else/case 파서·범위 표현식(+전용 정규식 상수) | 434 |
| `backend/ibl_parser.py` (본체) | parse/파이프라인 분해/**파이프 설탕(_pipe_block — 표준-코어 가드 스캔 대상, 잔류)**/포맷터/`__main__` 테스트 + 재수출 | 894 |

- 의존: 본체→blocks→values 단방향. 유일한 verbatim 편차 = `_parse_block_body` 의
  재귀 `parse` 호출을 지연 import(순환 차단, 1줄).
- ★표준-코어 가드는 `ibl_parser.py` 에서 `def _pipe_block` 을 정규식 스캔 — 설탕은
  본체 잔류라 가드 무수정 통과.
- 검증(§3-6 신절차): py_compile · AST 미해소 0(3파일) · 심볼 파리티(사적 정규식 9개만
  이동, 외부 사용 0 확인) · **구/신 파서 출력 diff 10/10 동일**(goal/if/case/변수/설탕/
  병렬/폴백/중첩 params — git HEAD 판을 spec-load 해 직접 대조) · `__main__` 내장
  테스트 전체 통과 · `--check`(표준-코어 가드 포함) · 라이브 /ibl/execute · body bundle 재파생.

### 2-10. 같은 세션의 별개 수정 (참고)

- `5ed52f9` — 지도 봉투 수확 깊이상한 8→16 (에피소드 802: CLI relay `{"result"}` 래핑 +2깊이
  + 병렬 깊이9가 상한 8에 1칸 모자라 지도 유실. claude_code `_extract_map_tags` +
  system_tools `_pluck_map_envelopes` 両관문). 실턴 종단 검증 완료.
- `7d2183d` — NAS 음악 구간 탐색(이전 세션 미커밋분 정리).

## 3. 방법론 (다음 분할도 이대로)

1. **의존자 전수 조사 먼저**: `grep -rn "from <모듈> import\|import <모듈>"` + 가드 스크립트가
   그 *파일 경로*를 참조하는지(`grep -rn "<파일명>" scripts/`) + 문서(system_docs·CLAUDE.md).
2. **새 모듈을 먼저 전부 쓴다** — 아무도 import 안 하므로 라이브 시스템에 무해.
   백엔드는 auto-reload(2초 배치)라 매 저장 시점이 import 가능해야 함.
3. **원본을 마지막에 한 번에 교체** — 슬림판 = 남는 코드 + (믹스인 합성 | 컴포넌트 유지) +
   **기존 이름 전부 재수출**. 코드는 verbatim 이동(동작 변경 금지 — 리팩터와 분할을 섞지 말 것).
4. 클래스는 **믹스인 합성**(backend), 컴포넌트는 **JSX/비-JSX 층 분리**(frontend)가 잘 맞았다.
5. 흔한 함정: 모듈 레벨 `import json` 등에 기대던 함수-내부 except 절(`json.JSONDecodeError`) —
   새 모듈 top import 로 보존할 것.
6. 검증 순서: py_compile/tsc → **AST 미해소-이름 전수 검사**(새 모듈의 Name Load −
   {정의∪import∪인자∪builtins} = ∅ — 모듈 전역 상태 참조 누락을 py_compile 은 못 잡는다,
   §2-8 실사례) → 합성 클래스 메서드/심볼 파리티 전수 → 기존 테스트 →
   가드(`--check`, consciousness_schema_check) → 라이브 스모크(실턴/실브라우저).
7. 커밋: backend 파일 추가 시 `build_body_bundle.py android` 재파생 포함(pre-commit이 막는다).

## 4. 문서·가드 접점 (분할 시 같이 볼 곳)

- `scripts/build_ibl_nodes.py` — 뷰-어휘 가드(GenericInstrument.tsx 경로),
  포크-가드·OS-가드 등이 backend 파일을 스캔.
- `scripts/consciousness_schema_check.py` CONSUMER_FILES — consciousness_output 키 소비 파일 목록.
- pre-commit 훅 — 몸 번들 파생 검사(backend 모듈 목록) + 의식 스키마 검사.
- `/Users/kangkukjin/Desktop/AI/CLAUDE.md` — backend/frontend 파일 목록(갱신함).
- 폰 번들은 자동(engine.json 재파생만). 데스크탑 Electron 재빌드 불필요(HMR).

## 5. 잔여 대기열 (읽기빈도×크기 순, 2026-07-18 기준)

| 순위 | 파일 | 줄수 | 메모 |
|---|---|---|---|
| ~~①~~ | ~~`scripts/build_ibl_nodes.py`~~ | ~~2772~~ | ✅완료(§2-3, 2026-07-18) |
| ~~②~~ | ~~`frontend/src/components/Launcher.tsx`~~ | ~~1596~~ | ✅완료(§2-4, 2026-07-18) |
| ~~③~~ | ~~`frontend/src/components/ForageBrowser.tsx`~~ | ~~1569~~ | ✅완료(§2-5, 2026-07-18) |
| ~~④~~ | ~~`backend/api_launcher_web.py`~~ | ~~2928~~ | ✅완료(§2-6, 2026-07-18) |
| ⑤ | `frontend/src/components/LectureWorkspace.tsx` | 2706 | AI 읽기 드묾 |
| ⑥ | `data/packages/installed/tools/media_producer/shadcn_slides.py` | 1955 | |
| ⑦ | `backend/indienet.py` | 1781 | |
| ~~⑧~~ | ~~`system_essentials/handler.py`~~ | ~~1659~~ | ✅완료(§2-7, 2026-07-18) |
| ⑨ | `media_producer/handler.py` | 1643 | 위와 동일 주의 |
| ~~⑩~~ | ~~`backend/system_tools.py`~~ | ~~1526~~ | ✅완료(§2-8, 2026-07-18) |
| ~~⑪~~ | ~~`backend/ibl_parser.py`~~ | ~~1522~~ | ✅완료(§2-9, 2026-07-18) |

## 6. 관련 후속 (별개 작업, 미실행)

- **`self:read` start/end 별칭 흡수**: 모델이 30% 확률로 `start`/`end`를 쓰는데 핸들러는
  `offset`/`limit`만 인식 → 조용히 무시되고 통파일이 온다. `aliases:` 인프라로
  start→offset, end→(end−start)=limit 흡수 + 미인식 범위 param 은 힌트 반환
  (param_layer_desilencing 원칙). 핸들러=`system_essentials/handler.py` read_op(445행~).
- **기존 tsc 오류 2건**(이번 작업과 무관, pre-existing): `NewspaperInstrument.tsx:459`
  `openArticle` 미정의 / `src/types/index.ts` `copyToClipboard` 중복 선언.
- 메모리 정본: `~/.claude/.../memory/project_file_size_modularization.md`.
