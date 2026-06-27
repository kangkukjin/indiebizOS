"""
ibl_routing.py - IBL 엔진 라우팅 모듈

IBL 엔진(ibl_engine.py)에서 분리된 라우팅 함수들.
노드 액션을 적절한 백엔드(handler, driver, system 등)로 라우팅합니다.
"""

import os
import json
import asyncio
from pathlib import Path
from typing import Any, Dict, Optional


# 도구 실행 타임아웃 (초) — 이 시간을 초과하면 강제로 에러 반환
TOOL_EXECUTION_TIMEOUT = 60


# === 파라미터 alias 정규화 ===
# AI(특히 실행기억/해마 RAG)가 자연스러운 이름으로 호출했을 때 핸들러의 정규 키로 자동 매핑.
# 형식: {"node:action": {"<정규 키>": ["<alias1>", "<alias2>", ...]}}
# 정규화 규칙: 정규 키가 비어있고 alias 키 중 하나에 값이 있으면 그 값을 정규 키로 옮긴다.
ACTION_PARAM_ALIASES: Dict[str, Dict[str, list]] = {
    # 2026-06-03 전수조사(param 이름 불일치): 코퍼스/자연어가 쓰는 키 → 핸들러 정규 키.
    #   옛 항목(apt_trade/resolve_library/recommended_books)은 어휘 통합으로 사라져 현재 액션명으로 재키잉.
    # === 부동산 (real-estate) — 옛 apt_*/house_* → realty{op}, region_code가 정식 ===
    "sense:realty": {"region_code": ["district_code", "dong_code", "code"]},
    "sense:commercial": {
        "region_code": ["district_code", "dong_code", "code"],
        "lat": ["latitude", "y"],
        "lng": ["longitude", "lon", "x"],
    },
    # === 라이브러리 문서 (context7) — 옛 resolve_library/get_library_docs → devdocs{op} ===
    "sense:devdocs": {"library_name": ["library", "lib", "name"], "library_id": ["id", "lib_id"]},
    # === 문화 (KCISA 전시 — keyword가 정식) ===
    "sense:exhibit": {"keyword": ["query"]},
    # === 지역 정보 DB (area가 정식) ===
    "sense:local_query": {"area": ["region"]},
    # === 웹 수집 (query op: site_id/query가 정식) ===
    "sense:collect": {"site_id": ["site"], "query": ["keyword"]},
    # === self ===
    "self:fs_query": {"min_size_mb": ["min_size"]},
    "self:folder_note": {"folder_path": ["path"], "root_path": ["path"]},
    "self:photo": {"media_type": ["filter"]},
    "self:grep": {"root_path": ["path"], "pattern": ["query"]},
    "self:trigger": {"trigger_id": ["id"]},
    "self:output": {"content": ["data"], "format": ["type"]},
    # === limbs ===
    # browser 통합(2026-06-04): 옛 limbs:drag 별칭을 limbs:browser{op:drag}로 재키.
    "limbs:browser": {"source_ref": ["from_ref"], "target_ref": ["to_ref"]},
    "limbs:radio_favorite": {"stream_url": ["url"], "name": ["title"]},
    "limbs:show_map": {"query": ["location"]},
    # (은퇴 2026-06-04) limbs:iframe name:[id] 별칭 — switch가 id를 HTML id 속성으로 직접 처리(name 폴백 포함).
    # === engines ===
    "engines:chart": {"chart_type": ["type"]},
    "engines:image_gemini": {"output_path": ["filename"]},
    # === others ===
    "others:messages": {"neighbor_id": ["contact", "name", "id"]},
    "others:delegate": {"steps": ["pipeline"]},
}


def _normalize_param_aliases(node: str, action: str, params: dict) -> dict:
    """액션별 alias 매핑을 적용해 핸들러가 받는 정규 키로 변환.

    핸들러는 변경 없이 정규 키만 받고, AI 호출자는 자연스러운 이름을 써도 통과한다.
    이미 정규 키에 값이 있으면 alias는 무시 (정규 키 우선).
    """
    if not isinstance(params, dict):
        return params
    key = f"{node}:{action}"
    aliases = ACTION_PARAM_ALIASES.get(key)
    if not aliases:
        return params
    for canonical, alts in aliases.items():
        if params.get(canonical) is not None:
            continue
        for alt in alts:
            if params.get(alt) is not None:
                params[canonical] = params[alt]
                break
    return params


# === 라우터 구현 ===

def _route_api_engine(action: str, params: dict, project_path: str,
                      mapped_tool: str = None) -> Any:
    """API 엔진으로 라우팅

    mapped_tool이 지정되면 해당 api_registry 도구를 직접 실행합니다.
    이를 통해 노드 액션(informant:search 등)이 handler.py 없이
    api_registry.yaml + api_engine.py transform으로 직접 동작합니다.
    """
    from api_engine import execute_tool as api_execute, is_registry_tool

    # 노드 액션에서 직접 매핑된 api_registry 도구 실행.
    # (범용 self:call / self:list_api 액션은 2026-06-04 은퇴 — 모든 등록 도구가
    #  정식 명명 액션으로 노출되어 mapped_tool 경로로만 디스패치됨.)
    if mapped_tool:
        if not is_registry_tool(mapped_tool):
            return {"error": f"api_registry에 등록되지 않은 도구: {mapped_tool}"}
        return api_execute(mapped_tool, dict(params), project_path)

    return {"error": f"api 노드에 '{action}' 액션이 없습니다 (mapped_tool 미지정)."}


