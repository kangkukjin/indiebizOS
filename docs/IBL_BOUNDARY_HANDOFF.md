# IBL 경계 수리 핸드오프 — 사적 심볼 월경 + 사전 이음매 계약화

작성: 2026-08-24 (Claude Code 세션, 조사만 수행 — 코드 무변경).
발단: "IBL을 다른 하네스가 쓸 수 있게 경계를 분명히 할까" 논의에서 지목된 3번 문제
(① `_load_nodes_data` 사적 심볼 누수, ② 사전 로더가 datastore 층에 있음)의 실측 조사와 수리 계획.

## 0. 조사 결과 요약 — 원래 진단 두 개 중 하나는 수정됨

**① 사적 심볼 누수 — 실재하되, 부류의 경계를 다시 그어야 한다.**
backend 전체의 모듈-간 언더스코어 import는 AST 실측 **208곳**이다. 그러나 대부분은
1500줄 규칙으로 쪼갠 **친구-모듈 간 공유**(ibl_engine↔ibl_executors↔ibl_routing,
ibl_parser↔parser_values↔parser_blocks, workflow_engine↔binding↔contract, world_pulse 3분할 등)로,
한 유기체를 파일만 나눈 자리다. 이건 결함이 아니고 개명하면 저비용 churn 만 남는다.
**진짜 결함은 "ibl 층 밖(cognition·surface·services·datastore·패키지)에서 ibl 층 모듈의
사적 심볼을 import 하는 것"** — 실측 **21 import 사이트, 16개 심볼, 11개 ibl 모듈** (§2 표).

**② "언어가 자기 사전을 자기 밖에서 읽는다" — 진단이 부정확했다. 이동은 기각.**
같은 `ibl_nodes.yaml`을 읽는 로더가 둘인데 중복이 아니라 의미가 다르다:

| 로더 | 층 | 의미 | 부재 시 | 파손 시 |
|---|---|---|---|---|
| `ibl_access._load_nodes_data` | ibl | **원본 사전집**(생 yaml) | `{}` 조용히 | RuntimeError + 재생성 안내 (2026-08-22 정직화) |
| `ibl_registry._load_nodes_config` | datastore | **이 몸에 설치된 사전**(api_registry 병합 + `_prune_foreign_vocabulary` 몸-필터) | `{"nodes":{}}` 조용히 | 생 yaml 예외 (안내문 없음) |

언어(ibl 층)는 원본 사전을 **이미 스스로 읽고 있다**(ibl_access). datastore에 있는 것은
**설치본 빌더**이고, 설치(=api_registry 병합, `detect_body` 기반 타몸 어휘 제거)는 몸의
의미론이다("몸의 명사=코드"). 언어를 반출하는 시나리오에서도 설치기는 숙주가 다시 짓는
부품이므로, 지금 자리가 헌법상 맞다. **`ibl_registry`를 ibl 층으로 옮기지 않는다.**
이동의 실비용도 확인했다: 유일한 하향 소비자 `datastore/ibl_usage_db.py:402`(해마 입구
소유-게이트 `code_is_own`)가 상향 간선이 되어 훅 주입 배관이 필요해지고, LAYERS·폰 번들
목록 churn 이 붙는다. 이득(상징적 소속감) < 비용.

대신 그 자리의 **진짜 결함 3개**를 고친다 (§3):
- (a) raw/설치본 구분이 이름에 없다 — `_load_nodes_data` vs `_load_nodes_config`는 아무 힌트가 없다 (이름법: 한단어=한개념 위반)
- (b) 경로 앵커 3중 중복 — `runtime_utils.get_base_path`(정본) 외에 `ibl_access._get_base_path`·`ibl_registry._get_nodes_path`/`_get_registry_path`가 같은 로직 재구현
- (c) 캐시 정합성이 손-유지 암묵 계약 — `/packages/reload`(api_packages.py:158~178)가 4단계
  수동 시퀀스로 3곳 캐시(access raw · registry 설치본 · node_registry)를 비우는데, 각 단계가
  `except Exception: pass` 로 삼켜져 실패해도 성공 응답이 나간다 (silent-clamp 부류)

## 1. 수리 3부 — **✅ 전부 완료 2026-08-24** (커밋 3개, main 직접)

| 부 | 내용 | 커밋 |
|---|---|---|
| A | ibl 층 사적 심볼의 층-밖 소비 → 공개 승격(개명) + 죽은 호환층 제거 | `1713f71` |
| B | 사전 이음매 계약화 (이동 없음): 경로 앵커·부재≠파손·reload 정직화·docstring 계약 | `a7a0232` |
| C | 관문: check_backend_layers.py 에 "ibl 사적 심볼 층-밖 import 금지" AST 검사 (부채 0 시작) | `70ee84b` |

