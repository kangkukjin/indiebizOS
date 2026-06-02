# 도구 SDK 마이그레이션 — 후속 작업

2026-05-21 세션에서 162번 슬라이드 사고를 진단하면서 도구 SDK(ToolContext)를 도입했다. 이 파일은 다음 세션에서 cold start로 이어 작업할 수 있도록 후속 작업을 자기완결적으로 정리한 것이다.

각 작업을 그대로 복사해서 새 세션의 첫 메시지로 보내면 된다.

---

## 공통 컨텍스트 (모든 후속 작업이 공유)

**무엇이 끝났는가** (2026-05-21):
- 도구 핸들러의 새 표준 시그니처: `def execute(tool_input: dict, context: ToolContext) -> str`
- ToolContext 클래스: `backend/tool_context.py` (project_path 필수, '.', None 거부, `output_dir()`/`resolve_path()` 빌트인)
- 디스패처 양립 어댑터: `backend/ibl_routing.py:_route_handler` — `inspect.signature`로 신규/구 시그니처 자동 분기
- 디스패처 안전망: `backend/ibl_routing.py:_resolve_project_path` — 호출자가 `project_path`를 누락하거나 `"."`로 넘기면 `thread_context.project_id` → `ProjectManager.get_project_path`로 자동 복구
- 첫 마이그레이션: `media_producer/handler.py` 신규 시그니처로 전환 완료
- 응급처치 abspath 한 줄 패치 (총 9곳, 5개 패키지): media_producer(4), remotion-video(1), visualization(1), web(1), blog(1), web-builder(1)

**왜 도입했는가**: 162번 사고에서 `project_path=" ."` 디폴트가 발동해 백엔드 cwd 기준 상대경로(`./outputs/...`)로 슬라이드가 떨어지고, AI가 그 상대경로를 그대로 사용자에게 안내해 거짓 보고가 되었다. 사후 검증이 아니라 신경계에서 "거짓말 할 재료를 안 주는" 방향을 선택. 단일 시그니처 통일, 임시방편 X — 사용자 명시 결정.

**관련 메모리**: `~/.claude/projects/-Users-kangkukjin-Desktop-AI/memory/project_tool_context_sdk.md`, `project_episodic_memory.md`, `project_strategic_thesis_commodity.md`

---

## 작업 #1 — 백엔드 재시작 + 162번 시나리오 회귀 검증

**상태**: 즉시 가능
**소요**: 5~10분
**의존**: 없음

### 새 세션에 던질 메시지

> indiebizOS에서 도구 SDK(ToolContext)를 도입했고 media_producer를 신규 시그니처로 마이그레이션했어. 도구 핸들러는 `_package_handlers_cache`에 캐싱되니까 백엔드 재시작 후 162번 시나리오를 재현해서 회귀 검증해줘.
>
> 1. 백엔드 재시작 (사용자가 직접 `./start.sh` 실행할 수 있게 안내)
> 2. 슬라이드 만들기 명령 (예: 책 한 챕터를 강의할 슬라이드 3장)
> 3. `/Users/kangkukjin/Desktop/AI/indiebizOS/data/world_pulse.db`의 `episode_log`에서 최신 에피소드 SELECT
> 4. 검증 포인트:
>    - `output_dir`이 절대경로(`/Users/.../projects/<프로젝트>/outputs/shadcn_slides_xxx`)로 반환되는가
>    - AI가 사용자에게 안내한 경로 = 실제 파일 위치인가
>    - Reflex EXECUTE 분기에서도 거짓 보고가 안 일어나는가
>
> 162번처럼 `./outputs/...` 상대경로가 어디서도 안 나오면 OK.

---

## 작업 #2 — 33개 도구 신규 시그니처 마이그레이션 (큰 작업)

**상태**: 호흡 긴 별도 세션 권장
**소요**: 패키지당 5~15분 × 33개 = 4~8시간 (분할 가능)
**의존**: 없음 (디스패처 양립 어댑터 덕에 점진 가능)

### 새 세션에 던질 메시지