# ─────────────────────────────────────────────────────────────────────
# 액션 스코프 (Phase 30) — 액션의 데이터 경계 선언
# ─────────────────────────────────────────────────────────────────────
#
# IBL 액션은 데이터 경계가 서로 다르다. 스코프는 ibl_actions.yaml에 명시:
#
#   - "project" (기본): 특정 프로젝트의 데이터에서 작동. project_path 필요.
#                       예: self:read, self:write — 프로젝트 폴더에서 작동.
#
#   - "workspace":      indiebizOS 인스턴스 전체에 걸친 데이터. 프로젝트 무관.
#                       예: lecture_workspace (outputs/lectures/),
#                       앞으로 추가될 비즈니스 관계, NAS, 통합 메모 등.
#                       resolved path = get_base_path() (indiebizOS 루트 / userData)
#
#   - "system":         indiebizOS 자체에 대한 작업 (설정, 패키지 관리 등).
#                       workspace와 동일한 경로를 쓰되, 향후 권한 모델에서 분리.
#
# scope는 ibl_actions.yaml의 파일 레벨(전체 적용) 또는 액션 레벨(개별 오버라이드)
# 어디든 선언 가능. 라우팅은 이 선언을 보고 project_path 강요 여부를 결정.

WORKSPACE_SCOPES = {"workspace", "system"}


def _resolve_path_by_scope(scope: str, project_path: str,
                            params: Optional[dict] = None) -> Optional[str]:
    """scope에 따라 ToolContext에 줄 base path 결정.

    - workspace/system: get_base_path() (indiebizOS 루트 / userData).
                       project_path/project_id 무시 — 의도적 격리.
    - project (기본):   기존 4단 폴백 우선순위 적용 (_resolve_project_path).
    """
    if scope in WORKSPACE_SCOPES:
        try:
            from runtime_utils import get_base_path
            return str(get_base_path())
        except Exception as e:
            print(f"[ibl_routing] workspace 경로 해석 실패: {e}")
            return None
    return _resolve_project_path(project_path, params)


def _resolve_project_path(project_path: str,
                          params: Optional[dict] = None) -> Optional[str]:
    """project_path를 4단 우선순위로 해석 (scope='project' 전용).

    우선순위:
      1) 호출자가 직접 인자로 넘긴 project_path (디폴트 '.' 가 아닐 때)
         — 프로젝트 에이전트 등 컨텍스트가 살아있는 정상 경로
      2) params["project_id"] — ID만 알면 ProjectManager로 절대경로 변환 (메타 키)
      3) params["project_path"] — 명시 절대/상대 경로 (web-builder처럼 동일
         키를 도구 인자로 쓰는 핸들러와의 충돌을 피하려고 positional이 빈
         경우에만 본다 — 프로젝트 에이전트 흐름에서는 1번에서 결정되므로
         params를 건드리지 않음)
      4) 안전망 — thread_context.project_id

    시스템 AI처럼 자신의 project_path가 없는 호출자는 2·3번으로 대상 프로젝트를
    명시한다. 1번이 살아있으면 params는 도구 인자로 그대로 보존된다.
    """
    # 1) 호출자가 직접 인자로 넘긴 값 — 가장 신뢰
    if project_path and project_path.strip() and project_path != ".":
        return os.path.abspath(project_path)

    # positional이 비어있을 때만 params에서 명시 키 탐색
    if isinstance(params, dict):
        # 2) params.project_id — 의미상 메타 키 (도구 인자로 쓰는 핸들러 없음)
        explicit_id = params.get("project_id")
        if isinstance(explicit_id, str) and explicit_id.strip():
            resolved = _resolve_project_id(explicit_id)
            if resolved:
                return resolved

        # 3) params.project_path — 명시 경로
        explicit_path = params.get("project_path")
        if isinstance(explicit_path, str) and explicit_path.strip() and explicit_path != ".":
            candidate = os.path.abspath(explicit_path)
            if os.path.isdir(candidate):
                return candidate
            # 디렉토리가 아니면 project_id처럼 생긴 값이라 보고 ID 해석 시도
            resolved = _resolve_project_id(explicit_path)
            if resolved:
                return resolved

    # 4) 안전망 — thread_context
    print(
        f"[ibl_routing] WARN: project_path 안전망 발동 (입력={project_path!r}). "
        "호출자가 명시 전달하지 못함 — thread_context.project_id로 복구 시도."
    )
    try:
        from thread_context import get_current_project_id
        project_id = get_current_project_id()
        if project_id:
            resolved = _resolve_project_id(project_id)
            if resolved:
                return resolved
    except Exception as e:
        print(f"[ibl_routing] project_path 복구 실패: {e}")

    return None