**세 부를 관통한 교훈**: C부 관문을 켜는 순간 A부가 놓친 위반이 하나 나왔다
(`system_essentials/handler.py:645 → ibl_executors._extract_path_from_prev`). A부의 AST
스윕이 `backend/` 만 훑고 패키지 트리는 이름 grep 으로만 봤기 때문이다 — **사람이 고른
스윕 범위는 반드시 샌다.** 부류를 다 걷었다는 주장은 관문이 대신 해야 한다.

B부에서도 같은 모양이 한 번 더 나왔다: `ibl_routing._rebuild_ibl_vocab` 이 "`/packages/reload`
와 동형"이라 적어두고 `reload_registry` 단계가 빠져 있었다 — **주석이 동형을 주장하면
드리프트가 이미 시작된 것이다.** 두 벌로 적힌 절차는 한쪽만 고쳐진다.

### 후속
- **순수 코어 폐포 가드 = ✅ 완료 `0349e57`** (§5). ★원안의 전제가 틀렸다: "의존 0인 9파일"은
  *층-밖* 의존 0이었지 분리 가능이 아니었다 — `ibl_control_blocks`·`ibl_exec_each` 는
  `ibl_engine`·`ibl_executors`·`workflow_engine` 을 끌어와 엔진 한복판이다. 실제 순수 코어는
  **7파일 + `backend/common/` 잎**이고, 폐포는 10모듈에서 닫힌다.
- 상향 5간선(BASELINE 동결분 중 ibl 층 발신: `ibl_engine→consciousness_agent` ·
  `ibl_executors→goal_evaluator` · `package_manager→ibl_usage_generator` ·
  `channel_engine→api_gmail`·`indienet`)의 훅 승격 = **지금은 보류**. 층 가드 BASELINE 이 이미
  새 간선을 막고 있어 *드리프트 방지*라는 목적은 달성돼 있다. 훅 전환에 남는 값은
  "떼어낼 수 있음" 하나뿐인데 등록 배관은 영구 표면이고 현재 소비자가 0이다 — 소비자를
  상상해 설계하면 틀린 모양이 나온다. **재론 조건: 두 번째 숙주 등장.**
  (참고: `channel_engine→api_gmail`·`indienet` 둘은 부류가 다르다 — "언어가 인지를 부른다"가
  아니라 "채널 엔진이 구체 채널을 안다"이므로 답은 훅이 아니라 채널 등록부일 가능성이 높다.)
- `ibl_registry` 의 ibl 층 이동 = **기각**(§0). 재론 조건: 언어 반출의 실소비자 등장

## 2. A부 — 공개 승격 (✅ 완료 2026-08-24)

**실행 결과**: 심볼 17종 개명, **47파일 203곳** 치환. 검증 = 층 가드 통과(모듈 309) ·
`build_ibl_nodes.py --check` 전항 통과 · backend 전 스위트 **456 passed, 2 skipped**.

**계획 대비 정정 2건**(계획이 좁았던 자리):
- 스캔 범위가 부족했다 — `data/ibl_nodes_src/`(어휘 단일 소스)와 `phone-companion/` 이 빠져
  있었다. 특히 `ibl_nodes_src/self.yaml` 의 `target_description` 은 **에이전트 프롬프트로
  들어가는 텍스트**라 옛 이름이 남으면 모델에게 거짓 포인터를 주게 된다. src 를 고치고
  `build_ibl_nodes.py` 로 파생(`ibl_nodes.yaml`)을 재생성 — 파생 직접 편집 없음.
- 테스트 환경 함정 2건(둘 다 이번 변경과 무관, 접지 확인함): `test_hippo_capability_gate`
  는 시스템 python 에서 sentence-transformers 버전 불일치로 실패한다 → **`.venv/bin/python`
  으로 돌릴 것**. `test_log_truncation_mark` 는 저장소-루트 상대경로를 열어 **cwd=루트**를
  요구한다.

**`docs/` 는 갱신하지 않았다** — 날짜가 박힌 설계 스냅샷(“2026-07-18 수리”, “✅ 완료”)이라
개명하면 기록이 거짓이 된다. `doc_drift` 감사 범위도 README+`system_docs` 뿐이다.
같은 이유로 `changelog.log`·`TOOL_SDK_FOLLOWUPS.md`(이미 옛 층 경로를 적은 역사 문서)도 보존.
현재형 코드 포인터인 `data/system_docs/`·`data/guides/`·`data/ibl_nodes_src/` 만 갱신했다.
옛↔새 이름 대응은 아래 표가 정본이다.

