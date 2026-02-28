"""
thread_context.py - 스레드 로컬 컨텍스트 관리
IndieBiz OS Core

에이전트 ID, Task ID 등 스레드별 상태 관리
각 에이전트가 별도 스레드에서 실행되므로 스레드 로컬 변수로 컨텍스트 관리
"""

import threading

# 스레드 로컬 저장소
_thread_local = threading.local()


# ============ 에이전트 ID 관리 ============

def set_current_agent_id(agent_id: str):
    """현재 스레드의 에이전트 ID 설정"""
    _thread_local.agent_id = agent_id


def get_current_agent_id() -> str:
    """현재 스레드의 에이전트 ID 가져오기"""
    return getattr(_thread_local, 'agent_id', None)


def set_current_project_id(project_id: str):
    """현재 스레드의 프로젝트 ID 설정"""
    _thread_local.project_id = project_id


def get_current_project_id() -> str:
    """현재 스레드의 프로젝트 ID 가져오기"""
    return getattr(_thread_local, 'project_id', None)


def get_current_registry_key() -> str:
    """현재 스레드의 레지스트리 키 가져오기 (project_id:agent_id 형식)"""
    project_id = get_current_project_id()
    agent_id = get_current_agent_id()
    if not agent_id:
        return None
    return f"{project_id}:{agent_id}" if project_id else agent_id


def get_current_agent_name() -> str:
    """현재 스레드의 에이전트 이름 가져오기"""
    return getattr(_thread_local, 'agent_name', None)


def set_current_agent_name(name: str):
    """현재 스레드의 에이전트 이름 설정"""
    _thread_local.agent_name = name


# ============ Task ID 관리 ============

def set_current_task_id(task_id: str):
    """현재 스레드의 task_id 설정 (시스템 자동 관리)"""
    _thread_local.task_id = task_id


def get_current_task_id() -> str:
    """현재 스레드의 task_id 가져오기"""
    return getattr(_thread_local, 'task_id', None)


def clear_current_task_id():
    """현재 스레드의 task_id 초기화"""
    _thread_local.task_id = None


# ============ call_agent 호출 추적 ============

def set_called_agent(called: bool = True):
    """
    현재 스레드에서 call_agent가 호출되었음을 표시

    이 플래그는 자동 보고 로직에서 사용됨:
    - True: AI가 다른 에이전트에게 작업을 위임함 → 자동 보고 스킵 (위임받은 에이전트가 보고할 것)
    - False: AI가 직접 작업 완료 → 자동 보고 실행
    """
    _thread_local.called_agent = called


def did_call_agent() -> bool:
    """현재 스레드에서 call_agent가 호출되었는지 확인"""
    return getattr(_thread_local, 'called_agent', False)


def clear_called_agent():
    """call_agent 호출 플래그 초기화"""
    _thread_local.called_agent = False


# ============ User Input 추적 (IBL 용례 학습용) ============

def set_user_input(text: str):
    """현재 스레드의 사용자 원본 입력 저장 (IBL 실행 로그에 사용)"""
    _thread_local.user_input = text


def get_user_input() -> str:
    """현재 스레드의 사용자 원본 입력 가져오기"""
    return getattr(_thread_local, 'user_input', '')


# ============ Allowed Nodes (IBL Node Access Control) ============

def set_allowed_nodes(allowed):
    """현재 스레드의 allowed_nodes 설정 (ibl_only 모드용)"""
    _thread_local.allowed_nodes = allowed


def get_allowed_nodes():
    """현재 스레드의 allowed_nodes 가져오기. None이면 제한 없음."""
    return getattr(_thread_local, 'allowed_nodes', None)


# ============ 컨텍스트 일괄 관리 ============

def clear_all_context():
    """모든 스레드 로컬 컨텍스트 초기화"""
    _thread_local.agent_id = None
    _thread_local.agent_name = None
    _thread_local.project_id = None
    _thread_local.task_id = None
    _thread_local.called_agent = False
    _thread_local.allowed_nodes = None
    _thread_local.user_input = ''


def get_context_summary() -> dict:
    """현재 컨텍스트 요약 (디버깅용)"""
    return {
        "agent_id": get_current_agent_id(),
        "agent_name": get_current_agent_name(),
        "project_id": get_current_project_id(),
        "registry_key": get_current_registry_key(),
        "task_id": get_current_task_id(),
        "called_agent": did_call_agent(),
        "allowed_nodes": get_allowed_nodes(),
        "user_input": get_user_input()
    }
