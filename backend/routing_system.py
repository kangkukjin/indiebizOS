"""routing_system.py — 시스템 라우터의 인지 능력 구현 (2026-08-05 감사 ⑦ 후반부).

왜 이 모듈인가: ibl_routing(언어층)의 `_route_system` 이 인지층(system_ai_*·
system_tools·body_ask·world_pulse·switch_runner·ai_agent…)을 14간선으로 직참조해
백엔드 매듭의 심장이었다. 라우터는 이름을 능력 테이블에서 찾을 뿐, **구현은 인지층의
것** — 여기로 이동하고, 조립 루트(boot_common.wire_local_subsystems)가 register_all()
로 테이블을 채운다. 파서 쌍(register_parse)·채팅 스트림 슬롯과 같은 의존 역전 패턴.

행동 불변 원칙: 각 능력 함수의 지연 import 는 옛 ibl_routing 자리 그대로다 —
없는 몸(폰 blocklist 등)에서는 옛날과 똑같이 호출 시점에 같은 에러가 난다.
"""

import json
import os
from pathlib import Path
from typing import Any


# === 위임 기계 — ibl_routing 에서 verbatim 이동 ===

def _delegate_unified(params: dict, project_path: str) -> Any:
    """위임 통합 디스패처 — mode(async/sync/workflow) × scope(same/cross/system)."""
    mode = (params.get("mode") or "async").lower()
    scope = (params.get("scope") or "same").lower()

    if scope == "system":
        # 시스템 AI(자율주행 top-level)에게 자연어 의도를 fire-and-forget 위임.
        # 프로젝트 에이전트 레지스트리 밖의 자율주행이 대상 — 앱 "생성" 버튼처럼
        # "이거 알아서 해줘"를 넘길 때. report-viewer 가 파이썬 send_message 를 직접
        # 때렸던 그 능력의 일반 어휘화(scope 차원 확장, 새 액션 아님).
        message = params.get("message", params.get("query", ""))
        if not message:
            return {"error": "message 파라미터가 필요합니다. 예: {scope: \"system\", message: \"AI 동향 보고서 써줘\"}"}
        try:
            from system_ai_runner import SystemAIRunner
            SystemAIRunner.send_message(content=message,
                                        from_agent=params.get("from_agent") or "앱")
        except Exception as e:  # noqa: BLE001 — 큐잉 실패는 그대로 보고
            return {"error": f"시스템 AI 위임 실패: {e}"}
        return {"success": True, "queued": True, "target": "시스템 AI",
                "message": "시스템 AI에 요청을 전달했습니다. 완료되면 결과를 확인하세요."}

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


def _agent_info(agent_id: str) -> Any:
    """에이전트 상세 정보 [others:info]{agent_id: "투자/투자컨설팅"} (Phase 11)"""
    from node_registry import list_nodes
    nodes = list_nodes(include_agents=True)
    for n in nodes:
        if n["type"] == "agent" and n["id"] == agent_id:
            return n
    return {"error": f"에이전트 '{agent_id}'을 찾을 수 없습니다."}


# === 능력 래퍼 — 지연 import 를 옛 자리 그대로 유지(행동 불변) ===

def _cap_send_notification(params: dict, project_path: str) -> Any:
    from system_tools import execute_send_notification
    return execute_send_notification(dict(params), project_path)


def _cap_ask_body(params: dict) -> Any:
    from body_ask import ask_peer
    return ask_peer(dict(params))


def _cap_list_project_agents(params: dict) -> Any:
    from system_ai_tools import _execute_list_project_agents
    return _execute_list_project_agents(params)


def _cap_call_project_agent(params: dict) -> Any:
    from system_ai_tools import _execute_call_project_agent
    return _execute_call_project_agent(dict(params))


def _cap_schedule(params: dict, agent_id: str = None, project_path: str = None) -> Any:
    from system_ai_plans import _execute_schedule
    return _execute_schedule(params, agent_id=agent_id, project_path=project_path)


def _cap_manage_events(params: dict) -> Any:
    from system_ai_tools import _execute_manage_events
    return _execute_manage_events(params)


def _cap_list_switches(params: dict) -> Any:
    from system_ai_tools import _execute_list_switches
    return _execute_list_switches(params)


def _cap_run_switch(params: dict) -> Any:
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


def _cap_world_pulse(action_name: str, params: dict) -> Any:
    from world_pulse import execute_world_pulse
    return execute_world_pulse(action_name, params)


def _cap_self_check() -> Any:
    from world_pulse_health import run_daily_health_check
    return run_daily_health_check()


def _cap_reset_consciousness() -> None:
    from consciousness_agent import reset_consciousness_agent
    reset_consciousness_agent()


def register_all() -> None:
    """시스템 라우터 능력 테이블 주입 — 조립 루트(boot_common)가 부팅 시 1회 호출."""
    from ibl_routing import register_system_capabilities
    register_system_capabilities({
        "delegate": _delegate_unified,
        "agent_info": _agent_info,
        "send_notification": _cap_send_notification,
        "ask_body": _cap_ask_body,
        "list_project_agents": _cap_list_project_agents,
        "call_project_agent": _cap_call_project_agent,
        "schedule": _cap_schedule,
        "manage_events": _cap_manage_events,
        "list_switches": _cap_list_switches,
        "run_switch": _cap_run_switch,
        "world_pulse": _cap_world_pulse,
        "self_check": _cap_self_check,
        "reset_consciousness": _cap_reset_consciousness,
    })