def _resolve_project_id(project_id: str) -> Optional[str]:
    """project_id 문자열 → 절대경로 (ProjectManager 경유)."""
    try:
        from project_manager import ProjectManager
        pm = ProjectManager()
        path = pm.get_project_path(project_id)
        if path and path.exists():
            return str(path.resolve())
    except Exception as e:
        print(f"[ibl_routing] project_id '{project_id}' 해석 실패: {e}")
    return None


def _route_handler(mapped_tool: str, params: dict,
                   project_path: str, agent_id: str = None,
                   scope: str = "project") -> Any:
    """handler.py로 위임 (타임아웃 적용).

    표준 시그니처: execute(tool_input, context: ToolContext).
    구 시그니처(tool_name, tool_input, project_path, [agent_id])는 더 이상 지원하지 않는다.

    scope (Phase 30):
        - "project" (기본): project_path 필요. 없으면 에러.
        - "workspace"/"system": project_path 무시, get_base_path()를 ToolContext에 주입.
    """
    from tool_loader import load_tool_handler

    if not mapped_tool:
        return {"error": "매핑된 도구가 없습니다."}

    handler = load_tool_handler(mapped_tool)
    if not handler or not hasattr(handler, "execute"):
        return {"error": f"도구 핸들러를 찾을 수 없습니다: {mapped_tool}"}

    merged_params = dict(params)

    # handler.execute는 신규 시그니처 (tool_input, context)만 지원
    import inspect
    sig = inspect.signature(handler.execute)
    if "context" not in sig.parameters:
        return {"error": (
            f"도구 핸들러가 구 시그니처를 사용합니다: {mapped_tool}. "
            "신규 시그니처 execute(tool_input, context: ToolContext)로 마이그레이션이 필요합니다."
        )}

    resolved_path = _resolve_path_by_scope(scope, project_path, merged_params)
    if not resolved_path:
        if scope in WORKSPACE_SCOPES:
            return {"error": (
                f"workspace 경로를 확보할 수 없습니다: {mapped_tool}. "
                "INDIEBIZ_BASE_PATH 환경변수 또는 backend 폴더 구조를 확인하세요."
            )}
        return {"error": (
            f"활성 프로젝트 경로를 확보할 수 없어 도구를 실행할 수 없습니다: {mapped_tool}. "
            "대상 프로젝트를 params.project_id로 명시하거나 "
            "프로젝트 컨텍스트(thread_context.project_id) 안에서 호출하세요. "
            "예: execute_ibl(code='[node:action]{..., project_id: \"컨텐츠\"}')"
        )}
    from tool_context import ToolContext, ToolContextError
    try:
        context = ToolContext.from_thread_context(resolved_path, mapped_tool)
    except ToolContextError as e:
        return {"error": f"ToolContext 생성 실패: {e}"}
    result = handler.execute(merged_params, context)

    # async 핸들러 지원 (persistent 이벤트 루프 + 타임아웃)
    if asyncio.iscoroutine(result):
        async def _run_with_timeout(coro):
            return await asyncio.wait_for(coro, timeout=TOOL_EXECUTION_TIMEOUT)

        try:
            import concurrent.futures
            from ibl_engine import _get_persistent_loop
            loop = _get_persistent_loop()
            # persistent 루프에 코루틴을 제출하고 결과를 기다림
            future = asyncio.run_coroutine_threadsafe(
                _run_with_timeout(result), loop
            )
            result = future.result(timeout=TOOL_EXECUTION_TIMEOUT + 5)
        except asyncio.TimeoutError:
            print(f"[IBL] 도구 실행 타임아웃 ({TOOL_EXECUTION_TIMEOUT}초): {mapped_tool}")
            result = json.dumps({
                "success": False,
                "error": f"도구 실행 시간 초과 ({TOOL_EXECUTION_TIMEOUT}초): {mapped_tool}. 다른 방법을 시도하세요."
            })
        except concurrent.futures.TimeoutError:
            print(f"[IBL] 도구 스레드 타임아웃 ({TOOL_EXECUTION_TIMEOUT}초): {mapped_tool}")
            result = json.dumps({
                "success": False,
                "error": f"도구 실행 시간 초과 ({TOOL_EXECUTION_TIMEOUT}초): {mapped_tool}. 다른 방법을 시도하세요."
            })
        except Exception as e:
            print(f"[IBL] async 핸들러 실행 실패: {e}")
            result = json.dumps({"success": False, "error": f"async 실행 오류: {str(e)}"})

    return result



