# indiebizOS 전체 반성 — IBL 현황과 그 바깥 (2026-09-11)

> 계기: 의식 에이전트의 역할을 감독·검수로 통합(09-10~11)하면서 인지층 구조가 바뀌었다. 이 문서는 그 변경을 판정하는 것이 아니라, 지금의 몸 전체를 한 번 내려다보고 **단순한 일을 복잡하게 처리하는 자리**를 찾는다. 읽기 전용 감사(층별 조사 4벌 + 실측)이며 아무 코드도 바꾸지 않았다.
>
> 판정 요약: **IBL 언어 자체는 건강하다. 복잡성은 언어가 아니라 언어 *주변의 배관*과 인지층의 *신구 공존*, 그리고 사건마다 관문·시험·문서를 하나씩 더 얹는 *누적 방식*에서 온다.**

---

## 0. 실측 — 몸의 크기와 성장 속도

| 시점 | backend .py(시험 제외) | 줄 | 시험 파일 |
|---|---:|---:|---:|
| 2026-07-15 | 169 | 79,957 | 4 |
| 2026-08-01 | 220 | 93,498 | 4 |
| 2026-08-15 | 251 | 98,435 | 14 |
| 2026-09-01 | 289 | 117,726 | 147 |
| **2026-09-11** | **344** | **137,888** | **288** |

- 6주에 **+44K 줄**, 최근 열흘에 +20K 줄. 시험 파일은 열흘에 141개(하루 13개) 늘었고 그중 80개(11,150줄)가 사건·날짜 이름(`test_episode3395_*`, `*_2026_09_07`).
- 커밋 속도: 8월 말~9월 초 주당 170~218건. `docs/` 125개 중 **45개가 2026-09 한 달치**이고 60개(48%)는 저장소 어디서도 참조되지 않는다.
- pre-commit 훅 534줄, 호출 관문 스크립트 **30종**. 주간·일일 감사 기관 15종이 각자 `*_state.json`/`*_flags.json` 짝을 `data/` 루트에 둔다(루트의 json/yaml 82개).
- 구성: 뇌(`ibl` 24K + `cognition` 29K) 53K / 표면·저장소·서비스·바닥·프로바이더 74K / 패키지 94K / 프론트 43K / 시험 46K / 빌드·검사 스크립트 30K.
- `data/` 실사용 저장소는 작다(ibl_usage 15MB, world_pulse 70MB). 무게는 `showcase_stage` 27GB, `_backups` 3GB, `spill` 70MB(그중 `tool_evidence` 37MB — 청소 코드 없음).

성장 자체는 문제가 아니다. 문제는 **성장의 단위**다. 아래 4장에서 다룬다.

---

## 1. IBL — 현황

### 1.1 언어 (건강)

- 6노드 164액션, op 값 381개(op 있는 액션 74개, 평균 4.3개). 라우터 분포: handler 136 · system 18 · channel 7 · driver 1 · workflow 1 · trigger 1. **`api_engine` 라우터를 쓰는 액션 0**.
- 문법: `>>` `&` `??` 괄호 분기, `;`/개행 문장 경계, `[on_error]`, if/case, try/catch/finally, repeat, goal, `[def:]`/`[fn:]`, `$변수`(턴 범위), `[table:each]`, 술어 언어, 정적 통화 검사(T1/T2). 전부 파서·엔진 한 벌이 소유하고 workflow_engine 은 블록을 재구현하지 않는다 — 좋은 상태.
- 어휘 단일 소스(`ibl_nodes_src/*.yaml` + 패키지 `ibl_actions.yaml`) → 빌드 파생(`ibl_nodes.yaml`·`tool.json` 40개·fixtures·문서 마커 13구간). 삼각검증(src↔tool.json↔handler AST)은 **세 자리가 구조적으로 동기화돼야 하므로 정당**하고, `tool.json` 을 검증에서 파생으로 승격한 것은 옳은 방향이다.

### 1.2 한 문장이 지나는 길 (20단계)

`api_ibl.execute_ibl_code` → `system_tools_ibl._execute_ibl_unified`(초크포인트) → 파서(+blocks/values/scope/code_ir/code_binding) → 턴 변수 주입 → typecheck → retyping 관문 → T1/T2 → progress 티켓 → `workflow_engine.execute_pipeline` → parallel/fallback → `ibl_engine.execute_ibl` → 블록/라우터 디스패치 → 패키지 `_OP_DISPATCHERS` → quality/criteria → traceback·honesty 표지 → **diet → _bound → _compact_currency → preview → result_ref** → 턴 변수 저장 → 표시 경계 → 공개 결과 직렬화.

