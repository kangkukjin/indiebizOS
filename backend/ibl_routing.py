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

    elif func_name == "show_calendar":
        from calendar_manager import get_calendar_manager
        cm = get_calendar_manager()
        year = params.get("year")
        month = params.get("month")
        file_path = cm.open_in_browser(
            year=int(year) if year else None,
            month=int(month) if month else None
        )
        return {"ok": True, "file": file_path}

    elif func_name == "launcher_command":
        # params.command에 실제 런처 명령이 들어옴 (open_project, open_system_ai 등)
        launcher_action = params.get("command", "")
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

    # World Pulse: 세계 상태 감각
    elif func_name in ("world_pulse", "world_trend", "world_refresh"):
        from world_pulse import execute_world_pulse
        action_name = func_name  # world_pulse, world_trend, world_refresh
        return execute_world_pulse(action_name, dict(params))

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
    파이프라인: [self:blog_search]{query: "AI"} >> [others:ask_sync]{agent_id: "컨텐츠/컨텐츠", message: "요약해줘"}
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