def _route_system(func_name: str, params: dict, project_path: str, agent_id: str = None) -> Any:
    """system_tools 내장 함수 직접 호출"""
    if func_name == "send_notification":
        from system_tools import execute_send_notification
        return execute_send_notification(dict(params), project_path)

    elif func_name == "delegate":
        return _delegate_unified(params, project_path)

    elif func_name == "agents":
        agent_id = params.get("agent_id", "")
        if agent_id:
            return _agent_info(agent_id)
        from system_ai_tools import _execute_list_project_agents
        return _execute_list_project_agents(dict(params))

    elif func_name == "call_agent":
        from system_tools import execute_call_agent
        return execute_call_agent(dict(params), project_path)

    elif func_name == "delegate_workflow":
        return _delegate_workflow(params.get("workflow", ""), params, project_path)

    elif func_name == "discover":
        return _discover_nodes(params.get("query", ""), params)

    # Phase 11: 에이전트 노드
    elif func_name == "agent_ask":
        return _agent_ask(params.get("agent_id", ""), params, project_path)
    elif func_name == "agent_ask_sync":
        return _agent_ask_sync(params.get("agent_id", ""), params, project_path)
    elif func_name == "agent_list":
        return _agent_list(params)
    elif func_name == "agent_info":
        return _agent_info(params.get("agent_id", ""))

    # 출력 싱크 — 단일 액션 패턴: output {op: gui|file|clipboard} (2026-06-04 통합)
    # download는 획득 동작이라 별도 액션 유지.
    elif func_name == "output_op":
        op = (params.get("op") or "gui").strip()  # 기본 gui (부작용 없는 표시)
        op_map = {
            "gui": "output_gui",
            "file": "output_file",
            "clipboard": "output_clipboard",
        }
        target_func = op_map.get(op)
        if not target_func:
            return {"success": False, "error": "op 파라미터가 필요합니다. (gui|file|clipboard)"}
        return _route_system(target_func, params, project_path, agent_id=agent_id)

    # Phase 13: 출력 노드 (순환 import 방지를 위해 lazy import)
    elif func_name == "output_gui":
        from ibl_executors import _output_gui
        return _output_gui(params.get("content", ""), params, project_path)
    elif func_name == "output_file":
        from ibl_executors import _output_file
        return _output_file(params.get("path", ""), params, project_path)
    elif func_name == "output_open":
        from ibl_executors import _output_open
        return _output_open(params.get("path", ""), params, project_path)
    elif func_name == "output_clipboard":
        from ibl_executors import _output_clipboard
        return _output_clipboard(params.get("content", ""), params)
    elif func_name == "output_download":
        from ibl_executors import _output_download
        return _output_download(params.get("url", ""), params, project_path)

    # Phase 17: 시스템 AI 전용 함수
    elif func_name == "list_project_agents":
        from api_system_ai import _execute_list_project_agents
        return _execute_list_project_agents(params)

    elif func_name == "call_project_agent":
        from api_system_ai import _execute_call_project_agent
        return _execute_call_project_agent(dict(params))

    elif func_name == "schedule":
        from api_system_ai import _execute_schedule
        return _execute_schedule(params, agent_id=agent_id, project_path=project_path)

    elif func_name == "manage_events":
        from api_system_ai import _execute_manage_events
        return _execute_manage_events(params)

    elif func_name == "launcher_command":
        # 신규: params.app ("project" 등) → "open_<app>" 합성
        # 호환: params.command ("open_project" 등) 직접 지정도 허용
        launcher_action = params.get("command", "")
        if not launcher_action:
            app = params.get("app", "")
            if app:
                launcher_action = f"open_{app}"
        return _execute_launcher_command(launcher_action, params)

    elif func_name == "list_switches":
        from api_system_ai import _execute_list_switches
        return _execute_list_switches(params)

    elif func_name == "run_switch":
        from switch_manager import SwitchManager
        from switch_runner import SwitchRunner
        switch_id = params.get("switch_id", "")
        if not switch_id:
            return {"success": False, "error": "switch_id가 필요합니다."}
        sm = SwitchManager()
        switch = sm.get_switch(switch_id)
        if not switch:
            return {"success": False, "error": f"스위치 없음: {switch_id}"}
        runner = SwitchRunner(sm)
        result = runner.run_switch(switch_id)
        return {"success": True, "switch_id": switch_id, "result": result}

    elif func_name == "switch_op":
        # 단일 액션 패턴: switch {op: list|run}
        op = (params.get("op") or "").strip()
        if op == "list":
            return _route_system("list_switches", params, project_path, agent_id=agent_id)
        if op == "run":
            return _route_system("run_switch", params, project_path, agent_id=agent_id)
        return {"success": False, "error": "op 파라미터가 필요합니다. (list|run)"}

    elif func_name == "goal_op":
        # 단일 액션 패턴: goal {op: list|status|kill|log|attempts}
        op = (params.get("op") or "").strip()
        op_map = {
            "list": "list_goals",
            "status": "get_goal_status",
            "kill": "kill_goal",
            "log": "log_attempt",
            "attempts": "get_attempts",
        }
        target_func = op_map.get(op)
        if not target_func:
            return {"success": False, "error": "op 파라미터가 필요합니다. (list|status|kill|log|attempts)"}
        return _route_system(target_func, params, project_path, agent_id=agent_id)

    # World Pulse: 세계 상태 감각 — 단일 액션 패턴: world {op: snapshot|trend|refresh}
    elif func_name == "world_op":
        from world_pulse import execute_world_pulse
        op = (params.get("op") or "snapshot").strip()  # 기본 snapshot
        op_map = {
            "snapshot": "world_pulse",
            "trend": "world_trend",
            "refresh": "world_refresh",
        }
        action_name = op_map.get(op)
        if not action_name:
            return {"success": False, "error": "op 파라미터가 필요합니다. (snapshot|trend|refresh)"}
        return execute_world_pulse(action_name, dict(params))

    # 자가점검: IBL 건강 점검 (정적+fixture+골든, AI 0)
    elif func_name == "self_check":
        from world_pulse_health import run_daily_health_check
        return run_daily_health_check()

    # Phase 26: Goal 프로세스 관리
    elif func_name == "list_goals":
        from ibl_engine import _goal_list
        return _goal_list(params, project_path)
    elif func_name == "get_goal_status":
        from ibl_engine import _goal_status
        return _goal_status(params.get("goal_id", ""), params, project_path)
    elif func_name == "kill_goal":
        from ibl_engine import _goal_kill
        return _goal_kill(params.get("goal_id", ""), params, project_path)

    # Phase 26b: 시도 기록 (전략 전환 + 라운드 메모리)
    elif func_name == "log_attempt":
        from ibl_engine import _log_attempt
        return _log_attempt(params, project_path)
    elif func_name == "get_attempts":
        from ibl_engine import _get_attempts
        return _get_attempts(params, project_path)

    return {"error": f"알 수 없는 시스템 함수: {func_name}"}


