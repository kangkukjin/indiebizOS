"""
api_system_ai.py - 시스템 AI 대화 API
IndieBiz OS Core

시스템 AI는 IndieBiz의 관리자이자 안내자입니다:
- 첫 실행 시 사용법 안내
- 도구 패키지 분석, 설치, 제거
- 에이전트 생성, 수정, 삭제 도움
- 오류 진단 및 해결

**통합 아키텍처**: AIAgent 클래스와 providers/ 모듈을 재사용하여
프로젝트 에이전트와 동일한 스트리밍/도구 실행 로직을 공유합니다.
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional, List, Generator, Callable
from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

# 메모리 관련
from system_ai_memory import (
    load_user_profile,
    save_conversation,
    get_recent_conversations,
    get_memory_context,
    save_memory,
    get_memories
)
# 시스템 문서 관련
from system_docs import (
    read_doc,
    init_all_docs
)
# 도구 로딩
from system_ai import (
    SYSTEM_AI_DEFAULT_PACKAGES,
    load_tools_from_packages,
    execute_system_tool as execute_system_ai_tool
)
# 통합: AIAgent 클래스 사용
from ai_agent import AIAgent
# 통합: 프롬프트 빌더 사용
from prompt_builder import build_system_ai_prompt

router = APIRouter()

# 경로 설정
BACKEND_PATH = Path(__file__).parent
from runtime_utils import get_base_path as _get_base_path
DATA_PATH = _get_base_path() / "data"
SYSTEM_AI_CONFIG_PATH = DATA_PATH / "system_ai_config.json"


# ============ 설정 및 캐시 ============

def load_system_ai_config() -> dict:
    """시스템 AI 설정 로드"""
    if SYSTEM_AI_CONFIG_PATH.exists():
        with open(SYSTEM_AI_CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "enabled": True,
        "provider": "anthropic",
        "model": "claude-sonnet-4-20250514",
        "apiKey": ""
    }


# ============ 도구 관련 ============

def _get_list_project_agents_tool() -> Dict:
    """list_project_agents 도구 정의"""
    return {
        "name": "list_project_agents",
        "description": """시스템 내 모든 프로젝트와 에이전트 목록을 조회합니다.

## 반환 정보
- project_id: 프로젝트 ID (폴더명)
- project_name: 프로젝트 이름
- agents: 에이전트 목록
  - id: 에이전트 ID
  - name: 에이전트 이름
  - role_description: 역할 설명 (전문 분야)

## 사용 시점
- call_project_agent 전 적합한 대상 확인
- 어떤 프로젝트/에이전트가 있는지 파악
- role_description을 보고 작업에 적합한 에이전트 선택

## 참고
- 에이전트가 실행 중이 아니어도 call_project_agent 시 자동 시작됨""",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }


def _get_call_project_agent_tool() -> Dict:
    """call_project_agent 도구 정의"""
    return {
        "name": "call_project_agent",
        "description": """프로젝트의 에이전트에게 작업을 위임합니다.

## 사용 전 확인
1. list_project_agents로 사용 가능한 에이전트 확인
2. role_description을 보고 적합한 에이전트 선택

## 사용 시나리오
- 특정 프로젝트의 전문 에이전트에게 작업을 맡기고 싶을 때
- 프로젝트별 도구나 컨텍스트가 필요한 작업일 때

