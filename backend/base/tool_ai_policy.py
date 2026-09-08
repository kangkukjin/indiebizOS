"""사용자가 선택한 에이전트 도구 원샷 실험 정책. 앱·인지 루프 자체와 구별한다."""
import json
from contextlib import contextmanager

from runtime_utils import get_base_path
from thread_context import get_call_channel, get_tool_ai_scope, set_tool_ai_scope


def agent_tool_ai_allowed():
    path = get_base_path() / "data" / "agent_tool_policy.json"
    try:
        policy = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return True  # 미설정 설치는 기존 동작.
    except (OSError, ValueError):
        return False  # 설정이 손상됐다고 차단을 조용히 풀지 않는다.
    return policy.get("allow_agent_tool_oneshot", True) is True


def tool_ai_blocked():
    scope = get_tool_ai_scope()
    return bool(scope and scope.get("blocked"))


def blocked_result(node="", action=""):
    return {
        "success": False,
        "blocked": True,
        "error_type": "tool_ai_policy",
        "error": "사용자가 설정한 비교 실험으로 자율주행 도구 안의 추가 AI 호출이 차단되었습니다. "
                 "현재 실행 모델이 자료를 직접 판단하고 일반 IBL로 후속 처리를 수행하세요. "
                 "다른 도구·스크립트·위임으로 추가 AI 호출을 우회하지 마세요.",
        "action": f"{node}:{action}",
    }


class ToolAIBlocked(RuntimeError):
    """원샷을 모델 획득 전에 차단. 공급자 오류/빈 응답과 혼동하지 않는다."""


def require_tool_ai_allowed():
    if tool_ai_blocked():
        from episode_logger import record_trajectory_event
        scope = get_tool_ai_scope()
        record_trajectory_event("ai.policy_blocked", dict(scope))
        raise ToolAIBlocked(blocked_result()["error"])


@contextmanager
def tool_ai_scope(node, action, agent_id=None):
    previous = get_tool_ai_scope()
    # 자식이 channel을 바꿔도 부모의 제한을 풀 수 없다. 스레드 snapshot/restore로 전파.
    channel = get_call_channel() or ("agent" if agent_id else None)
    blocked = (previous.get("blocked") if previous is not None else
               channel == "agent" and not agent_tool_ai_allowed())
    set_tool_ai_scope({"blocked": bool(blocked), "node": node, "action": action})
    try:
        yield
    finally:
        set_tool_ai_scope(previous)


def prompt_notice():
    return (
        "<tool_ai_policy>사용자가 선택한 비교 실험: 자율주행 IBL 도구 내부의 추가 AI 호출은 "
        "사용할 수 없다. AI 호출 액션은 아래 카탈로그에서 제외되어 있다. "
        "criteria에 의한 도구 결과 AI 심사도 사용할 수 없다. 자료의 의미 판단·선별·요약은 "
        "현재 실행 모델이 직접 하고, 일반 IBL로 자료 조회·계산·저장을 수행한다. "
        "가이드나 과거 관용구에 AI 단계가 있어도 이번 실행에서는 해당 단계를 직접 판단한다. "
        "다른 도구·스크립트·위임으로 추가 AI 호출을 우회하지 않는다.</tool_ai_policy>"
    )