def _execute_launcher_command(action: str, params: dict) -> dict:
    """Launcher(Electron) 창 제어 명령 실행 (Phase 27)

    WS로 Launcher에 명령을 보내 프로젝트 창 열기, 포커스 등 수행.
    """
    import asyncio

    # action 이름 → Launcher 명령 매핑
    command_map = {
        "open_project": "open_project_window",
        "open_system_ai": "open_system_ai_window",
        "open_indienet": "open_indienet_window",
        "open_business": "open_business_window",
        "open_multichat": "open_multichat_window",
        "open_folder": "open_folder_window",
    }

    command = command_map.get(action)
    if not command:
        return {"success": False, "error": f"알 수 없는 launcher 액션: {action}"}

    try:
        from api_websocket import send_launcher_command, get_launcher_ws

        if not get_launcher_ws():
            return {"success": False, "error": "Launcher WS 미연결"}

        # 비동기 함수를 동기 컨텍스트에서 실행
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    send_launcher_command(command, dict(params)),
                    loop
                )
                sent = future.result(timeout=5)
            else:
                sent = asyncio.run(send_launcher_command(command, dict(params)))
        except RuntimeError:
            sent = asyncio.run(send_launcher_command(command, dict(params)))

        if sent:
            return {"success": True, "message": f"Launcher 명령 전달: {command}"}
        else:
            return {"success": False, "error": "Launcher 명령 전달 실패"}

    except Exception as e:
        return {"success": False, "error": f"Launcher 명령 오류: {str(e)}"}


def _discover_nodes(query: str, params: dict) -> Any:
    """노드 디스커버리 (Phase 10)

    해마(fine-tuned 임베딩)로 적합한 노드/액션을 자동 탐색.
    "이 작업을 할 수 있는 노드가 뭐야?"를 해결.
    """
    import re as _re
    from node_registry import list_nodes, node_summary
    from ibl_access import _load_nodes_data

    if not query:
        return node_summary()

    # 해마로 관련 IBL 코드 사례 검색
    try:
        from ibl_usage_db import IBLUsageDB
        db = IBLUsageDB()
        limit = params.get("limit", 10)
        search_results = db.search_hybrid(query=query, top_k=limit)
    except Exception:
        search_results = []

    if not search_results:
        return {
            "query": query,
            "results": [],
            "message": f"'{query}'에 매칭되는 노드를 찾을 수 없습니다.",
            "total_nodes": len(list_nodes()),
        }

    # 해마 결과에서 [node:action] 추출 → ibl_nodes.yaml에서 상세 조회
    nodes_data = _load_nodes_data() or {}
    nodes_config = nodes_data.get("nodes", {})
    action_pattern = _re.compile(r'\[([a-z_-]+):([a-z_-]+)\]')

    # 노드별로 그룹화
    node_actions = {}  # {node_name: {action_name: {desc, impl, example, score}}}
    for r in search_results:
        for node_name, action_name in action_pattern.findall(r.ibl_code):
            if node_name not in node_actions:
                node_actions[node_name] = {}
            if action_name not in node_actions[node_name]:
                node_config = nodes_config.get(node_name, {})
                action_config = node_config.get("actions", {}).get(action_name, {})
                node_actions[node_name][action_name] = {
                    "action": action_name,
                    "description": action_config.get("description", ""),
                    "implementation": action_config.get("implementation", ""),
                    "example": r.ibl_code,
                }

    # 기존 반환 형식에 맞춰 변환
    results = []
    for node_name, actions in node_actions.items():
        node_config = nodes_config.get(node_name, {})
        action_details = list(actions.values())
        suggestion = f"[{node_name}:{action_details[0]['action']}]" if action_details else ""
        results.append({
            "node": node_name,
            "description": node_config.get("description", ""),
            "score": len(action_details) * 10,
            "matching_actions": [a["action"] for a in action_details],
            "suggestion": suggestion,
            "action_details": action_details,
        })

    results.sort(key=lambda x: x["score"], reverse=True)

    return {
        "query": query,
        "results": results,
        "count": len(results),
        "best_match": results[0]["suggestion"] if results else "",
    }


