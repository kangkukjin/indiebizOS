"""
system_ai_core.py - 시스템 AI 핵심 처리 모듈
IndieBiz OS Core

시스템 AI의 핵심 로직을 담당하는 모듈입니다:
- 설정 로드/저장
- AIAgent 인스턴스 생성
- 인지 아키텍처 (무의식/의식/평가) 처리
- 메시지 처리 (동기/스트리밍)
- 도구 실행
- 시스템 프롬프트 및 도구 정의

api_system_ai.py에서 분리된 코어 함수들로 구성됩니다.
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional, List, Generator, Callable

# 메모리 관련
from system_ai_memory import (
    load_user_profile,
)
# Phase 17: execute_ibl 단일 도구 (기존 패키지 로딩 제거)
from tool_loader import load_tool_schema
# 통합: AIAgent 클래스 사용
from ai_agent import AIAgent
# 통합: 프롬프트 빌더 사용
from prompt_builder import build_system_ai_prompt

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


def save_system_ai_config(config: dict):
    """시스템 AI 설정 저장"""
    with open(SYSTEM_AI_CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


# 도구 관련 — system_ai_tools.py에서 가져옴
from system_ai_tools import get_all_system_ai_tools


# ============ 에이전트 생성 ============

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
        git_enabled=git_enabled,
        model_name=ai_config.get("model", ""),
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


# ============ 인지 아키텍처 ============

def _build_execution_memory_for_system_ai(message: str) -> str:
    """시스템 AI용 실행기억 생성"""
    try:
        from ibl_usage_rag import build_execution_memory
        result = build_execution_memory(message, allowed_nodes=None)  # 시스템 AI는 전체 노드
        if not result:
            print(f"[시스템AI 실행기억] 빈 결과: \"{message[:40]}\"")
        return result
    except Exception as e:
        print(f"[시스템AI 실행기억] 생성 실패: {e}")
        return ""


def _classify_system_ai_request(message: str, execution_memory: str = "") -> str:
    """시스템 AI용 무의식 에이전트 — 실행형/판단형 분류"""
    try:
        from consciousness_agent import lightweight_ai_call, get_unconscious_prompt

        system_prompt = get_unconscious_prompt()
        input_message = message
        if execution_memory:
            input_message = f"{execution_memory}\n\n{message}"
        response = lightweight_ai_call(input_message, system_prompt=system_prompt)

        if response is None:
            return "THINK"

        result = response.strip().upper()
        if "EXECUTE" in result:
            return "EXECUTE"
        return "THINK"

    except Exception as e:
        print(f"[시스템AI 무의식] 분류 실패: {e}")
        return "THINK"


def _run_consciousness_for_system_ai(message: str, history: List[Dict] = None,
                                     execution_memory: str = "") -> dict:
    """시스템 AI용 의식 에이전트 실행"""
    try:
        from consciousness_agent import (
            get_consciousness_agent,
            get_guide_list,
            get_world_pulse_text,
        )
        agent = get_consciousness_agent()
        if not agent.is_ready:
            return None

        # 시스템 AI 역할 전문 로드
        role_path = DATA_PATH / "system_ai_role.txt"
        agent_role = role_path.read_text(encoding='utf-8').strip() if role_path.exists() else "IndieBiz OS의 관리자이자 안내자"

        # 사용자 프로필 (시스템 AI의 영구메모에 해당)
        agent_notes = load_user_profile()

        return agent.process(
            user_message=message,
            history=history or [],
            ibl_node_summary=execution_memory,  # 실행기억으로 대체
            guide_list=get_guide_list(message),
            world_pulse=get_world_pulse_text(),
            agent_name="시스템 AI",
            agent_role=agent_role,
            agent_notes=agent_notes,
        )
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"[SystemAI 의식] 실행 실패: {e}")
        return None


def _apply_consciousness(agent, message: str, history: List[Dict],
                         consciousness_output: dict, execution_memory: str = ""):
    """의식 에이전트 결과를 시스템 AI에 적용 — 프롬프트 갱신 + 히스토리 편집"""
    if not consciousness_output and not execution_memory:
        return history

    # 시스템 프롬프트 재구성
    user_profile = load_user_profile()
    git_enabled = (DATA_PATH / ".git").exists()

    from prompt_builder import build_system_ai_prompt
    config = load_system_ai_config()
    new_prompt = build_system_ai_prompt(
        user_profile=user_profile,
        git_enabled=git_enabled,
        consciousness_output=consciousness_output,
        model_name=config.get("model", ""),
        execution_memory=execution_memory,
    )
    agent.system_prompt = new_prompt
    if agent._provider:
        agent._provider.system_prompt = new_prompt

    # 히스토리 편집
    if consciousness_output:
        history_summary = consciousness_output.get("history_summary", "")
        if history_summary:
            return [{"role": "user", "content": f"[이전 대화 요약: {history_summary}]"}]
    return history


# ============ 메시지 처리 ============

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

    # 실행기억 생성 (1회)
    execution_memory = _build_execution_memory_for_system_ai(message)

    # 무의식 에이전트 — 실행형/판단형 분류 (반사 신경)
    request_type = _classify_system_ai_request(message, execution_memory)
    print(f"[시스템AI 무의식] 분류: {request_type}")

    consciousness_output = None
    if request_type == "THINK":
        consciousness_output = _run_consciousness_for_system_ai(
            message, history, execution_memory
        )
    # 실행기억 + 의식출력을 시스템 프롬프트에 반영
    history = _apply_consciousness(
        agent, message, history or [], consciousness_output, execution_memory
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

    # 실행기억 생성 (1회)
    execution_memory = _build_execution_memory_for_system_ai(message)

    # 무의식 에이전트 — 실행형/판단형 분류 (반사 신경)
    request_type = _classify_system_ai_request(message, execution_memory)
    print(f"[시스템AI 무의식] 분류: {request_type}")

    consciousness_output = None
    if request_type == "THINK":
        consciousness_output = _run_consciousness_for_system_ai(
            message, history, execution_memory
        )
    # 실행기억 + 의식출력을 시스템 프롬프트에 반영
    history = _apply_consciousness(
        agent, message, history or [], consciousness_output, execution_memory
    )

    yield from agent.process_message_stream(
        message_content=message,
        history=history,
        images=images,
        cancel_check=cancel_check
    )


# ============ 도구 실행 ============

def execute_system_tool(tool_name: str, tool_input: dict, work_dir: str = None, agent_id: str = None, **kwargs) -> str:
    """Phase 17: 시스템 AI 도구 실행 (execute_ibl 단일 경로)

    Args:
        tool_name: 도구 이름 (execute_ibl)
        tool_input: 도구 입력
        work_dir: 작업 디렉토리
        agent_id: 에이전트 ID
        **kwargs: 프로바이더가 전달하는 추가 인자 (cancel_check 등)
    """
    from system_tools import execute_tool
    return execute_tool(
        tool_name, tool_input,
        project_path=work_dir or str(DATA_PATH),
        agent_id=agent_id or "system_ai"
    )


# ============ 프롬프트 및 도구 정의 ============

def get_system_prompt(user_profile: str = "", git_enabled: bool = False) -> str:
    """시스템 AI의 시스템 프롬프트 (prompt_builder.py 사용)

    **통합**: 이제 공통 프롬프트 빌더를 사용합니다.
    - base_prompt_v2.md + (조건부 git) + 위임 프롬프트 + 개별역할 + 시스템메모
    """
    return build_system_ai_prompt(user_profile=user_profile, git_enabled=git_enabled)


def get_anthropic_tools():
    """Phase 17: Anthropic 형식의 도구 정의 (execute_ibl 단일)"""
    return get_all_system_ai_tools()  # 이미 올바른 형식