실행 전 검사 6단계, 실행 후 축소 6단계. 실행 자체는 가운데 넷.

### 1.3 IBL 쪽 과복잡 (우선순위순)

| # | 무엇 | 증거 | 더 단순한 것 | 위험 |
|---|---|---|---|---|
| I-1 | **모델용 결과 축소 메커니즘 10개, 한 반환 경로에 6개 순차 적용** | diet_envelope · preview_envelope · display_delivery_budget · `_compact_currency` · `_bound` · result_ref · `_spill_if_large` · 병렬가지 스필 · `_pp_compress` · providers 16K 절단(3벌 복제). 임계값 160/300/1,000/3,000/16,000/200,000자가 4개 모듈에 분산. preview 가 남긴 160자를 `_bound` 가 1,000자로 다시 재고 providers 가 16K 로 또 자른다 | `model_result_view.project_result` 를 유일 진입점으로, 임계값은 `lifecycle_policy.yaml` 한 블록(retyping 이 선례) | 중 — 봉투 회귀 시험 다수 존재 |
| I-2 | **`verbose` 가 무효 플래그** | `tool_loader.py:248` 스키마에 노출되나 `model_result_view.py:93,117` 이 `False` 고정. `retired_contracts.yaml:29` 가 이 계약을 은퇴시켰는데 스키마 자리가 남음. `system_tools_ibl.py:737,790,939` 의 `diet_envelope` import 3줄 미사용 | 스키마에서 제거 | 없음 |
| I-3 | **T1/T2 통화 검사 3중 실행** | `system_tools_ibl.py:654`(typecheck 내부) · `:799` · `workflow_engine.py:189/203` | 초크포인트 1회 + "검사됨" 플래그 전달 | 낮음 |
| I-4 | **`api_engine`+`api_pipeline`+`api_transforms` 1,682줄이 IBL 에서 도달 불가** | `backend/ibl/` 에 살면서 router 참조 0. YAML `pipeline:`/`for_each:`/`{step._result}` — IBL `$var` 와 별개의 **두 번째 이음매 언어**를 유지. `system_tools.py:1003` 직접 호출만 생존 | 사용량(`ibl_usage.db`/`pulse.db`) 확인 후 은퇴, 또는 `services/` 이주 | 중 |
| I-5 | **`execute_pipeline` 915줄 단일 함수** | `workflow_engine.py:105~1019`, 클로저 8개, 중첩 6단, `_seq` 딕셔너리 12키가 지역 전역. 1500줄 규칙 때문에 contract/binding/store 로 쪼갰지만 전부 재수출해 의존 그래프상 1,436줄 단일 이름 | `PipelineState` 데이터클래스 + 실패처리·스필을 모듈 함수로 | 낮음(기계적) |
| I-6 | **독립 ThreadPool 5벌** | `workflow_parallel:58/193` · `ibl_exec_each:552` · `api_pipeline:109` · `ibl_engine:558` · `channel_engine:560`. worker·타임아웃·예외 정책 제각각 | `common/` executor 팩토리 1개 | 중 |
| I-7 | **손으로 쓴 문자 스캐너 10벌** | 중괄호·괄호·따옴표 상태를 `ibl_parser`·`_values`·`_blocks` 의 함수 10개가 각자 재구현(인용부호 스킵 루프만 14곳) | 토크나이저 1개 위에 `split_top_level(text, sep)` | 중상 — 골든 코퍼스 회귀 필수 |
| I-8 | **파라미터 파서 이중화** | `_parse_params` JSON 경로 ↔ `_parse_relaxed_params` 손파서, 선착순 채택 | 느슨 파서를 정본, JSON 은 고속 경로 | 중 |
| I-9 | **죽은 것** | `event_engine.py`(7줄, importer 0 — 문서 4곳만 언급) · 참조 0 함수 12개(`ibl_ops.op_fixture`, `tool_selector` 4개, `api_engine` 3개 …) · `tool_selector.py` 519줄 중 `SystemDirector` 만 생존 · `ibl-core` 패키지 스텁+`tool.json.bak` 59KB · `radio` 도달불가 op 2개 | 삭제 | 없음 |
| I-10 | **빌드 기계에 얹힌 이물** | `iblbuild_appview.py` 877줄은 어휘가 아니라 **앱 뷰 DSL** 검증. `iblbuild_docs.py` 460줄은 문서 9개의 수치를 정규식 외과치환 — 산문 편집이 어휘 빌드를 깨는 결합 | appview 는 별도 빌드, 문서 마커는 "구간 통째 재생성"만 | 낮음 |