def _search_guide(query: str, params: dict) -> Any:
    """가이드 DB 검색 — 복잡한 작업 전에 워크플로우/레시피 확인

    DB(guide_db.json)에서 키워드 매칭 후 data/guides/ 폴더에서 파일 읽기.
    params.read=true (기본) → 첫 번째 매칭 가이드 내용까지 반환
    params.read=false → 목록만 반환
    """
    import json as _json
    from pathlib import Path as _Path

    data_dir = _Path(__file__).parent.parent / "data"
    guide_db_path = data_dir / "guide_db.json"

    if not guide_db_path.exists():
        return {"error": "guide_db.json이 없습니다."}

    with open(guide_db_path, 'r', encoding='utf-8') as f:
        db = _json.load(f)

    guides = db.get("guides", [])

    if not query:
        return {
            "guides": [{"id": g["id"], "name": g["name"], "description": g["description"]} for g in guides],
            "count": len(guides),
            "message": "가이드 전체 목록입니다. 키워드로 검색하세요.",
        }

    # 한국어 정규화: 조사 제거 + 복합어 분리 (korean_utils 공통 모듈)
    from korean_utils import tokenize_korean
    query_stems = tokenize_korean(query)

    scored = []
    for g in guides:
        score = 0
        search_text = " ".join([
            g.get("name", ""),
            g.get("description", ""),
            " ".join(g.get("keywords", [])),
        ]).lower()

        for word in query_stems:
            if word in search_text:
                score += 1
            if word in [kw.lower() for kw in g.get("keywords", [])]:
                score += 2

        if score > 0:
            scored.append((score, g))

    scored.sort(key=lambda x: x[0], reverse=True)

    if not scored:
        return {
            "query": query,
            "results": [],
            "message": f"'{query}'에 매칭되는 가이드가 없습니다.",
        }

    results = [{"id": g["id"], "name": g["name"], "description": g["description"], "score": s} for s, g in scored[:5]]

    response = {
        "query": query,
        "results": results,
        "count": len(results),
        "best_match": results[0]["name"],
    }

    # 기본적으로 첫 번째 매칭 가이드 파일을 읽어서 반환
    read_content = params.get("read", True)
    if read_content and scored:
        best = scored[0][1]
        guide_file = best.get("file", "")
        if guide_file:
            guide_path = data_dir / "guides" / guide_file
            if guide_path.exists():
                try:
                    response["guide_content"] = guide_path.read_text(encoding='utf-8')
                    response["guide_name"] = best["name"]
                except Exception:
                    pass

    return response


def _delegate_unified(params: dict, project_path: str) -> Any:
    """위임 통합 디스패처 — mode(async/sync/workflow) × scope(same/cross)."""
    mode = (params.get("mode") or "async").lower()
    scope = (params.get("scope") or "same").lower()

    if scope == "cross":
        from system_ai_tools import _execute_call_project_agent
        agent_id_raw = params.get("agent_id", "")
        if not agent_id_raw:
            return {"error": "agent_id가 필요합니다. 예: '의료/내과'"}
        # '프로젝트/에이전트' 자동 분리 (call_project_agent는 둘을 분리해서 받음)
        if "project_id" not in params and "/" in str(agent_id_raw):
            project_id, agent_id = str(agent_id_raw).split("/", 1)
            call_input = {**params, "project_id": project_id, "agent_id": agent_id}
        else:
            call_input = dict(params)
        return _execute_call_project_agent(call_input)

    if mode == "sync":
        return _agent_ask_sync(params.get("agent_id", ""), params, project_path)

    if mode == "workflow":
        return _delegate_workflow(params.get("agent_id", "") or params.get("workflow", ""),
                                   params, project_path)

    # 기본: async (같은 프로젝트 비동기 위임)
    from system_tools import execute_call_agent
    return execute_call_agent(dict(params), project_path)


