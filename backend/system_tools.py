"""
system_tools.py - 시스템 도구 정의 및 실행
IndieBiz OS Core

에이전트 간 통신, 알림, 프로젝트 정보 등 시스템 수준 도구
"""

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any

from tool_loader import build_tool_package_map, load_tool_handler, get_all_tool_names


# ============ 시스템 도구 정의 ============

SYSTEM_TOOLS = [
    {
        "name": "call_agent",
        "description": "다른 에이전트를 호출하여 작업을 요청합니다. 같은 프로젝트 내 에이전트 간 협업에 사용합니다. 에이전트 이름 또는 ID로 호출할 수 있습니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "호출할 에이전트 이름 또는 ID (예: '내과', 'agent_001')"
                },
                "message": {
                    "type": "string",
                    "description": "에이전트에게 전달할 메시지/요청"
                }
            },
            "required": ["agent_id", "message"]
        }
    },
    {
        "name": "list_agents",
        "description": "현재 프로젝트에서 사용 가능한 에이전트 목록을 가져옵니다.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "send_notification",
        "description": "사용자에게 알림을 보냅니다.",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "알림 제목"
                },
                "message": {
                    "type": "string",
                    "description": "알림 내용"
                },
                "type": {
                    "type": "string",
                    "description": "알림 유형: info, success, warning, error. 기본: info"
                }
            },
            "required": ["title", "message"]
        }
    },
    {
        "name": "get_project_info",
        "description": "현재 프로젝트의 정보를 가져옵니다 (이름, 설명, 에이전트 목록 등).",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_my_tools",
        "description": "현재 에이전트에게 허용된 도구 목록을 조회합니다. 위임 전 자신이 가진 도구로 처리 가능한지 확인할 때 사용합니다.",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }
]

# 시스템 도구 이름 목록
SYSTEM_TOOL_NAMES = [t["name"] for t in SYSTEM_TOOLS]


def is_system_tool(tool_name: str) -> bool:
    """시스템 도구인지 확인"""
    return tool_name in SYSTEM_TOOL_NAMES


# ============ 시스템 도구 실행 ============

def execute_call_agent(tool_input: dict, project_path: str) -> str:
    """call_agent 도구 실행 - 에이전트 간 통신"""
    agent_id_or_name = tool_input.get("agent_id", "")
    message = tool_input.get("message", "")

    try:
        from agent_runner import AgentRunner
        from thread_context import (
            get_current_agent_id, get_current_agent_name,
            get_current_task_id, set_called_agent
        )
        from conversation_db import ConversationDB

        # call_agent 호출 플래그 설정 (자동 보고 스킵용)
        set_called_agent(True)

        # 프로젝트 ID 추출
        project_id = Path(project_path).name

        # 1. 실행 중인 에이전트 레지스트리에서 찾기
        target_runner = AgentRunner.get_agent_by_name(agent_id_or_name, project_id=project_id)
        if not target_runner:
            target_runner = AgentRunner.get_agent_by_id(agent_id_or_name, project_id=project_id)

        if target_runner:
            return _send_to_running_agent(target_runner, message, project_path)

        # 2. 레지스트리에 없으면 agents.yaml 확인
        return _check_agents_yaml(agent_id_or_name, project_path)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


def _send_to_running_agent(target_runner, message: str, project_path: str) -> str:
    """실행 중인 에이전트에게 메시지 전송"""
    from agent_runner import AgentRunner
    from thread_context import get_current_agent_name, get_current_task_id
    from conversation_db import ConversationDB

    target_id = target_runner.config.get("id")
    target_name = target_runner.config.get("name")

    # 발신자 정보
    current_agent_name = get_current_agent_name()
    from_agent = current_agent_name if current_agent_name else "system"

    # 태스크 처리
    current_task_id = get_current_task_id()
    new_task_id = None

    if current_task_id:
        # 태스크 태그 제거
        message = re.sub(r'\[task:[^\]]+\]\s*', '', message)

        # 자식 태스크 생성
        new_task_id = _create_child_task(current_task_id, target_name, message, project_path)

        # 메시지에 태스크 ID 추가
        task_for_message = new_task_id if new_task_id else current_task_id
        message = f"[task:{task_for_message}] {message}"

    # 메시지 전송
    success = AgentRunner.send_message(
        to_agent_id=target_runner.registry_key,
        message=message,
        from_agent=from_agent,
        task_id=new_task_id if new_task_id else current_task_id
    )

    if success:
        return json.dumps({
            "success": True,
            "message": f"'{target_name}'에게 메시지를 전송했습니다. 비동기로 처리됩니다.",
            "agent": target_name,
            "task_id": new_task_id if new_task_id else current_task_id,
            "async": True
        }, ensure_ascii=False)
    else:
        return json.dumps({
            "success": False,
            "error": f"메시지 전송 실패: {target_name}"
        }, ensure_ascii=False)