## 주의사항
- 위임 후 결과를 기다려야 합니다
- 에이전트가 작업을 완료하면 자동으로 결과를 보고받습니다
- 에이전트가 실행 중이 아니면 자동으로 시작됩니다""",
        "input_schema": {
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "프로젝트 ID"
                },
                "agent_id": {
                    "type": "string",
                    "description": "에이전트 ID (agents.yaml의 id 필드)"
                },
                "message": {
                    "type": "string",
                    "description": "에이전트에게 전달할 작업 내용"
                }
            },
            "required": ["project_id", "agent_id", "message"]
        }
    }


def _get_manage_events_tool() -> Dict:
    """manage_events 통합 도구 정의 (캘린더 + 스케줄러)"""
    return {
        "name": "manage_events",
        "description": "캘린더 이벤트와 스케줄 작업을 통합 관리합니다 (기념일, 약속, 생일, 알림, 스케줄 등의 추가/수정/삭제/조회/토글). 첫 호출 시 가이드가 제공됩니다.",
        "guide_file": "calendar_guide.md",
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "description": "수행할 작업: list, add, update, delete, toggle, run_now"
                },
                "event_id": {
                    "type": "string",
                    "description": "이벤트 ID (update, delete, toggle, run_now 시 필수)"
                },
                "title": {
                    "type": "string",
                    "description": "이벤트 제목/이름 (add 시 필수)"
                },
                "date": {
                    "type": "string",
                    "description": "날짜 (YYYY-MM-DD 형식)"
                },
                "time": {
                    "type": "string",
                    "description": "시간 (HH:MM 형식)"
                },
                "type": {
                    "type": "string",
                    "description": "이벤트 타입: anniversary, birthday, appointment, reminder, schedule, other"
                },
                "repeat": {
                    "type": "string",
                    "description": "반복 유형: none, daily, weekly, monthly, yearly, interval"
                },
                "description": {
                    "type": "string",
                    "description": "이벤트 설명"
                },
                "event_action": {
                    "type": "string",
                    "description": "실행할 액션 (스케줄 작업일 때): run_switch, send_notification, test. null이면 순수 캘린더 이벤트"
                },
                "action_params": {
                    "type": "object",
                    "description": "액션 파라미터 (예: {switch_id: '...'} 또는 {message: '...', title: '...'})"
                },
                "weekdays": {
                    "type": "array",
                    "items": {"type": "integer"},
                    "description": "요일 목록 (weekly일 때, 0=월 ~ 6=일)"
                },
                "month": {
                    "type": "integer",
                    "description": "월 (yearly일 때 1-12, list 시 조회 월)"
                },
                "day": {
                    "type": "integer",
                    "description": "일 (yearly일 때 1-31)"
                },
                "interval_hours": {
                    "type": "integer",
                    "description": "반복 간격 시간 (interval일 때)"
                },
                "year": {
                    "type": "integer",
                    "description": "조회 연도 (list 시 선택)"
                },
                "enabled": {
                    "type": "boolean",
                    "description": "활성화 여부 (update 시)"
                }
            },
            "required": ["action"]
        }
    }


def _get_list_switches_tool() -> Dict:
    """list_switches 도구 정의"""
    return {
        "name": "list_switches",
        "description": """등록된 스위치 목록을 조회합니다. 스케줄에 스위치를 연결할 때 switch_id를 확인하는 용도입니다.