def _delegate_workflow(agent_id: str, params: dict, project_path: str) -> Any:
    """다른 에이전트에게 IBL 파이프라인을 위임

    Args:
        agent_id: 대상 에이전트 이름 또는 ID
        params: {"steps": [...], "message": "..."} 파이프라인 정의
    """
    if not agent_id:
        return {"error": "agent_id가 필요합니다."}

    steps = params.get("steps", [])
    if not steps:
        return {"error": "params.steps가 필요합니다. 파이프라인 단계를 정의해주세요."}

    # 파이프라인 steps를 JSON으로 직렬화
    steps_json = json.dumps(steps, ensure_ascii=False)
    user_message = params.get("message", "")

    # 위임 메시지 구성
    delegation_msg = f"""다음 IBL 파이프라인을 실행해주세요.

```json
{steps_json}
```

execute_ibl(node="system", action="run_pipeline", params={{"steps": {steps_json}}}) 로 실행하세요."""

    if user_message:
        delegation_msg = f"{user_message}\n\n{delegation_msg}"

    # call_agent으로 위임
    from system_tools import execute_call_agent
    return execute_call_agent(
        {"agent_id": agent_id, "message": delegation_msg},
        project_path
    )


def _agent_ask(agent_id: str, params: dict, project_path: str) -> Any:
    """에이전트에게 질문/위임 [others:delegate]{agent_id: "투자/투자컨설팅"} (Phase 11)"""
    if not agent_id:
        return {"error": "agent_id(문자열)가 필요합니다. 예: \"대장장이\" 또는 \"컨텐츠/대장장이\" 형식"}

    if isinstance(agent_id, (int, float)):
        agent_id = str(int(agent_id))

    # "프로젝트/에이전트이름" 파싱
    parts = agent_id.split("/", 1)
    if len(parts) == 2:
        project_id, agent_name = parts
    else:
        agent_name = parts[0]
        project_id = Path(project_path).name

    message = params.get("message", params.get("query", ""))
    if not message:
        return {"error": "message 파라미터가 필요합니다. 예: {agent_id: \"대장장이\", message: \"이것 좀 해줘\"}"}

    from system_tools import execute_call_agent
    env_path = os.environ.get("INDIEBIZ_BASE_PATH")
    base = Path(env_path) if env_path else Path(__file__).parent.parent
    target_project_path = str(base / "projects" / project_id)
    return execute_call_agent({"agent_id": agent_name, "message": message}, target_project_path)


def _agent_ask_sync(agent_id: str, params: dict, project_path: str) -> Any:
    """에이전트에게 동기 질문 — 응답을 기다려서 반환 (파이프라인용)

    비동기 agent_ask와 달리, 임시 AI 에이전트를 생성하여
    메시지를 처리하고 결과 텍스트를 직접 반환합니다.

    사용: [others:delegate]{mode: "sync", agent_id: "프로젝트/에이전트", message: "분석해줘"}
    파이프라인: [self:blog]{op: "search", query: "AI"} >> [others:delegate]{mode: "sync", agent_id: "컨텐츠/컨텐츠", message: "요약해줘"}
    """
    if not agent_id:
        return {"error": "agent_id(문자열)가 필요합니다. 예: \"대장장이\" 또는 \"컨텐츠/대장장이\" 형식"}

    # agent_id가 숫자로 들어온 경우 문자열로 변환
    if isinstance(agent_id, (int, float)):
        agent_id = str(int(agent_id))

    # "프로젝트/에이전트이름" 파싱
    parts_split = agent_id.split("/", 1)
    if len(parts_split) == 2:
        project_id, agent_name = parts_split
    else:
        agent_name = parts_split[0]
        project_id = Path(project_path).name

    message = params.get("message", params.get("query", ""))
    if not message:
        return {"error": "message 파라미터가 필요합니다. 예: {agent_id: \"대장장이\", message: \"이것 좀 분석해줘\"}"}

    # _prev_result가 있으면 message에 첨부
    prev = params.get("_prev_result", "")
    if prev and prev not in message:
        message = f"{message}\n\n--- 이전 단계 결과 ---\n{prev}"

    # agents.yaml에서 대상 에이전트 설정 로드
    env_path = os.environ.get("INDIEBIZ_BASE_PATH")
    base = Path(env_path) if env_path else Path(__file__).parent.parent
    target_project_path = base / "projects" / project_id
    agents_yaml = target_project_path / "agents.yaml"

    if not agents_yaml.exists():
        return {"error": f"프로젝트 '{project_id}'를 찾을 수 없습니다."}

    try:
        import yaml as _yaml
        data = _yaml.safe_load(agents_yaml.read_text(encoding='utf-8'))
    except Exception as e:
        return {"error": f"agents.yaml 로드 실패: {e}"}

    # 에이전트 찾기
    agents = data.get("agents", [])
    agent_config = None
    for ag in agents:
        if ag.get("name") == agent_name or ag.get("id") == agent_name:
            agent_config = ag
            break

    if not agent_config:
        available = [ag.get("name", ag.get("id", "?")) for ag in agents]
        return {"error": f"에이전트 '{agent_name}'을 찾을 수 없습니다.", "available": available}

    ai_config = agent_config.get("ai", {})
    if not ai_config.get("api_key"):
        return {"error": f"에이전트 '{agent_name}'의 API 키가 설정되지 않았습니다."}

    # 임시 AI 에이전트 생성 + 동기 호출
    try:
        from ai_agent import AIAgent
        from prompt_builder import build_agent_prompt
        from ibl_access import build_environment
        from tool_loader import load_tool_schema

        # IBL 도구 로드
        ibl_schema = load_tool_schema("execute_ibl")
        tools = [ibl_schema] if ibl_schema else []

        # 프롬프트 구성
        allowed_nodes = agent_config.get("allowed_nodes")
        system_prompt = build_agent_prompt(
            agent_name=agent_name,
            role=agent_config.get("role_description", ""),
            agent_count=1,
            ibl_only=True,
            allowed_nodes=allowed_nodes,
            project_path=str(target_project_path),
            agent_id=agent_config.get("id", ""),
        )

        agent = AIAgent(
            ai_config=ai_config,
            system_prompt=system_prompt,
            agent_name=agent_name,
            tools=tools,
        )

        # 동기 호출 — AI가 응답할 때까지 대기
        response = agent.process_message_with_history(
            message_content=message,
            from_email="pipeline@system",
            history=[],
        )

        return {
            "success": True,
            "agent": agent_name,
            "project": project_id,
            "response": response,
            "sync": True,
        }

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": f"동기 에이전트 호출 실패: {e}"}


