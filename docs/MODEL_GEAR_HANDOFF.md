# 모델 기어 — 핸드오프 (다음 세션 이어가기)

> 정본 설계: `docs/MODEL_GEAR_DESIGN.md` · 메모리: `project_model_gear`
> 이 문서는 *이어서 무엇을 어떻게* 할지의 실행 지침.

## 0. 한 줄 목표

계기판 레버 하나(절약/균형/최대)로 시스템 전체 모델 등급을 변속. 텍스트 역할은 **4축**
(분류·평가·실행·의식)→기어→티어(경량/중급/고급)로 해소. 모달리티(이미지·임베딩)는 기어 밖.
근거: 속도 명제(대부분 작업은 심사숙고 불요, 최고 모델은 비싸고 느림) + 튼튼함=속도(같은 메커니즘).

## 1. 현재 상태

### ✅ 완료
- **1단계 — 리졸버 + 스키마** (동작 변화 0, 검증 완료)
  - `backend/model_resolver.py`: `resolve(role, agent_id?)` → `{provider, model, api_key, tier, axis, source}` /
    `get_gear()` / `set_gear(name)` / `list_gears()` / `get_provider_for(role, agent_id?, system_prompt, tools)` /
    `clear_provider_cache()`. config 매 호출 읽음(핫리로드), provider 캐시 키=`bucket|provider|model|keyhash`
    (bucket=oneshot/session — 2단계서 추가).
  - `data/model_gear.json`: `current_gear`, `tiers`(경량→lightweight_ai_config / 중급→midtier / 고급→system_ai),
    `presets`(절약/균형/최대 4축), `role_axis`(역할→축), `overrides`(핀), `modality`(기어 밖).
  - API key 폴백: 티어 키 비면 고급(system_ai) 키 사용(기존 _get_midtier_provider 동작 보존).
- **UI 정리** (tsc 그린)
  - `SettingsDialog.tsx`: 3탭(시스템/경량/중급) → **`모델 설정` 1탭**(경량→중급→고급, flex order). '시스템'→'고급' 라벨.
  - 새 탭 **`시스템 AI 역할`**: 프롬프트 템플릿 + 역할 프롬프트(편집 모달) + **시스템 메모**(api.getProfile/updateProfile 자체 로드·저장).
  - `Launcher.tsx`: 상단 '메모' 버튼 제거, `ProfileDialog` 완전 은퇴(파일 삭제+index export 제거+핸들러/상태/키보드/`User` import 정리).

- **2단계 (부분) — 원샷 호출 이관** (2026-06-29, 동작 변화 0, 라이브 검증 완료)
  - `consciousness_agent.py`: 새 헬퍼 `_resolve_oneshot_provider(role)` — `model_resolver.get_provider_for(role)`
    로 원샷 provider 획득 + `disable_session_persistence` 강제(원샷 계약, hasattr 가드=google엔 무영향).
    `lightweight_ai_call`·`system_ai_call` 에 `role` 인자 추가(기본 classify / translate),
    폴백 순서=리졸버→옛 getter→의식 에이전트.
  - **이관 완료된 표 항목**: #1 classify(기본값) · #3~8 background(consciousness_fit_gate / distill_deep×2 /
    distill_forage / forage_consolidation×2 / ibl_usage_rag reflection / ibl_engine recall 압축) +
    `memory_consolidation.py` 2곳(표 밖, background) · #2 evaluate(평가자, opus→경량 개선) · #14 translate(수동번역).
  - 검증: 전 모듈 컴파일 OK / 리졸버 4역할 provider 생성 확인 / 백엔드 재시작 후
    `/ibl/translate` 종단(`role=translate`→실행축→중급→flash-lite, `[sense:weather]{city:"서울"}` 산출).