**IBL 에서 건드리지 말 것**: 문법·의미론, 삼각검증, `flow:`/`side_effect:`/fixture 선언 체계, `workflow_verdict.is_error_result` 같은 단일 판정 소유.

---

## 2. IBL 바깥 — 현황

### 2.1 인지층 (의식·감독·평가·증류)

한 턴의 실제 경로는 `agent_pipeline.cognitive_stream` 한 드라이버가 엮는다: 관문 통지 → pursuit 바인딩 → 감독 객체 → 연상 → 분류 → 의식(또는 규정 재사용) → 프롬프트 재조립 → 실행(도구마다 `supervision_bus.wrap`) → **finalize(감독) 또는 GoalEval(구)** → 자기반성 → 증류 큐.

| # | 무엇 | 증거 | 더 단순한 것 | 위험 |
|---|---|---|---|---|
| C-1 | **평가 엔진이 셋, 그중 구 GoalEval 은 도달 불가** | `conscious_supervisor.py:222` `enabled = bool(framing) or enabled` → 의식 출력이 있으면 항상 감독 ON. `agent_pipeline.py:721` 의 `elif consciousness_output` 은 앞 `if _supervisor.enabled` 를 못 넘긴다. `cognitive_eval.py` 822줄 중 루프 본체 ~330줄 사망, 그러나 `goal_eval.max_rounds` 설정·`revise_from_eval` 배선은 살아 있는 것처럼 보임. 세 번째 루프 `agent_goals._judgment_loop` 는 감독·과제원장과 미연결 | `_extract_achievement_criteria`·`_collect_visual_artifacts` 등 부품만 `eval_inputs.py` 로 남기고 루프 삭제. 단 `open_supervisor` 가 None 을 돌려주는 빈도(agent_id 없는 위임·스케줄 턴)를 먼저 로그로 잰다 | 중 |
| C-2 | **의식이 전체 카탈로그(56,737자)를 매 턴 받음** | `consciousness_agent.py:139` 가 `build_environment()` 를 인자 없이 호출 → `compact=False`. 의식이 내는 건 액션 *이름*(`highlight_actions`)뿐인데 ⟨인자⟩⟨열⟩⟨동반⟩ 37K자를 받는다. 실행자는 brief 19,384자 | `compact=True` 한 줄 — 턴당 **−37K자(≈9K 토큰)** | 낮음 — 09-10 진단 문서도 "의식 입력이 자료 읽기 전부터 크다"고 지적 |
| C-3 | **신원·예산을 나르는 객체 6종** | thread_context · model_call_context · `_turn_token_ledger` · supervision_bus · Supervisor.usage 3벌 · pursuit Binding. 같은 agent_id 를 4곳이 각자 유도(`reframe:93`, `agent_pipeline:869`, `supervision_bus:9`, `conscious_supervisor:41`). `Supervisor.__init__` 인스턴스 필드 50여 개 | 턴 신원 1객체(`TurnIdentity`)를 contextvar 로, 나머지는 그것을 참조 | 중 |
| C-4 | **턴 중 지시 주입 채널 3종** | steer_inbox · reframe · Supervisor.pending — 셋 다 "도는 실행자에게 다음 도구 결과로 텍스트를 얹는다". TTL·상한·정리 코드가 3벌 | Supervisor 가 이미 도구 경계를 쥐므로 `pending` 큐에 source 태그로 합류(재규정의 의식 재호출은 유지) | 중 |
| C-5 | **감독 예산 회계 4중, 판정 신선도 프로토콜 2중** | `DEFAULTS` 예산 키 11개, finalize 재검수 판정에 중간값 5개. `review_conditions` 지문과 `exec_revision` 카운터가 같은 질문에 둘 다 답함(`_take_pending:409`) | `budget_mode` soft 고정 + `max_repairs` 횟수, 신선도는 `exec_revision` 하나 | 중 |
| C-6 | **증류 경로 6종, 그중 셋은 저장소별 사본** | `memory_consolidation`·`forage_consolidation`·`run_hippocampus_consolidation` 이 각자 `_is_due` + LLM 병합 프롬프트 | 카덴스·병합 정형 1벌, 저장소 어댑터만 다르게 | 낮음 |
| C-7 | **의식 파일 안의 프로바이더 팩토리** | `consciousness_agent.py:645~1018` 약 340줄 — `_get_lightweight/midtier/midtier_legacy/system_oneshot/execution_image` + 3단 폴백 2벌. `model_resolver` 가 이미 역할→축→티어를 푼다 | `_resolve_oneshot_provider` 한 겹만, 파일 분리 | 낮음 |
| C-8 | 소품: `_PriorityLock` 44줄(증류 워커가 이미 단일 스레드), REPAIR 그랜트 발급 블록 26줄 2벌, `_collect` 95줄이 같은 도구 호출을 두 평행 리스트로 유지(감독이 세 번째 궤적을 또 쌓음) | — | 각각 10줄 | 없음 |

