"""
ibl_engine.py - IBL 노드-액션 실행 엔진

[node:action]{params} 모델을 파싱하고 적절한 백엔드로 라우팅합니다.

사용법:
    from ibl_engine import execute_ibl, list_ibl_nodes, list_actions

    # 노드 도구 실행
    result = execute_ibl({"action": "search", "params": {"query": "임대차"}}, ".")

    # 노드 목록
    nodes = list_ibl_nodes()

    # 노드별 액션 목록
    actions = list_actions("sense")
"""

import os
import json
import asyncio
import threading
import yaml
from pathlib import Path
from typing import Any, Dict, List, Optional


# === Persistent 이벤트 루프 (async 핸들러용) ===
# browser-action 등 async 도구가 파이프라인에서 연속 호출될 때,
# 같은 이벤트 루프를 공유해야 Playwright 객체가 유효함.
_persistent_loop: Optional[asyncio.AbstractEventLoop] = None
_persistent_thread: Optional[threading.Thread] = None


def _get_persistent_loop() -> asyncio.AbstractEventLoop:
    """async 핸들러 전용 이벤트 루프를 반환 (없으면 생성)"""
    global _persistent_loop, _persistent_thread

    if _persistent_loop and not _persistent_loop.is_closed():
        return _persistent_loop

    _persistent_loop = asyncio.new_event_loop()

    def _run_loop(loop):
        asyncio.set_event_loop(loop)
        loop.run_forever()

    _persistent_thread = threading.Thread(target=_run_loop, args=(_persistent_loop,), daemon=True)
    _persistent_thread.start()
    return _persistent_loop


# === 노드 레지스트리 로딩 ===

_nodes: Optional[Dict] = None
_nodes_path: Optional[Path] = None


def _get_nodes_path() -> Path:
    """ibl_nodes.yaml 경로"""
    global _nodes_path
    if _nodes_path:
        return _nodes_path
    env_path = os.environ.get("INDIEBIZ_BASE_PATH")
    if env_path:
        _nodes_path = Path(env_path) / "data" / "ibl_nodes.yaml"
    else:
        _nodes_path = Path(__file__).parent.parent / "data" / "ibl_nodes.yaml"
    return _nodes_path


def _merge_api_registry_actions(nodes_config: Dict):
    """api_registry의 node 필드 기반 노드 액션 자동 병합.

    api_registry.yaml 도구에 node/action_name이 선언되어 있으면
    해당 노드의 actions dict에 in-place 병합한다.
    YAML 앵커(&id005 등)가 가리키는 동일 dict를 직접 변경하므로
    nodes 섹션에도 자동 반영된다.
    """
    try:
        from api_engine import _load_registry
    except ImportError:
        return

    registry = _load_registry()
    tools = registry.get("tools", {})

    for tool_name, tool_cfg in tools.items():
        node_name = tool_cfg.get("node")
        if not node_name:
            continue

        action_name = tool_cfg.get("action_name", tool_name)
        node_cfg = nodes_config.get(node_name)
        if not node_cfg:
            continue

        actions = node_cfg.get("actions")
        if actions is None:
            actions = {}
            node_cfg["actions"] = actions

        # 수동 정의가 이미 있으면 덮어쓰지 않음
        if action_name in actions:
            continue

        action = {"router": "api_engine", "tool": tool_name}
        if tool_cfg.get("description"):
            action["description"] = tool_cfg["description"]
        if tool_cfg.get("target_key"):
            action["target_key"] = tool_cfg["target_key"]

        actions[action_name] = action


def _load_nodes_config() -> Dict:
    """노드 정의 로드 (캐싱)"""
    global _nodes
    if _nodes is not None:
        return _nodes

    path = _get_nodes_path()
    if not path.exists():
        _nodes = {"nodes": {}}
        return _nodes

    with open(path, "r", encoding="utf-8") as f:
        _nodes = yaml.safe_load(f) or {"nodes": {}}

    # api_registry에서 node 바인딩된 액션 자동 병합
    _merge_api_registry_actions(_nodes.get("nodes", {}))

    return _nodes


def reload_nodes():
    """노드 정의 강제 리로드"""
    global _nodes
    _nodes = None
    _load_nodes_config()


def get_node_actions(node_name: str) -> set:
    """특정 노드의 유효한 액션 이름 set 반환"""
    config = _load_nodes_config()
    nodes = config.get("nodes", {})
    node_def = nodes.get(node_name, {})
    actions = node_def.get("actions", {})
    return set(actions.keys())


# === 공개 API ===

def list_ibl_nodes() -> List[Dict]:
    """사용 가능한 노드 목록"""
    reg = _load_nodes_config()
    result = []
    for name, config in reg.get("nodes", {}).items():
        result.append({
            "node": name,
            "description": config.get("description", ""),
            "actions": list(config.get("actions", {}).keys()),
        })
    return result


def list_actions(node: str) -> List[Dict]:
    """특정 노드의 액션 목록"""
    reg = _load_nodes_config()
    node_config = reg.get("nodes", {}).get(node)
    if not node_config:
        return []

    result = []
    for name, config in node_config.get("actions", {}).items():
        info = {
            "action": name,
            "description": config.get("description", ""),
            "router": config.get("router", ""),
        }
        if config.get("tool"):
            info["mapped_tool"] = config["tool"]
        if config.get("phase"):
            info["phase"] = config["phase"]
        result.append(info)
    return result