- **2단계 (이어서) — 의식 분리(#9) + 프로젝트 에이전트 상속(#11)** (2026-06-29, 동작 변화 0)
  - **#9** `consciousness_agent._init_provider`: `load_system_ai_config` → `resolve('consciousness')`.
    의식을 시스템AI 설정에서 분리(이제 기어 의식 축이 따로 해소). 키/모델 없으면 비활성(보존),
    세션비활성 보존. import 검증: `[ConsciousnessAgent] 초기화 완료 (google/flash-lite, gear:균형|의식→중급)`.
    ★의식은 원래도 config 변경 시 재초기화 훅이 없었음 → 회귀 없음(핫리로드는 3단계 몫).
  - **#11** `agent_cognitive._init_ai`(프로젝트 에이전트 분기) + 새 헬퍼 `_resolve_execution_config(ai_config, agent_id)`.
    우선순위 = **기어 중앙 핀(overrides[agent_id]) > yaml ai.model 핀 > 실행 축 상속**. 판정은
    `resolve('execution', agent_id).source.startswith('override:')`. 현재 모든 에이전트가 yaml 핀 보유 →
    동작 변화 0. 새 capability = `model_gear.overrides`로 yaml 핀까지 중앙에서 갈아끼움.
    검증: 임시 override 에이전트→고급(is_override=True) / 일반 에이전트→중급(yaml 존중), model_gear.json 원복.

- **2단계 (완료) — init 시점 provider 구성 이관 #10·#12~13·#15·#16 + oneshot 버킷** (2026-06-29, 동작 변화 0)
  - **리졸버 oneshot 버킷**: `get_provider_for(role, oneshot=False)` — 캐시 키에 `oneshot|`/`session|` 버킷
    prefix + oneshot이면 `disable_session_persistence`. 옛 2-싱글턴(lightweight=원샷 / midtier=세션) 재현.
    검증: 같은 모델이어도 oneshot/session 객체 분리(다른 id), 같은 버킷 재호출은 같은 객체(싱글턴).
    `_resolve_oneshot_provider`→`oneshot=True`. reset 훅 3종(`reset_midtier/lightweight/system_oneshot`)이
    `_clear_resolver_cache()`로 리졸버 캐시까지 비움 → 티어 config 변경 핫리로드 보존.
  - **#10** `system_ai_core`: 새 `_resolve_system_ai_config()` = `resolve('system_ai')`(실행 축), 변경 감지도
    해소 결과 기준 → 기어/설정 변경 시 자동 재생성. 폴백=옛 system_ai_config.
  - **#12/#13** `consciousness_agent._get_midtier_provider`를 리졸버 `get_provider_for('reflex', oneshot=False)`
    위임으로 재정의(3 호출처 agent_communication/api_websocket/`_switch_to_midtier` 무변경 — 변이-스왑 패턴 보존).
    옛 본체는 `_get_midtier_provider_legacy`(폴백). ★캐시-공유 우려는 oneshot 버킷으로 해소(검증 완료).
  - **#15** android(`android_agent._init_ai`→`resolve('android')`) / auto_response(`_resolve_tool_capable_config`
    1순위 `resolve('auto_response')`, 단 SDK 가능 provider일 때만 — claude_code면 기존 파일스캔 폴백) /
    channel_poller(게이트 `_load_system_ai_config`→`resolve('system_ai')`, no-key provider 지원).
  - **#16** 슬라이드 텍스트 `slide_author`·`slide_native`의 `_get_author_ai`→`resolve('content_text')`
    (새 `_resolve_content_text_config`, 폴백=옛 config). ★슬라이드 이미지(Gemini/`_gemini_key`)=모달리티, 무변경.
  - 검증: 전 모듈(backend+slide 도구) 컴파일·import OK / android·auto_response·content_text 해소=실행축→중급.