### 2.2 텍스트 기질 (프롬프트·가이드·문서)

| # | 무엇 | 증거 | 더 단순한 것 |
|---|---|---|---|
| T-1 | **IBL 문법 3판 독립 서술** | `12_ibl_compact.md` 1,834자 / `12_ibl_only.md` 22,638자 / `ibl.md` 160,587자 — 줄 교집합 사실상 0(복붙이 아니라 세 번 따로 씀, 유지보수 3배). `.deprecated` 4번째 판 13,105자 | `12_ibl_only` 를 `ibl.md` 마커 발췌로 파생(codebase_map 선례) |
| T-2 | **가이드 색인 2벌 + 자기모순** | 자원 목록 1,422자(74제목, 항상) + `<execution_map>` guide 줄 4,850자(항상). execution_map 주석은 "guide 가 **유일한** 목차"라 선언 | 자원 목록 폐지 |
| T-3 | **가이드 77개 중 31개가 25일간 0회 주입** | `guide_usage.db` 08-17~09-11: 주입 46/77, 총 379회. 그런데 lifecycle·guide_audit(LLM)·guide_downscale 세 기관이 77개 전부를 순찰 | lifecycle 의 candidate/retire 를 가이드에 실제 집행 |
| T-4 | **쌍둥이·보고서 골격 4벌** | `delegation_agent`↔`delegation_system_ai`(액션 겹침 1.00, heading 10 공통, 11KB). 보고서 가이드 4종 105KB 가 쌍별 0.50~0.79 겹침 | 한 파일+대상 절 / 공통 골격 12KB + 도메인 절 4×4KB(−75KB) |
| T-5 | **docs/ 125개, 48% 무참조, 9월 45개** | 런타임 AI 는 `docs/` 를 읽지 않는다(읽는 건 `system_docs/`뿐). anatomy 가 가리키는 5 + system_docs 가 가리키는 43 만 산 문서 | `docs/archive/<월>/` 이동. **이 문서도 행동 뒤엔 같은 운명** |
| T-6 | **사건-핀 시험 80개 + `__main__` 287/288** | 주제 중복(idiom 8개, language_revision 4개). pytest 도입 전 자기실행부 유물 | 주제별 통합, `__main__` 일괄 제거 |
| T-7 | 고아 스크립트 23개(`seed_*` 11, `migrate_*`, `iblbuild_guide_wiring`, `iblbuild_params_check`…) | 훅·CI·backend·문서 어디서도 참조 0 | `scripts/oneshot/` 또는 삭제 |

### 2.3 표면·저장소·부팅·프로바이더·프론트

