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


def _resolve_system_ai_config() -> dict:
    """시스템 AI 모델 설정을 모델 기어 'system_ai' 역할(실행 축)로 해소.

    과거엔 system_ai_config.json 을 직접 읽었으나, 이제 리졸버가 현재 기어→실행 축→티어로
    모델을 정한다(기어 프리셋이 시스템AI를 중급/고급으로 가를 수 있음). 리졸버 실패/모델
    미설정 시 옛 system_ai_config 로 폴백(동작 보존)."""
    try:
        from model_resolver import resolve
        d = resolve("system_ai")
        if d.get("model"):
            return {
                "provider": d.get("provider", "anthropic"),
                "model": d["model"],
                "api_key": d.get("api_key", ""),
                "_source": d.get("source", ""),
            }
    except Exception as e:
        print(f"[시스템AI] 기어 해소 실패(옛 config 폴백): {e}")
    config = load_system_ai_config()
    return {
        "provider": config.get("provider", "anthropic"),
        "model": config.get("model", "claude-sonnet-4-20250514"),
        "api_key": config.get("apiKey", ""),
        "_source": "system_ai_config(fallback)",
    }


def get_system_ai_runner():
    """시스템 AI용 AgentRunner 싱글턴 반환.

    프로젝트 에이전트와 동일한 인지 파이프라인(무의식→의식→실행→평가)을 사용.
    차이점은 config의 _is_system_ai 플래그로 분기: 도구/프롬프트/권한만 다름.
    모델은 모델 기어 'system_ai' 역할(실행 축)로 해소 — 기어/설정 변경 시 자동 재생성.
    """
    global _system_ai_runner

    resolved = _resolve_system_ai_config()

    if _system_ai_runner is not None and _system_ai_runner.ai is not None:
        # 기어/설정 변경 시 재생성 (해소된 provider/model 변경 감지)
        current_ai = _system_ai_runner.config.get("ai", {})
        if (current_ai.get("provider") != resolved["provider"] or
            current_ai.get("model") != resolved["model"]):
            _system_ai_runner = None
        else:
            return _system_ai_runner

    from agent_runner import AgentRunner

    agent_config = {
        "id": "system_ai",
        "name": "시스템 AI",
        "_project_path": str(DATA_PATH),
        "_project_id": "system",
        "_is_system_ai": True,
        "type": "internal",
        "allowed_nodes": None,  # 전체 접근
        "ai": {
            "provider": resolved["provider"],
            "model": resolved["model"],
            "api_key": resolved["api_key"],
        }
    }

    runner = AgentRunner(agent_config)
    runner._init_ai()
    runner.running = True
    _system_ai_runner = runner
    print(f"[시스템AI] AgentRunner 초기화 완료 ({resolved['provider']}/{resolved['model']}, {resolved.get('_source')})")
    return runner


def reset_system_ai_runner():
    """시스템 AI 러너 싱글턴 초기화 — 기어/설정 변경 시 호출(다음 호출에서 새 티어로 재구성)."""
    global _system_ai_runner
    _system_ai_runner = None


def create_system_ai_agent(config: dict = None, user_profile: str = "") -> AIAgent:
    """시스템 AI용 AIAgent 인스턴스 반환 (하위 호환)"""
    runner = get_system_ai_runner()
    return runner.ai


# ============ 중급 모델 전환 헬퍼 ============

def _switch_to_midtier(runner):
    """reflex(해마 고확신) 경로에서 중급 모델로 provider 전환. 전환 성공 시 원래 provider 반환."""
    try:
        from consciousness_agent import _get_midtier_provider
        midtier = _get_midtier_provider()
        if midtier is None:
            return None  # 중급 설정 없으면 본격 모델 유지

        original_provider = runner.ai._provider
        # 중급 provider에 현재 시스템 프롬프트와 도구 설정 복사
        midtier.system_prompt = runner.ai._provider.system_prompt
        midtier.tools = runner.ai._provider.tools
        # 발신 신원·컨텍스트도 복사 — 중급 provider가 spawn하는 subprocess(claude)가
        # 시스템 AI 신원(agent_id="system_ai")을 갖고 가야 channel_send/read 게이트를 통과한다.
        # (agent_communication.py의 프로젝트AI 전환과 동일. 빠지면 EXECUTE 경로에서 identity 유실 → "identity 없음".)
        midtier.agent_id = runner.ai._provider.agent_id
        midtier.project_path = runner.ai._provider.project_path
        midtier.agent_name = runner.ai._provider.agent_name

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


