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
from typing import Dict, Any, Optional, List

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
# 하드캡 요약 체크포인트 — 임포트 부작용으로 datastore 훅 등록(install(), 의존 역전)
import history_checkpoint  # noqa: F401

# 경로 설정
BACKEND_PATH = Path(__file__).parent.parent
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

# 역할 전환 시 원자적으로 옮겨야 하는 실행 컨텍스트 필드 묶음 (2026-08-14 원자화).
# 옛날엔 두 스왑 함수가 각자 필드를 개별 대입해 목록이 표류했다 — 과거 agent_id 누락이
# "identity 없음"을 실제로 냈다(아래 주석 유래). 이제 이 튜플이 단일 진실이고,
# 스왑 함수 둘 다 _carry_context 하나를 쓴다.
_CONTEXT_FIELDS = ("system_prompt", "tools", "agent_id", "project_path", "agent_name")


def _carry_context(target, source):
    """실행 컨텍스트 묶음을 source provider → target provider 로 원자적으로 복사.

    - agent_id: 발신 신원 — target 이 spawn 하는 subprocess(claude)가 시스템 AI
      신원(agent_id="system_ai")을 갖고 가야 channel_send/read 게이트를 통과한다.
      (agent_communication.py 프로젝트AI 전환과 동일. 빠지면 identity 유실.)
    - Gemini 계열은 도구 캐시 재구축까지가 전환의 일부."""
    for f in _CONTEXT_FIELDS:
        setattr(target, f, getattr(source, f))
    if hasattr(target, '_cached_gemini_tools') and target.tools:
        try:
            from google.genai import types
            target._cached_gemini_tools = [types.Tool(function_declarations=target._convert_tools())]
        except Exception:
            pass


def _record_switch(role: str, provider):
    """역할 전환을 스텝 원장에 기록 + 역할 태그 설정 — 어느 프롬프트·모델로 돌았는지의
    사후 추적이 로그 텍스트 grep 이 아니라 구조화 기록으로 남는다."""
    try:
        from episode_logger import record_role_switch, set_step_role
        record_role_switch(role, type(provider).__name__.replace("Provider", ""),
                           getattr(provider, "model", "?"))
        set_step_role(role)
    except Exception:
        pass


def _switch_to_midtier(runner):
    """reflex(해마 고확신) 경로에서 중급 모델로 provider 전환. 전환 성공 시 원래 provider 반환."""
    try:
        from consciousness_agent import _get_midtier_provider
        midtier = _get_midtier_provider()
        if midtier is None:
            return None  # 중급 설정 없으면 본격 모델 유지

        # ★캐시 공유 객체를 그대로 변이하지 않는다 (2026-08-31): model_resolver 는
        # provider 를 (프로바이더|모델|키) 로 캐시한다 — 같은 티어로 스왑하는 동시 턴이
        # 같은 객체를 받는다. 거기에 _carry_context 로 system_prompt·agent_id 를 쓰면
        # 서로의 신원·프롬프트를 덮는다. 턴 사유 사본에 실어 옮긴다.
        from agent_pipeline import per_turn_provider_view
        midtier = per_turn_provider_view(midtier)
        original_provider = runner.ai._provider
        _carry_context(midtier, original_provider)
        runner.ai._provider = midtier
        _record_switch("reflex-midtier", midtier)
        print(f"[시스템AI] 중급 모델로 전환: {midtier.model}")
        return original_provider
    except Exception as e:
        print(f"[시스템AI] 중급 모델 전환 실패 (본격 모델 유지): {e}")
        return None


def _restore_provider(runner, original_provider):
    """원래 provider로 복원 (+역할 태그 원복)"""
    if original_provider is not None:
        runner.ai._provider = original_provider
        try:
            from episode_logger import set_step_role
            set_step_role("")
        except Exception:
            pass


def _switch_to_role(runner, role, agent_id: str = None):
    """지정 역할(예: 'forage')로 해소된 provider 로 전환 — _switch_to_midtier 의 일반화.

    model_resolver 가 role → 티어 → 모델로 해소(forage 는 기본 경량, 계기판 override 로 변경).
    현재 provider 의 실행 컨텍스트 묶음(_CONTEXT_FIELDS)을 원자적으로 옮겨
    IBL 도구를 그대로 쓰게 한다. 전환 성공 시 원래 provider 반환(호출 측이 finally 에서 복원).

    agent_id: 역할보다 우선하는 구체 핀(model_gear.overrides 의 키). 위임 경로가
    'system_ai_delegation' 핀을 파이프라인 바깥에서 걸 때 쓴다 — 파이프라인 안쪽의
    THINK/REPAIR 스왑은 진입 시점 provider 로 복원하므로 바깥 핀과 겹쳐도 안전하다."""
    try:
        from model_resolver import get_provider_for
        prov, d = get_provider_for(role, agent_id=agent_id, oneshot=False)
        if prov is None:
            return None  # 해당 티어 설정/키 없음 → 기존(본격) 모델 유지
        # 캐시 공유 객체 변이 금지 — _switch_to_midtier 의 같은 주석 참조.
        from agent_pipeline import per_turn_provider_view
        prov = per_turn_provider_view(prov)
        cur = runner.ai._provider
        _carry_context(prov, cur)
        runner.ai._provider = prov
        _record_switch(role, prov)
        print(f"[{role}] 모델 전환: {d.get('model')} ({d.get('source')})")
        return cur
    except Exception as e:
        print(f"[{role}] 모델 전환 실패 (기존 모델 유지): {e}")
        return None


# ============ 메시지 처리 (AgentRunner 인지 파이프라인 사용) ============

def process_system_ai_message(message: str, history: List[Dict] = None, images: List[Dict] = None,
                              action_hint: str = None, extra_role: str = "", force_role: str = "",
                              allowed_set=None):
    """시스템 AI 메시지 처리 (동기 모드) — cognitive_stream을 drain하는 블로킹 어댑터.

    인지 오케스트레이션(연상→분류→의식→실행→평가→반성→증류)은 전부
    runner.cognitive_stream(agent_pipeline.py) 안에서 일어난다. 블로킹 경로가
    내부적으로 스트림을 소비해 최종 응답만 취하므로, 반성 등 파이프라인 기능을
    스트림 경로와 자동 공유한다(Task B 통합).

    Args:
        action_hint: 마법책에서 사용자가 명시적으로 선택한 액션 ID ("sense:price" 등).
        force_role: 표면 강제 EXECUTE(포식 등) — 분류·의식 건너뛰고 지정 모델로 실행.

    Returns:
        (response_text, tool_images)
    """
    from agent_pipeline import drain_stream
    runner = get_system_ai_runner()
    result = drain_stream(runner.cognitive_stream(
        message, history or [],
        images=images, action_hint=action_hint,
        extra_role=extra_role, force_role=force_role, allowed_set=allowed_set,
    ))
    response = result["final"]
    if not response and result.get("error"):
        response = f"AI 응답 생성 실패: {result['error']}"
    if result.get("clarify") or result.get("session_reset"):
        # 실행 에이전트 미호출 — 이전 턴 잔여 도구 이미지가 새어들지 않게 빈 목록
        return response, []
    tool_images = runner.ai.get_last_tool_images()
    return response, tool_images


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
    - base_prompt_v6.md + (조건부 git) + 위임 프롬프트 + 개별역할 + 시스템메모
    """
    return build_system_ai_prompt(user_profile=user_profile, git_enabled=git_enabled)


def get_anthropic_tools():
    """Phase 17: Anthropic 형식의 도구 정의 (execute_ibl 단일)"""
    return get_all_system_ai_tools()  # 이미 올바른 형식