def execute_ibl(tool_input: dict, project_path: str = ".", agent_id: str = None) -> Any:
    """
    IBL 노드 도구 실행

    Args:
        tool_input: {
            "action": "search",      # 필수: 액션 이름
            "params": {...},         # 파라미터
            ...기타 노드별 파라미터
        }
        project_path: 프로젝트 경로
        agent_id: 에이전트 ID

    Returns:
        실행 결과
    """
    # Phase 26: Goal Block 실행
    if tool_input.get("_goal"):
        return _execute_goal_block(tool_input, project_path, agent_id)

    # Phase 26: 조건문 (if/else) 실행
    if tool_input.get("_condition"):
        return _execute_condition(tool_input, project_path, agent_id)

    # Phase 26: Case문 실행
    if tool_input.get("_case"):
        return _execute_case(tool_input, project_path, agent_id)

    # Phase 12: 노드 타입 모드
    node_type = tool_input.get("_node_type")
    if node_type:
        return _execute_node(node_type, tool_input, project_path, agent_id)

    action = tool_input.get("action")
    if not action:
        node = tool_input.get("_node")
        if node:
            reg = _load_nodes_config()
            nc = reg.get("nodes", {}).get(node, {})
            actions = list(nc.get("actions", {}).keys())
            return {
                "error": f"action 파라미터가 필요합니다. [node:action] 형식으로 호출하세요.",
                "node": node,
                "available_actions": actions[:20],
                "example": f'[{node}:{actions[0]}]{{...}}' if actions else None,
                "hint": f"총 {len(actions)}개 액션 사용 가능"
            }
        return {"error": "action 파라미터가 필요합니다.", "available_nodes": [d["node"] for d in list_ibl_nodes()]}

    # 노드는 tool_name에서 결정됨 (ibl_api -> api, ibl_web -> web 등)
    # 이 함수는 노드가 이미 결정된 상태로 호출됨
    node = tool_input.get("_node")
    if not node:
        return {"error": "_node이 설정되지 않았습니다. handler.py를 통해 호출해주세요."}

    reg = _load_nodes_config()
    node_config = reg.get("nodes", {}).get(node)
    if not node_config:
        return {"error": f"알 수 없는 노드: {node}", "available_nodes": [d["node"] for d in list_ibl_nodes()]}

    action_config = node_config.get("actions", {}).get(action)
    if not action_config:
        available = list(node_config.get("actions", {}).keys())
        return {"error": f"노드 '{node}'에 '{action}' 액션이 없습니다.",
                "available_actions": available}

    router = action_config.get("router")
    params = tool_input.get("params", {})

    # default_input 병합: 액션에 정의된 기본값을 params에 적용 (사용자 값 우선)
    default_input = action_config.get("default_input")
    if default_input and isinstance(default_input, dict):
        for k, v in default_input.items():
            if k not in params:
                params[k] = v

    # 라우터별 실행
    if router == "api_engine":
        mapped_tool = action_config.get("tool")
        return _route_api_engine(action, params, project_path,
                                 mapped_tool=mapped_tool)
    elif router == "handler":
        mapped_tool = action_config.get("tool")
        return _route_handler(mapped_tool, params, project_path, agent_id)
    elif router == "system":
        func_name = action_config.get("func")
        return _route_system(func_name, params, project_path, agent_id=agent_id)
    elif router == "workflow_engine":
        from workflow_engine import execute_workflow_action
        return execute_workflow_action(action, params, project_path)
    elif router == "channel_engine":
        from channel_engine import execute_channel_action
        return execute_channel_action(action, params, project_path, agent_id=agent_id)
    elif router == "web_collector":
        from web_collector import execute_web_collect_action
        return execute_web_collect_action(action, params, project_path)
    elif router in ("event_engine", "trigger_engine"):
        from trigger_engine import execute_trigger
        return execute_trigger(action, params, project_path)
    elif router == "driver":
        driver_type = action_config.get("driver", "sqlite")
        dn = action_config.get("driver_node")  # Phase 22: 하위 핸들러 지정
        return _route_driver(driver_type, node, action, params, project_path, driver_node=dn)
    elif router == "stub":
        phase = action_config.get("phase", "?")
        return {
            "error": f"[{node}:{action}]은 Phase {phase}에서 구현 예정입니다.",
            "node": node,
            "action": action,
            "status": "not_implemented",
        }
    else:
        return {"error": f"알 수 없는 라우터: {router}"}


# === 라우터 구현 ===

def _route_api_engine(action: str, params: dict, project_path: str,
                      mapped_tool: str = None) -> Any:
    """API 엔진으로 라우팅

    mapped_tool이 지정되면 해당 api_registry 도구를 직접 실행합니다.
    이를 통해 노드 액션(informant:search 등)이 handler.py 없이
    api_registry.yaml + api_engine.py transform으로 직접 동작합니다.
    """
    from api_engine import execute_tool as api_execute, list_registry_tools, is_registry_tool

    # 1) 노드 액션에서 직접 매핑된 api_registry 도구 실행
    if mapped_tool:
        if not is_registry_tool(mapped_tool):
            return {"error": f"api_registry에 등록되지 않은 도구: {mapped_tool}"}
        return api_execute(mapped_tool, dict(params), project_path)

    # 2) 범용 api_engine 액션
    if action == "list":
        tools = list_registry_tools()
        return {"node": "api", "action": "list", "tools": tools, "count": len(tools)}

    if action == "call":
        tool_name = params.get("tool", "")
        if not tool_name:
            tools = list_registry_tools()
            return {
                "error": "params.tool(도구 이름)이 필요합니다.",
                "available_tools": tools,
            }
        if not is_registry_tool(tool_name):
            tools = list_registry_tools()
            return {
                "error": f"레지스트리에 등록되지 않은 도구: {tool_name}",
                "available_tools": tools,
            }
        return api_execute(tool_name, params, project_path)

    return {"error": f"api 노드에 '{action}' 액션이 없습니다."}