> indiebizOS의 도구 핸들러 33개를 신규 시그니처 `(tool_input, context: ToolContext)`로 마이그레이션해줘. 첫 사례인 media_producer를 패턴으로 삼아.
>
> **마이그레이션 패턴** (media_producer/handler.py 참조):
> ```python
> # Before
> def execute(tool_name: str, tool_input: dict, project_path: str = ".") -> str:
>     output_base = os.path.join(project_path, "outputs")
>     os.makedirs(output_base, exist_ok=True)
>     if tool_name == "foo": ...
>
> # After
> def execute(tool_input: dict, context) -> str:
>     """ToolContext 기반 신규 시그니처."""
>     tool_name = context.tool_name
>     output_base = context.output_dir()  # 항상 절대경로 + mkdir 자동
>     if tool_name == "foo": ...
> ```
>
> **우선순위 1순위** (응급처치 패치 안 들어간 27개 — 더 위험): business, ibl-core, computer-use, culture, health-record, legal, pc-manager, location-services, publishing, cloudflare, investment, kosis, music-composer, cctv, context7, local-info, memory, photo-manager, python-exec, nodejs, browser-action, real-estate, shopping-assistant, startup, study, system_essentials, youtube
>
> **우선순위 2순위** (응급처치 패치 적용된 5개 — 이미 안전): blog, visualization, web, remotion-video, web-builder
>
> **시그니처 변종 4종 주의** (도구별로 다름):
> - `(tool_name, tool_input, project_path=".")` — 대다수
> - `(tool_name, params, project_path=None)` — cloudflare, investment, kosis, music-composer
> - `(tool_name, args, project_path=".")` — blog, cctv, context7, local-info, memory
> - `(tool_name, params, project_path=".", agent_id=None)` — 일부
>
> 모두 `(tool_input, context)`로 통일. `params`/`args`였던 곳은 함수 내부 참조도 함께 수정.
>
> **패키지별 단계**:
> 1. `data/packages/installed/tools/<패키지>/handler.py` Read
> 2. `execute()` 함수 시그니처 변경 + `output_base = context.output_dir()`로 대체
> 3. 응급처치 패치가 있던 패키지는 `os.path.abspath` 한 줄 제거 가능 (ToolContext가 대체)
> 4. 백엔드 재시작 후 해당 도구 1개 호출 검증 (episode_log 확인)
>
> 한 세션에 다 못 하면 우선순위 1순위만이라도. 매 5개 패키지마다 백엔드 재시작 + 빠른 sanity 확인.

---

## 작업 #3 — 구 시그니처 지원 제거

**상태**: 작업 #2 완료 후
**소요**: 30분
**의존**: #2 완료

### 새 세션에 던질 메시지

> indiebizOS의 모든 도구가 신규 시그니처 `(tool_input, context)`로 마이그레이션 완료됐어. 이제 `backend/ibl_routing.py:_route_handler`의 구 시그니처 분기를 제거해서 단일 시그니처로 통일해줘.
>
> **작업**:
> 1. `_route_handler`에서 다음 두 분기 제거 (또는 명시적 에러로 변경):
>    ```python
>    elif "agent_id" in sig.parameters:
>        result = handler.execute(mapped_tool, merged_params, project_path, agent_id)
>    else:
>        result = handler.execute(mapped_tool, merged_params, project_path)
>    ```
>    → `context` 분기만 남기고 `else: return {"error": "구 시그니처 도구는 더 이상 지원하지 않습니다."}` 정도로.
>
> 2. 응급처치 abspath 패치 제거 (선택, 잉여가 됨):
>    - `media_producer/shadcn_slides.py:1210, 1269`
>    - `media_producer/handler.py:688, 741`
>    - `remotion-video/handler.py:119`
>    - `visualization/handler.py:71`
>    - `web/handler.py:456`
>    - `blog/tool_blog_insight.py:487`
>    - `web-builder/handler.py:79-84` (raw_output_dir abspath 처리)
>
> 3. 회귀 검증: 모든 도구 호출이 정상 동작하는지 (도구당 1회 sanity 호출).
>
> 응급처치 패치는 제거해도 ToolContext가 대체하지만, 디펜시브 코드로 남겨두는 것도 OK — 사용자에게 옵션 제시하고 결정 받을 것.

