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
        "name": "request_user_approval",
        "description": """사용자 승인을 요청합니다.

## 사용 시점
- 파일 삭제, 시스템 설정 변경 등 위험한 작업 전
- 외부 서비스에 데이터 전송 전
- 비용이 발생할 수 있는 작업 전

## 중요 규칙
- 하나의 작업 요청에 대해 한 번만 호출
- 승인 후 모든 단계를 완료하고 결과 보고
- 같은 작업에 두 번 이상 호출 금지

## 사용하지 않을 때
- 일반적인 파일 읽기/쓰기
- 정보 조회
- 안전한 도구 실행""",
        "input_schema": {
            "type": "object",
            "properties": {
                "action_type": {
                    "type": "string",
                    "description": "수행하려는 작업 유형 (예: 파일 삭제, 패키지 설치, 시스템 설정 변경)"
                },
                "description": {
                    "type": "string",
                    "description": "수행하려는 작업에 대한 상세 설명"
                },
                "affected_items": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "영향받는 파일, 패키지 등의 목록"
                }
            },
            "required": ["action_type", "description"]
        }
    },
    {
        "name": "call_agent",
        "description": """다른 에이전트에게 작업을 위임합니다 (비동기).

## 위임 흐름
1. call_agent 호출 → 대상 에이전트에게 메시지 전송
2. 대상 에이전트가 작업 수행 (비동기)
3. 완료 시 자동으로 결과가 당신에게 보고됨
4. 결과를 받아 최종 처리 후 사용자에게 응답

## 사용 시점
- 다른 전문 분야의 에이전트가 필요할 때
- 자신의 도구로 처리할 수 없는 작업일 때
- 병렬로 여러 작업을 진행해야 할 때

## 사용 전 확인
1. list_agents로 사용 가능한 에이전트 확인
2. get_my_tools로 자신의 도구 확인 (직접 처리 가능한지)

## 금지 사항
- 자기 자신에게 위임 금지
- 에이전트가 1명뿐이면 위임 불가 (직접 처리)
- 무한 위임 체인 금지

## 병렬 위임
여러 에이전트에게 동시 위임 가능. 모든 응답이 도착하면 통합 결과 수신.

## 주의
call_agent 호출 후 바로 응답하지 마세요. 결과 보고가 도착할 때까지 기다렸다가 최종 응답.""",
        "input_schema": {
            "type": "object",
            "properties": {
                "agent_id": {
                    "type": "string",
                    "description": "호출할 에이전트 이름 또는 ID (예: '내과', 'agent_001')"
                },
                "message": {
                    "type": "string",
                    "description": "에이전트에게 전달할 요청 내용. 명확하고 구체적으로 작성."
                }
            },
            "required": ["agent_id", "message"]
        }
    },
    {
        "name": "list_agents",
        "description": """현재 프로젝트의 에이전트 목록을 조회합니다.

## 반환 정보
- id: 에이전트 ID
- name: 에이전트 이름
- role_description: 역할 설명
- active: 활성화 여부
- running: 현재 실행 중 여부

## 사용 시점
- call_agent 전 적합한 대상 확인
- 프로젝트 내 협업 가능한 에이전트 파악
- 실행 중인 에이전트 확인

## 주의
- running=false인 에이전트는 호출 불가
- 위임 전 반드시 확인 권장""",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "send_notification",
        "description": """사용자에게 알림을 보냅니다.

## 알림 유형
- info: 일반 정보 (기본값)
- success: 성공 메시지 (녹색)
- warning: 주의 메시지 (노란색)
- error: 오류 메시지 (빨간색)

## 사용 시점
- 장시간 작업 완료 알림
- 중요한 이벤트 발생 시
- 스케줄 작업 결과 보고
- 오류/경고 상황 알림

## 주의
- 일반적인 응답은 알림 대신 직접 메시지로
- 너무 빈번한 알림은 피할 것""",
        "input_schema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "알림 제목 (간결하게)"
                },
                "message": {
                    "type": "string",
                    "description": "알림 본문 내용"
                },
                "type": {
                    "type": "string",
                    "description": "알림 유형: info, success, warning, error (기본: info)"
                }
            },
            "required": ["title", "message"]
        }
    },
    {
        "name": "get_project_info",
        "description": """현재 프로젝트의 정보를 조회합니다.

## 반환 정보
- name: 프로젝트 이름
- description: 프로젝트 설명
- agent_count: 에이전트 수
- agents: 에이전트 목록 (id, name, active)
- path: 프로젝트 경로

## 사용 시점
- 프로젝트 구조 파악
- 협업 가능한 에이전트 확인
- 프로젝트 컨텍스트 이해""",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "get_my_tools",
        "description": """현재 에이전트에게 허용된 도구 목록을 조회합니다.

## 반환 정보
- tools: 사용 가능한 전체 도구 목록
- base_tools: 시스템 기본 도구 (call_agent, list_agents 등)
- allowed_tools: 허용된 도구 패키지 도구들

## 사용 시점
- 위임 전 자가 처리 가능 여부 판단
- 자신의 역량 범위 확인
- 도구 사용 가능 여부 확인

## 위임 결정 기준
1. get_my_tools로 내 도구 확인
2. 필요한 작업이 내 도구로 가능하면 → 직접 처리
3. 내 도구로 불가능하면 → list_agents로 적합한 에이전트 찾아 위임""",
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
        # 에이전트 간 위임 메시지 DB 기록
        try:
            db = ConversationDB(str(Path(project_path) / "conversations.db"))
            from_agent_id = db.get_or_create_agent(from_agent, "ai_agent")
            to_agent_id = db.get_or_create_agent(target_name, "ai_agent")
            db.save_message(from_agent_id, to_agent_id, message, contact_type='delegation')
        except Exception as e:
            print(f"[call_agent] 위임 메시지 DB 기록 실패: {e}")

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
        # requester_channel은 "나에게 직접 위임한 부모가 누구인가"를 나타냄
        # 프로젝트 내부 에이전트 간 위임이므로 'internal'
        db.create_task(
            task_id=new_task_id,
            requester=from_agent,  # 나에게 위임한 에이전트
            requester_channel='internal',  # 프로젝트 내부 위임
            original_request=message,  # 부모가 나에게 보낸 위임 메시지
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
    """위임 컨텍스트 가져오기 또는 생성

    이전 위임 사이클이 완료된 경우:
    - completed 배열은 유지 (이전 작업 기록)
    - delegations, responses는 비움 (새 사이클용)

    Note:
        pending_delegations 카운터를 기준으로 완료 여부 판단 (Race Condition 방지)
        responses 배열 길이는 동시성 문제로 정확하지 않을 수 있음
    """
    existing_context_str = parent_task.get('delegation_context')
    pending = parent_task.get('pending_delegations', 0)

    if existing_context_str:
        try:
            existing_context = json.loads(existing_context_str)
            if 'delegations' not in existing_context:
                # 구 형식 → 새 형식으로 변환 (completed 유지)
                existing_context = {
                    'original_request': existing_context.get('original_request', ''),
                    'requester': existing_context.get('requester', ''),
                    'completed': existing_context.get('completed', []),
                    'delegations': [],
                    'responses': []
                }
                return existing_context

            # 이전 위임 사이클이 완료되었는지 확인
            # pending_delegations 카운터를 기준으로 판단 (DB에서 원자적으로 관리됨)
            delegations = existing_context.get('delegations', [])

            # pending_delegations == 0 이고 이전 위임이 있었으면 → 새 사이클 시작
            # 단, completed 배열은 유지!
            if len(delegations) > 0 and pending == 0:
                # 모든 응답이 도착함 → 새 위임 사이클 시작
                # delegations/responses만 초기화, completed는 유지
                print(f"   [위임 컨텍스트] 이전 사이클 완료 (pending=0, delegations={len(delegations)}) → 새 사이클 준비")
                completed = existing_context.get('completed', [])
                return {
                    'original_request': parent_task.get('original_request', ''),
                    'requester': parent_task.get('requester', ''),
                    'completed': completed,  # 이전 작업 기록 유지
                    'delegations': [],
                    'responses': []
                }

            return existing_context
        except json.JSONDecodeError:
            pass

    return {
        'original_request': parent_task.get('original_request', ''),
        'requester': parent_task.get('requester', ''),
        'completed': [],
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


def execute_get_my_tools(tool_input: dict, project_path: str, agent_id: str = None) -> str:
    """get_my_tools 도구 실행"""
    try:
        from agent_runner import AgentRunner
        from thread_context import get_current_registry_key, get_current_project_id

        # 1. thread_context에서 시도
        registry_key = get_current_registry_key()

        # 2. thread_context 실패 시 agent_id + project_path로 구성
        if not registry_key and agent_id:
            # project_path에서 project_id 추출 (/path/to/projects/홍보 -> 홍보)
            project_id = get_current_project_id()
            if not project_id and project_path:
                from pathlib import Path
                project_id = Path(project_path).name
            registry_key = f"{project_id}:{agent_id}" if project_id else agent_id

        if not registry_key:
            return json.dumps({
                "success": False,
                "tools": [],
                "message": "현재 에이전트를 식별할 수 없습니다"
            }, ensure_ascii=False)

        runner = AgentRunner.agent_registry.get(registry_key)
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

def execute_request_user_approval(tool_input: dict, project_path: str) -> str:
    """request_user_approval 도구 실행 - 사용자 승인 요청"""
    action_type = tool_input.get("action_type", "작업")
    description = tool_input.get("description", "")
    affected_items = tool_input.get("affected_items", [])

    result_parts = [
        "🔔 **승인 요청**",
        f"**작업 유형**: {action_type}",
        f"**설명**: {description}"
    ]
    if affected_items:
        result_parts.append(f"**영향받는 항목**: {', '.join(affected_items)}")
    result_parts.append("\n진행하시려면 '승인' 또는 '진행해'라고 답해주세요.")

    # 특수 마커 추가 - 도구 호출 루프에서 이를 감지하여 중단
    return "[[APPROVAL_REQUESTED]]" + "\n".join(result_parts)


def execute_tool(tool_name: str, tool_input: dict, project_path: str = ".", agent_id: str = None) -> str:
    """
    도구 실행 (시스템 도구 + 동적 로딩)

    Args:
        tool_name: 도구 이름
        tool_input: 도구 입력
        project_path: 프로젝트 경로
        agent_id: 에이전트 ID (에이전트별 상태 저장용)

    Returns:
        실행 결과 (JSON 문자열)
    """
    try:
        # 승인 요청 도구 (가장 먼저 처리)
        if tool_name == "request_user_approval":
            return execute_request_user_approval(tool_input, project_path)

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
            return execute_get_my_tools(tool_input, project_path, agent_id)

        # 동적 로딩된 도구 패키지에서 실행
        handler = load_tool_handler(tool_name)
        if handler and hasattr(handler, 'execute'):
            # handler.execute의 시그니처에 따라 agent_id 전달
            import inspect
            sig = inspect.signature(handler.execute)
            if 'agent_id' in sig.parameters:
                result = handler.execute(tool_name, tool_input, project_path, agent_id)
            else:
                result = handler.execute(tool_name, tool_input, project_path)

            # 승인 필요 여부 확인
            if isinstance(result, str) and result.startswith("__REQUIRES_APPROVAL__:"):
                command = result.replace("__REQUIRES_APPROVAL__:", "")
                return json.dumps({
                    "requires_approval": True,
                    "command": command,
                    "message": f"⚠️ 위험한 명령어가 감지되었습니다:\n\n`{command}`\n\n이 명령어를 실행하려면 '승인' 또는 'yes'라고 답해주세요."
                }, ensure_ascii=False)

            # 지도 데이터가 있으면 [MAP:...] 형식으로 변환하여 추가
            if isinstance(result, str):
                try:
                    result_data = json.loads(result)
                    if isinstance(result_data, dict) and "map_data" in result_data:
                        map_data = result_data["map_data"]
                        map_tag = f"\n\n[MAP:{json.dumps(map_data, ensure_ascii=False)}]"
                        # map_data 필드 제거 (중복 방지)
                        del result_data["map_data"]
                        result = json.dumps(result_data, ensure_ascii=False, indent=2) + map_tag
                except (json.JSONDecodeError, TypeError):
                    pass

            return result
        else:
            return json.dumps({"success": False, "error": f"알 수 없는 도구: {tool_name}"}, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)
