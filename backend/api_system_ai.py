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
    get_history_for_ai,
    get_memory_context,
    save_memory,
    get_memories
)
# 시스템 문서 관련
from system_docs import (
    read_doc,
    init_all_docs
)
# Phase 17: execute_ibl 단일 도구 (기존 패키지 로딩 제거)
from tool_loader import load_tool_schema
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


# ============ 작업계획서 실행 레지스트리 ============
# fire-and-forget 패턴에서 에이전트 완료 후 다음 단계를 자동 트리거하기 위한 레지스트리.
# Key: (project_id, agent_id), Value: {"plan_file": str, "step_number": int, "total_steps": int}
import threading as _threading
_active_plan_steps: Dict[tuple, dict] = {}
_plan_steps_lock = _threading.Lock()


def register_plan_step(project_id: str, agent_id: str,
                       plan_file: str, step_number: int, total_steps: int):
    """작업계획서의 현재 실행 중인 단계를 레지스트리에 등록."""
    with _plan_steps_lock:
        _active_plan_steps[(project_id, agent_id)] = {
            "plan_file": plan_file,
            "step_number": step_number,
            "total_steps": total_steps,
        }
    print(f"[PlanRegistry] 등록: ({project_id}/{agent_id}) → 단계 {step_number}/{total_steps}")


def on_agent_plan_step_complete(project_id: str, agent_id: str, result_text: str):
    """에이전트가 작업계획서 단계를 완료했을 때 호출.

    - 레지스트리에서 활성 단계 정보를 꺼냄
    - 계획서 상태를 '완료' 또는 '실패'로 업데이트
    - 다음 '대기' 단계가 있으면 별도 스레드에서 자동 실행
    """
    with _plan_steps_lock:
        key = (project_id, agent_id)
        step_info = _active_plan_steps.pop(key, None)

    if not step_info:
        return  # 이 에이전트에 활성 계획서 단계 없음

    plan_file = step_info["plan_file"]
    step_number = step_info["step_number"]

    # 결과 텍스트 정리 (너무 길면 잘라냄)
    result_summary = (result_text or "")[:2000]

    # 에러인지 확인
    is_error = result_summary.startswith("[오류]")

    # 단계 상태 업데이트
    new_status = "실패" if is_error else "완료"
    _update_plan_status(plan_file, step_number, new_status, result_text=result_summary)
    print(f"[PlanRegistry] 단계 {step_number} {new_status}: {plan_file}")

    if is_error:
        print(f"[PlanRegistry] 단계 실패로 인해 다음 단계 진행하지 않음")
        return  # 실패 시 다음 단계로 진행하지 않음

    # 다음 단계 자동 실행 (별도 스레드)
    def _trigger_next_step():
        import time as _time
        _time.sleep(2)  # 에이전트 정리 시간
        try:
            result = _execute_plan(
                {"file": plan_file, "context": result_summary},
                agent_id=None,
                project_path=None
            )
            result_data = json.loads(result)
            if result_data.get("all_done"):
                print(f"[PlanRegistry] 작업계획서 전체 완료: {plan_file}")
            elif result_data.get("success"):
                print(f"[PlanRegistry] 다음 단계 시작: {result_data.get('step_title')}")
            else:
                print(f"[PlanRegistry] 다음 단계 실행 실패: {result_data.get('error')}")
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"[PlanRegistry] 다음 단계 트리거 실패: {e}")

    next_thread = _threading.Thread(target=_trigger_next_step, daemon=True)
    next_thread.start()


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
        "description": "캘린더 이벤트와 스케줄 작업을 통합 관리합니다 (기념일, 약속, 생일, 알림, 스케줄 등의 추가/수정/삭제/조회/토글).",
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
                    "description": "실행할 액션 (스케줄 작업일 때): run_pipeline, run_switch, send_notification, test. run_pipeline은 IBL 코드를 예약 실행할 때 사용. null이면 순수 캘린더 이벤트"
                },
                "action_params": {
                    "type": "object",
                    "description": "액션 파라미터. run_pipeline일 때: {pipeline: \"[limbs:play]{query: '검색어'}\"}, run_switch일 때: {switch_id: '...'}, send_notification일 때: {message: '...', title: '...'}"
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
    """시스템 AI 도구: execute_ibl + 범용 언어 도구 + search_guide

    프로젝트 에이전트와 동일한 도구 구조.
    차이는 IBL에서 접근 가능한 노드 범위뿐 (시스템 AI: 전체 노드).
    """
    import json as _json

    tools = []
    ibl_schema = load_tool_schema("execute_ibl")
    if ibl_schema:
        tools.append(ibl_schema)

    # 범용 언어 도구 (프로젝트 에이전트와 동일)
    pkg_base = Path(__file__).parent.parent / "data" / "packages" / "installed" / "tools"
    lang_tools = [
        ("python-exec", "execute_python"),
        ("nodejs", "execute_node"),
        ("system_essentials", "run_command"),
    ]
    for pkg_id, tool_name in lang_tools:
        tool_json = pkg_base / pkg_id / "tool.json"
        if tool_json.exists():
            try:
                with open(tool_json, 'r', encoding='utf-8') as f:
                    pkg_data = _json.load(f)
                for tool_def in pkg_data.get("tools", []):
                    if tool_def.get("name") == tool_name:
                        tools.append(tool_def)
                        break
            except Exception as e:
                print(f"[시스템AI] {pkg_id}/tool.json 로드 실패: {e}")

    # 가이드 검색 도구
    tools.append({
        "name": "search_guide",
        "description": "복잡한 작업 전에 가이드(워크플로우/레시피)를 검색합니다. 캘린더, 스케줄, 영상 제작 등 절차가 있는 작업 전에 호출하세요.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "검색 키워드 (예: 캘린더, 스케줄, 영상)"},
                "read": {"type": "boolean", "description": "true(기본): 가이드 내용까지 반환, false: 목록만"}
            },
            "required": ["query"]
        }
    })

    return tools