## 반환 정보
- id: 스위치 ID (스케줄 등록 시 사용)
- name: 스위치 이름
- command: 실행 명령어
- project: 연결된 프로젝트
- run_count: 총 실행 횟수
- last_run: 마지막 실행 시간""",
        "input_schema": {
            "type": "object",
            "properties": {},
            "required": []
        }
    }


def get_all_system_ai_tools() -> List[Dict]:
    """시스템 AI가 사용할 모든 도구 로드 (패키지 도구 + 위임 도구 + 메시징 도구 + 스케줄러 도구)

    NOTE: 시스템 AI는 일반 에이전트와 동일한 도구를 사용하며,
    추가로 call_project_agent 도구를 통해 프로젝트 에이전트에게 위임할 수 있습니다.
    """
    # 패키지에서 동적 로딩 (system_essentials, python-exec, nodejs 등)
    tools = load_tools_from_packages(SYSTEM_AI_DEFAULT_PACKAGES)

    # 위임 관련 도구 추가
    tools.append(_get_list_project_agents_tool())
    tools.append(_get_call_project_agent_tool())

    # 메시징 도구 추가 (Nostr DM, Gmail 전송)
    from system_ai import get_messaging_tools
    tools.extend(get_messaging_tools())

    # 통합 이벤트 관리 도구 추가
    tools.append(_get_manage_events_tool())
    tools.append(_get_list_switches_tool())

    return tools


def create_system_ai_agent(config: dict = None, user_profile: str = "") -> AIAgent:
    """시스템 AI용 AIAgent 인스턴스 생성

    **통합 아키텍처**: 프로젝트 에이전트와 동일한 AIAgent 클래스를 사용합니다.
    - 동일한 프로바이더 코드 (anthropic, openai, gemini, ollama)
    - 동일한 스트리밍 로직
    - 동일한 도구 실행 로직

    Args:
        config: 시스템 AI 설정 (None이면 자동 로드)
        user_profile: 사용자 프로필

    Returns:
        AIAgent 인스턴스
    """
    if config is None:
        config = load_system_ai_config()

    # AI 설정
    ai_config = {
        "provider": config.get("provider", "anthropic"),
        "model": config.get("model", "claude-sonnet-4-20250514"),
        "api_key": config.get("apiKey", "")
    }

    # 시스템 AI 전용 도구 로드
    tools = get_all_system_ai_tools()

    # Git 활성화 조건: run_command 도구가 있고 .git 폴더가 있을 때
    tool_names = [t.get("name") for t in tools]
    git_enabled = "run_command" in tool_names and (DATA_PATH / ".git").exists()

    # 시스템 프롬프트 생성 (공통 프롬프트 빌더 사용)
    system_prompt = build_system_ai_prompt(
        user_profile=user_profile,
        git_enabled=git_enabled
    )

    # AIAgent 인스턴스 생성 (시스템 AI 전용 도구 실행 함수 전달)
    agent = AIAgent(
        ai_config=ai_config,
        system_prompt=system_prompt,
        agent_name="시스템 AI",
        agent_id="system_ai",
        project_path=str(DATA_PATH),
        tools=tools,
        execute_tool_func=execute_system_tool
    )

    return agent


def process_system_ai_message(message: str, history: List[Dict] = None, images: List[Dict] = None) -> str:
    """시스템 AI 메시지 처리 (AIAgent 사용, 동기 모드)

    Args:
        message: 사용자 메시지
        history: 대화 히스토리
        images: 이미지 데이터

    Returns:
        AI 응답
    """
    user_profile = load_user_profile()

    agent = create_system_ai_agent(
        user_profile=user_profile
    )

    return agent.process_message_with_history(
        message_content=message,
        history=history,
        images=images
    )


def process_system_ai_message_stream(
    message: str,
    history: List[Dict] = None,
    images: List[Dict] = None,
    cancel_check: Callable = None
) -> Generator:
    """시스템 AI 메시지 처리 (AIAgent 사용, 스트리밍 모드)

    Args:
        message: 사용자 메시지
        history: 대화 히스토리
        images: 이미지 데이터
        cancel_check: 중단 여부를 확인하는 콜백 함수

    Yields:
        스트리밍 이벤트 딕셔너리
    """
    user_profile = load_user_profile()

    agent = create_system_ai_agent(
        user_profile=user_profile
    )

    yield from agent.process_message_stream(
        message_content=message,
        history=history,
        images=images,
        cancel_check=cancel_check
    )


def execute_system_tool(tool_name: str, tool_input: dict, work_dir: str = None, agent_id: str = None) -> str:
    """
    시스템 AI 도구 실행

    Args:
        tool_name: 도구 이름
        tool_input: 도구 입력
        work_dir: 작업 디렉토리
        agent_id: 에이전트 ID (프로바이더에서 전달, 시스템 AI는 "system_ai")
    """
    # 위임 관련 도구 처리
    if tool_name == "list_project_agents":
        return _execute_list_project_agents(tool_input)
    if tool_name == "call_project_agent":
        return _execute_call_project_agent(tool_input)

    # 메시징 도구 처리
    if tool_name == "send_nostr_message":
        from system_ai import execute_send_nostr_message
        return execute_send_nostr_message(tool_input)
    if tool_name == "send_gmail_message":
        from system_ai import execute_send_gmail_message
        return execute_send_gmail_message(tool_input)

    # 통합 이벤트 관리 도구 처리
    if tool_name == "manage_events":
        result = _execute_manage_events(tool_input)
        result = _inject_system_guide(tool_name, result, agent_id)
        return result
    if tool_name == "list_switches":
        return _execute_list_switches(tool_input)

    if work_dir is None:
        work_dir = str(DATA_PATH)
    return execute_system_ai_tool(tool_name, tool_input, work_dir)


def _execute_list_project_agents(tool_input: dict) -> str:
    """list_project_agents 도구 실행 - 모든 프로젝트/에이전트 목록 조회"""
    import yaml

    try:
        # projects 폴더 경로 (api.py의 BASE_PATH/projects와 동일)
        projects_path = _get_base_path() / "projects"
        result = []

        # 모든 프로젝트 폴더 순회
        for project_dir in projects_path.iterdir():
            if not project_dir.is_dir():
                continue
            if project_dir.name in ['trash', '.DS_Store']:
                continue

            agents_yaml = project_dir / "agents.yaml"
            if not agents_yaml.exists():
                continue

            try:
                data = yaml.safe_load(agents_yaml.read_text(encoding='utf-8'))
                agents = data.get("agents", [])

                agent_list = []
                for agent in agents:
                    if not agent.get("active", True):
                        continue  # 비활성화된 에이전트 제외
                    agent_list.append({
                        "id": agent.get("id"),
                        "name": agent.get("name"),
                        "role_description": agent.get("role_description", "")
                    })

                if agent_list:  # 에이전트가 있는 프로젝트만 포함
                    result.append({
                        "project_id": project_dir.name,
                        "project_name": project_dir.name,
                        "agents": agent_list
                    })
            except Exception as e:
                print(f"[list_project_agents] {project_dir.name} 파싱 오류: {e}")
                continue

        return json.dumps({
            "success": True,
            "projects": result,
            "total_projects": len(result),
            "total_agents": sum(len(p["agents"]) for p in result)
        }, ensure_ascii=False, indent=2)

    except Exception as e:
        return json.dumps({
            "success": False,
            "error": str(e)
        }, ensure_ascii=False)


def _execute_call_project_agent(tool_input: dict) -> str:
    """프로젝트 에이전트 호출 실행 (자동 시작 포함)"""
    import uuid
    import yaml
    from agent_runner import AgentRunner
    from thread_context import get_current_task_id, set_called_agent
    from system_ai_memory import get_task, update_task_delegation

    project_id = tool_input.get("project_id", "")
    agent_id = tool_input.get("agent_id", "")
    message = tool_input.get("message", "")

    if not project_id or not agent_id or not message:
        return "오류: project_id, agent_id, message가 모두 필요합니다."

    # 대상 에이전트 찾기 (실행 중인지 확인)
    registry_key = f"{project_id}:{agent_id}"
    target = AgentRunner.agent_registry.get(registry_key)

    # 에이전트가 실행 중이 아니면 프로젝트 전체 에이전트 시작
    if not target:
        print(f"[시스템 AI] 프로젝트 활성화: {project_id}")
        try:
            # 프로젝트 경로 직접 계산
            project_path = _get_base_path() / "projects" / project_id
            agents_yaml = project_path / "agents.yaml"

            if not agents_yaml.exists():
                return f"오류: 프로젝트 '{project_id}'를 찾을 수 없습니다."

            data = yaml.safe_load(agents_yaml.read_text(encoding='utf-8'))
            agents = data.get("agents", [])

            # 대상 에이전트 확인
            target_config = None
            for agent in agents:
                if agent.get("id") == agent_id:
                    target_config = agent
                    break

            if not target_config:
                return f"오류: 에이전트 '{agent_id}'를 찾을 수 없습니다."

            if not target_config.get("active", True):
                return f"오류: 에이전트 '{agent_id}'가 비활성화되어 있습니다."

            # 공통 설정 로드
            common_config = data.get("common", {})

            # 프로젝트의 모든 활성 에이전트 시작
            started_agents = []
            for agent_config in agents:
                if not agent_config.get("active", True):
                    continue

                aid = agent_config.get("id")
                rkey = f"{project_id}:{aid}"

                # 이미 실행 중이면 스킵
                if AgentRunner.agent_registry.get(rkey):
                    continue

                # 프로젝트 정보 추가 (api_agents.py 방식)
                agent_config["_project_path"] = str(project_path)
                agent_config["_project_id"] = project_id

                runner = AgentRunner(agent_config, common_config, delegated_from_system_ai=True)
                runner.start()
                started_agents.append(agent_config.get("name", aid))

            # 에이전트들이 준비될 때까지 잠시 대기
            import time
            time.sleep(0.5)

            if started_agents:
                print(f"[시스템 AI] 프로젝트 '{project_id}' 에이전트 시작 완료: {', '.join(started_agents)}")

            # 대상 에이전트 다시 조회
            target = AgentRunner.agent_registry.get(registry_key)
            if not target:
                return f"오류: 에이전트 '{agent_id}' 시작 실패"

        except Exception as e:
            return f"오류: 프로젝트 활성화 실패 - {str(e)}"

    # 현재 태스크 ID (시스템 AI의 태스크)
    parent_task_id = get_current_task_id()
    if not parent_task_id:
        return "오류: 현재 태스크 ID가 없습니다. (내부 오류)"

    # 자식 태스크 생성
    child_task_id = f"task_{uuid.uuid4().hex[:8]}"

    # 위임 컨텍스트 업데이트
    parent_task = get_task(parent_task_id)
    if parent_task:
        delegation_context_str = parent_task.get('delegation_context')
        if delegation_context_str:
            delegation_context = json.loads(delegation_context_str)
        else:
            delegation_context = {
                'original_request': parent_task.get('original_request', ''),
                'requester': parent_task.get('requester', 'user@gui'),
                'delegations': [],
                'responses': []
            }

        delegation_context['delegations'].append({
            'child_task_id': child_task_id,
            'delegated_to': target.config.get('name', agent_id),
            'delegation_message': message,
            'delegation_time': datetime.now().isoformat()
        })

        update_task_delegation(
            parent_task_id,
            json.dumps(delegation_context, ensure_ascii=False),
            increment_pending=True
        )

    # 프로젝트 에이전트의 DB에 자식 태스크 생성
    target.db.create_task(
        task_id=child_task_id,
        requester="system_ai",
        requester_channel="system_ai",
        original_request=message,
        delegated_to=target.config.get('name', agent_id),
        parent_task_id=parent_task_id
    )

    # 프로젝트 에이전트에게 메시지 전송
    msg_dict = {
        'content': f"[task:{child_task_id}] {message}",
        'from_agent': '시스템 AI',
        'task_id': child_task_id,
        'timestamp': datetime.now().isoformat()
    }

    with AgentRunner._lock:
        if registry_key not in AgentRunner.internal_messages:
            AgentRunner.internal_messages[registry_key] = []
        AgentRunner.internal_messages[registry_key].append(msg_dict)

    # call_agent 호출 플래그 설정
    set_called_agent(True)

    agent_name = target.config.get('name', agent_id)
    print(f"[시스템 AI] 위임: 시스템 AI → {agent_name} (task: {child_task_id})")

    return f"'{agent_name}'에게 작업을 위임했습니다. 결과를 기다리세요."


# 시스템 AI 도구 가이드 주입 추적
_system_guide_injected: set = set()

# 시스템 AI 도구의 가이드 파일 매핑 (도구명 → 파일명)
_SYSTEM_TOOL_GUIDES = {
    "manage_events": "calendar_guide.md",
}


def _inject_system_guide(tool_name: str, result: str, agent_id: str = None) -> str:
    """시스템 AI 도구용 가이드 주입 (첫 호출 시에만)

    tool_loader의 get_tool_guide()는 도구 패키지만 탐색하므로,
    시스템 AI 전용 도구는 system_docs 폴더에서 직접 가이드를 로드합니다.
    """
    global _system_guide_injected

    guide_key = f"{agent_id or 'system_ai'}:{tool_name}"
    if guide_key in _system_guide_injected:
        return result

    guide_filename = _SYSTEM_TOOL_GUIDES.get(tool_name)
    if not guide_filename:
        return result

    guide_path = DATA_PATH / "system_docs" / guide_filename
    if not guide_path.exists():
        return result

    try:
        guide_content = guide_path.read_text(encoding='utf-8')
        _system_guide_injected.add(guide_key)
        print(f"[시스템 AI 가이드 주입] {tool_name}")
        guide_header = f"=== {tool_name} 사용 가이드 ===\n{guide_content}\n{'=' * 40}\n\n"
        return guide_header + result
    except Exception as e:
        print(f"[시스템 AI 가이드 로드 실패] {guide_path}: {e}")
        return result


def _execute_manage_events(tool_input: dict) -> str:
    """manage_events 통합 도구 실행 (캘린더 + 스케줄러)"""
    from calendar_manager import get_calendar_manager

    action = tool_input.get("action", "")
    cm = get_calendar_manager()

    try:
        if action == "list":
            year = tool_input.get("year")
            month = tool_input.get("month")
            events = cm.list_events(year=year, month=month)
            if not events:
                return json.dumps({"success": True, "events": [], "message": "등록된 이벤트가 없습니다."}, ensure_ascii=False)
            return json.dumps({"success": True, "events": events, "count": len(events)}, ensure_ascii=False)

        elif action == "add":
            title = tool_input.get("title")
            if not title:
                return json.dumps({"success": False, "error": "title은 필수입니다."}, ensure_ascii=False)

            event_date = tool_input.get("date")
            event_action = tool_input.get("event_action")
            repeat = tool_input.get("repeat", "none")

            # 실행 이벤트 (스케줄)인 경우 date 없이도 허용 (daily, interval 등)
            if not event_date and not event_action:
                return json.dumps({"success": False, "error": "date는 필수입니다. (YYYY-MM-DD)"}, ensure_ascii=False)

            event = cm.add_event(
                title=title,
                event_date=event_date,
                event_type=tool_input.get("type", "schedule" if event_action else "other"),
                repeat=repeat,
                description=tool_input.get("description", ""),
                event_time=tool_input.get("time"),
                action=event_action,
                action_params=tool_input.get("action_params"),
                enabled=tool_input.get("enabled", True),
                weekdays=tool_input.get("weekdays"),
                month=tool_input.get("month"),
                day=tool_input.get("day"),
                interval_hours=tool_input.get("interval_hours"),
            )
            return json.dumps({"success": True, "event": event, "message": f"이벤트 '{title}' 추가됨"}, ensure_ascii=False)

        elif action == "update":
            event_id = tool_input.get("event_id")
            if not event_id:
                return json.dumps({"success": False, "error": "event_id는 필수입니다."}, ensure_ascii=False)

            updates = {}
            for key in ["title", "date", "time", "type", "repeat", "description",
                         "enabled", "weekdays", "month", "day", "interval_hours", "action_params"]:
                if key in tool_input:
                    updates[key] = tool_input[key]
            if "event_action" in tool_input:
                updates["action"] = tool_input["event_action"]

            if cm.update_event(event_id, **updates):
                return json.dumps({"success": True, "message": f"이벤트 '{event_id}' 수정됨"}, ensure_ascii=False)
            return json.dumps({"success": False, "error": f"이벤트 '{event_id}'를 찾을 수 없습니다."}, ensure_ascii=False)

        elif action == "delete":
            event_id = tool_input.get("event_id")
            if not event_id:
                return json.dumps({"success": False, "error": "event_id는 필수입니다."}, ensure_ascii=False)
            if cm.delete_event(event_id):
                return json.dumps({"success": True, "message": f"이벤트 '{event_id}' 삭제됨"}, ensure_ascii=False)
            return json.dumps({"success": False, "error": f"이벤트 '{event_id}'를 찾을 수 없습니다."}, ensure_ascii=False)

        elif action == "toggle":
            event_id = tool_input.get("event_id")
            if not event_id:
                return json.dumps({"success": False, "error": "event_id는 필수입니다."}, ensure_ascii=False)
            result = cm.toggle_task(event_id)
            if result is not None:
                status = "활성화" if result else "비활성화"
                return json.dumps({"success": True, "enabled": result, "message": f"이벤트 {status}됨"}, ensure_ascii=False)
            return json.dumps({"success": False, "error": f"이벤트 '{event_id}'를 찾을 수 없습니다."}, ensure_ascii=False)

        elif action == "run_now":
            event_id = tool_input.get("event_id")
            if not event_id:
                return json.dumps({"success": False, "error": "event_id는 필수입니다."}, ensure_ascii=False)
            if cm.run_task_now(event_id):
                return json.dumps({"success": True, "message": f"이벤트 '{event_id}' 즉시 실행 시작"}, ensure_ascii=False)
            return json.dumps({"success": False, "error": f"이벤트 '{event_id}'를 찾을 수 없습니다. (실행 가능한 이벤트만 run_now 가능)"}, ensure_ascii=False)

        else:
            return json.dumps({"success": False, "error": f"알 수 없는 action: {action}. list, add, update, delete, toggle, run_now 중 선택하세요."}, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


def _execute_list_switches(tool_input: dict) -> str:
    """list_switches 도구 실행"""
    try:
        from switch_manager import SwitchManager
        sm = SwitchManager()
        switches = sm.list_switches()

        result = []
        for sw in switches:
            if sw.get("in_trash"):
                continue
            result.append({
                "id": sw.get("id"),
                "name": sw.get("name"),
                "icon": sw.get("icon", ""),
                "command": sw.get("command", "")[:100],
                "project": sw.get("config", {}).get("projectId", ""),
                "agent": sw.get("config", {}).get("agent_name", ""),
                "run_count": sw.get("run_count", 0),
                "last_run": sw.get("last_run")
            })

        return json.dumps({"success": True, "switches": result, "count": len(result)}, ensure_ascii=False)

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


class ImageData(BaseModel):
    base64: str
    media_type: str


class ChatMessage(BaseModel):
    message: str
    context: Optional[Dict[str, Any]] = None
    images: Optional[List[ImageData]] = None


class ChatResponse(BaseModel):
    response: str
    timestamp: str
    provider: str
    model: str


def get_system_prompt(user_profile: str = "", git_enabled: bool = False) -> str:
    """시스템 AI의 시스템 프롬프트 (prompt_builder.py 사용)

    **통합**: 이제 공통 프롬프트 빌더를 사용합니다.
    - base_prompt_v2.md + (조건부 git) + 위임 프롬프트 + 개별역할 + 시스템메모
    """
    return build_system_ai_prompt(user_profile=user_profile, git_enabled=git_enabled)


def get_anthropic_tools():
    """Anthropic 형식의 도구 정의 (동적 로딩)"""
    all_tools = get_all_system_ai_tools()

    # Anthropic 형식으로 변환 (parameters -> input_schema)
    anthropic_tools = []
    for tool in all_tools:
        t = {
            "name": tool["name"],
            "description": tool.get("description", "")
        }
        # input_schema 또는 parameters 사용
        if "input_schema" in tool:
            t["input_schema"] = tool["input_schema"]
        elif "parameters" in tool:
            t["input_schema"] = tool["parameters"]
        else:
            t["input_schema"] = {"type": "object", "properties": {}}
        anthropic_tools.append(t)

    return anthropic_tools


# 시스템 문서 초기화 플래그
_docs_initialized = False


@router.post("/system-ai/chat", response_model=ChatResponse)
async def chat_with_system_ai(chat: ChatMessage):
    """
    시스템 AI와 대화

    **통합 아키텍처**: AIAgent 클래스를 사용하여 프로젝트 에이전트와
    동일한 프로바이더 코드를 공유합니다. 모든 프로바이더(Anthropic, OpenAI,
    Google, Ollama)가 자동으로 지원됩니다.

    **태스크 기반 처리**: 시스템 AI도 태스크를 생성하고 위임 체인을 지원합니다.
    - 위임이 없으면 → 즉시 응답
    - 위임이 있으면 → "위임 중" 응답, 결과는 WebSocket으로 전송
    """
    import uuid
    from thread_context import set_current_task_id, clear_current_task_id, did_call_agent, clear_called_agent
    from system_ai_memory import create_task as create_system_ai_task

    global _docs_initialized

    config = load_system_ai_config()

    if not config.get("enabled", True):
        raise HTTPException(status_code=400, detail="시스템 AI가 비활성화되어 있습니다.")

    api_key = config.get("apiKey", "")
    if not api_key:
        raise HTTPException(status_code=400, detail="API 키가 설정되지 않았습니다. 설정에서 API 키를 입력해주세요.")

    provider = config.get("provider", "anthropic")
    model = config.get("model", "claude-sonnet-4-20250514")

    # 시스템 문서 초기화 (서버 시작 후 최초 1회만)
    if not _docs_initialized:
        init_all_docs()
        _docs_initialized = True

    # 태스크 생성
    task_id = f"task_sysai_{uuid.uuid4().hex[:8]}"
    ws_client_id = chat.context.get("ws_client_id") if chat.context else None

    create_system_ai_task(
        task_id=task_id,
        requester="user@gui",
        requester_channel="gui",
        original_request=chat.message,
        delegated_to="system_ai",
        ws_client_id=ws_client_id
    )

    # 태스크 컨텍스트 설정
    set_current_task_id(task_id)
    clear_called_agent()

    # 최근 대화 히스토리 로드 (7회) + Observation Masking 적용
    RECENT_TURNS_RAW = 2    # 최근 2턴은 원본 유지
    MASK_THRESHOLD = 500    # 500자 이상이면 마스킹

    recent_conversations = get_recent_conversations(limit=7)
    history = []

    for idx, conv in enumerate(recent_conversations):
        original_role = conv["role"]
        content = conv["content"]

        # Claude API는 role에 "user"와 "assistant"만 허용
        # delegation, agent_report 등은 맥락 정보를 content에 포함시켜 매핑
        if original_role == "user":
            role = "user"
        elif original_role == "assistant":
            role = "assistant"
        elif original_role == "delegation":
            # 시스템 AI가 에이전트에게 위임한 기록
            role = "assistant"
            content = f"[에이전트 위임 기록]\n{content}"
        elif original_role == "agent_report":
            # 에이전트가 시스템 AI에게 보고한 기록
            role = "user"
            content = f"[에이전트 보고 수신]\n{content}"
        else:
            # 기타 (알 수 없는 role)
            role = "user"
            content = f"[{original_role}]\n{content}"

        # Observation Masking: 최근 2턴은 원본, 오래된 것은 500자 이상이면 축약
        if idx >= RECENT_TURNS_RAW and len(content) > MASK_THRESHOLD:
            first_line = content.split('\n')[0][:100]
            content = f"[이전 대화: {first_line}... ({len(content)}자)]"

        history.append({"role": role, "content": content})

    # 사용자 메시지 저장
    save_conversation("user", chat.message)

    # 이미지 데이터 변환
    images_data = None
    if chat.images:
        images_data = [{"base64": img.base64, "media_type": img.media_type} for img in chat.images]

    # AIAgent를 사용한 통합 처리 (모든 프로바이더 자동 지원)
    try:
        response_text = process_system_ai_message(
            message=chat.message,
            history=history,
            images=images_data
        )
    except Exception as e:
        clear_current_task_id()
        clear_called_agent()
        raise HTTPException(status_code=500, detail=f"AI 응답 생성 실패: {str(e)}")

    # 위임 여부 확인
    called_another = did_call_agent()

    # 컨텍스트 정리
    clear_current_task_id()
    clear_called_agent()

    if called_another:
        # 위임이 발생함 → 결과는 나중에 WebSocket으로 전송
        return ChatResponse(
            response=f"[위임 중] 프로젝트 에이전트에게 작업을 위임했습니다. 결과는 잠시 후 도착합니다.\n\n{response_text}",
            timestamp=datetime.now().isoformat(),
            provider=provider,
            model=model
        )
    else:
        # 위임 없음 → 즉시 응답, 태스크 완료
        from system_ai_memory import complete_task as complete_system_ai_task
        complete_system_ai_task(task_id, response_text[:500])

        # AI 응답 저장
        save_conversation("assistant", response_text)

        return ChatResponse(
            response=response_text,
            timestamp=datetime.now().isoformat(),
            provider=provider,
            model=model
        )


@router.get("/system-ai/welcome")
async def get_welcome_message():
    """
    첫 실행 시 환영 메시지
    (API 키 없이도 표시 가능한 정적 메시지)
    """
    return {
        "message": """안녕하세요! IndieBiz OS에 오신 걸 환영합니다.

