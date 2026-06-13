# 폰-자아 호스팅 — 다음 세션 HANDOFF

작성 2026-06-13. 깊은 기록은 메모리 `project_body_proprioception_detection.md`("START HERE"). 이 문서는 **다음 세션이 바로 구현을 시작**하도록 한 장에 압축.

---

## 0. 한 줄 목표

폰을 **두 번째 독립 자아**로 세운다 — 폰이 *자기 하네스+기억*을 호스팅해서, 추론하는 자아가 진짜 폰이 되고(자기 인식이 *참*이 됨), 자기 하드웨어 능력에서 추론한다. 못 하는 건 상시 켜둔 맥에서 빌린다.

## 1. 왜 (진짜 동기 — 흔들리지 말 것)

- **인지적 위치 정확성**이지, 맥다운 회복력이 *아님*. 맥은 일부러 상시 켠다(맥다운 질문 무의미). claude_code 기형적 사용은 비용 강제라 선택지 없음 — 맥 의존은 흠이 아니다.
- 하드웨어가 실제로 다르니, AI가 자기 몸을 자각 못 하면 "뭘 할 수 있나"를 혼동한다. 윈도우 AI는 윈도우로, 폰 AI는 폰으로 사고해야 — *허락받아서가 아니라 자기가 무슨 기계인지 알아서.*
- **현재 무방비 위험**: 집밖 폰 채팅 → `_mac_proxy`(투명 포워드) → 맥 에이전트가 자기 world_pulse("나는 맥") 읽고 *자기를 맥이라 믿으며* 답. 폰 세션엔 거짓말. 실행 라우팅은 chokepoint가 옳게 보내(안 깨짐), 깨지는 건 *자기-모델*(집밖인데 맥 화면에 띄우려 함 등).

## 2. 확정된 설계 결정 (이 세션에서 사용자와 합의)

1. **단일 코드베이스, 포크 금지(0조)**. 어느 HW에나 설치, 런타임 능력 감지로 적응. "폰전용"이 쌓이면 = 두 indiebizOS화 = 포크.
2. **두 독립 자아 = 서로 다른 두 대의 PC**. 각자 자기 하네스·기억·정체성, 각자 증류·학습.
3. **공유 = 기본 비공유(opt-in)**. 사용자 지정한 것만. 현재 지정 = **business.db 하나**(연락처/이웃 포함). 일정은 동기화 아님(home_only 빌림).
4. **빌림 = 호출하는 주체가 액션 주체**. → `_forward_*`이 호출자 신원 전파해야(현재 system_ai로 떨굼 = 고쳐야).
5. **substrate 렌트 / 경험 로컬**: LLM(맥 claude_code)·임베딩 인코더는 상시 맥에서 렌트. 하네스·대화·해마 *인덱스*·자기상태·정체성은 폰 로컬·비동기화. (인코더=공유 substrate, 인덱스=사적 경험.)
6. **모델은 어디서 렌트하든 정체성과 무관**(claude_code-on-맥 ≡ Gemini-클라우드). 정체성은 *하네스가 어느 몸 위에서 자기인식하느냐.*

## 3. 무포크 규율 (구현 내내 지킬 것)

- **profile 보지 말고 capability 봐라**: `if not local_claude_code_available()` ○ / `if INDIEBIZ_PROFILE=="phone"` ✗. 판별="반대편 HW가 같은 능력 잃으면 같은 경로 타나?".
- **"폰전용"은 [이음매](architecture) 아래(핸들러·Java브리지·호스트)에만.** 위(하네스·인지·어휘)의 `INDIEBIZ_PROFILE` 분기 = 포크냄새, 0으로.
- 현재 `INDIEBIZ_PROFILE` 분기 = **12개/8파일**(runtime_utils, indienet, phone_notifications, api_launcher_web, world_pulse_collectors, nostr_phone_bridge, ibl_engine, channel_engine). 추세 하향 못박기.
- ✅ **(구현됨 2026-06-13) 포크 가드**: `build_ibl_nodes.py --check`의 `check_profile_branches()`가 "이음매 위 모듈의 INDIEBIZ_PROFILE 분기 적발". `PROFILE_BRANCH_ALLOWLIST`(이음매-아래 9파일) 밖에서 참조 시 --check 실패. pre-commit·self-check에 합류. 발산 원천 차단 완료.
- 4규율: ①capability-게이트 ②차이는 데이터(runs_on/config)로 ③번들 손-리스트(`_ENGINE_MODULES`) 말고 선언서 파생 ④`phone_api.py`(현 509줄·28라우트)를 0으로 수렴 — 자라면 포크중, 줄면 수렴중.