| # | 무엇 | 증거 | 더 단순한 것 | 위험 |
|---|---|---|---|---|
| S-1 | **재기동 안전 9겹** | uvicorn 디바운스 · excludes · quiescent_reload · reload_gate · red_apply · red_watchdog · keeper 3스트라이크 · `.intentional_shutdown` · preflight. 타임아웃 5개(300/110/600/900/120s)가 서로 참조하며 균형(`backend_keeper.sh:151-156` 이 "kill→콜드로드→kill 3연타 실측" 기록). 각 겹은 실제 사고(ep1673/1689/1917/2519/2520)에서 나왔다 | **blue/green**: 새 프로세스를 다른 포트에 띄우고 /health 초록이면 리스너 스왑, 옛 몸은 턴 끝내고 자연사. 3·4·5·6·9 가 전부 불필요 → 2겹 | 중 — 자기수리 경로 재배선 |
| S-2 | **"에이전트가 한 일" 원장 6중** | episode_log · trajectory_event · write_ledger.jsonl · supervision_store events/cost · pursuit_ledger · conversation_db. 조인 키(`task_id`) 전파 주석이 6개 파일에 흩어짐(`write_ledger:5`, `episode_logger:269,839`, `thread_context:337,559`, `mcp_server:27-36`, `red_grant:20`) — **키가 프로세스·스레드·HTTP 경계를 6번 건너야 하는 것 자체가 비용** | episode_log 를 단일 이벤트 스트림, 나머지는 그 위의 뷰 | 높음 — 헌법급 |
| S-3 | **쓰기 전용 원장** | `boot_profile.jsonl` 528KB 리더 0(`api.py:352`), `body_ask_log.jsonl` 리더 0, `write_ledger.jsonl` 5.3MB 는 `[self:body]{op:writes}` 낱말만 읽음 | 회전 또는 삭제 | 없음 |
| S-4 | **런처 표면 3벌** | React `Launcher.tsx` 1,198 / 파이썬 문자열 속 JS ≈3.9K(`launcher_web_*`+`launcher_app_*`) / lite 859. 렌더 로직만 `app_render_core.js` 공유, 마크업·상태·조립은 3중 | 원격은 React 번들 서빙(이미 `/nas/app` 이 그렇게 함), lite 만 예외 | 낮음 |
| S-5 | **설정 페이지 2벌·로그 뷰어 3벌·MessageContent 2벌** | launcher SettingsDialog 계열 2,895줄 vs manager SettingsDialog 370, 공유 0. `SystemLogViewer`+`EpisodeJournal` 이 같은 페이지에 나란히, `launcher_app_manual.py` 가 같은 API 3개를 원격 HTML 로 재구현 | 하나씩 | 낮음 |
| S-6 | **모델 설정 6파일 + 3단 폴백** | `model_gear` + lightweight/midtier/unconscious/vision/system_ai 5개 json. `unconscious_ai_config` 편집 라우트는 프론트 호출자 0 | 단일 `models.yaml`, 폴백 제거 후 정직 실패 | 낮음 |
| S-7 | **죽은 프로바이더 1,489줄** | `anthropic.py` 777 · `ollama.py` 663 · `openrouter.py` 49 — 어떤 설정도 안 가리킴. 실제 도는 건 claude_code+deepseek(openai 상속)+gemini(무의식) | 미설치 시 안내로 대체 | 낮음 |
| S-8 | **죽은 라우트 ~28개, ≤3 라우트 라우터 10개** | `/goals/*` 4 · `/world-pulse/{pulses,self-checks,run-self-check,diagnostic-report}` 4 · `/unconscious-ai` · `/xray/goals` · `/nodes/live` … **`api_gmail.py` 라우트 9개 전부 호출자 0** — 실제 Gmail 경로는 HTTP 를 건너뛰고 `get_gmail_client_for_email` 을 직접 부른다(`channel_engine.py:402`, `portal_auth.py:216`), 프론트는 `/business/channels/gmail/authenticate` 만 씀. `api_health`(41줄)·`api_finance`(43줄)·`api_business` 의 `/sync/export|merge` **3중 동형 복제** | 삭제 / `/sync/{domain}` 하나 / gmail 은 라우터 등록만 빼고 헬퍼를 `channel_engine` 쪽으로 | 낮음 |
| S-9 | **`api_websocket.py` 1,369줄에 라우트 2개** | 이름은 라우터, 실체는 스트림 오케스트레이터 | cognition/services 로 이동 | 낮음 |
| S-10 | services 의 LLM 스크래치 | `gen_newspaper.py`/`generate_newspaper.py` importer 0, 본문에 "mocked for the script, I will replace…" 독백. `backend/newspaper.html`, `backend_restart_20260719.log` 커밋됨 | 삭제 | 없음 |

### 2.4 관문·감사 기계 (횡단)