def _switch_to_role(runner, role):
    """지정 역할(예: 'forage')로 해소된 provider 로 전환 — _switch_to_midtier 의 일반화.

    model_resolver 가 role → 티어 → 모델로 해소(forage 는 기본 경량, 계기판 override 로 변경).
    현재 provider 의 시스템 프롬프트·도구·발신 신원을 복사해 IBL 도구를 그대로 쓰게 한다.
    전환 성공 시 원래 provider 반환(호출 측이 finally 에서 복원)."""
    try:
        from model_resolver import get_provider_for
        prov, d = get_provider_for(role, oneshot=False)
        if prov is None:
            return None  # 해당 티어 설정/키 없음 → 기존(본격) 모델 유지
        cur = runner.ai._provider
        prov.system_prompt = cur.system_prompt
        prov.tools = cur.tools
        prov.agent_id = cur.agent_id
        prov.project_path = cur.project_path
        prov.agent_name = cur.agent_name
        if hasattr(prov, '_cached_gemini_tools') and prov.tools:
            try:
                from google.genai import types
                prov._cached_gemini_tools = [types.Tool(function_declarations=prov._convert_tools())]
            except Exception:
                pass
        runner.ai._provider = prov
        print(f"[{role}] 모델 전환: {d.get('model')} ({d.get('source')})")
        return cur
    except Exception as e:
        print(f"[{role}] 모델 전환 실패 (기존 모델 유지): {e}")
        return None


# ============ 메시지 처리 (AgentRunner 인지 파이프라인 사용) ============