def _agent_list(params: dict) -> Any:
    """에이전트 노드 목록 [agent:list] (Phase 11)"""
    from node_registry import list_nodes
    nodes = list_nodes(include_agents=True)
    agent_nodes = [n for n in nodes if n["type"] == "agent"]

    # 프로젝트 필터
    project_filter = params.get("project")
    if project_filter:
        agent_nodes = [n for n in agent_nodes if n["project_id"] == project_filter]

    return {
        "agents": [{
            "id": n["id"],
            "name": n["agent_name"],
            "project": n["project_id"],
            "description": n["description"],
            "capabilities": n.get("capabilities", []),
            "running": n.get("running", False),
        } for n in agent_nodes],
        "count": len(agent_nodes),
    }


def _agent_info(agent_id: str) -> Any:
    """에이전트 상세 정보 [others:info]{agent_id: "투자/투자컨설팅"} (Phase 11)"""
    from node_registry import list_nodes
    nodes = list_nodes(include_agents=True)
    for n in nodes:
        if n["type"] == "agent" and n["id"] == agent_id:
            return n
    return {"error": f"에이전트 '{agent_id}'을 찾을 수 없습니다."}


def _route_driver(driver_type: str, node: str, action: str,
                  params: dict, project_path: str,
                  driver_node: str = None) -> Any:
    """드라이버 계층으로 라우팅 (Phase 7)

    드라이버는 프로토콜(SQLite, ADB, CDP 등)을 감추고
    통일된 execute(action, params) 인터페이스를 제공한다.

    Phase 22: driver_node 파라미터 추가.
    6-Node 통합으로 source/messenger 등 상위 노드가 photo/health/blog/contact/memory
    등의 하위 핸들러를 포함하게 됨. driver_node가 지정되면 실제 드라이버 핸들러명으로 사용.
    """
    # 드라이버 인스턴스 가져오기
    driver_registry = {
        "sqlite": ("drivers.sqlite_driver", "get_driver"),
        # 향후 확장:
        # "adb": ("drivers.adb_driver", "get_driver"),
        # "cdp": ("drivers.cdp_driver", "get_driver"),
        # "stream": ("drivers.stream_driver", "get_driver"),
    }

    entry = driver_registry.get(driver_type)
    if not entry:
        return {"error": f"알 수 없는 드라이버: {driver_type}"}

    module_path, factory_name = entry
    try:
        import importlib
        mod = importlib.import_module(module_path)
        get_driver = getattr(mod, factory_name)
        driver = get_driver()
    except Exception as e:
        return {"error": f"드라이버 로드 실패 ({driver_type}): {str(e)}"}

    # 노드 정보를 params에 전달 (driver_node 우선, 없으면 node)
    params["_node"] = driver_node or node
    if project_path:
        params["project_path"] = project_path

    return driver.execute(action, params)


def _route_by_config(action_config, params, node, action,
                     project_path, agent_id):
    """YAML 액션 설정 기반 통합 라우팅"""
    # 자연스러운 파라미터 이름(district_code, name 등)을 핸들러 정규 키로 자동 매핑
    params = _normalize_param_aliases(node, action, params)

    router = action_config.get("router")
    # Phase 30: scope 선언 (workspace/system/project). 미지정 시 project.
    scope = action_config.get("scope", "project")

    if router == "handler":
        mapped_tool = action_config.get("tool")
        return _route_handler(mapped_tool, params, project_path, agent_id, scope=scope)
    elif router == "driver":
        driver_type = action_config.get("driver", "sqlite")
        dn = action_config.get("driver_node")  # Phase 22: 하위 핸들러 지정
        return _route_driver(driver_type, node, action, params, project_path, driver_node=dn)
    return {"error": f"지원하지 않는 라우터: {router}"}