- **4단계 — 계기판 레버 + 핫리로드 훅** (2026-06-29)
  - **핫리로드 훅**: `consciousness_agent.reset_consciousness_agent()`(싱글턴 None+리졸버캐시 clear) +
    `system_ai_core.reset_system_ai_runner()`. 기어 변경 시 init-시점 provider 가 다음 호출에서 새 티어로 재구성.
  - **gear REST** (`api_config.py`): `GET /model-gear`(현재 기어·gears·presets·4축 대표역할 resolve=tier/model) +
    `PUT /model-gear {gear}`(set_gear → 리졸버 캐시 clear + 의식·시스템AI 러너·midtier/lightweight/oneshot 리셋).
    `_describe_gear()`=4축(분류=classify/평가=evaluate/실행=execution/의식=consciousness) resolve 표시.
  - **레버 UI = 계기판**(★ManualMode '계기판' 탭 — *설정 다이얼로그 아님*. 모델 기어=조작 계기라 계기판이 제자리):
    신규 `ModelGearLever.tsx`(launcher-components, stone 팔레트) 계기판 최상단(시스템 상태 위). 절약/균형/최대
    세그먼트 + 4축→티어 요약 + ⚙ 설정 토글. `api.getModelGear/setModelGear`(api-system-ai.ts). tsc green.
  - 검증(단위): set_gear 왕복, `_describe_gear` 4축 표시, 리셋 함수 호출 OK.
  - ✅검증(라이브): `GET/PUT /model-gear` — 최대→고급/절약→경량/균형 원복/잘못된 기어 400/변속 직후 채팅 정상.
    브라우저 프리뷰=계기판 최상단에 모델 기어 렌더 확인(스크린샷).
- **5단계 — 프리셋 편집기 + 에이전트 핀** (2026-06-29, ⚙ 설정 안에서)
  - **model_resolver 셰터**: `set_presets(presets)`(축=AXES·티어=TIERS 검증)·`set_overrides(overrides)`·`get_presets`·
    `get_overrides`. 상수 `AXES`/`TIERS` 노출. `_write_gear`(쓰기+캐시 clear) 공용화.
  - **REST**(`api_config.py`): `PUT /model-gear/presets {presets}`(기어×축→티어 편집) +
    `GET/PUT /model-gear/overrides`(에이전트 핀). `_reset_gear_providers()` 공용 리셋. `_list_pinnable_agents()`=
    시스템AI + 전 프로젝트 에이전트. ★핀 키=`{project}:{agent_id}` 복합키(agent_id 가 프로젝트 간 중복=여러
    'agent_001'). `_describe_gear` 에 `tiers`/`axis_names` 추가.
  - **★핀 키 일치**: `agent_cognitive._resolve_execution_config` 가 resolve 에 넘기는 키를 `{project_id}:{agent_id}`로
    바꿈(= registry_key 형식, _list_pinnable_agents 와 동일). 안 그러면 핀이 동명 에이전트 전체에 걸림.
  - **UI**: `ModelGearLever` ⚙ 설정 패널 = 프리셋 표(기어×축 드롭다운+저장) + 에이전트 핀 목록(에이전트별
    "기어 따름"/티어 고정 드롭다운). `updateModelGearPresets`·`getModelGearOverrides`·`updateModelGearOverrides`.
  - ✅검증(라이브): 프리셋 PUT(균형 실행 중급→고급 저장·400 거부·원복) / 핀 PUT(`study:agent_001`→고급 resolve
    적용, 동명 `CCTV:agent_001`은 기어 따름=중급 → **복합키 격리 정확**, 해제 원복). 프리뷰=설정 패널 표+핀목록
    렌더(select 46=프리셋12+에이전트34, 스크린샷).

### ⏳ 남음 (정리/심화)
- **3단계 — 옛 캐시 싱글턴 제거**: `_midtier_provider`/`_get_midtier_provider_legacy`·`_lightweight_provider`·
  `_system_oneshot_provider` → 리졸버 캐시로 완전 일원화. 지금은 폴백 전용이라 살아 있음(제거는 안전성 확인 후).
- **종단 차별화**: 고급=opus 등 티어 모델을 *다르게* 설정 후, 기어별로 실제 다른 모델이 도는지(지금까진 안전창 flash-lite).
- **원격/폰 계기판 레버**: 현재 레버·⚙설정은 데스크탑 ManualMode(React)만. `api_launcher_web.py` HTML 계기판엔 미구현.
- **러닝 중 프로젝트 에이전트 교체**: 기어/핀 변경은 의식·시스템AI·원샷·reflex만 즉시 반영. 실행 중 프로젝트
  에이전트는 다음 시작에서 반영(러닝 중 provider 교체는 범위 밖 — 필요 시 agent stop/start 트리거).