def _create_child_task(parent_task_id: str, target_name: str, message: str, project_path: str) -> str:
    """위임 시 자식 태스크 생성"""
    from conversation_db import ConversationDB
    from thread_context import get_current_agent_name

    try:
        db_path = Path(project_path) / "conversations.db"
        db = ConversationDB(str(db_path))
        parent_task = db.get_task(parent_task_id)

        if not parent_task:
            return None

        new_task_id = f"task_{uuid.uuid4().hex[:8]}"
        from_agent = get_current_agent_name() or "system"

        # 위임 컨텍스트 구성
        existing_context = _get_or_create_delegation_context(parent_task)
        existing_context['delegations'].append({
            'child_task_id': new_task_id,
            'delegated_to': target_name,
            'delegation_message': message,
            'delegation_time': datetime.now().isoformat()
        })

        delegation_context = json.dumps(existing_context, ensure_ascii=False)
        db.update_task_delegation(parent_task_id, delegation_context, increment_pending=True)

        # 자식 태스크 생성
        db.create_task(
            task_id=new_task_id,
            requester=parent_task.get('requester', ''),
            requester_channel=parent_task.get('requester_channel', 'gui'),
            original_request=parent_task.get('original_request', ''),
            delegated_to=target_name,
            parent_task_id=parent_task_id
        )

        print(f"   [call_agent] 자식 태스크 생성: {new_task_id} (parent: {parent_task_id})")
        print(f"   [call_agent] 위임: {from_agent} → {target_name}")

        return new_task_id

    except Exception as e:
        import traceback
        print(f"   [call_agent] 태스크 생성 실패: {e}")
        traceback.print_exc()
        return None


def _get_or_create_delegation_context(parent_task: dict) -> dict:
    """위임 컨텍스트 가져오기 또는 생성"""
    existing_context_str = parent_task.get('delegation_context')

    if existing_context_str:
        try:
            existing_context = json.loads(existing_context_str)
            if 'delegations' not in existing_context:
                existing_context = {
                    'original_request': existing_context.get('original_request', ''),
                    'requester': existing_context.get('requester', ''),
                    'delegations': [],
                    'responses': []
                }
            return existing_context
        except json.JSONDecodeError:
            pass

    return {
        'original_request': parent_task.get('original_request', ''),
        'requester': parent_task.get('requester', ''),
        'delegations': [],
        'responses': []
    }


def _check_agents_yaml(agent_id_or_name: str, project_path: str) -> str:
    """agents.yaml에서 에이전트 확인"""
    import yaml as yaml_lib
    from agent_runner import AgentRunner

    agents_yaml = Path(project_path) / "agents.yaml"
    if not agents_yaml.exists():
        return json.dumps({
            "success": False,
            "error": "에이전트 설정 파일(agents.yaml)을 찾을 수 없습니다."
        }, ensure_ascii=False)

    agents_data = yaml_lib.safe_load(agents_yaml.read_text(encoding='utf-8'))
    agents = agents_data.get("agents", [])

    # 이름 또는 ID로 에이전트 찾기
    target_agent = None
    for agent in agents:
        if agent.get("id") == agent_id_or_name or agent.get("name") == agent_id_or_name:
            target_agent = agent
            break

    if not target_agent:
        available_running = AgentRunner.get_all_agent_names()
        available_yaml = [f"{a.get('name')} (id: {a.get('id')})" for a in agents if a.get("active", True)]
        return json.dumps({
            "success": False,
            "error": f"에이전트를 찾을 수 없습니다: {agent_id_or_name}",
            "running_agents": available_running,
            "available_agents": available_yaml
        }, ensure_ascii=False)

    return json.dumps({
        "success": False,
        "error": f"에이전트 '{target_agent.get('name')}'가 실행 중이 아닙니다. 먼저 에이전트를 시작해주세요.",
        "agent": target_agent.get("name"),
        "agent_id": target_agent.get("id")
    }, ensure_ascii=False)