- 실행 중 관문(매 턴/도구): selfbuild_gate 261줄 · shell_shadow_gate 636줄 · supervision_hook · ibl_distill_gates 315줄 · retyping 관문 · typecheck.
- 일일: derived_freshness · component_lifecycle 756줄 · run_daily_health_check.
- 주간: guide_audit(LLM) · guide_downscale · ibl_description_audit(LLM) · corpus_vocab_audit · vocab_overlap_audit · vocab_crystallization · data_ownership · doc_drift 410줄 · store_waste · fixture_sweeps ×5.
- **산출**: `guide_audit_flags` {flags:[]} · `doc_drift_flags` {flags:[]} · `guide_downscale_flags` {targets:[]} · `lifecycle_flags` {total:257, candidates:0, retired:0, verdicts:0}. 9개 감사가 각자 `_should_run`+`_save_state` 를 구현하고 `weekly_audits.py` 정형에는 4개만 합류. `world_pulse_health.py` 1,451줄(규칙 1500 임박)의 `run_maintenance_bundle` 이 항목당 8~20줄 try 블록 × 10.

이 기계들은 개별로는 전부 "한 번 샜던 자리"에 세운 정당한 것이다. 문제는 **감사가 0 을 계속 보고해도 카덴스가 줄지 않고, 상태 파일이 루트에 쌓이며, 새 감사가 정형에 합류하지 않는다**는 데 있다.

---

## 3. 왜 이렇게 됐나 — 다섯 패턴

1. **사건 → (관문 + 시험 + 문서) 한 벌씩.** 에피소드 하나가 시험 파일 하나, docs 하나, 관문 하나를 낳는다. 각 산출물은 그 사건에 대해 옳다. 그러나 열흘에 시험 141개·문서 45개·관문 30종이 되면 **누적물이 스스로를 못 본다** — 80개 사건-핀 시험은 주제별로 8개·4개씩 같은 것을 찌른다.
2. **새 것을 세우고 옛 것을 안 치운다.** GoalEval↔감독 finalize, 3 문법판, 6 신원 객체, 10 축소 메커니즘, 9 재기동 겹, 3 런처 표면, 6 모델 설정, 3 sync 라우트. 매번 "호환 경로로 남긴다"가 정당했고, 합치면 **판정을 두 번 하는 구조**가 된다. 09-06 기억의 교훈("한 방향만 보는 감사는 반대로 샌다")이 여기서도 적용된다 — 소비처 없는 생산자를 찾는 관문은 있지만, *새 소유자가 생겼을 때 옛 소유자를 은퇴시키는* 관문은 없다.
3. **감사가 감사를 낳는다.** 15개 상태 파일, 대부분 flags 0. 관측을 늘리는 건 쉽고 관측을 줄이는 규칙은 없다(`no-counter-watch` 원칙의 역방향).
4. **1500줄 규칙의 부작용.** 규칙은 파일을 쪼개게 하지만 의존을 끊게 하진 않는다. `workflow_engine` 은 셋으로 갈라 전부 재수출, `api_nas_hls` 는 분할 이유가 규칙뿐, 프론트 16개 파일이 한도 바로 아래에 안착.
5. **자기 기록의 다중화.** 같은 턴이 6곳에 적히고, 그 6곳을 잇는 키 전파가 코드 곳곳에 주석으로 산다. 몸 원장(`[self:body]`)의 취지 — "변화 자체가 회상 가능해야 한다" — 는 옳지만, 그 원장이 하나가 아니면 회상도 여섯 번 한다.

---

## 4. 단순화 후보 — 우선순위

### A. 위험 낮음·즉시 (사용자 판정 불요, 근본 집행 대상)

| 항목 | 절감 |
|---|---|
| C-2 의식 `compact=True` | 턴당 −37K자(≈9K 토큰), THINK 턴마다 |
| I-2 `verbose` 스키마 제거 + 미사용 import 3줄 | 모델 재실행 유인 제거 |
| I-9 · S-3 · S-7 · S-8 · S-10 죽은 것 삭제(event_engine, 참조0 함수 12, 라우트 28, 프로바이더 1,489줄, 스크래치, 쓰기전용 원장) | ≈4K 줄 |
| C-8 소품 셋(`_PriorityLock`, 그랜트 중복, `_collect` 평행 리스트) | ≈150줄 |
| T-2 자원 목록 폐지 · T-4 쌍둥이 가이드 병합 · T-7 고아 스크립트 격리 | 턴당 −1.4K자, −5KB, 23파일 |
| 2.4 감사 카덴스 정형화(`AUDITS` 4튜플로 카덴스 소유, `_should_run` 9벌 제거) + **0-flag 3회 연속이면 카덴스 감쇠** | `world_pulse_health` −200줄, 상태 파일 15→1 |
| I-3 T1/T2 1회 계산 | 문장당 검사 3→1 |