- (선택) 커스텀 모델 핀(현재 핀은 티어명만; overrides 는 `{provider,model,apiKey}` dict 도 지원).

## 2. ★안전 창 (지금 이관해도 안 깨짐)

3 티어가 **전부 `gemini-3.1-flash-lite`**(테스트로 깔아둠). 즉 어느 역할이든 어느 기어든 같은 모델로 해소 →
**이관해도 동작이 안 바뀌는 안전 창.** 기어가 실제로 갈리는 건 사용자가 `고급=opus` 등으로 티어 모델을 달리 설정한 뒤.
이관 검증은 "깨지지 않음 + source가 올바른 축/티어"로 충분.

## 3. 이관 대상 — 역할별 전수 (file:line / 현재 메커니즘 → 목표 role)

리졸버의 role 키(`model_gear.json.role_axis`): classify·background·evaluate·consciousness·execution·system_ai·reflex·translate·content_text·android·auto_response.

| # | 위치 | 현재 | 목표 role(축) |
|---|---|---|---|
| 1 | `agent_cognitive.py:1673` `_classify_request` | lightweight_ai_call | classify(분류) |
| 2 | `agent_cognitive.py:2003` evaluator | **system_ai_call** | evaluate(평가) ← opus→경량 개선 |
| 3 | `agent_cognitive.py:1049` `_consciousness_fit_gate` | lightweight_ai_call | background(분류) |
| 4 | `agent_cognitive.py:1175,1241` `_distill_deep_memory` | lightweight_ai_call | background(분류) |
| 5 | `agent_cognitive.py:1379` `_distill_forage_memory` | lightweight_ai_call | background(분류) |
| 6 | `ibl_usage_rag.py:595` 경험증류 reflection | lightweight_ai_call | background(분류) |
| 7 | `forage_consolidation.py:84,108` 포식정리 | lightweight_ai_call | background(분류) |
| 8 | `ibl_engine.py:763` recall 압축 | lightweight_ai_call | background(분류) |
| 9 | `consciousness_agent.py:_init_provider(44)` 의식 | load_system_ai_config | **consciousness(의식)** ← 시스템AI서 분리 |
| 10 | `system_ai_core.py:get_system_ai_runner(88)` 시스템AI 실행 | load_system_ai_config | system_ai(실행) |
| 11 | `agent_runner.py:_init_ai(94)` 프로젝트 에이전트 | agent_config.ai (각자 yaml) | **execution(실행), agent_id 핀 지원** ← 개별설정 불요 |
| 12 | `agent_communication.py:363` Reflex | _get_midtier_provider | reflex(실행) |
| 13 | `api_websocket.py:610` Reflex | _get_midtier_provider | reflex(실행) |
| 14 | `api_ibl.py:266` 수동모드 번역 | **system_ai_call** | translate(실행) ← "수동=경량" 의도 정합 |
| 15 | `android_agent.py:198` / `auto_response.py:281` / `channel_poller.py:928` | load_system_ai_config | android / auto_response(실행) |
| 16 | `media_producer/slide_author.py:106` `slide_native.py:219` 슬라이드 텍스트 | _load_system_ai_config | content_text(실행) |
| — | `slide_native.py` Gemini 이미지 | GEMINI_API_KEY | **모달리티(기어 밖, 손대지 말 것)** |

## 4. 권장 리팩터 방식

**원샷 호출(lightweight_ai_call / system_ai_call)**: 시그니처에 `role` 인자 추가하고 내부에서
`model_resolver.get_provider_for(role)` 로 provider 획득. 기본 role 유지 시 현 동작 보존.
호출 사이트는 자기 role만 넘기면 됨(예: `lightweight_ai_call(prompt, role="classify")`).
→ `consciousness_agent.py`의 `lightweight_ai_call`(589)·`system_ai_call`(672)이 1차 수술 지점.

