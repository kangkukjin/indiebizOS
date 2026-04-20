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


# ============ AgentRunner 기반 통합 ============

_system_ai_runner = None  # 싱글턴


def get_system_ai_runner():
    """시스템 AI용 AgentRunner 싱글턴 반환.

    프로젝트 에이전트와 동일한 인지 파이프라인(무의식→의식→실행→평가)을 사용.
    차이점은 config의 _is_system_ai 플래그로 분기: 도구/프롬프트/권한만 다름.
    """
    global _system_ai_runner

    if _system_ai_runner is not None and _system_ai_runner.ai is not None:
        # 설정 변경 시 재생성 (provider/model 변경 감지)
        config = load_system_ai_config()
        current_ai = _system_ai_runner.config.get("ai", {})
        if (current_ai.get("provider") != config.get("provider") or
            current_ai.get("model") != config.get("model")):
            _system_ai_runner = None
        else:
            return _system_ai_runner

    from agent_runner import AgentRunner

    config = load_system_ai_config()
    agent_config = {
        "id": "system_ai",
        "name": "시스템 AI",
        "_project_path": str(DATA_PATH),
        "_project_id": "system",
        "_is_system_ai": True,
        "type": "internal",
        "allowed_nodes": None,  # 전체 접근
        "ai": {
            "provider": config.get("provider", "anthropic"),
            "model": config.get("model", "claude-sonnet-4-20250514"),
            "api_key": config.get("apiKey", "")
        }
    }

    runner = AgentRunner(agent_config)
    runner._init_ai()
    runner.running = True
    _system_ai_runner = runner
    print(f"[시스템AI] AgentRunner 초기화 완료 (provider={config.get('provider')}, model={config.get('model')})")
    return runner


def create_system_ai_agent(config: dict = None, user_profile: str = "") -> AIAgent:
    """시스템 AI용 AIAgent 인스턴스 반환 (하위 호환)"""
    runner = get_system_ai_runner()
    return runner.ai


# ============ 중급 모델 전환 헬퍼 ============

def _switch_to_midtier(runner):
    """EXECUTE/reflex 경로에서 중급 모델로 provider 전환. 전환 성공 시 원래 provider 반환."""
    try:
        from consciousness_agent import _get_midtier_provider
        midtier = _get_midtier_provider()
        if midtier is None:
            return None  # 중급 설정 없으면 본격 모델 유지

        original_provider = runner.ai._provider
        # 중급 provider에 현재 시스템 프롬프트와 도구 설정 복사
        midtier.system_prompt = runner.ai._provider.system_prompt
        midtier.tools = runner.ai._provider.tools

        # Gemini provider의 경우 도구 캐시 재구축
        if hasattr(midtier, '_cached_gemini_tools') and midtier.tools:
            try:
                from google.genai import types
                midtier._cached_gemini_tools = [types.Tool(function_declarations=midtier._convert_tools())]
            except Exception:
                pass

        runner.ai._provider = midtier
        print(f"[시스템AI] 중급 모델로 전환: {midtier.model}")
        return original_provider
    except Exception as e:
        print(f"[시스템AI] 중급 모델 전환 실패 (본격 모델 유지): {e}")
        return None


def _restore_provider(runner, original_provider):
    """원래 provider로 복원"""
    if original_provider is not None:
        runner.ai._provider = original_provider


# ============ 메시지 처리 (AgentRunner 인지 파이프라인 사용) ============