def execute_list_agents(tool_input: dict, project_path: str) -> str:
    """list_agents 도구 실행"""
    try:
        from agent_runner import AgentRunner
        import yaml as yaml_lib

        running_agents = AgentRunner.get_all_agents()
        running_ids = {a["id"] for a in running_agents}

        agents_yaml = Path(project_path) / "agents.yaml"
        if not agents_yaml.exists():
            return json.dumps({
                "success": True,
                "agents": running_agents,
                "running_count": len(running_agents)
            }, ensure_ascii=False)

        agents_data = yaml_lib.safe_load(agents_yaml.read_text(encoding='utf-8'))
        agents = agents_data.get("agents", [])

        agent_list = []
        for agent in agents:
            agent_id = agent.get("id")
            agent_list.append({
                "id": agent_id,
                "name": agent.get("name"),
                "type": agent.get("type", "internal"),
                "role_description": agent.get("role_description", ""),
                "active": agent.get("active", True),
                "running": agent_id in running_ids
            })

        return json.dumps({
            "success": True,
            "agents": agent_list,
            "running_count": len(running_agents)
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


def execute_send_notification(tool_input: dict, project_path: str) -> str:
    """send_notification 도구 실행"""
    title = tool_input.get("title", "")
    message = tool_input.get("message", "")
    noti_type = tool_input.get("type", "info")

    try:
        from notification_manager import get_notification_manager
        nm = get_notification_manager()
        notification = nm.create(title=title, message=message, type=noti_type)
        return json.dumps({"success": True, "notification_id": notification["id"]}, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


def execute_get_project_info(tool_input: dict, project_path: str) -> str:
    """get_project_info 도구 실행"""
    try:
        import yaml as yaml_lib

        project_json = Path(project_path) / "project.json"
        project_data = {}
        if project_json.exists():
            project_data = json.loads(project_json.read_text(encoding='utf-8'))

        agents_yaml = Path(project_path) / "agents.yaml"
        agents = []
        if agents_yaml.exists():
            agents_data = yaml_lib.safe_load(agents_yaml.read_text(encoding='utf-8'))
            agents = agents_data.get("agents", [])

        project_name = Path(project_path).name

        info = {
            "name": project_data.get("name", project_name),
            "description": project_data.get("description", ""),
            "agent_count": len(agents),
            "agents": [{"id": a.get("id"), "name": a.get("name"), "active": a.get("active", True)} for a in agents],
            "path": str(project_path)
        }

        return json.dumps({"success": True, "project": info}, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


def execute_get_my_tools(tool_input: dict, project_path: str) -> str:
    """get_my_tools 도구 실행"""
    try:
        from agent_runner import AgentRunner
        from thread_context import get_current_agent_id

        current_agent_id = get_current_agent_id()
        if not current_agent_id:
            return json.dumps({
                "success": False,
                "tools": [],
                "message": "현재 에이전트를 식별할 수 없습니다"
            }, ensure_ascii=False)

        runner = AgentRunner.agent_registry.get(current_agent_id)
        if not runner:
            return json.dumps({
                "success": False,
                "tools": [],
                "message": "에이전트 정보를 찾을 수 없습니다"
            }, ensure_ascii=False)

        allowed_tools = runner.config.get('allowed_tools', [])
        base_tools = SYSTEM_TOOL_NAMES

        if not allowed_tools:
            all_installed = get_all_tool_names()
            all_tools = list(base_tools) + all_installed
        else:
            all_tools = list(base_tools) + allowed_tools

        return json.dumps({
            "success": True,
            "tools": all_tools,
            "base_tools": base_tools,
            "allowed_tools": allowed_tools if allowed_tools else "all (제한 없음)",
            "message": f"기본 도구 {len(base_tools)}개 + 허용 도구 {len(allowed_tools) if allowed_tools else '전체'}개"
        }, ensure_ascii=False)

    except Exception as e:
        return json.dumps({
            "success": False,
            "tools": [],
            "message": f"에러 발생: {str(e)}"
        }, ensure_ascii=False)


# ============ 통합 도구 실행 함수 ============

def execute_tool(tool_name: str, tool_input: dict, project_path: str = ".") -> str:
    """
    도구 실행 (시스템 도구 + 동적 로딩)

    Args:
        tool_name: 도구 이름
        tool_input: 도구 입력
        project_path: 프로젝트 경로

    Returns:
        실행 결과 (JSON 문자열)
    """
    try:
        # 시스템 도구 처리
        if tool_name == "call_agent":
            return execute_call_agent(tool_input, project_path)
        elif tool_name == "list_agents":
            return execute_list_agents(tool_input, project_path)
        elif tool_name == "send_notification":
            return execute_send_notification(tool_input, project_path)
        elif tool_name == "get_project_info":
            return execute_get_project_info(tool_input, project_path)
        elif tool_name == "get_my_tools":
            return execute_get_my_tools(tool_input, project_path)

        # 동적 로딩된 도구 패키지에서 실행
        handler = load_tool_handler(tool_name)
        if handler and hasattr(handler, 'execute'):
            result = handler.execute(tool_name, tool_input, project_path)

            # 승인 필요 여부 확인
            if isinstance(result, str) and result.startswith("__REQUIRES_APPROVAL__:"):
                command = result.replace("__REQUIRES_APPROVAL__:", "")
                return json.dumps({
                    "requires_approval": True,
                    "command": command,
                    "message": f"⚠️ 위험한 명령어가 감지되었습니다:\n\n`{command}`\n\n이 명령어를 실행하려면 '승인' 또는 'yes'라고 답해주세요."
                }, ensure_ascii=False)

            return result
        else:
            return json.dumps({"success": False, "error": f"알 수 없는 도구: {tool_name}"}, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