## 4. 이미 된 것 (이 세션, 전부 미커밋)

- **`detect_body()`** (`backend/runtime_utils.py`): 부팅1회·캐시. 맥=sysctl 칩명, 폰=`jclass("android.os.Build")`. 맥 실측 "Apple M4 Pro", 폰 getprop "samsung SM-A366N/Android16"(jclass 경로 데이터 검증, in-process는 APK 재빌드 필요라 미실행).
- **`build_capability_portrait()`** (`runtime_utils.py`): 최소판 — "나는 {body}에서 돈다" + "{peer}의 액션을 빌릴 수 있다"(peer URL 설정 시). 액션목록·실시간 연결상태 *제외*(어휘가 따로 가르침 / 월드펄스 주기와 어긋나 stale).
- 배선: `world_pulse_collectors._collect_self_state()`→`state["capability"]`→`world_pulse_health.generate_guide()` "## 나는 누구인가"→`world_pulse.md`→`prompt_builder._load_world_pulse()`→프롬프트. **맥에서만 검증**(맥-자아 프롬프트에 자기 인식 줄 들어감).
- **양방향 빌림 이미 존재**: `ibl_engine._forward_to_mac`(폰→맥)·`_forward_to_phone`(맥→폰), chokepoint=`execute_ibl` line 465/487.
- 미커밋 3파일: `backend/runtime_utils.py`, `backend/world_pulse_collectors.py`, `backend/world_pulse_health.py`.

## 5. 핵심 미완 = 폰엔 자화상을 *소비할* 것이 없다

`runtime_utils`는 폰 번들에 있어 `build_capability_portrait()`는 폰서 "나는 안드로이드 폰"을 *반환은* 함. 그러나:
- ❌ `world_pulse_collectors`·`world_pulse_health`·`prompt_builder`·`agent_cognitive` 등 **하네스가 폰 번들에 없음**.
- ❌ 폰엔 로컬 에이전트·모델 없음 → 프롬프트가 들어갈 곳 자체가 없음(맥 프록시).

→ **폰-자아 하네스 호스팅이 전제.** 그게 서야 자화상이 폰에서 *참*이 됨.

## 6. 다음 단계 (순서)