### (계획 원문 — 부채 목록 전수)

원칙: **층 안 친구-모듈 사적 공유는 그대로 둔다.** 층 밖 소비가 있는 심볼만 정의처에서
공개명으로 개명하고, 저장소 내 전 호출처(층 안 포함)를 일괄 갱신한다. 별칭·재수출 금지
(no_temporary_patches — 소비자가 전부 저장소 안이므로 호환층 불요).

### 2-1. 개명 대상 심볼 (16종)

| 현재 | 공개명 | 층-밖 소비처 |
|---|---|---|
| `ibl_access._load_nodes_data` | `load_nodes_raw` | api_ibl.py:254·346·362·411·474·541, ibl_usage_rag.py:367·439·468, system_tools_ibl.py:284, **패키지** community-portal/portal_core.py:693 |
| `ibl_access._load_package_meta` | `load_package_meta` | api_packages.py:84 |
| `ibl_registry._load_nodes_config` | `load_nodes_installed` | api_ibl.py:383 (층 안: engine·executors·safety·routing·param_vocab·capability_card) |
| `ibl_registry._self_can_run` | `self_can_run` | body_ask.py:154 (층 안: ibl_access:396, capability_card) |
| `capability_card._action_entry` | `action_entry` | body_ask.py:153 |
| `capability_card._registry` | (개명 대신) body_ask 가 `load_nodes_installed` 직수입 | body_ask.py:153 |
| `workflow_engine._is_error_result` | `is_error_result` | agent_pipeline.py:347 |
| `workflow_contract._coerce_caller_params` | `coerce_caller_params` | calendar_actions.py:89 (현재 workflow_engine 경유 — 직수입으로) |
| `ibl_routing._search_guide` | `search_guide` | api_ibl.py:210, system_tools.py:920 (현재 ibl_engine 재수출 경유 — 직수입으로) |
| `ibl_routing._resolve_project_path` | `resolve_project_path` | system_tools.py:964 |
| `ibl_param_vocab._documented_vocab` | `documented_vocab` | system_tools_ibl.py:298 |
| `ibl_engine._forward_to_phone` | `forward_to_phone` | api_launcher_web.py:678 |
| `ibl_translate._IBL_TRANSLATE_TASK` | `IBL_TRANSLATE_TASK` | body_ask.py:118, api_ibl.py:282 |
| `ibl_translate._load_ibl_spec` | `load_ibl_spec` | 〃 |
| `ibl_translate._strip_code_fence` | `strip_code_fence` | body_ask.py:118·218, api_ibl.py:282 |
| `trigger_engine._add_history` | `add_history` | calendar_actions.py:195, channel_poller.py:813·820 (층 안: event_engine.py:5) |
| `trigger_engine._load_triggers` | `load_triggers` | channel_poller.py:758 |
| `channel_engine._get_system_gmail_address` | `get_system_gmail_address` | portal_auth.py:215 |
| `ibl_exec_output._extract_path_from_prev` | `extract_path_from_prev` | **C부에서 뒤늦게 발견** — system_essentials/handler.py:645 (재수출: ibl_executors·ibl_engine) |

### 2-2. 같은 커밋의 청소

- **ibl_engine.py:62 `_get_nodes_path` 죽은 import 삭제** (import 후 사용 0).
- **capability_card.py:33 F401 재수출 3종(`_self_can_run`·`foreign_actions`·`code_is_own`) 삭제** —
  외부 소비자 0 실측 (2026-08-05 이동의 호환층 잔재). 소비처는 ibl_registry 직수입이 이미 정착.
- 문자열·주석·문서의 옛 이름 갱신: `iblbuild_common.py:225`, `test_corrupt_not_absent.py`
  (S2 시나리오명), guides·system_docs 내 언급 — 마감 조건: `grep -rn "_load_nodes_data\|_load_nodes_config" backend scripts data/packages data/guides data/system_docs` **0건**.
- `getattr` 동적 참조 확인: `grep -rn "getattr.*_load_nodes\|getattr.*_search_guide"` 등 개명 대상 전수 — 0건 확인 후 진행.

## 3. B부 — 사전 이음매 계약화 (✅ 완료 `a7a0232`, 코드 이동 없음)