def process_system_ai_message(message: str, history: List[Dict] = None, images: List[Dict] = None,
                              action_hint: str = None, extra_role: str = "", force_role: str = "",
                              allowed_set=None):
    """시스템 AI 메시지 처리 (동기 모드, AgentRunner 인지 파이프라인)

    Args:
        action_hint: 마법책에서 사용자가 명시적으로 선택한 액션 ID ("sense:price" 등).
            지정되면 해마 검색 대신 그 액션을 Top-1로 <execution_memory>에 주입.

    Returns:
        (response_text, tool_images)
    """
    runner = get_system_ai_runner()

    # 인지 파이프라인: 연상 → (Reflex 또는 무의식) → 의식 → 프롬프트 갱신
    execution_memory, _hippo_score, _top_code = runner._build_execution_memory(message, action_hint=action_hint)

    # 판정: 명시 태그(#think/#execute, 무조건) → Reflex(해마 고확신) → 무의식 분류
    if force_role:
        # 포식 등 강제 EXECUTE 표면: 어차피 EXECUTE 고정 → 무의식 분류기(경량 LLM 1회 호출)를 건너뛴다.
        request_type, reflex_hint = "EXECUTE", None
        print(f"[무의식] 분류: EXECUTE (force_role={force_role} — 분류기 건너뜀)")
    else:
        request_type, reflex_hint = runner._decide_request_type(message, _hippo_score, _top_code)

    consciousness_output = None
    original_provider = None
    if force_role:
        # 포식 등 표면별 전용 에이전트: 의식(THINK) 건너뛰고 지정 모델(기본 경량)로 바로 실행 — 빠르고 싸게.
        original_provider = _switch_to_role(runner, force_role)
    elif request_type == "THINK":
        consciousness_output = runner._run_consciousness_or_reuse(message, history or [], execution_memory)
    elif reflex_hint:
        # reflex(해마 고확신)는 *경량* 모델 — "이미 찾은 답을 그대로 내보냄"이라 가장 싼 티어로 충분
        # (확정 2026-06-30). 모델 해소는 기어 'reflex' 역할이 경량 티어로 고정(model_resolver).
        # 무의식 EXECUTE 는 기어 실행 축 모델 유지.
        original_provider = _switch_to_midtier(runner)

    # Clarification fast-path — 정보 부족 시 의식이 만든 질문을 그대로 응답으로 반환.
    _clarify_text = runner._consciousness_clarification(consciousness_output) if consciousness_output else None
    if _clarify_text:
        print(f"[시스템AI 의식] clarification fast-path: 실행 에이전트 스킵")
        _restore_provider(runner, original_provider)
        return _clarify_text, []

    # 프롬프트 갱신 — 안정/가변 분리 (캐시 prefix 보존)
    role = runner._load_role()
    augmented_message = message
    if consciousness_output or execution_memory or reflex_hint or extra_role:
        _exec_mem = execution_memory
        if reflex_hint:
            _exec_mem = f"{execution_memory}\n\n[Reflex 매칭] {reflex_hint}" if execution_memory else f"[Reflex 매칭] {reflex_hint}"
        stable_prompt, dynamic_context = runner._build_system_ai_prompt_split(
            role, consciousness_output, _exec_mem, extra_role=extra_role, allowed_set=allowed_set
        )
        runner.ai.system_prompt = stable_prompt
        runner.ai._provider.system_prompt = stable_prompt
        if consciousness_output:
            # 사용자 명령 변형: [원문 명령 + 의식 보강]을 한 '사용자 명령' 프레임으로 융합.
            from prompt_builder import compile_user_command
            _fused = compile_user_command(message, consciousness_output)
            augmented_message = f"{dynamic_context}\n\n{_fused}" if dynamic_context else _fused
        elif dynamic_context:
            augmented_message = f"{dynamic_context}\n\n{message}"

    # 히스토리 편집
    history = runner._apply_consciousness_to_history(history or [], consciousness_output)

    try:
        response = runner.ai.process_message_with_history(
            message_content=augmented_message,
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
                # provider가 누적한 도구 실행 결과를 평가자에 전달
                tool_results_for_eval = runner.ai.get_last_tool_results()
                tool_calls_for_eval = (
                    runner.ai.get_last_tool_calls()
                    if hasattr(runner.ai, "get_last_tool_calls") else None
                )
                evaluated = runner._run_goal_evaluation_loop(
                    user_message=message,
                    criteria=criteria,
                    initial_response=response,
                    history=history,
                    consciousness_output=consciousness_output,
                    max_rounds=_goal_cfg.get("max_rounds", 3),
                    tool_results=tool_results_for_eval,
                    tool_calls=tool_calls_for_eval,
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
    cancel_check: Callable = None,
    action_hint: str = None,
    extra_role: str = "",
    force_role: str = "",
    allowed_set=None
) -> Generator:
    """시스템 AI 메시지 처리 (스트리밍 모드, AgentRunner 인지 파이프라인)

    Args:
        action_hint: 마법책에서 사용자가 명시적으로 선택한 액션 ID ("sense:price" 등).
            지정되면 해마 검색 대신 그 액션을 Top-1로 <execution_memory>에 주입.

    Yields:
        스트리밍 이벤트 딕셔너리

    Note:
        평가 루프는 api_websocket.py의 시스템 AI 핸들러에서 처리
        (프로젝트 에이전트와 동일한 패턴)
    """
    runner = get_system_ai_runner()

    # 인지 파이프라인: 연상 → (Reflex 또는 무의식) → 의식 → 프롬프트 갱신
    execution_memory, _hippo_score, _top_code = runner._build_execution_memory(message, action_hint=action_hint)

    # 판정: 명시 태그(#think/#execute, 무조건) → Reflex(해마 고확신) → 무의식 분류
    if force_role:
        # 포식 등 강제 EXECUTE 표면: 어차피 EXECUTE 고정 → 무의식 분류기(경량 LLM 1회 호출)를 건너뛴다.
        request_type, reflex_hint = "EXECUTE", None
        print(f"[무의식] 분류: EXECUTE (force_role={force_role} — 분류기 건너뜀)")
    else:
        request_type, reflex_hint = runner._decide_request_type(message, _hippo_score, _top_code)

    consciousness_output = None
    original_provider = None
    if force_role:
        # 포식 등 표면별 전용 에이전트: 의식(THINK) 건너뛰고 지정 모델(기본 경량)로 바로 실행 — 빠르고 싸게.
        original_provider = _switch_to_role(runner, force_role)
    elif request_type == "THINK":
        consciousness_output = runner._run_consciousness_or_reuse(message, history or [], execution_memory)
    elif reflex_hint:
        # reflex(해마 고확신)는 *경량* 모델 — "이미 찾은 답을 그대로 내보냄"이라 가장 싼 티어로 충분
        # (확정 2026-06-30). 모델 해소는 기어 'reflex' 역할이 경량 티어로 고정(model_resolver).
        # 무의식 EXECUTE 는 기어 실행 축 모델 유지.
        original_provider = _switch_to_midtier(runner)

    # Clarification fast-path — 정보 부족 시 텍스트/종료 이벤트만 흘리고 종료.
    # 평가 루프는 _consciousness_output 메타가 없으면 자동으로 안 탄다.
    _clarify_text = runner._consciousness_clarification(consciousness_output) if consciousness_output else None
    if _clarify_text:
        print(f"[시스템AI 의식] clarification fast-path: 실행 에이전트 스킵")
        _restore_provider(runner, original_provider)
        yield {"type": "text", "content": _clarify_text}
        yield {"type": "final", "content": _clarify_text}
        return

    # 프롬프트 갱신 — 안정/가변 분리 (캐시 prefix 보존)
    role = runner._load_role()
    augmented_message = message
    if consciousness_output or execution_memory or reflex_hint or extra_role:
        _exec_mem = execution_memory
        if reflex_hint:
            _exec_mem = f"{execution_memory}\n\n[Reflex 매칭] {reflex_hint}" if execution_memory else f"[Reflex 매칭] {reflex_hint}"
        stable_prompt, dynamic_context = runner._build_system_ai_prompt_split(
            role, consciousness_output, _exec_mem, extra_role=extra_role, allowed_set=allowed_set
        )
        runner.ai.system_prompt = stable_prompt
        runner.ai._provider.system_prompt = stable_prompt
        if consciousness_output:
            # 사용자 명령 변형: [원문 명령 + 의식 보강]을 한 '사용자 명령' 프레임으로 융합.
            from prompt_builder import compile_user_command
            _fused = compile_user_command(message, consciousness_output)
            augmented_message = f"{dynamic_context}\n\n{_fused}" if dynamic_context else _fused
        elif dynamic_context:
            augmented_message = f"{dynamic_context}\n\n{message}"

    # 히스토리 편집
    history = runner._apply_consciousness_to_history(history or [], consciousness_output)

    # 스트리밍 실행 — 이벤트를 중간 수집하면서 yield
    # consciousness_output을 메타데이터로 첫 이벤트에 첨부 (평가 루프용)
    if consciousness_output:
        yield {"type": "_consciousness_output", "data": consciousness_output,
               "execution_memory": execution_memory}

    try:
        yield from runner.ai.process_message_stream(
            message_content=augmented_message,
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
    - base_prompt_v5.md + (조건부 git) + 위임 프롬프트 + 개별역할 + 시스템메모
    """
    return build_system_ai_prompt(user_profile=user_profile, git_enabled=git_enabled)


def get_anthropic_tools():
    """Phase 17: Anthropic 형식의 도구 정의 (execute_ibl 단일)"""
    return get_all_system_ai_tools()  # 이미 올바른 형식