### B. 설계 판정 후 집행 (한 세션 규모, 회귀 시험 있음)

| 항목 | 요지 |
|---|---|
| C-1 구 GoalEval 루프 제거 | 먼저 `open_supervisor` None 빈도 로그. 그 경로가 실존하면 감독을 fail-closed 로 만들고 루프 삭제 |
| I-1 축소 메커니즘 10→1 소유자 | `project_result` 단일 진입, 임계값 정책 한 블록 |
| I-4 `api_engine` 3형제 1,682줄 | 사용량 확인 → 은퇴 또는 services 이주. IBL 밖 두 번째 이음매 언어를 없앤다 |
| C-3·C-4·C-5 턴 신원 1객체, 주입 채널 1큐, 예산 회계 1겹 | 감독 통합의 마무리 — 09-10 통합이 옳았다면 그 주변 옛 객체가 은퇴해야 통합이 끝난다 |
| T-1 문법 3판→1 파생 | `12_ibl_only` 를 `ibl.md` 마커 발췌로 |
| S-4·S-5·S-6 런처 3→1(+lite), 설정·로그 뷰어 1벌, 모델 설정 1파일 | 프론트·표면 |
| I-5·I-6·I-7 execute_pipeline 상태 추출, executor 팩토리, 토크나이저 1개 | 파서·엔진 배관(의미 불변) |

### C. 헌법급 — 사용자 판정 필요

| 항목 | 왜 판정인가 |
|---|---|
| **S-1 재기동 9겹 → blue/green 2겹** | "살아 있는 프로세스가 자기 코드를 고친다"는 전제를 "새 몸을 옆에 띄우고 스왑한다"로 바꾸는 것. keeper 교리(09-17 개정)·RED 경로 전부가 이 전제 위에 있다 |
| **S-2 자기 기록 6중 → 단일 이벤트 스트림 + 뷰** | 몸 원장·과제 원장·감독 작업대·에피소드가 저장 모델을 공유하게 되는 언어급 변경 |
| **성장 규율**: 사건 하나에 시험·문서·관문을 *추가*하는 대신 *기존 것에 합류*를 기본값으로. 시험은 주제 파일에 케이스로, 문서는 system_docs 절에 갱신으로, 관문은 정형 레지스트리에 한 줄로 | 이건 코드가 아니라 작업 방식이라 사용자만 정할 수 있다. 지금 속도(주 200커밋)에서 이 규율 없이는 A·B 를 다 해도 두 달 뒤 같은 자리다 |

---

## 5. 반성의 경계 — 건드리지 말 것

- IBL 문법·의미론. 언어 개정은 별도 판정 경로.
- 삼각검증·fixture·`side_effect:`·`flow:` 선언 체계 — 세 자리 동기화는 구조적 필요.
- 09-10 의식 감독 통합 자체. 09-10 진단 문서의 결론("통합 구조를 폐기할 근거 없음")과 이 감사는 일치한다. 문제는 통합이 아니라 **통합 뒤 남은 옛 배관**이다.
- 실제 사고에서 나온 관문들의 *존재*. 다만 그것들이 **정형에 합류하고, 0 을 보고하면 줄어들고, 새 소유자가 생기면 은퇴하는** 규칙이 없다는 것이 이 문서의 지적이다.

---

## 6. 제안하는 다음 걸음

1. A 묶음을 한 세션에 집행(전부 위험 낮음, 회귀 시험 존재). 먼저 C-2 한 줄.
2. C-1 의 `open_supervisor` None 로그 하나를 오늘 심고 사흘 관찰 → B 착수.
3. C 셋은 사용자 판정. 특히 세 번째(성장 규율)는 이 문서를 포함한 모든 산출물의 운명을 정한다.

*조사 근거: 층별 읽기 전용 감사 4벌(인지 / IBL / 텍스트 기질 / 표면·저장소·부팅·프로바이더·프론트) + git 실측. 수치는 2026-09-11 `9c1dfc8c` 기준.*
