# 인지 파이프라인 통합 (Task B) — 핸드오프

**목표:** 여러 진입점에 복사-붙여넣기된 인지 파이프라인 오케스트레이션(연상→분류→의식→실행→평가→반성)을 **하나의 공유 드라이버**로 통합한다. 진입점은 얇은 transport 어댑터가 된다.

**왜(사용자 동기):** "이메일/통신 경로로 명령이 들어오면 새 에이전트가 일하나? 왜 따로따로 프로그램을 짜야 하지?" — 답: 새 에이전트가 아니다(같은 runner·모델·IBL·해마). 다른 건 transport뿐인데 파이프라인이 진입점마다 복제됨 = `entrypoint_drift_shared_boot` 드리프트. 기능 하나(반성) 더하는 데 여러 곳을 고쳐야 하는 게 그 증상.

**★핵심 payoff:** 통합하면 **이메일 경로 반성이 "공짜"로 딸려온다.** "이메일에 반성 추가"(Task A)를 따로 하지 말고, 통합으로 이메일이 반성을 상속하게 하는 게 이 작업의 진짜 이유. (그래서 사용자가 A 대신 B를 택함.)

---

## 1. 현 상태 지도 — 파이프라인이 중복된 7곳

모든 곳이 **같은 runner 메서드**를 부른다(`_build_execution_memory`, `_decide_request_type`, `_run_consciousness_or_reuse`, `_run_goal_evaluation_loop`). 뇌는 하나, 오케스트레이션 코드만 복제됨.