---

## 작업 #4 — `project_path` 디폴트 `"."` 시스템 전체 제거 (가장 깊은 정리)

**상태**: 작업 #2, #3 완료 후. 영향 범위 큼.
**소요**: 1~2시간
**의존**: #2, #3 완료

### 새 세션에 던질 메시지

> indiebizOS의 도구 SDK 마이그레이션이 끝났어. 이제 가장 깊은 정리 — `project_path` 디폴트 `"."`를 시스템 전체에서 제거해서, 호출자가 명시 전달하지 않으면 컴파일 타임(또는 호출 시점)에 명확히 실패하도록 해줘.
>
> **배경**: 디스패처 `_route_handler`에 `_resolve_project_path()` 폴백을 깔아둬서 당장은 안전하지만, 폴백은 안전망이지 정상 경로가 아냐. 호출자가 명시 전달하는 게 본래 옳은 방향. 이번 작업으로 "호출자가 항상 project_path를 알고 있어야 한다"는 컨트랙트를 시스템 레벨에서 강제.
>
> **작업**:
> 1. 다음 함수들의 `project_path: str = "."` 디폴트 제거 (필수 인자로):
>    - `backend/system_tools.py:1125` execute_tool
>    - `backend/system_tools.py:1220` _execute_tool_inner
>    - `backend/system_tools.py:896` _execute_ibl_unified
>    - `backend/ibl_engine.py:213` execute_ibl
>
> 2. 호출자들이 명시 전달하도록 수정:
>    - `backend/system_ai_core.py:315`
>    - `backend/system_ai_runner.py:147`
>    - `backend/api_engine.py:11` (테스트 코드)
>    - `backend/auto_response.py:658, 721, 788`
>
> 3. 호출자가 활성 프로젝트 경로를 모를 때는 `thread_context.get_current_project_id()` → `ProjectManager.get_project_path()`로 변환 (디스패처와 같은 로직을 호출자 레벨에 끌어올림). 이걸 헬퍼 함수로 분리하는 게 좋음 — `backend/project_manager.py` 또는 `backend/thread_context.py`에.
>
> 4. 디스패처의 `_resolve_project_path()` 폴백은 안전망으로 유지 (제거 X — 외부에서 새로운 호출자가 늘 명시 전달한다는 보장이 깨졌을 때 사고를 막아줌). 단, 로그에 경고 추가: "호출자가 project_path를 명시 전달하지 않았다, 안전망 발동".
>
> 5. 회귀 검증: 시스템 AI / 프로젝트 에이전트 / API 직접 호출 / auto_response — 각 경로별로 도구 호출 1회씩.
>
> 영향 범위가 크니까 일단 변경 범위만 표로 보고하고 사용자 승인 받은 후 진행할 것.

---

## 작업 #5 — backend/outputs/ 정리 (사용자 수동)

**상태**: 사용자가 수동 처리하기로 한 항목 — 참고용
**의존**: 없음

162번 사고 이전에 같은 패턴으로 잘못 떨어진 디렉토리 8개:
- 경로: `/Users/kangkukjin/Desktop/AI/indiebizOS/backend/outputs/`
- 디렉토리: `house-designs/`, `indiebiz_slides_v1`, `slides/`, `indiebiz_slides_v2`, `slides_ac60b3b5`, `slides_35c9d929`, `v3_images/`, `shadcn_slides_196381ab`

각 디렉토리 내용 확인 후, 필요한 것만 해당 프로젝트의 `projects/<프로젝트명>/outputs/`로 이동, 나머지 삭제. 사용자 판단.

---

## 의존 관계 그래프

```
#1 (재시작 + 검증) ────── 독립, 즉시
#5 (outputs 정리) ────── 독립, 사용자 수동

#2 (33개 마이그레이션) ──┐
                       └─ #3 (구 시그니처 제거)
                              └─ #4 (디폴트 "." 제거, 가장 깊은 정리)
```

**추천 진행 순서**: #1 (즉시) → #2 (다음 큰 세션) → #3 (작음, #2 같은 세션 가능) → #4 (별도 세션, 영향 큼)