def create_system_ai_agent(config: dict = None, user_profile: str = "") -> AIAgent:
    """시스템 AI용 AIAgent 인스턴스 생성

    **Phase 17 통합 아키텍처**: 프로젝트 에이전트와 동일한 구조.
    - execute_ibl 단일 도구
    - IBL 환경 프롬프트로 노드/액션 인식
    - 차이점: 모든 노드 접근 가능 + 프로젝트 간 위임

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

    # Phase 17: execute_ibl 단일 도구
    tools = get_all_system_ai_tools()

    # Git 활성화: .git 폴더 존재 여부로 판단
    git_enabled = (DATA_PATH / ".git").exists()

    # 시스템 프롬프트 생성 (IBL 환경 포함)
    system_prompt = build_system_ai_prompt(
        user_profile=user_profile,
        git_enabled=git_enabled
    )

    # AIAgent 인스턴스 생성 (execute_ibl → IBL 경로)
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
    """Phase 17: 시스템 AI 도구 실행 (execute_ibl 단일 경로)

    Args:
        tool_name: 도구 이름 (execute_ibl)
        tool_input: 도구 입력
        work_dir: 작업 디렉토리
        agent_id: 에이전트 ID
    """
    from system_tools import execute_tool
    return execute_tool(
        tool_name, tool_input,
        project_path=work_dir or str(DATA_PATH),
        agent_id=agent_id or "system_ai"
    )


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
    # agent_id는 id 또는 name일 수 있음 → 먼저 id로, 없으면 name으로 검색
    registry_key = f"{project_id}:{agent_id}"
    target = AgentRunner.agent_registry.get(registry_key)
    if not target:
        # name으로 검색 (registry는 project_id:agent_id 형식이므로 순회)
        for rkey, runner in AgentRunner.agent_registry.items():
            if rkey.startswith(f"{project_id}:") and runner.config.get("name") == agent_id:
                target = runner
                agent_id = runner.config.get("id", agent_id)
                registry_key = rkey
                break

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

            # 대상 에이전트 확인 (id 또는 name으로 검색)
            target_config = None
            for agent in agents:
                if agent.get("id") == agent_id or agent.get("name") == agent_id:
                    target_config = agent
                    # agent_id를 실제 id로 통일 (registry_key 매칭용)
                    agent_id = agent.get("id", agent_id)
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

            # 대상 에이전트 다시 조회 (agent_id는 실제 id로 통일됨)
            registry_key = f"{project_id}:{agent_id}"
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
        pending = parent_task.get('pending_delegations', 0)

        if delegation_context_str:
            delegation_context = json.loads(delegation_context_str)

            # 이전 사이클 완료 감지: delegations 있고 pending==0 → completed로 병합
            prev_delegations = delegation_context.get('delegations', [])
            if len(prev_delegations) > 0 and pending == 0:
                completed = delegation_context.get('completed', [])
                responses = delegation_context.get('responses', [])

                # 이전 사이클 결과를 completed에 병합
                response_map = {}
                for resp in responses:
                    child_id = resp.get('child_task_id', '')
                    response_map[child_id] = resp

                for deleg in prev_delegations:
                    child_id = deleg.get('child_task_id', '')
                    resp = response_map.get(child_id, {})
                    completed.append({
                        'to': deleg.get('delegated_to', ''),
                        'message': deleg.get('delegation_message', ''),
                        'result': resp.get('response', '(응답 없음)'),
                        'completed_at': resp.get('completed_at', deleg.get('delegation_time', ''))
                    })

                print(f"   [시스템 AI 위임 컨텍스트] 이전 사이클 {len(prev_delegations)}개 → completed 병합 (총 {len(completed)}개)")
                delegation_context = {
                    'original_request': parent_task.get('original_request', ''),
                    'requester': parent_task.get('requester', 'user@gui'),
                    'completed': completed,
                    'delegations': [],
                    'responses': []
                }
        else:
            delegation_context = {
                'original_request': parent_task.get('original_request', ''),
                'requester': parent_task.get('requester', 'user@gui'),
                'completed': [],
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


# 시스템 AI 가이드 주입 — 비활성화됨
# 가이드 시스템이 search_guide 독립 도구로 통합됨 (data/guides/ + guide_db.json)


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
            event_time = tool_input.get("time")
            event_action = tool_input.get("event_action")
            repeat = tool_input.get("repeat", "none")

            # start_time 호환: "2026-03-09T17:44:00" → date + time 자동 분리
            start_time = tool_input.get("start_time")
            if start_time and (not event_date or not event_time):
                try:
                    from datetime import datetime as _dt
                    parsed = _dt.fromisoformat(start_time)
                    if not event_date:
                        event_date = parsed.strftime("%Y-%m-%d")
                    if not event_time:
                        event_time = parsed.strftime("%H:%M")
                except (ValueError, TypeError):
                    pass

            # 실행 이벤트 (스케줄)인 경우 date 없이도 허용 (daily, interval 등)
            if not event_date and not event_action:
                return json.dumps({"success": False, "error": "date는 필수입니다. (YYYY-MM-DD)"}, ensure_ascii=False)

            event = cm.add_event(
                title=title,
                event_date=event_date,
                event_type=tool_input.get("type", "schedule" if event_action else "other"),
                repeat=repeat,
                description=tool_input.get("description", ""),
                event_time=event_time,
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


def _execute_schedule(params: dict, agent_id: str = None, project_path: str = None) -> str:
    """[self:schedule] — 미래 실행 통합 액션

    "N분 후에 해줘", "매일 9시에 해줘", "내일 3시에 해줘" 모두 이 하나로 처리.
    target_project_id / target_agent_id를 지정하면 다른 에이전트의 스케줄로 등록 (크로스 위임).

    동작 모드 (파라미터에 따라 자동 결정):
    1. minutes/seconds 있으면 → 지연 실행 (타이머 + 캘린더 백업)
    2. date/time만 있으면 → 특정 시각 1회 실행
    3. repeat 있으면 → 반복 실행

    파라미터:
        pipeline: 실행할 IBL 코드 (필수)
        minutes: 지연 시간 (분) — 지연 모드
        seconds: 지연 시간 (초) — 지연 모드
        date: 실행 날짜 (YYYY-MM-DD) — 특정 시각 모드
        time: 실행 시각 (HH:MM) — 특정 시각/반복 모드
        repeat: 반복 유형 (daily/weekly/monthly/yearly/interval)
        title: 이벤트 제목 (선택)
        weekdays: 요일 목록 (weekly일 때, 0=월 ~ 6=일)
        interval_hours: 반복 간격 (interval일 때)
        target_project_id: 대상 에이전트의 프로젝트 ID (크로스 위임 시)
        target_agent_id: 대상 에이전트 ID (크로스 위임 시)
    """
    import threading
    from datetime import datetime, timedelta
    from calendar_manager import get_calendar_manager

    # pipeline 또는 code 둘 다 허용 (AI가 자주 혼동하므로)
    pipeline = params.get("pipeline", "") or params.get("code", "")
    if not pipeline:
        return json.dumps({"success": False, "error": "pipeline은 필수입니다. 실행할 IBL 코드를 지정하세요."}, ensure_ascii=False)

    # 'at' 통합 파라미터: "2026-03-10 09:00" 또는 "09:00" 또는 "2026-03-10T09:00:00"
    # date/time을 각각 지정하지 않아도 at 하나로 처리
    at_param = params.get("at", "")
    if at_param and not params.get("date") and not params.get("time"):
        try:
            at_str = at_param.replace("T", " ")
            if " " in at_str:
                parsed = datetime.fromisoformat(at_param.replace(" ", "T"))
                params["date"] = parsed.strftime("%Y-%m-%d")
                params["time"] = parsed.strftime("%H:%M")
            else:
                # 시간만 지정된 경우: "09:00" → 오늘 날짜
                params["time"] = at_str[:5]
        except (ValueError, TypeError):
            pass

    minutes = params.get("minutes", 0)
    seconds = params.get("seconds", 0)
    repeat = params.get("repeat", "none")
    title = params.get("title", pipeline[:40])
    cm = get_calendar_manager()

    # ── owner 결정: target이 지정되면 크로스 위임, 아니면 셀프 ──
    target_project_id = params.get("target_project_id", "")
    target_agent_id = params.get("target_agent_id", "")

    if target_project_id or target_agent_id:
        # 크로스 위임: 다른 에이전트의 스케줄로 등록
        project_id = target_project_id or "__system_ai__"
        owner_agent = target_agent_id or ""

        # target_agent_id가 없으면 프로젝트의 에이전트를 자동 결정
        if not owner_agent and project_id and project_id != "__system_ai__":
            try:
                import yaml
                from project_manager import ProjectManager
                pm = ProjectManager()
                _proj_path = pm.get_project_path(project_id)
                if _proj_path:
                    _agents_file = _proj_path / "agents.yaml"
                    if _agents_file.exists():
                        with open(_agents_file, 'r', encoding='utf-8') as f:
                            _agents_data = yaml.safe_load(f)
                        _active_agents = [a for a in _agents_data.get("agents", [])
                                          if a.get("active", True)]
                        if len(_active_agents) == 1:
                            # 에이전트가 하나뿐이면 자동 선택
                            owner_agent = _active_agents[0].get("name") or _active_agents[0].get("id", "")
                            print(f"[Schedule] 에이전트 자동 결정: {project_id} → {owner_agent} (유일한 에이전트)")
                        elif len(_active_agents) > 1:
                            # 여러 에이전트가 있으면 첫 번째를 기본으로
                            owner_agent = _active_agents[0].get("name") or _active_agents[0].get("id", "")
                            print(f"[Schedule] 에이전트 자동 결정: {project_id} → {owner_agent} (첫 번째 에이전트, {len(_active_agents)}개 중)")
            except Exception as e:
                print(f"[Schedule] 에이전트 자동 결정 실패: {e}")

        print(f"[Schedule] 크로스 위임: {agent_id} → {project_id}/{owner_agent}")
    else:
        # 셀프: 호출한 에이전트 자신의 스케줄
        # 시스템 AI 판별: agent_id가 "system_ai"이거나, project_path가 data/ 디렉토리인 경우
        _is_system_ai_caller = (agent_id == "system_ai")
        if not _is_system_ai_caller and project_path and project_path != ".":
            from pathlib import Path as _Path
            _pp = _Path(project_path)
            # data 디렉토리면 시스템 AI (projects/ 하위가 아님)
            _is_system_ai_caller = (_pp.name == "data" or _pp.name == "system_ai"
                                    or "projects" not in str(_pp))

        if _is_system_ai_caller:
            project_id = "__system_ai__"
        else:
            # project_path에서 project_id 추출 (예: ".../projects/투자" → "투자")
            project_id = ""
            if project_path and project_path != ".":
                from pathlib import Path as _Path
                project_id = _Path(project_path).name
            if not project_id:
                project_id = "__system_ai__"
        owner_agent = agent_id

    try:
        total_seconds = float(minutes) * 60 + float(seconds)
    except (ValueError, TypeError):
        total_seconds = 0

    # ── 모드 판별 ──
    is_delay = total_seconds > 0
    is_recurring = repeat and repeat != "none"

    if is_delay:
        # ── 지연 모드: N분/초 후 실행 ──
        if total_seconds > 86400:
            return json.dumps({"success": False, "error": "지연은 24시간 이내만 가능합니다."}, ensure_ascii=False)

        execute_at = datetime.now() + timedelta(seconds=total_seconds)
        execute_date = execute_at.strftime("%Y-%m-%d")
        execute_time_hm = execute_at.strftime("%H:%M")
        execute_at_str = execute_at.strftime("%H:%M:%S")

        # 캘린더 이벤트 등록 (영속성)
        event_id = None
        try:
            event = cm.add_event(
                title=title,
                event_date=execute_date,
                event_type="schedule",
                repeat="none",
                event_time=execute_time_hm,
                action="run_pipeline",
                action_params={"pipeline": pipeline},
                owner_project_id=project_id,
                owner_agent_id=owner_agent or ("system_ai" if project_id == "__system_ai__" else ""),
            )
            event_id = event.get("id")
        except Exception as e:
            print(f"[Schedule] 캘린더 등록 실패: {e}")

        # 타이머 시작 (정밀 실행) — owner 컨텍스트에서 실행
        # 크로스 위임 시: 호출자(A)의 path가 아니라 target(B)의 path를 써야 함
        # project_id로 resolve하도록 "."로 설정 → _delayed_run에서 ProjectManager로 해결
        _is_cross = bool(target_project_id or target_agent_id)
        _timer_project_path = "." if _is_cross else (project_path or ".")
        _timer_project_id = project_id
        _timer_agent_id = owner_agent or agent_id

        def _delayed_run():
            try:
                from ibl_parser import parse as ibl_parse
                from workflow_engine import execute_pipeline

                if event_id:
                    try:
                        get_calendar_manager().update_event(event_id, enabled=False)
                    except Exception:
                        pass

                # owner의 project_path에서 실행
                run_path = _timer_project_path
                if run_path == "." and _timer_project_id and _timer_project_id != "__system_ai__":
                    try:
                        from project_manager import ProjectManager
                        pm = ProjectManager()
                        resolved = pm.get_project_path(_timer_project_id)
                        if resolved and resolved.exists():
                            run_path = str(resolved)
                    except Exception:
                        pass

                print(f"[Schedule] ⏰ 타이머 만료, 실행: {pipeline[:80]}... (context: {_timer_project_id}/{_timer_agent_id})")
                steps = ibl_parse(pipeline)
                if steps:
                    result = execute_pipeline(steps, run_path, agent_id=_timer_agent_id)
                    print(f"[Schedule] 완료: success={result.get('success')}")

                    # 결과를 owner의 대화창에 전달
                    if result.get("success") and (_timer_project_id or _timer_agent_id):
                        try:
                            task_for_delivery = {
                                "title": title,
                                "owner_project_id": _timer_project_id,
                                "owner_agent_id": _timer_agent_id,
                                "action_params": {"pipeline": pipeline},
                            }
                            cm._deliver_result_to_chat(task_for_delivery, _timer_agent_id, pipeline, result)
                        except Exception as e:
                            print(f"[Schedule] 결과 전달 실패: {e}")
            except Exception as e:
                print(f"[Schedule] 실행 실패: {e}")

        timer = threading.Timer(total_seconds, _delayed_run)
        timer.daemon = True
        timer.start()

        if minutes >= 1:
            display = f"{int(minutes)}분" + (f" {int(seconds)}초" if seconds else "")
        else:
            display = f"{int(total_seconds)}초"

        print(f"[Schedule] {display} 후 ({execute_at_str}) 실행 예정 — {pipeline[:60]}")

        return json.dumps({
            "success": True,
            "message": f"{display} 후({execute_at_str})에 실행 예약됨",
            "execute_at": execute_at_str,
            "event_id": event_id
        }, ensure_ascii=False)

    else:
        # ── 특정 시각 / 반복 모드 ──
        event_date = params.get("date")
        event_time = params.get("time")

        # start_time 호환: "2026-03-09T17:44:00" 형태 자동 파싱
        start_time = params.get("start_time")
        if start_time and (not event_date or not event_time):
            try:
                parsed = datetime.fromisoformat(start_time)
                if not event_date:
                    event_date = parsed.strftime("%Y-%m-%d")
                if not event_time:
                    event_time = parsed.strftime("%H:%M")
            except (ValueError, TypeError):
                pass

        # time 파라미터에 full datetime이 들어온 경우 정규화
        # "2026-03-10 09:00:00" → date="2026-03-10", time="09:00"
        if event_time and " " in event_time:
            try:
                parsed = datetime.fromisoformat(event_time.replace(" ", "T"))
                if not event_date:
                    event_date = parsed.strftime("%Y-%m-%d")
                event_time = parsed.strftime("%H:%M")
            except (ValueError, TypeError):
                # 공백 뒤만 추출 (fallback)
                event_time = event_time.split()[-1][:5]
        elif event_time and "T" in event_time:
            try:
                parsed = datetime.fromisoformat(event_time)
                if not event_date:
                    event_date = parsed.strftime("%Y-%m-%d")
                event_time = parsed.strftime("%H:%M")
            except (ValueError, TypeError):
                pass
        # HH:MM:SS → HH:MM 정규화
        elif event_time and len(event_time) == 8 and event_time.count(":") == 2:
            event_time = event_time[:5]

        if not event_time and not is_recurring:
            return json.dumps({"success": False, "error": "time(HH:MM) 또는 minutes가 필요합니다."}, ensure_ascii=False)

        if not event_date and not is_recurring:
            event_date = datetime.now().strftime("%Y-%m-%d")

        try:
            event = cm.add_event(
                title=title,
                event_date=event_date,
                event_type="schedule",
                repeat=repeat,
                event_time=event_time,
                action="run_pipeline",
                action_params={"pipeline": pipeline},
                owner_project_id=project_id,
                owner_agent_id=owner_agent or ("system_ai" if project_id == "__system_ai__" else ""),
                weekdays=params.get("weekdays"),
                interval_hours=params.get("interval_hours"),
            )
            event_id = event.get("id")

            if is_recurring:
                msg = f"반복 스케줄 등록됨 ({repeat}, {event_time or '설정됨'})"
            else:
                msg = f"{event_date} {event_time}에 실행 예약됨"

            print(f"[Schedule] 이벤트 등록: {event_id} — {msg}")

            return json.dumps({
                "success": True,
                "message": msg,
                "event_id": event_id
            }, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"success": False, "error": str(e)}, ensure_ascii=False)


def _execute_create_plan(params: dict, agent_id: str = None, project_path: str = None) -> str:
    """[self:create_plan] — 구조화된 작업계획서 생성

    AI가 읽고 실행할 수 있는 형식의 작업계획서를 생성합니다.
    각 단계에 상태 마커가 있어서 실행 후 업데이트되고,
    다음 에이전트는 상태를 보고 자기 차례를 판단합니다.

    파라미터:
        file: 저장할 파일 경로 (필수)
        title: 계획서 제목
        goal: 전체 목표 설명
        steps: 단계 목록 (list of dict)
            각 단계: {
                agent_project_id: 실행할 에이전트의 프로젝트 ID,
                agent_id: 실행할 에이전트 ID,
                title: 단계 제목,
                description: 상세 지시,
                pipeline: 실행할 IBL 코드 (선택),
                on_failure: 실패 시 지시 (선택),
                max_retries: 최대 재시도 횟수 (기본 2)
            }
    """
    from pathlib import Path as _Path
    from datetime import datetime

    plan_file = params.get("file", "")
    title = params.get("title", "작업계획서")
    goal = params.get("goal", "")
    steps = params.get("steps", [])

    if not plan_file:
        return json.dumps({"success": False, "error": "file 파라미터가 필요합니다."}, ensure_ascii=False)
    if not steps:
        return json.dumps({"success": False, "error": "steps 파라미터가 필요합니다."}, ensure_ascii=False)

    # 파일 경로 해석
    file_path = _Path(plan_file)
    if not file_path.is_absolute():
        base = _Path(project_path) if project_path and project_path != "." else DATA_PATH
        file_path = base / plan_file

    # ── 작업계획서 마크다운 생성 ──
    lines = []
    lines.append(f"# {title}")
    lines.append(f"")
    lines.append(f"- **생성**: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"- **상태**: 대기중")
    if goal:
        lines.append(f"- **목표**: {goal}")
    lines.append(f"")
    lines.append(f"---")
    lines.append(f"")

    # ── 필수 필드 검증 ──
    errors = []
    for i, step in enumerate(steps, 1):
        agent_proj = step.get("agent_project_id", "")
        agent = step.get("agent_id", "")
        if not agent_proj or not agent:
            errors.append(f"단계 {i}: agent_project_id와 agent_id는 필수입니다. "
                          f"(현재: project='{agent_proj}', agent='{agent}'). "
                          f"[others:list_projects]로 프로젝트/에이전트 목록을 확인하세요.")
    if errors:
        return json.dumps({
            "success": False,
            "error": "작업계획서 단계에 담당 에이전트가 지정되지 않았습니다.",
            "details": errors,
            "hint": "각 step에 agent_project_id(프로젝트 ID)와 agent_id(에이전트 ID)를 반드시 지정하세요. "
                     "search_guide('작업계획서')로 가이드를 읽고, "
                     "[others:list_projects]로 프로젝트/에이전트 목록을 확인하세요."
        }, ensure_ascii=False)

    # ── description 품질 검증 ──
    import re as _re
    quality_warnings = []
    for i, step in enumerate(steps, 1):
        desc = step.get("description", "")
        step_title = step.get("title", f"단계 {i}")

        # 빈 description 체크
        if not desc or len(desc.strip()) < 10:
            quality_warnings.append(
                f"단계 {i}({step_title}): description이 너무 짧습니다 ({len(desc.strip())}자). "
                f"담당 에이전트가 무엇을 해야 하는지 구체적으로 적어주세요.")

        # IBL 코드 패턴 감지
        elif _re.search(r'\[(?:self|sense|limbs|engines|data|others):', desc):
            quality_warnings.append(
                f"단계 {i}({step_title}): description에 IBL 코드가 포함되어 있습니다. "
                f"자연어로 의도를 전달하세요. 담당 에이전트가 실행 방법은 자기 맥락으로 판단합니다.")

        # 제네릭한 description 체크
        elif len(desc.strip()) < 30:
            quality_warnings.append(
                f"단계 {i}({step_title}): description이 짧습니다 ({len(desc.strip())}자). "
                f"더 구체적으로 작성하면 결과 품질이 높아집니다.")

    if quality_warnings:
        # 경고는 반환하되 생성은 계속 진행 (에러가 아닌 경고)
        print(f"[CreatePlan] 품질 경고: {quality_warnings}")

    for i, step in enumerate(steps, 1):
        step_title = step.get("title", f"단계 {i}")
        agent_proj = step.get("agent_project_id", "")
        agent = step.get("agent_id", "")
        desc = step.get("description", "")
        pipeline = step.get("pipeline", "")
        on_failure = step.get("on_failure", "보고하고 중단")
        max_retries = step.get("max_retries", 2)

        lines.append(f"## 단계 {i}: {step_title}")
        lines.append(f"")
        lines.append(f"- **상태**: [ ] 대기")
        lines.append(f"- **담당**: project={agent_proj}, agent={agent}")
        lines.append(f"- **최대재시도**: {max_retries}")
        lines.append(f"- **시도횟수**: 0")
        lines.append(f"")

        if desc:
            lines.append(f"### 지시사항")
            lines.append(f"{desc}")
            lines.append(f"")

        if pipeline:
            lines.append(f"### 실행 코드")
            lines.append(f"```ibl")
            lines.append(f"{pipeline}")
            lines.append(f"```")
            lines.append(f"")

        lines.append(f"### 실패 시")
        lines.append(f"{on_failure}")
        lines.append(f"")

        lines.append(f"### 결과")
        lines.append(f"_(미실행)_")
        lines.append(f"")
        lines.append(f"---")
        lines.append(f"")

    # 실행 가이드
    lines.append(f"## 실행 규칙")
    lines.append(f"")
    lines.append(f"이 계획서는 `[self:execute_plan]`으로 실행합니다.")
    lines.append(f"시스템이 자동으로 순차 실행합니다:")
    lines.append(f"1. 상태가 `[ ] 대기`인 가장 빠른 단계를 찾아 담당 에이전트에게 전달")
    lines.append(f"2. 에이전트는 자기 단계의 지시사항만 받아서 실행")
    lines.append(f"3. 완료되면 시스템이 상태를 업데이트하고 다음 단계로 진행")
    lines.append(f"4. 상태 마커: `[ ] 대기` → `[~] 진행중` → `[v] 완료` 또는 `[x] 실패`")

    content = "\n".join(lines)

    try:
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding='utf-8')
        print(f"[CreatePlan] 작업계획서 생성: {file_path} ({len(steps)}단계)")

        result = {
            "success": True,
            "file": str(file_path),
            "title": title,
            "steps_count": len(steps),
            "message": f"작업계획서 '{title}' 생성 완료 ({len(steps)}단계)"
        }
        if quality_warnings:
            result["quality_warnings"] = quality_warnings
            result["message"] += (
                f" (품질 경고 {len(quality_warnings)}건 — "
                f"search_guide('작업계획서')로 가이드를 참고하여 개선하세요)")
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"success": False, "error": f"파일 저장 실패: {e}"}, ensure_ascii=False)


def _update_plan_status(file_path: str, step_number: int,
                        status: str, result_text: str = "",
                        increment_retry: bool = False) -> bool:
    """작업계획서의 특정 단계 상태를 업데이트

    Args:
        file_path: 계획서 파일 경로
        step_number: 단계 번호 (1부터)
        status: 새 상태 ("진행중", "완료", "실패")
        result_text: 결과 섹션에 기록할 텍스트
        increment_retry: True면 시도횟수를 +1
    """
    import re
    from pathlib import Path as _Path

    fp = _Path(file_path)
    if not fp.exists():
        return False

    content = fp.read_text(encoding='utf-8')

    # 상태 마커 매핑
    status_markers = {
        "대기": "[ ] 대기",
        "진행중": "[~] 진행중",
        "완료": "[v] 완료",
        "실패": "[x] 실패",
    }
    new_marker = status_markers.get(status, f"[?] {status}")

    # 해당 단계 섹션 찾기
    step_header = f"## 단계 {step_number}:"
    lines = content.split('\n')
    in_target_step = False
    updated = False

    for i, line in enumerate(lines):
        if line.startswith(step_header):
            in_target_step = True
            continue

        if in_target_step and line.startswith("## 단계 "):
            # 다음 단계에 도달
            break

        if in_target_step:
            # 상태 마커 업데이트
            if line.startswith("- **상태**:"):
                lines[i] = f"- **상태**: {new_marker}"
                updated = True

            # 시도횟수 업데이트
            if increment_retry and line.startswith("- **시도횟수**:"):
                try:
                    current = int(line.split(":")[1].strip())
                    lines[i] = f"- **시도횟수**: {current + 1}"
                except (ValueError, IndexError):
                    lines[i] = f"- **시도횟수**: 1"

            # 결과 섹션 업데이트
            if result_text and line.strip() == "_(미실행)_":
                lines[i] = result_text

    # 모든 단계가 완료되었는지 확인 → 전체 상태 업데이트
    all_done = True
    any_failed = False
    for line in lines:
        if "- **상태**: [ ] 대기" in line or "- **상태**: [~] 진행중" in line:
            all_done = False
        if "- **상태**: [x] 실패" in line:
            any_failed = True

    if all_done:
        for i, line in enumerate(lines):
            if line.startswith("- **상태**:") and "완료" not in line and "실패" not in line and "진행중" not in line and "대기" not in line:
                continue
            if line == "- **상태**: 대기중":
                lines[i] = f"- **상태**: {'일부실패' if any_failed else '완료'}"
                break

    if updated:
        fp.write_text('\n'.join(lines), encoding='utf-8')

    return updated


def _parse_plan_steps(plan_content: str) -> list:
    """작업계획서 마크다운을 파싱하여 단계 목록 반환.

    Returns:
        [{"number": 1, "title": "...", "status": "대기",
          "project_id": "...", "agent_id": "...",
          "description": "...", "pipeline": "...",
          "on_failure": "...", "max_retries": 2, "retry_count": 0}, ...]
    """
    import re
    steps = []
    current_step = None
    current_section = None  # "description", "pipeline", "failure", "result"

    for line in plan_content.split('\n'):
        # 새 단계 헤더 감지: ## 단계 N: 제목
        m = re.match(r'^## 단계 (\d+):\s*(.*)', line)
        if m:
            if current_step:
                steps.append(current_step)
            current_step = {
                "number": int(m.group(1)),
                "title": m.group(2).strip(),
                "status": "대기",
                "project_id": "", "agent_id": "",
                "description": "", "pipeline": "",
                "on_failure": "보고하고 중단",
                "max_retries": 2, "retry_count": 0,
            }
            current_section = None
            continue

        if not current_step:
            continue

        # 메타데이터 파싱
        if line.startswith("- **상태**:"):
            if "완료" in line:
                current_step["status"] = "완료"
            elif "실패" in line:
                current_step["status"] = "실패"
            elif "진행중" in line:
                current_step["status"] = "진행중"
            else:
                current_step["status"] = "대기"
        elif line.startswith("- **담당**:"):
            # project=투자, agent=agent_001
            pm = re.search(r'project=(\S+)', line)
            am = re.search(r'agent=(\S+)', line)
            if pm:
                current_step["project_id"] = pm.group(1).rstrip(',')
            if am:
                current_step["agent_id"] = am.group(1).rstrip(',')
        elif line.startswith("- **최대재시도**:"):
            try:
                current_step["max_retries"] = int(line.split(":")[1].strip())
            except (ValueError, IndexError):
                pass
        elif line.startswith("- **시도횟수**:"):
            try:
                current_step["retry_count"] = int(line.split(":")[1].strip())
            except (ValueError, IndexError):
                pass
        # 섹션 감지
        elif line.strip() == "### 지시사항":
            current_section = "description"
        elif line.strip() == "### 실행 코드":
            current_section = "pipeline"
        elif line.strip() == "### 실패 시":
            current_section = "failure"
        elif line.strip() == "### 결과":
            current_section = "result"
        elif line.startswith("## ") or line.startswith("---"):
            current_section = None
        # 섹션 내용 수집
        elif current_section == "description" and line.strip():
            if current_step["description"]:
                current_step["description"] += "\n" + line
            else:
                current_step["description"] = line
        elif current_section == "pipeline" and line.strip() and not line.startswith("```"):
            if current_step["pipeline"]:
                current_step["pipeline"] += "\n" + line
            else:
                current_step["pipeline"] = line
        elif current_section == "failure" and line.strip():
            current_step["on_failure"] = line

    if current_step:
        steps.append(current_step)

    return steps


def _execute_plan(params: dict, agent_id: str = None, project_path: str = None) -> str:
    """[self:execute_plan] — 작업계획서를 읽고 순차 실행

    작업계획서를 파싱하여 다음 대기 단계를 찾고,
    해당 담당 에이전트에게 그 단계의 지시사항만 전달합니다.
    에이전트가 작업을 완료하면, 시스템이 계획서 상태를 업데이트하고
    다음 단계가 있으면 자동으로 다음 담당 에이전트에게 넘깁니다.

    순차 실행 원칙:
    - 한 번에 하나의 단계만 실행
    - 이전 단계가 완료되어야 다음 단계로 진행
    - 에이전트에게는 자기 단계의 지시사항만 전달 (계획서 전체를 던지지 않음)
    - 상태 관리와 단계 전달은 시스템이 처리

    파라미터:
        file: 계획서 파일 경로 (필수)
        context: 이전 단계 결과/추가 컨텍스트 (선택)
    """
    from pathlib import Path as _Path

    plan_file = params.get("file", "")
    extra_context = params.get("context", "")

    if not plan_file:
        return json.dumps({
            "success": False,
            "error": "file 파라미터가 필요합니다."
        }, ensure_ascii=False)

    # ── 계획서 파일 읽기 ──
    file_path = _Path(plan_file)
    if not file_path.is_absolute():
        base = _Path(project_path) if project_path and project_path != "." else DATA_PATH
        file_path = base / plan_file

    if not file_path.exists():
        return json.dumps({
            "success": False,
            "error": f"계획서 파일을 찾을 수 없습니다: {file_path}"
        }, ensure_ascii=False)

    resolved_path = str(file_path)
    try:
        plan_content = file_path.read_text(encoding='utf-8')
    except Exception as e:
        return json.dumps({
            "success": False,
            "error": f"계획서 파일 읽기 실패: {e}"
        }, ensure_ascii=False)

    # ── 계획서 파싱: 다음 실행할 단계 찾기 ──
    steps = _parse_plan_steps(plan_content)
    if not steps:
        return json.dumps({
            "success": False,
            "error": "계획서에서 단계를 파싱할 수 없습니다."
        }, ensure_ascii=False)

    # 상태가 "대기"인 가장 빠른 단계 찾기
    next_step = None
    for step in steps:
        if step["status"] == "대기":
            next_step = step
            break

    if not next_step:
        # 모든 단계가 완료/실패됨
        completed = sum(1 for s in steps if s["status"] == "완료")
        failed = sum(1 for s in steps if s["status"] == "실패")
        return json.dumps({
            "success": True,
            "message": f"작업계획서의 모든 단계가 이미 처리됨 (완료: {completed}, 실패: {failed}, 전체: {len(steps)})",
            "plan_file": resolved_path,
            "all_done": True
        }, ensure_ascii=False)

    step_num = next_step["number"]
    step_title = next_step["title"]
    target_project_id = next_step["project_id"]
    target_agent_id = next_step["agent_id"]
    description = next_step["description"]
    pipeline = next_step["pipeline"]

    print(f"[ExecutePlan] 단계 {step_num}/{len(steps)}: {step_title} → {target_project_id}/{target_agent_id}")

    # ── 담당 에이전트 검증 ──
    if not target_project_id or not target_agent_id:
        _update_plan_status(resolved_path, step_num, "실패",
                            result_text="담당 에이전트가 지정되지 않음 (agent_project_id/agent_id 누락)")
        return json.dumps({
            "success": False,
            "error": f"단계 {step_num}({step_title}): 담당 에이전트가 지정되지 않았습니다. "
                     f"(project='{target_project_id}', agent='{target_agent_id}'). "
                     f"작업계획서를 다시 작성해주세요. "
                     f"search_guide('작업계획서')로 가이드를 참고하세요.",
            "plan_file": resolved_path,
            "step": step_num
        }, ensure_ascii=False)

    # ── 상태를 "진행중"으로 업데이트 ──
    _update_plan_status(resolved_path, step_num, "진행중")

    # ── 에이전트에게 보낼 메시지 구성 (이 단계의 지시사항만) ──
    msg_parts = []
    msg_parts.append(f"## 작업 지시: {step_title}")
    msg_parts.append(f"(작업계획서 '{_Path(resolved_path).stem}' — 단계 {step_num}/{len(steps)})\n")

    if description:
        msg_parts.append(f"### 해야 할 일")
        msg_parts.append(description)
        msg_parts.append("")

    if pipeline:
        msg_parts.append(f"### 실행할 코드")
        msg_parts.append(f"```ibl\n{pipeline}\n```")
        msg_parts.append("")

    if extra_context:
        msg_parts.append(f"### 이전 단계 결과")
        msg_parts.append(extra_context)
        msg_parts.append("")

    msg_parts.append("작업을 완료하면 결과를 보고해주세요.")
    user_message = "\n".join(msg_parts)

    # ── 레지스트리에 현재 단계 등록 (완료 콜백용) ──
    effective_project = target_project_id or "__self__"
    effective_agent = target_agent_id or "__self__"
    register_plan_step(effective_project, effective_agent,
                       resolved_path, step_num, len(steps))

    # ── 담당 에이전트에게 보이는 실행으로 전달 ──
    try:
        from calendar_manager import get_calendar_manager
        cm = get_calendar_manager()

        if not target_project_id or not target_agent_id:
            # 담당 에이전트 정보가 없으면 현재 프로젝트/에이전트로 실행
            is_system_ai = (not project_path or project_path == "." or
                            project_path == str(DATA_PATH))
            if is_system_ai:
                result = cm._execute_visible_system_ai(user_message, {})
            else:
                pp = _Path(project_path)
                result = cm._execute_visible_agent(
                    pp.name, agent_id or "", user_message, {})
        else:
            result = cm._execute_visible_agent(
                target_project_id, target_agent_id, user_message, {})

        if not result.get("success"):
            # 보이는 실행 실패 → 레지스트리 해제, 상태 복원
            with _plan_steps_lock:
                _active_plan_steps.pop((effective_project, effective_agent), None)
            _update_plan_status(resolved_path, step_num, "대기")
            return json.dumps({
                "success": False,
                "error": f"단계 {step_num} 실행 실패: {result.get('error', '알 수 없음')}",
                "plan_file": resolved_path,
                "step": step_num,
                "step_title": step_title
            }, ensure_ascii=False)

        # ── 성공: fire-and-forget으로 에이전트에게 전달됨.
        # 에이전트 완료 시 handle_chat_message_stream → on_agent_plan_step_complete()
        # 콜백이 자동으로 상태 업데이트 및 다음 단계 트리거.
        return json.dumps({
            "success": True,
            "visible": True,
            "plan_file": resolved_path,
            "current_step": step_num,
            "total_steps": len(steps),
            "step_title": step_title,
            "target": f"{target_project_id}/{target_agent_id}",
            "message": f"단계 {step_num}/{len(steps)} '{step_title}'을(를) {target_project_id}/{target_agent_id} 에이전트에게 전달했습니다. 해당 프로젝트 창에서 실행 중입니다."
        }, ensure_ascii=False)

    except Exception as e:
        import traceback
        traceback.print_exc()
        # 레지스트리 해제 및 상태 복원
        with _plan_steps_lock:
            _active_plan_steps.pop((effective_project, effective_agent), None)
        _update_plan_status(resolved_path, step_num, "대기")
        return json.dumps({
            "success": False,
            "error": f"계획서 실행 실패: {e}"
        }, ensure_ascii=False)


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
    """Phase 17: Anthropic 형식의 도구 정의 (execute_ibl 단일)"""
    return get_all_system_ai_tools()  # 이미 올바른 형식


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

    # 최근 대화 히스토리 로드 (조회 + 역할 매핑 + Observation Masking 통합)
    history = get_history_for_ai(limit=7)

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