| # | 위치 | transport | 실행 호출 | 평가 | 반성 |
|---|---|---|---|---|---|
| 1 | `api_websocket.py:530` `handle_chat_message_stream` (프로젝트) | **스트림** | `runner.ai.process_message_stream` :817 | :881 ✓ | **:922 ✓** |
| 2 | `api_websocket.py:1178` `handle_system_ai_chat_stream` | **스트림** | `process_system_ai_message_stream` :1296 | :1358 ✓ | **:1398 ✓** |
| 3 | `api_websocket.py:317` `handle_chat_message` (프로젝트, 논스트림) | **블로킹** | `process_message_with_history` :469 | ✓ | ✗ |
| 4 | `api_websocket.py:209` `handle_android_chat` | 스트림 | run_stream :231 | ? | ✗ |
| 5 | `agent_communication.py:281` (이메일/통신) | **블로킹** | `process_message_with_history` :425 | :449 ✓ | ✗ |
| 6 | `agent_communication.py:590` (2차 블록 — 자동응답 추정) | 블로킹 | :624 | ? | ✗ |
| 7 | `system_ai_core.py:245` `process_system_ai_message` (블로킹) | **블로킹** | `process_message_with_history` :301 | :324 ✓ | ✗ |
| — | `system_ai_core.py:342` `process_system_ai_message_stream` | 스트림 제너레이터 | `yield ... process_message_stream` :435 | (호출자가 #2에서) | (호출자가 #2에서) |

**관찰:**
- transport는 딱 **두 종류**: 스트림(이벤트를 yield/pump) vs 블로킹(완성 문자열 반환).
- 반성은 스트림 2곳(#1,#2)에만. 블로킹 3곳(#3,#5,#7)·안드로이드(#4)엔 없음.
- 시스템 AI는 오케스트레이션이 `system_ai_core.process_system_ai_message_stream`에 있고, 프로젝트는 `api_websocket.run_stream`에 인라인 → **같은 로직 두 집**(드리프트의 핵심).
- `agent_communication.py`엔 블록이 2개(:303, :590).

---

## 2. 이미 공유된 조각 (재사용)

- `runner._build_execution_memory(msg, action_hint)` — 연상(해마+심층+포식+디스크골격)
- `runner._decide_request_type(msg, hippo, top)` — 분류 (#think/#execute·Reflex·무의식)
- `runner._run_consciousness_or_reuse(msg, history, exec_mem)` — 의식(THINK)
- `runner._run_goal_evaluation_loop(...)` — 평가 루프
- `runner._consciousness_clarification(out)` — clarification fast-path 텍스트
- `build_reflection_message(response, tool_calls)` — 반성 메시지 (agent_cognitive.py, module fn)
- `serialize_tool_trace()`, `build_action_ledger()` — 궤적 직렬화
- `run_self_reflection_turn(stream_iter, event_queue, loop, ...)` — **스트림 전용** 반성 실행기 (api_websocket.py:89) → 통합 시 제너레이터 버전으로 흡수/대체

---

## 3. 목표 설계 — 하나의 제너레이터 + 얇은 어댑터

### 3.1 공유 드라이버 (runner 메서드 또는 신규 모듈)

```
runner.cognitive_stream(
    message, history, *,
    agent_name, project_path, is_system_ai=False,
    action_hint=None, images=None, extra_role=None, cancel_check=None,
) -> Generator[event]   # event = {type: text|tool_start|tool_result|thinking|final|clarify, ...}
```

내부에서 **한 번만** 수행:
1. 연상 `_build_execution_memory`
2. 분류 `_decide_request_type` (SESSION_RESET 분기 포함)
3. THINK면 의식 `_run_consciousness_or_reuse` + clarification fast-path(yield clarify+final 후 return)
4. reflex면 중급 모델 provider 스왑(현 api_websocket:610-633 이관)
5. 시스템프롬프트 split·`compile_user_command` 융합(현 api_websocket:665-696 이관)
6. 실행 `process_message_stream` → 이벤트 yield, 궤적(eval_tool_calls) 수집
7. consciousness_output 있으면 평가 루프(`_run_goal_evaluation_loop`) → 필요 시 재실행 yield
8. EXECUTE(의식 없음)+도구 호출+not reflex면 **반성 턴**: `build_reflection_message` → 세션 resume 재개(`process_message_stream` 재호출) → 이벤트 yield → 새 final

`is_system_ai=True`면 6단계 실행을 `process_system_ai_message_stream` 경로로(또는 `_is_system_ai` 플래그가 이미 하듯 runner 내부 분기). **시스템 AI/프로젝트 차이는 파라미터·플래그로 흡수** (별도 집 없앰).

### 3.2 Transport 어댑터 (얇게)

**스트림 진입점**(WS #1,#2,#4):
```python
for ev in runner.cognitive_stream(...):
    asyncio.run_coroutine_threadsafe(event_queue.put(ev), loop)
    if ev["type"] == "final": final_content = ev["content"]
```

**블로킹 진입점**(#3,#5,#7): 작은 drain 헬퍼:
```python
def drain(gen):
    final = ""
    for ev in gen:
        if ev.get("type") == "final": final = ev["content"]
    return final
response = drain(runner.cognitive_stream(...))
```
→ **블로킹이 내부적으로 스트림을 소비해 final만 취함.** 반성도 제너레이터 안에서 일어나므로 **이메일·시스템AI 블로킹이 반성을 자동 상속**(= payoff).

---

## 4. 옮겨야 할 조각들 (현재 transport에 흩어진 인지 로직)

이것들이 지금 api_websocket run_stream 등에 인라인 → cognitive_stream으로 이관:
- **clarification fast-path** (api_websocket:635-661) → THINK 직후 yield clarify+final
- **중급 모델 reflex 스왑** (api_websocket:610-633) + finally 복원
- **시스템프롬프트 split + compile_user_command 융합** (api_websocket:663-696)
- **goal-eval 블록** (api_websocket:838/1313, agent_communication:435, system_ai_core:324) → 제너레이터 안 1곳
- **반성 elif** (api_websocket:877/1398) → 제너레이터 안 1곳
- **eval_tool_calls / tool_results_log 수집** (tool_start/tool_result 페어링) → 제너레이터 안

transport에 남길 것: 에피소드 start/end(요청 경계), event_queue pump / drain, DB save_message, 세션·클라이언트 관리, 취소 플래그.

---

## 5. 단계별 계획 (점진적·각 단계 라이브 검증)

1. **스캐폴드**: `runner.cognitive_stream` 뼈대 작성 — 처음엔 #1(프로젝트 스트림) 로직만 그대로 옮겨 담고, #1을 이 제너레이터 호출로 교체. 라이브 검증(자율주행 채팅).
2. **시스템 AI 합류**: `is_system_ai` 분기 흡수 → #2를 cognitive_stream 호출로. `process_system_ai_message_stream`의 오케스트레이션(system_ai_core:370-435 앞부분)을 제거하고 실행 부분만 남김. 라이브 검증(시스템 AI 채팅).
3. **블로킹 drain**: drain 헬퍼 도입 → #3(프로젝트 논스트림)·#7(시스템AI 블로킹)을 cognitive_stream+drain으로. 반성 자동 상속 확인.
4. **이메일/통신**: #5(agent_communication:281)·#6(자동응답 :590)을 cognitive_stream+drain으로. **이메일 반성 검증**(사용자 원래 요청 충족).
5. **안드로이드**: #4 합류.
6. **정리**: 죽은 인라인 오케스트레이션 삭제, `run_self_reflection_turn`을 제너레이터 반성으로 대체(스트림 pump는 어댑터가). `system_ai_core.process_system_ai_message[_stream]` 중복 축소.

각 단계 후 회귀 없는지 에피소드 로그로 확인. 한 번에 다 바꾸지 말 것(블라스트 반경 큼).

---

## 6. 검증

- 진입점별 라이브 종단: 프로젝트 스트림/블로킹, 시스템AI 스트림/블로킹, 이메일, 자동응답, 안드로이드 — 각각 도구 쓰는 요청으로 실행 → 에피소드 로그에 연상·분류·(의식)·실행·(평가)·**반성** 마커 확인.
- `[SelfReflect] 자기반성 턴 시작`이 **모든** 도구-실행 EXECUTE 턴(전 경로)에서 뜨는지.
- 세션 resume 연속성(같은 에이전트 이어감) 유지 확인.
- `python3 scripts/build_ibl_nodes.py --check` (인지층은 IBL 무관하나 습관).
- 회귀: clarification·reflex 중급모델·SESSION_RESET·타임아웃·취소 각각 살아있는지.

---

## 7. 위험·함정

- **블라스트 반경 최대** — 코어 인지 루프 전체. 반드시 진입점 하나씩 이관·검증(빅뱅 금지).
- **두 runner**: 시스템 AI는 `get_system_ai_runner()` 싱글턴, 프로젝트는 프로젝트별 runner. `cognitive_stream`이 runner 메서드면 자연히 올바른 runner에서 돎 — 단 `is_system_ai` 플래그·agent_id·project_path 정확히 전달.
- **스트림→블로킹 전환**: 블로킹 경로가 이제 내부적으로 `process_message_stream`(제너레이터)을 소비. executor 스레드/동기 컨텍스트에서 정상 작동 확인(현재도 동기 제너레이터라 OK 예상).
- **에피소드 contextvar**: start_episode는 transport에서 요청 진입 시 유지. cognitive_stream 안 print가 같은 버퍼로 모이는지(copy_context 경유) 확인.
- **반성 재개 = 세션 resume**: 두 번째 process_message_stream 호출이 같은 세션 이어받아야 함(claude_code 세션맵 = 에이전트별). 시스템AI는 현재 `process_system_ai_message_stream` 재호출로 파이프라인 재진입 → 통합 후엔 실행 부분만 재호출하도록 정리(더 가벼움).
- **no_temporary_patches**: 이관 후 옛 인라인 오케스트레이션은 삭제(호환층 남기지 말 것).

---

## 8. 관련 파일·메모리

- 진입점: `api_websocket.py`(#1~4), `agent_communication.py`(#5,6), `system_ai_core.py`(#7 + stream)
- 인지 코어: `agent_cognitive.py`(runner 메서드들·`build_reflection_message`·`serialize_tool_trace`)
- 반성 실행기: `api_websocket.py:89 run_self_reflection_turn`
- 반성 프롬프트: `data/common_prompts/execution_reflection_prompt.md`
- 메모리: `entrypoint_drift_shared_boot`(핵심 — 진입점 포크=드리프트), `project_execution_self_reflection`(반성 v2 설계·현 배선), `harness_sturdiness`, `substrate_superstructure_seam`, `three_tier_cognition`, `no_temporary_patches`

**시작 지점:** 이 문서 §3.1의 `cognitive_stream` 시그니처로 스캐폴드 → §5 1단계(프로젝트 스트림부터). 현 반성 배선(api_websocket:877~)이 이관의 참조 구현.