저는 시스템 AI입니다. IndieBiz 사용을 도와드릴게요.

시작하려면 먼저 AI API 키를 설정해주세요:
1. 오른쪽 상단의 설정(⚙️) 버튼을 클릭
2. AI 프로바이더 선택 (Claude/GPT/Gemini)
3. API 키 입력

설정이 완료되면 저와 대화하면서 IndieBiz를 배워보세요!

무엇이든 물어보세요:
• "뭘 할 수 있어?"
• "새 프로젝트 만들어줘"
• "에이전트가 뭐야?"
• "도구 설치하려면?"
""",
        "needs_api_key": True
    }


@router.get("/system-ai/status")
async def get_system_ai_status():
    """시스템 AI 상태 확인"""
    config = load_system_ai_config()

    has_api_key = bool(config.get("apiKey", ""))

    return {
        "enabled": config.get("enabled", True),
        "provider": config.get("provider", "anthropic"),
        "model": config.get("model", "claude-sonnet-4-20250514"),
        "has_api_key": has_api_key,
        "ready": has_api_key and config.get("enabled", True)
    }


@router.get("/system-ai/providers")
async def get_available_providers():
    """사용 가능한 AI 프로바이더 목록"""
    return {
        "providers": [
            {
                "id": "anthropic",
                "name": "Anthropic Claude",
                "models": [
                    {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4 (추천)"},
                    {"id": "claude-3-5-sonnet-20241022", "name": "Claude 3.5 Sonnet"},
                    {"id": "claude-3-5-haiku-20241022", "name": "Claude 3.5 Haiku (빠름)"},
                ],
                "api_url": "https://console.anthropic.com"
            },
            {
                "id": "openai",
                "name": "OpenAI GPT",
                "models": [
                    {"id": "gpt-4o", "name": "GPT-4o (추천)"},
                    {"id": "gpt-4o-mini", "name": "GPT-4o Mini (빠름)"},
                    {"id": "gpt-4-turbo", "name": "GPT-4 Turbo"},
                ],
                "api_url": "https://platform.openai.com/api-keys"
            },
            {
                "id": "google",
                "name": "Google Gemini",
                "models": [
                    {"id": "gemini-2.0-flash-exp", "name": "Gemini 2.0 Flash (추천)"},
                    {"id": "gemini-1.5-pro", "name": "Gemini 1.5 Pro"},
                    {"id": "gemini-1.5-flash", "name": "Gemini 1.5 Flash (빠름)"},
                ],
                "api_url": "https://aistudio.google.com/apikey"
            }
        ]
    }


# ============ 메모리 관련 API ============

@router.get("/system-ai/conversations")
async def get_conversations(limit: int = 20):
    """시스템 AI 대화 이력 조회"""
    conversations = get_recent_conversations(limit)
    return {"conversations": conversations}


@router.get("/system-ai/conversations/recent")
async def get_conversations_recent(limit: int = 20):
    """시스템 AI 최근 대화 조회"""
    conversations = get_recent_conversations(limit)
    return {"conversations": conversations}


@router.get("/system-ai/conversations/dates")
async def get_conversation_dates():
    """대화가 있는 날짜 목록 조회 (날짜별 메시지 수 포함)"""
    import sqlite3
    from system_ai_memory import MEMORY_DB_PATH

    conn = sqlite3.connect(str(MEMORY_DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT date(timestamp) as date, COUNT(*) as count
        FROM conversations
        GROUP BY date(timestamp)
        ORDER BY date DESC
    """)

    rows = cursor.fetchall()
    conn.close()

    dates = [{"date": row[0], "count": row[1]} for row in rows if row[0]]
    return {"dates": dates}