**에이전트 init(전체 루프)**: init 시점에 `resolve(role[, agent_id])`로 provider 구성.
- 의식: `consciousness_agent._init_provider` → `resolve('consciousness')`
- 시스템AI: `system_ai_core.get_system_ai_runner` → `resolve('system_ai')` (모델변경 감지 재생성 로직은 이미 있음 — resolve 결과로 비교)
- 프로젝트 에이전트: `agent_runner._init_ai` → `resolve('execution', agent_id=self.config['id'])`.
  agent_config.ai 가 명시되면 그걸 오버라이드로 존중(또는 model_gear.overrides 로 일원화).

**Reflex**: `_get_midtier_provider()` 호출부(2곳)를 `get_provider_for('reflex')`로.

## 5. 함정 / 주의

- **slice마다 backend 재시작** 후 검증(인지층·코어 변경은 부팅 로드).
- **모달리티는 절대 기어로 묶지 말 것**(이미지 모델≠텍스트 모델). slide_native 이미지·해마 임베딩은 그대로.
- **3단계에서 옛 캐시 제거 필수**: `consciousness_agent`의 `_midtier_provider_initialized`/`_lightweight_provider`/
  `_system_oneshot_provider` 싱글턴이 남으면 기어 변경이 안 먹음(재시작 강제 원인). 리졸버 캐시(`clear_provider_cache`)로 일원화.
- **API 키 폴백**은 리졸버가 이미 처리(티어 키 비면 고급 키). 호출부에서 중복 폴백 넣지 말 것.
- **에이전트 핀**: `model_gear.json.overrides`에 `"<agent_id>": "고급"` 또는 `{provider,model,apiKey}`. resolve가 agent_id 우선 적용.

## 6. 검증

- 단위: `python3 -c "import model_resolver as M; ..."` 로 4축×3기어·핀·핫리로드 (이미 통과한 패턴).
- 이관 후: 라이브에서 `[연상:실행기억]`·`[무의식] 분류`·`[GoalEval]` 로그에 *기대 티어 모델*이 찍히는지.
  (지금은 다 flash-lite라 "안 깨짐 + source 올바름"으로 충분. 고급=opus 설정 후 기어별로 모델이 갈리는지 종단 확인.)
- 4단계 후: 계기판 레버로 절약↔최대 전환 시 **재시작 없이** 다음 작업이 다른 모델로 도는지.

## 7. 다음 세션 첫 액션

✅ **2단계 이관 전부 완료**(#1~16 + oneshot 버킷 + reset 캐시 일원화). 남은 건 정리/UI:
1. **3단계 — 옛 캐시 싱글턴 제거** (선택, 정리): `_midtier_provider`/`_get_midtier_provider_legacy`·
   `_lightweight_provider`·`_system_oneshot_provider` 가 지금은 *폴백 전용*으로 살아 있음. 리졸버가
   안정적이라 판단되면 제거해 리졸버 캐시로 완전 일원화. ★제거 전 폴백이 실제로 안 쓰이는지(리졸버가
   항상 provider 반환) 확인. 의식 에이전트 핫리로드(재초기화 훅 부재)도 여기서 보완 — config 변경 시
   `_consciousness_instance=None` 리셋 훅 추가(api_config PUT 핸들러에서).
2. **4단계 — 계기판 레버**(핵심 UX): 런처/설정에 절약/균형/최대 스위치 + gear REST 엔드포인트
   (`model_resolver.set_gear/get_gear/list_gears` 래핑 — 아직 REST 미노출). 레버만 붙으면 **재시작 없이**
   변속(리졸버 핫리로드·캐시 무효화 완비). (선택) 에이전트 핀 UI = `model_gear.overrides` 편집.
3. **종단 차별화 검증**: 고급=opus 등으로 티어 모델을 *다르게* 설정한 뒤, 기어별로 실제 다른 모델이
   도는지 확인(지금까진 안전창=3티어 flash-lite라 "안 깨짐"만 검증). `[무의식]`·`[GoalEval]`·`[시스템AI]`
   로그의 모델명으로 확인.

★2단계 이관 라이브 검증 완료: 백엔드 재시작 후 `/ibl/translate`(translate) + `/system-ai/chat` THINK
종단(의식·분류·평가 전부 리졸버 경유, google/flash-lite 일관) 통과.