**계획 대비 추가 2건**: ①경로 앵커 사본이 셋이 아니라 **넷**이었다 —
`ibl_registry._phone_runnable` 안에 `os.environ.get("INDIEBIZ_BASE_PATH") or …` 가 한 벌 더
있었다(폰 매니페스트 읽는 자리). ②`/packages/reload` 뿐 아니라 그 짝인
`ibl_routing._rebuild_ibl_vocab`(패키지 install/remove 후 호출)도 같은 삼킴이었고, 게다가
**"동형"이라 적어두고 `reload_registry` 단계가 빠져 있었다** — `/packages/reload` 가
2026-07-03 에 고친 유령-액션 병이 이쪽에만 살아 있었다. 둘 다 함께 집행.

1. **경로 앵커 단일화**: `ibl_access._get_base_path`/`_get_nodes_path`,
   `ibl_registry._get_nodes_path`/`_get_registry_path` 의 자체 경로 계산을
   `runtime_utils.get_base_path()` 경유로 통일 (ibl→base, datastore→base 모두 정방향).
   `INDIEBIZ_BASE_PATH` 해석이 한 곳이 된다.
2. **registry 로더 corrupt-not-absent 정직화**: `_load_nodes_config`(→`load_nodes_installed`)와
   `_load_registry` 의 파손 시 생 yaml 예외를 ibl_access 와 같은 문구의 RuntimeError
   (재생성 안내 포함)로 통일. 부재 시 조용히 빈 값은 양쪽 기존 방침 유지.
   `test_corrupt_not_absent.py` 에 registry 케이스 추가.
3. **`/packages/reload` 예외 삼킴 제거**: api_packages.py 리로드 4단계의
   `except Exception: pass` 를 실패 수집으로 바꿔 응답에 `failed_steps` 로 표면화.
   스테일 사전인 채 200 OK 가 나가는 구멍을 막는다 (silent-clamp 부류).
4. **이음매 문서화**: `ibl_registry` 모듈 docstring 에 "사전 이음매 — ibl 층이 소비하는
   공개 표면은 `load_nodes_installed`·`invalidate_nodes`·`pruned_reason`·`self_can_run`·
   `foreign_actions`·`code_is_own`·`phone_runnable`(승격 시)·레지스트리 로더" 를 명시하고,
   같은 내용을 `data/system_docs/architecture.md` 의 해당 절에 한 단락으로.
   (어휘 변경이 아니므로 문서 7표면 의무는 비해당 — 산문 한 곳이면 된다.)

## 4. C부 — 관문 (✅ 완료 `70ee84b` · no-counter-watch: 세지 말고 실패시켜라)

`scripts/check_backend_layers.py` (이미 모듈→층 지도를 가진 자리)에 검사 추가:

- **규칙**: AST `ImportFrom` 에서, importer 의 층 ≠ ibl 이고 imported 모듈의 층 = ibl 이며
  심볼명이 `_` 로 시작하면 실패. `ibl_registry` 는 datastore 지만 사전 이음매로 같은 규칙에
  명시 포함.
- **스캔 범위**: `backend/**/*.py` + `data/packages/installed/tools/**/*.py`
  (패키지의 backend 사적 심볼 의존 금지 — community-portal 이 A부에서 마지막 부채였다).
- **면제**: `backend/test_*.py` (화이트박스 테스트는 내부 도달이 정당).
- **부채 목록·동결 없음**: A부가 부채를 0으로 만든 뒤 켠다. 신규 위반 = 즉시 실패.
- 층 안 친구-모듈 공유는 규칙 밖 — 기존 관례 그대로.

## 5. 검증·반영·커밋

- 검증: `python3 scripts/check_backend_layers.py` → `python3 scripts/build_ibl_nodes.py --check`
  → `backend/test_corrupt_not_absent.py` → `backend/test_pipe_currency_failures.py`(P1~P19,
  엔진 표면을 건드리므로) → §2-2 grep 0건 마감.
- 라이브 반영: 변경이 전부 backend 모듈·패키지 서브모듈이므로 `/packages/reload` 로 부족 —
  **백엔드 재시작 필요** (portal_core.py 는 tool_* 서브모듈 부류). 평범한 backend 편집이므로
  keeper 의례 불요.
- 커밋 3개(A→B→C), main 직접, 동시 세션 대비 pathspec 으로. 예:
  `git commit -m "..." -- backend/ data/packages/installed/tools/community-portal/ scripts/check_backend_layers.py docs/ data/system_docs/architecture.md`

## 5. 순수 코어 폐포 가드 (✅ 완료 2026-08-24)

헌법 "표준 = 문법 + 기능어 코어"(`ibl.md` 언어의 경계)는 그동안 **어휘 층에서만** 기계적으로
강제됐다(`STANDARD_CORE_NODES`). 이 가드가 그것을 **코드 층**까지 내린다: 문법·통화 계약은
숙주(DB·에이전트·HTTP·설정)를 몰라야 한다.

