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


# ============ Health Check 컨텍스트 ============

def set_health_check_mode(enabled: bool = True):
    """현재 스레드가 건강 체크 모드임을 표시

    SystemAI 가 건강 점검 맥락(from_agent=__health_check__)에서 실행될 때,
    IBL 액션 결과를 source=self_check 으로 기록하기 위한 플래그.
    (현 일일 건강 점검 run_daily_health_check 은 SystemAI 를 거치지 않아 이 플래그를
    켜지 않는다 — 향후 AI triage 가 다시 필요해질 때를 위한 무해한 배관으로 남겨둠.)
    """
    _thread_local.health_check_mode = enabled


def is_health_check_mode() -> bool:
    """현재 스레드가 건강 체크 모드인지 확인"""
    return getattr(_thread_local, 'health_check_mode', False)


# ============ User Input 추적 (IBL 용례 학습용) ============

def set_user_input(text: str):
    """현재 스레드의 사용자 원본 입력 저장 (IBL 실행 로그에 사용)"""
    _thread_local.user_input = text


def get_user_input() -> str:
    """현재 스레드의 사용자 원본 입력 가져오기"""
    return getattr(_thread_local, 'user_input', '')


# ============ 도구 호출 이력 (경험 증류용) ============

def append_tool_call(tool_name: str, tool_input: dict, success: bool = True,
                     node: str = "", action: str = "", duration_ms: int = 0):
    """현재 스레드의 도구 호출 이력에 추가"""
    if not hasattr(_thread_local, 'tool_calls'):
        _thread_local.tool_calls = []
    _thread_local.tool_calls.append({
        "tool_name": tool_name,
        "input": tool_input,
        "success": success,
        "node": node,
        "action": action,
        "ms": duration_ms,
    })


def get_tool_calls() -> list:
    """현재 스레드의 도구 호출 이력 반환"""
    return getattr(_thread_local, 'tool_calls', [])


def clear_tool_calls():
    """현재 스레드의 도구 호출 이력 초기화"""
    _thread_local.tool_calls = []


# ============ Goal 평가 결과 (증류 게이트용) ============
# 목표 평가 루프의 최종 판정을 증류 단계로 전달한다. 평가가 NOT_ACHIEVED로
# 끝난(=목표 미달성) 실행의 IBL 패턴을 해마에 학습하면 실패가 코퍼스에 누적되어
# 시간이 갈수록 추천 품질을 깎는다(복리 출혈). 증류 전에 이 판정을 보고 거른다.
# None = 평가 안 함(EXECUTE/Reflex 등) → 증류 허용(기존 동작).

def set_goal_eval_outcome(achieved: bool, severity: int = 0):
    """현재 스레드의 목표 평가 최종 판정 저장."""
    _thread_local.goal_eval_outcome = {"achieved": bool(achieved), "severity": int(severity)}


def get_goal_eval_outcome():
    """현재 스레드의 목표 평가 판정 반환. 평가가 없었으면 None."""
    return getattr(_thread_local, 'goal_eval_outcome', None)


def clear_goal_eval_outcome():
    """현재 스레드의 목표 평가 판정 초기화."""
    _thread_local.goal_eval_outcome = None


# ============ Allowed Nodes (IBL Node Access Control) ============

def set_allowed_nodes(allowed):
    """현재 스레드의 allowed_nodes 설정 (ibl_only 모드용)"""
    _thread_local.allowed_nodes = allowed


def get_allowed_nodes():
    """현재 스레드의 allowed_nodes 가져오기. None이면 제한 없음."""
    return getattr(_thread_local, 'allowed_nodes', None)


def snapshot() -> dict:
    """현재 스레드의 thread-local 컨텍스트 스냅샷.

    IBL 핸들러를 워커 스레드로 오프로드할 때(async 안전), agent_id/allowed_nodes/
    task_id 등 컨텍스트를 워커 스레드로 전파하기 위해 사용한다.
    threading.local은 스레드 간 자동 전파가 안 되므로 명시적으로 떠서 옮긴다.
    """
    return dict(_thread_local.__dict__)


def restore(snap: dict):
    """snapshot()으로 떠둔 컨텍스트를 현재 스레드의 thread-local에 복원."""
    for k, v in (snap or {}).items():
        setattr(_thread_local, k, v)


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
    _thread_local.tool_calls = []
    _thread_local.health_check_mode = False


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