# 도구 실행 타임아웃 (초) — 이 시간을 초과하면 강제로 에러 반환
TOOL_EXECUTION_TIMEOUT = 60


def _route_handler(mapped_tool: str, params: dict,
                   project_path: str, agent_id: str = None) -> Any:
    """handler.py로 위임 (타임아웃 적용)"""
    from tool_loader import load_tool_handler

    if not mapped_tool:
        return {"error": "매핑된 도구가 없습니다."}

    handler = load_tool_handler(mapped_tool)
    if not handler or not hasattr(handler, "execute"):
        return {"error": f"도구 핸들러를 찾을 수 없습니다: {mapped_tool}"}

    merged_params = dict(params)

    # handler.execute 호출
    import inspect
    sig = inspect.signature(handler.execute)
    if "agent_id" in sig.parameters:
        result = handler.execute(mapped_tool, merged_params, project_path, agent_id)
    else:
        result = handler.execute(mapped_tool, merged_params, project_path)

    # async 핸들러 지원 (persistent 이벤트 루프 + 타임아웃)
    if asyncio.iscoroutine(result):
        async def _run_with_timeout(coro):
            return await asyncio.wait_for(coro, timeout=TOOL_EXECUTION_TIMEOUT)

        try:
            import concurrent.futures
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

    # Phase 13: 출력 노드
    elif func_name == "output_gui":
        return _output_gui(params.get("content", ""), params, project_path)
    elif func_name == "output_file":
        return _output_file(params.get("path", ""), params, project_path)
    elif func_name == "output_open":
        return _output_open(params.get("path", ""), params, project_path)
    elif func_name == "output_clipboard":
        return _output_clipboard(params.get("content", ""), params)
    elif func_name == "output_download":
        return _output_download(params.get("url", ""), params, project_path)

    # Phase 17→19: user 노드 함수
    elif func_name == "ask_user_question":
        from system_tools import execute_ask_user_question
        return execute_ask_user_question(dict(params), project_path)

    elif func_name == "request_user_approval":
        from system_tools import execute_request_user_approval
        return execute_request_user_approval(dict(params), project_path)

    elif func_name == "todo_write":
        from system_tools import execute_todo_write
        return execute_todo_write(dict(params), project_path)

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
        return _execute_launcher_command(action, params)

    elif func_name == "list_switches":
        from api_system_ai import _execute_list_switches
        return _execute_list_switches(params)

    # World Pulse: 세계 상태 감각
    elif func_name in ("world_pulse", "world_trend", "world_refresh"):
        from world_pulse import execute_world_pulse
        action_name = func_name  # world_pulse, world_trend, world_refresh
        return execute_world_pulse(action_name, dict(params))

    # Phase 26: Goal 프로세스 관리
    elif func_name == "list_goals":
        return _goal_list(params, project_path)
    elif func_name == "get_goal_status":
        return _goal_status(params.get("goal_id", ""), params, project_path)
    elif func_name == "kill_goal":
        return _goal_kill(params.get("goal_id", ""), params, project_path)

    # Phase 26b: 시도 기록 (전략 전환 + 라운드 메모리)
    elif func_name == "log_attempt":
        return _log_attempt(params, project_path)
    elif func_name == "get_attempts":
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

    키워드로 적합한 노드/액션을 자동 탐색.
    "이 작업을 할 수 있는 노드가 뭐야?"를 해결.
    """
    from node_registry import discover, list_nodes, get_node, node_summary

    if not query:
        # 쿼리 없으면 전체 노드 요약 반환
        return node_summary()

    # discover 실행
    limit = params.get("limit", 10)
    results = discover(query, limit=limit)

    if not results:
        return {
            "query": query,
            "results": [],
            "message": f"'{query}'에 매칭되는 노드를 찾을 수 없습니다.",
            "total_nodes": len(list_nodes()),
        }

    return {
        "query": query,
        "results": results,
        "count": len(results),
        "best_match": results[0]["suggestion"],
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
    """에이전트에게 질문/위임 [others:ask]{agent_id: "투자/투자컨설팅"} (Phase 11)"""
    if not agent_id:
        return {"error": "agent_id가 필요합니다."}

    # "프로젝트/에이전트이름" 파싱
    parts = agent_id.split("/", 1)
    if len(parts) == 2:
        project_id, agent_name = parts
    else:
        agent_name = parts[0]
        project_id = Path(project_path).name

    message = params.get("message", params.get("query", ""))
    if not message:
        return {"error": "params.message가 필요합니다."}

    from system_tools import execute_call_agent
    env_path = os.environ.get("INDIEBIZ_BASE_PATH")
    base = Path(env_path) if env_path else Path(__file__).parent.parent
    target_project_path = str(base / "projects" / project_id)
    return execute_call_agent({"agent_id": agent_name, "message": message}, target_project_path)


def _agent_ask_sync(agent_id: str, params: dict, project_path: str) -> Any:
    """에이전트에게 동기 질문 — 응답을 기다려서 반환 (파이프라인용)

    비동기 agent_ask와 달리, 임시 AI 에이전트를 생성하여
    메시지를 처리하고 결과 텍스트를 직접 반환합니다.

    사용: [others:ask_sync]{agent_id: "프로젝트/에이전트", message: "분석해줘"}
    파이프라인: [self:rag_search]{query: "AI"} >> [others:ask_sync]{agent_id: "컨텐츠/컨텐츠", message: "요약해줘"}
    """
    if not agent_id:
        return {"error": "agent_id가 필요합니다."}

    # "프로젝트/에이전트이름" 파싱
    parts_split = agent_id.split("/", 1)
    if len(parts_split) == 2:
        project_id, agent_name = parts_split
    else:
        agent_name = parts_split[0]
        project_id = Path(project_path).name

    message = params.get("message", params.get("query", ""))
    if not message:
        return {"error": "params.message가 필요합니다."}

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


# === Phase 12: 가이드 해결 및 첨부 ===



# === Phase 12: 노드 타입 라우팅 ===

_nodes_cache: Optional[Dict] = None


def _load_nodes() -> Dict:
    """nodes: 섹션 로드 (캐싱)"""
    global _nodes_cache
    if _nodes_cache is not None:
        return _nodes_cache
    data = _load_nodes_config()
    _nodes_cache = data.get("nodes", {})
    return _nodes_cache


def _execute_node(node_type: str, tool_input: dict, project_path: str, agent_id: str) -> Any:
    """노드 타입별 실행 분기"""
    nodes = _load_nodes()
    node_config = nodes.get(node_type)
    if not node_config:
        return {"error": f"알 수 없는 노드: {node_type}", "available": list(nodes.keys())}

    config_type = node_config.get("type")
    if config_type == "info":
        return _execute_info_node(node_config, tool_input, project_path, agent_id)
    elif config_type == "store":
        return _execute_store_node(node_config, tool_input, project_path, agent_id)
    elif config_type == "exec":
        return _execute_exec_node(node_config, tool_input, project_path, agent_id)
    elif config_type == "output":
        return _execute_output_node(node_config, tool_input, project_path)
    return {"error": f"알 수 없는 노드 타입: {config_type}"}


def _execute_info_node(node_config, tool_input, project_path, agent_id):
    """info 타입 노드 실행 (레거시, 현재 미사용 - 7개 정보 노드가 informant로 통합됨)"""
    source = tool_input.get("source")
    if not source:
        sources = node_config.get("sources", {})
        return {
            "error": "source 파라미터가 필요합니다.",
            "sources": {k: v.get("description", "") for k, v in sources.items()},
        }

    source_config = node_config.get("sources", {}).get(source)
    if not source_config:
        return {
            "error": f"알 수 없는 source: {source}",
            "sources": list(node_config.get("sources", {}).keys()),
        }

    action = tool_input.get("action")
    actions = source_config.get("actions", {})
    action_config = actions.get(action)
    if not action_config:
        return {
            "error": f"source '{source}'에 '{action}' 액션이 없습니다.",
            "actions": list(actions.keys()),
        }

    params = tool_input.get("params", {})
    return _route_by_config(action_config, params, source, action,
                            project_path, agent_id)


def _execute_store_node(node_config, tool_input, project_path, agent_id):
    """store 노드 실행: ibl_store(store='health', action='summary')"""
    store = tool_input.get("store")
    if not store:
        stores = node_config.get("stores", {})
        return {
            "error": "store 파라미터가 필요합니다.",
            "stores": {k: v.get("description", "") for k, v in stores.items()},
        }

    store_config = node_config.get("stores", {}).get(store)
    if not store_config:
        return {
            "error": f"알 수 없는 store: {store}",
            "stores": list(node_config.get("stores", {}).keys()),
        }

    action = tool_input.get("action")
    actions = store_config.get("actions", {})
    action_config = actions.get(action)
    if not action_config:
        return {
            "error": f"store '{store}'에 '{action}' 액션이 없습니다.",
            "actions": list(actions.keys()),
        }

    params = tool_input.get("params", {})
    router = action_config.get("router")
    if router == "driver":
        driver_type = action_config.get("driver", "sqlite")
        dn = action_config.get("driver_node")  # Phase 22: 하위 핸들러 지정
        return _route_driver(driver_type, store, action, params, project_path, driver_node=dn)

    return _route_by_config(action_config, params, store, action,
                            project_path, agent_id)


def _execute_exec_node(node_config, tool_input, project_path, agent_id):
    """exec 노드 실행: ibl_exec(action='python')"""
    action = tool_input.get("action")
    if not action:
        executors = list(node_config.get("executors", {}).keys())
        programs = list(node_config.get("programs", {}).keys())
        return {
            "error": "action 파라미터가 필요합니다.",
            "executors": executors,
            "programs": programs,
        }

    params = tool_input.get("params", {})

    # executors (python, node, shell)
    executors = node_config.get("executors", {})
    if action in executors:
        config = executors[action]
        return _route_by_config(config, params, "exec", action,
                                project_path, agent_id)

    # programs (remotion, video, slides, image, music)
    programs = node_config.get("programs", {})
    if action in programs:
        config = programs[action]
        return _route_by_config(config, params, "exec", action,
                                project_path, agent_id)

    available = list(executors.keys()) + list(programs.keys())
    return {"error": f"알 수 없는 exec 액션: {action}", "available": available}


# ============================================================
# Phase 13: 출력 노드 함수들
# ============================================================

def _output_gui(content: str, params: dict, project_path: str) -> Any:
    """UI에 결과를 HTML/카드/테이블로 표시"""
    content = params.get("content", content or "")
    format_type = params.get("format", "html")  # html, card, table, markdown
    title = params.get("title", "결과")

    result = {
        "type": "gui_output",
        "title": title,
        "format": format_type,
        "content": content,
    }

    # WebSocket으로 프론트엔드에 전송
    try:
        from websocket_manager import broadcast_message
        import asyncio
        msg = {"type": "ibl_output", "data": result}
        loop = asyncio.get_event_loop()
        if loop.is_running():
            asyncio.ensure_future(broadcast_message(msg))
        else:
            loop.run_until_complete(broadcast_message(msg))
    except Exception:
        pass

    return {"ok": True, "output": result}


def _output_file(path: str, params: dict, project_path: str) -> Any:
    """결과를 파일로 저장"""
    if not path:
        return {"error": "path(파일 경로)가 필요합니다."}

    content = params.get("content", "")
    encoding = params.get("encoding", "utf-8")

    # 상대경로면 outputs/ 폴더 기준
    file_path = path
    if not os.path.isabs(file_path):
        base = os.environ.get("INDIEBIZ_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        outputs_dir = os.path.join(base, "outputs")
        os.makedirs(outputs_dir, exist_ok=True)
        file_path = os.path.join(outputs_dir, file_path)

    os.makedirs(os.path.dirname(file_path), exist_ok=True)

    with open(file_path, "w", encoding=encoding) as f:
        if isinstance(content, (dict, list)):
            json.dump(content, f, ensure_ascii=False, indent=2)
        else:
            f.write(str(content))

    return {"ok": True, "path": file_path, "size": os.path.getsize(file_path)}


def _extract_path_from_prev(prev_result: str) -> Optional[str]:
    """_prev_result JSON에서 파일 경로 또는 URL을 추출

    1차: 명시적 키 매칭 (file, path, url 등)
    2차: 값 패턴 매칭 (*_path, *_file, *_url 키 또는 http/파일경로 값)
    """
    if not prev_result:
        return None
    try:
        data = json.loads(prev_result)
        if isinstance(data, dict):
            # 1차: 명시적 키 매칭 (우선순위순)
            for key in ("file", "path", "url", "opened",
                        "output_file", "output_path", "report_path",
                        "html_path", "file_path", "filepath"):
                val = data.get(key)
                if val and isinstance(val, str):
                    return val
            # 2차: *_path, *_file, *_url 패턴 키 검색
            for key, val in data.items():
                if isinstance(val, str) and val and (
                    key.endswith("_path") or key.endswith("_file") or key.endswith("_url")
                ):
                    return val
            # 3차: 값이 http:// 또는 / 로 시작하는 첫 번째 문자열
            for key, val in data.items():
                if isinstance(val, str) and val and (
                    val.startswith("http://") or val.startswith("https://") or
                    (val.startswith("/") and "." in val.split("/")[-1])
                ):
                    return val
    except (json.JSONDecodeError, TypeError):
        pass
    return None


def _output_open(path: str, params: dict, project_path: str = ".") -> Any:
    """URL을 브라우저로, 파일을 Finder로 열기

    파이프라인에서 사용 시: >> [self:open]
    _prev_result에서 file/path/url 필드를 자동 추출하여 열어준다.
    상대경로는 project_path 기준으로 절대경로로 자동 변환된다.
    """
    import subprocess
    import platform
    from pathlib import Path

    # 파이프라인 자동 추출: path가 비어있으면 _prev_result에서 경로 추출
    if not path and "_prev_result" in params:
        extracted = _extract_path_from_prev(params.get("_prev_result", ""))
        if extracted:
            path = extracted
        else:
            prev = params.get("_prev_result", "")
            return {"error": "열 대상을 찾을 수 없습니다. 이전 step이 file/path/url 키를 포함한 결과를 반환해야 합니다.",
                    "hint": "파이프라인: [도구]{...} >> [self:open] — 이전 도구가 경로/URL을 반환해야 동작합니다.",
                    "_prev_result_preview": prev[:300] if prev else "(empty)"}

    if not path:
        return {"error": "path가 필요합니다. URL 또는 파일 경로를 지정하세요."}

    if path.startswith("http://") or path.startswith("https://"):
        # URL → 브라우저
        if platform.system() == "Darwin":
            subprocess.Popen(["open", path])
        elif platform.system() == "Windows":
            subprocess.Popen(["start", path], shell=True)
        else:
            subprocess.Popen(["xdg-open", path])
        return {"ok": True, "opened": path, "type": "url"}
    else:
        # 상대경로 → 절대경로 변환 (project_path 기준)
        file_path = Path(path)
        if not file_path.is_absolute():
            file_path = (Path(project_path) / file_path).resolve()
        path = str(file_path)

        # 파일/폴더 → Finder/Explorer
        if platform.system() == "Darwin":
            subprocess.Popen(["open", path])
        elif platform.system() == "Windows":
            subprocess.Popen(["explorer", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return {"ok": True, "opened": path, "type": "file"}


def _output_clipboard(content: str, params: dict) -> Any:
    """결과를 클립보드에 복사"""
    content = params.get("content", content or "")
    if not content:
        return {"error": "복사할 내용이 없습니다."}

    import subprocess
    import platform

    text = str(content) if not isinstance(content, str) else content

    if platform.system() == "Darwin":
        p = subprocess.Popen(["pbcopy"], stdin=subprocess.PIPE)
        p.communicate(text.encode("utf-8"))
    elif platform.system() == "Windows":
        p = subprocess.Popen(["clip"], stdin=subprocess.PIPE)
        p.communicate(text.encode("utf-8"))
    else:
        try:
            p = subprocess.Popen(["xclip", "-selection", "clipboard"], stdin=subprocess.PIPE)
            p.communicate(text.encode("utf-8"))
        except FileNotFoundError:
            return {"error": "xclip이 설치되어 있지 않습니다."}

    return {"ok": True, "copied_length": len(text)}


def _output_download(url: str, params: dict, project_path: str) -> Any:
    """URL에서 파일 다운로드"""
    if not url:
        return {"error": "url(다운로드 URL)이 필요합니다."}

    import urllib.request
    from urllib.parse import urlparse

    filename = params.get("filename")
    if not filename:
        parsed = urlparse(url)
        filename = os.path.basename(parsed.path) or "download"

    save_dir = params.get("save_dir")
    if not save_dir:
        base = os.environ.get("INDIEBIZ_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        save_dir = os.path.join(base, "outputs")
    os.makedirs(save_dir, exist_ok=True)

    save_path = os.path.join(save_dir, filename)

    try:
        urllib.request.urlretrieve(url, save_path)
        return {"ok": True, "path": save_path, "size": os.path.getsize(save_path)}
    except Exception as e:
        return {"error": f"다운로드 실패: {str(e)}"}


def _execute_output_node(node_config, tool_input, project_path):
    """output 노드 실행: ibl_output(action='gui', params={...})
    Phase 19: output → orchestrator로 통합됨. 라우터 내부 구현은 유지."""
    action = tool_input.get("action")
    actions = node_config.get("actions", {})
    action_config = actions.get(action)
    if not action_config:
        return {
            "error": f"알 수 없는 output 액션: {action}",
            "available": list(actions.keys()),
        }

    func_name = action_config.get("func")
    params = tool_input.get("params", {})
    return _route_system(func_name, params, project_path)


def _route_by_config(action_config, params, node, action,
                     project_path, agent_id):
    """YAML 액션 설정 기반 통합 라우팅"""
    router = action_config.get("router")
    if router == "handler":
        mapped_tool = action_config.get("tool")
        return _route_handler(mapped_tool, params, project_path, agent_id)
    elif router == "driver":
        driver_type = action_config.get("driver", "sqlite")
        dn = action_config.get("driver_node")  # Phase 22: 하위 핸들러 지정
        return _route_driver(driver_type, node, action, params, project_path, driver_node=dn)
    return {"error": f"지원하지 않는 라우터: {router}"}


# ===========================================================================
# Phase 26: Goal 프로세스 관리 함수
# ===========================================================================

def _goal_list(params: dict, project_path: str = "") -> dict:
    """등록된 목표 목록 조회 (상태별 필터 가능)"""
    try:
        from conversation_db import ConversationDB
        db_path = str(Path(project_path) / "conversations.db")
        db = ConversationDB(db_path)
        status_filter = params.get("status")  # "active", "pending", "achieved" 등
        goals = db.list_goals(status=status_filter)

        if not goals:
            return {"success": True, "goals": [], "message": "등록된 목표가 없습니다."}

        result_goals = []
        for g in goals:
            result_goals.append({
                "goal_id": g["goal_id"],
                "name": g["name"],
                "status": g["status"],
                "current_round": g["current_round"],
                "max_rounds": g["max_rounds"],
                "cumulative_cost": g["cumulative_cost"],
                "max_cost": g["max_cost"],
                "every_frequency": g.get("every_frequency"),
                "deadline": g.get("deadline"),
                "created_at": g.get("created_at"),
            })

        return {
            "success": True,
            "goals": result_goals,
            "total": len(result_goals),
        }
    except Exception as e:
        return {"error": f"목표 목록 조회 실패: {str(e)}"}


def _goal_status(goal_id: str, params: dict, project_path: str = "") -> dict:
    """목표 상태 및 진행도 상세 조회"""
    if not goal_id:
        return {"error": "goal_id가 필요합니다."}

    try:
        from conversation_db import ConversationDB
        db_path = str(Path(project_path) / "conversations.db")
        db = ConversationDB(db_path)
        goal = db.get_goal(goal_id)

        if not goal:
            return {"error": f"목표를 찾을 수 없습니다: {goal_id}"}

        # rounds_data JSON 파싱
        rounds_data = []
        if goal.get("rounds_data"):
            try:
                rounds_data = json.loads(goal["rounds_data"])
            except (json.JSONDecodeError, TypeError):
                pass

        progress_pct = 0
        if goal["max_rounds"] > 0:
            progress_pct = round(goal["current_round"] / goal["max_rounds"] * 100, 1)

        cost_pct = 0
        if goal["max_cost"] > 0:
            cost_pct = round(goal["cumulative_cost"] / goal["max_cost"] * 100, 1)

        return {
            "success": True,
            "goal_id": goal["goal_id"],
            "name": goal["name"],
            "status": goal["status"],
            "success_condition": goal.get("success_condition"),
            "progress": {
                "current_round": goal["current_round"],
                "max_rounds": goal["max_rounds"],
                "progress_pct": progress_pct,
            },
            "cost": {
                "cumulative_cost": goal["cumulative_cost"],
                "max_cost": goal["max_cost"],
                "cost_pct": cost_pct,
            },
            "time": {
                "deadline": goal.get("deadline"),
                "every_frequency": goal.get("every_frequency"),
                "until_condition": goal.get("until_condition"),
                "within_duration": goal.get("within_duration"),
            },
            "rounds_history": rounds_data[-5:],  # 최근 5라운드만
            "created_at": goal.get("created_at"),
            "started_at": goal.get("started_at"),
            "completed_at": goal.get("completed_at"),
        }
    except Exception as e:
        return {"error": f"목표 상태 조회 실패: {str(e)}"}


def _goal_kill(goal_id: str, params: dict, project_path: str = "") -> dict:
    """실행 중인 목표 취소/중단"""
    if not goal_id:
        return {"error": "goal_id가 필요합니다."}

    try:
        from conversation_db import ConversationDB
        db_path = str(Path(project_path) / "conversations.db")
        db = ConversationDB(db_path)
        goal = db.get_goal(goal_id)

        if not goal:
            return {"error": f"목표를 찾을 수 없습니다: {goal_id}"}

        if goal["status"] in ("achieved", "expired", "limit_reached", "cancelled"):
            return {
                "success": False,
                "message": f"이미 종료된 목표입니다 (상태: {goal['status']})",
            }

        reason = params.get("reason", "사용자 요청에 의한 취소")
        db.update_goal_status(goal_id, "cancelled")

        return {
            "success": True,
            "goal_id": goal_id,
            "name": goal["name"],
            "previous_status": goal["status"],
            "new_status": "cancelled",
            "reason": reason,
            "rounds_completed": goal["current_round"],
            "total_cost": goal["cumulative_cost"],
        }
    except Exception as e:
        return {"error": f"목표 취소 실패: {str(e)}"}


# ============ Phase 26b: 시도 기록 (전략 전환 + 라운드 메모리) ============

def _log_attempt(params: dict, project_path: str = ".") -> dict:
    """
    시도 기록 저장

    필수 파라미터:
        task_id: 태스크 ID (같은 작업의 시도를 묶는 키)
        approach_category: 접근 범주 (예: "cv2_direct_import", "pillow_fallback", "ffmpeg_cli")
        description: 구체적으로 무엇을 시도했는지

    선택 파라미터:
        result: "success" 또는 "failure" (기본값: "failure")
        lesson: 이 시도에서 배운 점
    """
    task_id = params.get("task_id", "")
    category = params.get("approach_category", params.get("category", ""))
    description = params.get("description", "")

    if not task_id or not category or not description:
        return {"error": "task_id, approach_category, description은 필수입니다."}

    result = params.get("result", "failure")
    lesson = params.get("lesson")

    try:
        from conversation_db import ConversationDB
        from thread_context import get_current_agent_id
        db_path = str(Path(project_path) / "conversations.db")
        db = ConversationDB(db_path)
        agent_id = get_current_agent_id() or "unknown"

        round_num = db.log_attempt(
            task_id=task_id,
            agent_id=agent_id,
            approach_category=category,
            description=description,
            result=result,
            lesson=lesson
        )

        # 연속 실패 횟수 확인 → 전략 전환 경고
        consecutive = db.get_consecutive_failures(task_id, category)
        failed_categories = db.get_failed_categories(task_id, threshold=3)

        response = {
            "success": True,
            "round_num": round_num,
            "approach_category": category,
            "result": result,
        }

        if consecutive >= 3:
            response["warning"] = (
                f"⚠ '{category}' 접근이 {consecutive}회 연속 실패했습니다. "
                f"이 접근을 포기하고 근본적으로 다른 방법으로 전환하세요."
            )
            response["escalation_required"] = True

        if failed_categories:
            response["exhausted_categories"] = failed_categories
            all_cats = [row["approach_category"] for row in
                        db.get_attempt_history(task_id, limit=100)]
            unique_cats = set(all_cats)
            active_cats = unique_cats - set(failed_categories)
            if not active_cats:
                response["all_exhausted"] = True
                response["warning"] = (
                    "⚠ 시도한 모든 접근 범주가 실패 임계값을 넘었습니다. "
                    "사용자에게 상황을 보고하고 판단을 요청하세요."
                )

        return response
    except Exception as e:
        return {"error": f"시도 기록 실패: {str(e)}"}


def _get_attempts(params: dict, project_path: str = ".") -> dict:
    """
    시도 이력 조회

    파라미터:
        task_id: 태스크 ID (필수)
        limit: 최대 조회 수 (기본 20)
    """
    task_id = params.get("task_id", "")
    if not task_id:
        return {"error": "task_id가 필요합니다."}

    limit = int(params.get("limit", 20))

    try:
        from conversation_db import ConversationDB
        db_path = str(Path(project_path) / "conversations.db")
        db = ConversationDB(db_path)
        history = db.get_attempt_history(task_id, limit=limit)
        failed_categories = db.get_failed_categories(task_id, threshold=3)

        return {
            "task_id": task_id,
            "total_attempts": len(history),
            "attempts": history,
            "exhausted_categories": failed_categories,
            "summary": _summarize_attempts(history, failed_categories)
        }
    except Exception as e:
        return {"error": f"시도 이력 조회 실패: {str(e)}"}


def _summarize_attempts(history: list, failed_categories: list) -> str:
    """시도 이력 요약 생성"""
    if not history:
        return "시도 이력 없음"

    # 카테고리별 통계
    cat_stats = {}
    for h in history:
        cat = h.get("approach_category", "unknown")
        if cat not in cat_stats:
            cat_stats[cat] = {"success": 0, "failure": 0}
        if h.get("result") == "success":
            cat_stats[cat]["success"] += 1
        else:
            cat_stats[cat]["failure"] += 1

    parts = [f"총 {len(history)}회 시도:"]
    for cat, stats in cat_stats.items():
        status = "🚫 포기" if cat in failed_categories else "진행중"
        parts.append(
            f"  - {cat}: 성공 {stats['success']}회, 실패 {stats['failure']}회 [{status}]"
        )

    if failed_categories:
        parts.append(f"포기된 접근: {', '.join(failed_categories)}")

    return "\n".join(parts)


# ===========================================================================
# Phase 26: Goal/Condition/Case 실행 함수
# ===========================================================================

def _execute_goal_block(tool_input: dict, project_path: str, agent_id: str) -> dict:
    """
    Goal Block 실행 — agent_runner의 execute_goal에 위임

    파서가 생성한 _goal dict를 받아 agent_runner에 전달한다.
    활성 에이전트가 없으면 DB에 Goal만 생성한다.
    """
    from agent_runner import AgentRunner

    goal_name = tool_input.get("name", "unnamed")

    # 활성 에이전트 찾기
    agent = None
    for aid, a in AgentRunner.agent_registry.items():
        if a.running and (
            str(a.project_path) in str(project_path) or
            (agent_id and aid == agent_id)
        ):
            agent = a
            break

    if agent:
        return agent.execute_goal(tool_input)

    # 에이전트 없으면 DB에만 생성 (나중에 approve로 활성화)
    try:
        from conversation_db import ConversationDB
        import os, uuid
        from datetime import datetime

        db_path = os.path.join(project_path, "conversations.db")
        db = ConversationDB(db_path)
        goal_id = f"goal_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        db.create_goal(goal_id, tool_input)

        return {
            "goal_id": goal_id,
            "status": "pending",
            "name": goal_name,
            "message": f"Goal '{goal_name}' 생성됨. 활성 에이전트가 없어 대기 상태."
        }
    except Exception as e:
        return {"error": f"Goal 생성 실패: {str(e)}"}


def _execute_condition(tool_input: dict, project_path: str, agent_id: str) -> Any:
    """
    if/else 조건문 실행

    각 분기의 조건을 평가하고, 매칭되는 분기의 action을 실행한다.
    """
    branches = tool_input.get("branches", [])

    for branch in branches:
        condition = branch.get("condition")
        action = branch.get("action")

        if condition is None:
            # else 분기
            if action:
                return execute_ibl(action, project_path, agent_id)
            return {"message": "else 분기 실행 (action 없음)"}

        # 조건 평가: sense 노드 실행
        try:
            sense_result = _evaluate_sense_condition(condition, project_path, agent_id)
            if sense_result:
                if action:
                    return execute_ibl(action, project_path, agent_id)
                return {"message": f"조건 충족: {condition}"}
        except Exception as e:
            continue  # 조건 평가 실패 시 다음 분기로

    return {"message": "모든 조건 불일치, 실행할 분기 없음"}


def _execute_case(tool_input: dict, project_path: str, agent_id: str) -> Any:
    """
    case문 실행

    source에서 sense 값을 가져온 후 분기를 선택하여 action 실행.
    """
    from goal_evaluator import select_case_branch

    source = tool_input.get("source", "")
    branches = tool_input.get("branches", [])
    default = tool_input.get("default")

    # source에서 sense 값 가져오기
    sense_value = _get_sense_value(source, project_path, agent_id)

    if sense_value is not None:
        action = select_case_branch(sense_value, branches, default)
    else:
        action = default

    if action:
        return execute_ibl(action, project_path, agent_id)

    return {"message": f"case문 실행 완료 (source={source}, value={sense_value})"}


def _evaluate_sense_condition(condition: str, project_path: str, agent_id: str) -> bool:
    """
    조건 표현식에서 sense 노드 실행 후 비교

    Args:
        condition: "sense:kospi < 2400" 형태

    Returns:
        조건 충족 여부
    """
    import re

    # sense 참조 추출
    match = re.match(r'(sense:\w+)', condition)
    if not match:
        return False

    sense_ref = match.group(1)
    sense_value = _get_sense_value(sense_ref, project_path, agent_id)

    if sense_value is None:
        return False

    # 비교 연산자 추출
    op_match = re.search(r'(==|!=|>=|<=|>|<)\s*(.+)$', condition)
    if not op_match:
        return bool(sense_value)

    op = op_match.group(1)
    compare_raw = op_match.group(2).strip().strip("'\"")

    try:
        sv = float(sense_value)
        cv = float(compare_raw)
        if op == "==": return sv == cv
        if op == "!=": return sv != cv
        if op == ">":  return sv > cv
        if op == ">=": return sv >= cv
        if op == "<":  return sv < cv
        if op == "<=": return sv <= cv
    except (ValueError, TypeError):
        ss = str(sense_value)
        if op == "==": return ss == compare_raw
        if op == "!=": return ss != compare_raw

    return False


def _get_sense_value(source: str, project_path: str, agent_id: str) -> Any:
    """
    sense 참조 (예: "sense:kospi")에서 실제 값 가져오기
    """
    parts = source.split(":")
    if len(parts) != 2:
        return None

    node, action = parts[0], parts[1]

    try:
        step = {"_node": node, "action": action, "params": {}}
        result = execute_ibl(step, project_path, agent_id)

        if isinstance(result, dict):
            return result.get("value", result.get("result", str(result)))
        return result
    except Exception:
        return None