### 5-1. 원안의 전제가 틀렸다 (실측 정정)

원 제안은 "의존 0인 9파일을 빈 환경에서 단독 import"였다. 실행해 보면 **첫날부터 2개가
실패한다**:

| 파일 | 실제 내부 의존 |
|---|---|
| `ibl_control_blocks` | `ibl_engine` · `ibl_executors` · `workflow_engine` · `ibl_predicates` |
| `ibl_exec_each` | `ibl_parser` · `workflow_contract` · `workflow_engine` |

"의존 0"은 *층-밖* 의존이 0이었다는 뜻이고, 이 둘은 층 안에서 가장 무거운 모듈들(층-밖 간선
94건을 지고 있는 그 모듈들)을 끌어온다. 즉 **분리 가능이 아니라 엔진 한복판**이다.

실제 순수 코어는 **7파일 + `backend/common/` 잎**이다. 단독 import 실증: 5개
(`ibl_parser_values`·`ibl_parser_blocks`·`ibl_ops`·`ibl_envelope`·`ibl_predicates`)는 저장소
경로를 다 걷어낸 환경에서 그대로 떴고, `ibl_parser`·`api_transforms` 는 `common` 하나만
필요했다. `common/` 은 층 체계 **밖**의 잎 기질이고(층 가드 `_SKIP_DIRS`) 통화 계약
(`common.currency`)·변수 표기(`common.ibl_vars`)·HTML 유틸이 산다 — 의미상 코어가 맞다.

### 5-2. 설계 — 파일 목록이 아니라 폐포

★**손으로 유지하는 파일 목록을 쓰지 않는다.** 1500줄 규칙으로 파서가 또 쪼개지는 날 새 파일이
목록에 안 들어가고 가드가 조용히 그 파일을 안 보게 된다(오늘 배운 바로 그 병).

- **뿌리**: `ibl_parser` · `ibl_envelope` · `ibl_predicates` · `ibl_ops` · `api_transforms`
- **불변식**: 뿌리의 전이 폐포가 `{ibl 층 모듈, backend/common/*}` 밖으로 나가지 않는다.
  직접이든 전이든 숙주에 닿으면 실패 — 파서가 `ibl_engine` 을 import 하면 엔진이 끌고 오는
  `ibl_registry`(data 층)에서 걸린다.
- 새로 쪼갠 파일은 폐포에 자동으로 들어와 자기 import 까지 검사받는다. 목록 드리프트 불가.
- 현재 폐포 = **10모듈**에서 닫힘(뿌리 5 + `ibl_parser_blocks`·`ibl_parser_values` +
  `common.ibl_vars`·`common.currency`·`common.html_utils`).

### 5-3. 실증

self-test 가 판정 3갈래(common 허용 / 숙주 직접 도달 / 전이 도달)를 인공 트리로 검사하고,
실그래프 폐포가 닫혀 있음을 불변식으로 못박는다. 라이브 실증도 했다:

```
ibl_parser_values 에 conversation_db import 한 줄
  → conversation_db ← ibl_parser_values ← ibl_parser        (전이 1단)
ibl_envelope 에 ibl_engine import 한 줄
  → conversation_db ← ibl_exec_goal ← ibl_executors ← ibl_engine ← ibl_envelope
  → ibl_usage_generator ← package_manager ← ibl_routing ← ibl_engine ← ibl_envelope  (외 2건)
```
둘 다 exit 1 + 도달 경로 출력, 원복 후 재통과.

## 6. 하지 않는 것 (범위 밖 — 별도 판단)

- **`ibl_registry` 의 ibl 층 이동** — §0 에서 기각. 재론 조건: 언어 반출의 실소비자 등장.
- 같은 파일 3중 캐시(access raw · registry 설치본 · node_registry) 통합 — 의미가 셋 다 달라
  (raw/설치본/타입드 노드 뷰) 지금은 정합성 배선(B-3)만 정직화. 통합은 수요 생기면.
- 상향 5간선 훅 승격 — **보류**(§1 후속에 사유·재론 조건).
- `ibl_control_blocks`·`ibl_exec_each` 를 순수 코어로 끌어오기 — 엔진 한복판이라 뿌리가 아니다
  (§5-1). 끌어오려면 제어 블록에서 엔진 재귀(`execute_ibl`)를 걷어내야 하는데, 그건 언어
  설계 변경이지 정리가 아니다.
- 층 안 친구-모듈 언더스코어 공유 (~180곳) — 결함 아님, 손대지 않는다.