def process_system_ai_message(message: str, history: List[Dict] = None, images: List[Dict] = None):
    """시스템 AI 메시지 처리 (동기 모드, AgentRunner 인지 파이프라인)

    Returns:
        (response_text, tool_images)
    """
    runner = get_system_ai_runner()

    # 인지 파이프라인: 실행기억 → 무의식 → 의식 → 프롬프트 갱신
    execution_memory = runner._build_execution_memory(message)

    request_type, reflex_hint = runner._classify_request(message, execution_memory)
    print(f"[시스템AI 무의식] 분류: {request_type}")

    consciousness_output = None
    original_provider = None
    if request_type == "THINK":
        consciousness_output = runner._run_consciousness(message, history or [], execution_memory)
    else:
        # EXECUTE/reflex: 중급 모델로 전환
        original_provider = _switch_to_midtier(runner)

    # 프롬프트 갱신
    role = runner._load_role()
    if consciousness_output or execution_memory or reflex_hint:
        _exec_mem = execution_memory
        if reflex_hint:
            _exec_mem = f"{execution_memory}\n\n[Reflex 매칭] {reflex_hint}" if execution_memory else f"[Reflex 매칭] {reflex_hint}"
        new_prompt = runner._build_system_prompt(role, consciousness_output, _exec_mem)
        runner.ai.system_prompt = new_prompt
        runner.ai._provider.system_prompt = new_prompt

    # 히스토리 편집
    history = runner._apply_consciousness_to_history(history or [], consciousness_output)

    try:
        response = runner.ai.process_message_with_history(
            message_content=message,
            history=history,
            images=images
        )
    finally:
        # 중급 모델 사용 후 원래 provider 복원
        _restore_provider(runner, original_provider)

    # 평가 루프 — 달성 기준이 있으면 실행
    if consciousness_output and response:
        criteria = runner._extract_achievement_criteria(consciousness_output)
        if criteria:
            from world_pulse import _load_config as _load_wp_config
            _goal_cfg = _load_wp_config().get("goal_eval", {})
            if _goal_cfg.get("enabled", True):
                print(f"[GoalEval] 달성 기준 감지: {criteria[:80]}")
                evaluated = runner._run_goal_evaluation_loop(
                    user_message=message,
                    criteria=criteria,
                    initial_response=response,
                    history=history,
                    consciousness_output=consciousness_output,
                    max_rounds=_goal_cfg.get("max_rounds", 3),
                    execution_memory=execution_memory,
                )
                if evaluated and evaluated.strip():
                    response = evaluated

    tool_images = runner.ai.get_last_tool_images()
    return response, tool_images


def process_system_ai_message_stream(
    message: str,
    history: List[Dict] = None,
    images: List[Dict] = None,
    cancel_check: Callable = None
) -> Generator:
    """시스템 AI 메시지 처리 (스트리밍 모드, AgentRunner 인지 파이프라인)

    Yields:
        스트리밍 이벤트 딕셔너리

    Note:
        평가 루프는 api_websocket.py의 시스템 AI 핸들러에서 처리
        (프로젝트 에이전트와 동일한 패턴)
    """
    runner = get_system_ai_runner()

    # 인지 파이프라인: 실행기억 → 무의식 → 의식 → 프롬프트 갱신
    execution_memory = runner._build_execution_memory(message)

    request_type, reflex_hint = runner._classify_request(message, execution_memory)
    print(f"[시스템AI 무의식] 분류: {request_type}")

    consciousness_output = None
    original_provider = None
    if request_type == "THINK":
        consciousness_output = runner._run_consciousness(message, history or [], execution_memory)
    else:
        # EXECUTE/reflex: 중급 모델로 전환
        original_provider = _switch_to_midtier(runner)

    # 프롬프트 갱신
    role = runner._load_role()
    if consciousness_output or execution_memory or reflex_hint:
        _exec_mem = execution_memory
        if reflex_hint:
            _exec_mem = f"{execution_memory}\n\n[Reflex 매칭] {reflex_hint}" if execution_memory else f"[Reflex 매칭] {reflex_hint}"
        new_prompt = runner._build_system_prompt(role, consciousness_output, _exec_mem)
        runner.ai.system_prompt = new_prompt
        runner.ai._provider.system_prompt = new_prompt

    # 히스토리 편집
    history = runner._apply_consciousness_to_history(history or [], consciousness_output)

    # 스트리밍 실행 — 이벤트를 중간 수집하면서 yield
    # consciousness_output을 메타데이터로 첫 이벤트에 첨부 (평가 루프용)
    if consciousness_output:
        yield {"type": "_consciousness_output", "data": consciousness_output,
               "execution_memory": execution_memory}

    try:
        yield from runner.ai.process_message_stream(
            message_content=message,
            history=history,
            images=images,
            cancel_check=cancel_check
        )
    finally:
        # 중급 모델 사용 후 원래 provider 복원
        _restore_provider(runner, original_provider)


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