1. ✅ **(완료 2026-06-13) 포크-가드**를 `build_ibl_nodes.py --check`에 합류 — `check_profile_branches()` + `PROFILE_BRANCH_ALLOWLIST`(이음매-아래 9파일). allowlist 밖 .py가 `INDIEBIZ_PROFILE` 참조하면 --check 실패(stale도 안내). 임시 위반 파일로 종료1 검증, pre-commit/self-check 자동 합류.
2. ✅ **(완료 2026-06-13) 신원 전파 수정**: `_forward_to_mac`/`_forward_to_phone`이 호출자 `agent_id`를 payload에 동봉(`ibl_engine.py`). 수신측 `api_ibl.py`는 이미 `req.agent_id` 소비라 송신측만 고쳐 종단 완성. 미동봉 시 키 부재→종전 system_ai 폴백 보존(무회귀). `phone_api.py`도 incoming agent_id honor("phone" 폴백)로 대칭. 송신 payload 단위테스트 3종 + 라이브 맥 빌림(world_bank) 검증. **폰 번들 반영은 APK 재빌드 후**(폰-자아 에이전트 존재 시 의미있게 종단검증 — steps 4~7 후).
3. ✅ **(완료 2026-06-13) 맥 `/embed` 엔드포인트**: `POST /ibl/embed`({text}|{texts}→768 L2정규화 벡터). `IBLUsageDB.embed_vectors()`(=`_generate_embeddings_batch` 와 동일 encode+정규화, float 리스트 반환). **정합성 검증**: `/embed` 벡터 == 인덱싱 벡터(diff 1.49e-08, cosine 1.0), `search_semantic`도 raw query `_generate_embedding` 사용 → 폰 brute-force 코사인이 맥 search_semantic 과 동치. 라이브 단건/배치 검증(norm=1.0).
4. ✅ **(완료 2026-06-13) 하네스를 폰 번들로**: `build.gradle _ENGINE_MODULES`에 인지 하네스 13(최상위 import 폐포 AST 산정) + `providers/` 패키지 + `data/common_prompts/` 에셋. import 안전 3중 사전검증(폰 pip 밖 서드파티 0·최상위 pydantic 0·맥 스모크 clean) + **A36 온디바이스 검증(임시 엔드포인트로 12모듈+providers import → `_all_ok:true`, 검증 후 제거+클린 재빌드)**. doFirst 가드에 providers·common_prompts 추가.
5. ✅ **(완료 2026-06-13) 폰-자아 모델 프로바이더**: `ClaudeCodeProvider +backend_url`(_build_env→INDIEBIZOS_BACKEND_URL→MCP 라우팅) + 맥 엔드포인트 `POST /providers/claude_code/remote_turn`(claude_code 한 턴, backend_url=폰, remote_access_guard 인증) + 폰 `ClaudeCodeRemoteProvider`(providers/claude_code_remote.py, 레지스트리 등록, 런처세션 인증). **A36 종단검증**: backend_url=adb-forward(폰)로 맥 claude_code 실행→폰 logcat `POST /ibl/execute 200 OK`(맥 추론·폰 IBL 입증). 폰 provider 전체 루프는 step7 후 완성. ⚠️함정: 폰 미도달 시 claude_code 가 WebSearch 폴백→오검증, logcat으로 확인 필수.
6. **폰 해마**: 맥 인코더 렌트(`/ibl/embed` 완료, #3) + 폰 로컬 인덱스 brute-force 코사인(~2400개라 sqlite-vec 불필요). torch·ONNX 폰에 불필요. ← **다음 시작점**
7. **폰 진입점 전환**: `phone_api.py`의 `/system-ai/chat`을 `_mac_proxy`→**로컬 하네스 실행**으로. 로컬 하네스 미가용 시 맥-프록시 폴백(전환 안전). + 폰 system_ai_config 3티어(경량=gemini_http, 중급·본격=claude_code_remote) 작성. 여기서 step5 폰 provider 전체 루프 종단.

## 7. 검증 (A36 USB 상시 연결)

- **폰 자기 인식**: 폰서 채팅 → 폰-로컬 하네스 → 폰 `world_pulse.md`에 "나는 **안드로이드 폰(SM-A366N)**에서 돈다 / 맥미니의 액션을 빌릴 수 있다". (맥 아니라 폰이라 말해야 성공.)
- **신원 단 빌림**: 폰-자아가 home_only(예 `self:manage_events`) 요청 → `_forward_to_mac`이 맥서 실행하되 *폰-자아 신원*으로 기록.
- 빌드순서 엄수: src 편집 시 `python3 scripts/build_ibl_nodes.py`→`--check`→`cd phone-companion && ./gradlew assembleDebug`→`adb install -r`.

## 8. 함정

- **claude_code는 에이전트**(자기 루프, 단발 호출 불가) — 맥 CLI에서만. 폰은 원격 렌트만 가능(루프=맥). 폰이 claude_code를 LLM처럼 단발 호출 불가.
- **`_ENGINE_MODULES`는 손-리스트** — 모듈 추가 시 거기 추가 안 하면 stale. 장기엔 선언서 파생으로.
- **무거운 deps**: 해마 torch→인코더 렌트로 우회. sqlite-vec→brute-force로 우회.
- **band-aid 금지**: 프록시에 "폰서 왔다" 주입해 맥-에이전트가 폰인 척 = 임시방편(`feedback_no_temporary_patches` 위반). 깨끗한 해=에이전트가 진짜 폰-자아.
- 폰 백엔드는 앱 포그라운드일 때만 가동. 폰 동적 IP·WiFi 수동연결(`project_indiebizos_phone_native` 환경 섹션 참조).

## 9. 관련 메모리

- `project_body_proprioception_detection`(이 작업 본체·설계·원리) ·`project_indiebizos_phone_native`(폰 네이티브 인프라·번들·환경) ·`project_phone_mac_routing_plan`(chokepoint 빌림) ·`project_agent_id_propagation_fix`(신원 전파 패턴) ·`architecture_substrate_superstructure_seam`(이음매 헌법) ·`project_augmentation_over_autonomy`(능력≠허락).