@router.get("/system-ai/conversations/by-date/{date}")
async def get_conversations_by_date(date: str):
    """특정 날짜의 대화 조회"""
    import sqlite3
    from system_ai_memory import MEMORY_DB_PATH

    conn = sqlite3.connect(str(MEMORY_DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, timestamp, role, content, summary, importance
        FROM conversations
        WHERE date(timestamp) = ?
        ORDER BY id ASC
    """, (date,))

    rows = cursor.fetchall()
    conn.close()

    conversations = []
    for row in rows:
        conversations.append({
            "id": row[0],
            "timestamp": row[1],
            "role": row[2],
            "content": row[3],
            "summary": row[4],
            "importance": row[5]
        })

    return {"conversations": conversations}


@router.delete("/system-ai/conversations")
async def clear_conversations():
    """시스템 AI 대화 이력 삭제"""
    import sqlite3
    from system_ai_memory import MEMORY_DB_PATH

    conn = sqlite3.connect(str(MEMORY_DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    cursor = conn.cursor()
    cursor.execute("DELETE FROM conversations")
    conn.commit()
    conn.close()

    return {"status": "cleared"}




# ============ 프롬프트 설정 API ============

def save_system_ai_config(config: dict):
    """시스템 AI 설정 저장"""
    with open(SYSTEM_AI_CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


class PromptConfigUpdate(BaseModel):
    selected_template: Optional[str] = None


@router.get("/system-ai/prompts/config")
async def get_prompt_config():
    """프롬프트 설정 조회"""
    config = load_system_ai_config()
    return {
        "selected_template": config.get("selected_template", "default")
    }


@router.put("/system-ai/prompts/config")
async def update_prompt_config(data: PromptConfigUpdate):
    """프롬프트 설정 업데이트"""
    config = load_system_ai_config()

    if data.selected_template is not None:
        config["selected_template"] = data.selected_template

    save_system_ai_config(config)
    return {"status": "updated", "config": {
        "selected_template": config.get("selected_template")
    }}


# 시스템 AI 역할 파일 경로
SYSTEM_AI_ROLE_PATH = DATA_PATH / "system_ai_role.txt"


@router.get("/system-ai/prompts/role")
async def get_role_prompt():
    """역할 프롬프트 조회 (별도 파일에서 로드)"""
    if SYSTEM_AI_ROLE_PATH.exists():
        content = SYSTEM_AI_ROLE_PATH.read_text(encoding='utf-8')
    else:
        content = ""
    return {"content": content}


class RolePromptUpdate(BaseModel):
    content: str


@router.put("/system-ai/prompts/role")
async def update_role_prompt(data: RolePromptUpdate):
    """역할 프롬프트 업데이트 (별도 파일에 저장)"""
    SYSTEM_AI_ROLE_PATH.write_text(data.content, encoding='utf-8')
    return {"status": "updated"}
