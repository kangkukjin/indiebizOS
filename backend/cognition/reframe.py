"""턴의 현재 실행 요청을 소유하고 의식의 초기·중간 재규정을 연결한다.

실행자가 발견한 문제는 reframe으로 의식에 전달하고, 중간감사가 이미 내린 판단은
같은 채택 경로로 바로 반영한다. 요청·기준·계획을 함께 전달하며 기존 결과를 이어 쓴다.
IBL 어휘가 아닌 실행자↔의식의 통로이며 채널은 (agent_id, task_id)별이다.
"""
import copy
import json
import threading
import time
from typing import Dict, Optional
from thread_context import execution_key, snapshot, restore

MAX_REVISIONS = 2
_TTL_SECONDS = 3600 * 3   # 턴이 닫히지 않고 죽은 채널의 유령 방지

_channels: Dict[tuple, "TurnChannel"] = {}
_lock = threading.Lock()

TOOL_SCHEMA = {
    "name": "reframe",
    "description": (
        "실행 근거에 비춰 현재 요청 자체를 고쳐야 할 때 의식에게 재규정을 요청한다. "
        "전제·범위·질문이 부정확하거나 이 틀로 사용자 목적을 이룰 수 없을 때 근거를 보낸다. "
        "깨진 계획 위에 계속 짓거나 혼자 목표를 바꾸지 말 것 — 이 도구가 새 규정(문제·접근·전제·달성 기준)을 "
        "돌려주고 작업은 그 자리에서 이어진다(처음부터 다시 시작하지 않는다). "
        "사소한 오류·재시도로 풀리는 실패에는 쓰지 않는다. 한 턴에 최대 2회."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "broken_assumption": {
                "type": "string",
                "description": "깨진 전제 또는 틀린 규정 한 문장 (규정의 '이 계획의 전제' 줄을 그대로 인용하면 좋다)"
            },
            "evidence": {
                "type": "string",
                "description": "그것이 깨졌음을 보여주는 근거 — 실제 도구 결과·오류·수치를 압축해 3줄 안팎"
            },
            "progress": {
                "type": "string",
                "description": "지금까지 확보한 사실·산출물 요약 (새 규정이 제약으로 흡수한다)"
            },
            "kind": {
                "type": "string",
                "enum": ["impossible", "dangerous", "wrong_problem", "other"],
                "description": "impossible=이 틀 안에서 풀 수 없음 · dangerous=그대로 하면 위해 · wrong_problem=문제가 다른 것이었음"
            },
        },
        "required": ["broken_assumption", "evidence"],
    },
}


class TurnChannel:
    """한 턴의 재규정 통로 — 파이프라인이 열고 닫는다."""

    def __init__(self, key: str, runner, message: str, history: list, execution_memory: str,
                 consciousness_output: dict, repair: bool, registry_key: str):
        self.key = key
        self.task_id = execution_key()[1]
        self.context = snapshot()
        self.lock = threading.RLock()
        self.runner = runner
        self.message = message
        self.history = list(history or [])
        self.execution_memory = execution_memory or ""
        from consciousness_agent import project_framing
        self.original = project_framing(consciousness_output) or {}
        self.current = project_framing(consciousness_output) or {}
        self.repair = bool(repair)
        self.registry_key = registry_key or "default"
        self.revisions = 0
        self.log: list = []          # [{trigger, broken, kind, ts}]
        self.opened_at = time.time()
        self.closed = False
        self.on_change = None

    @property
    def revised(self) -> bool:
        return self.revisions > 0


def turn_key_for(runner, fallback: str = "") -> str:
    """도구 실행이 실어 오는 agent_id 와 같은 키 — 조향 인박스와 같은 식(agent_pipeline 의 _skey)."""
    try:
        prov = getattr(getattr(runner, "ai", None), "_provider", None)
        k = getattr(prov, "agent_id", "") or ""
        if k:
            return k
    except Exception:
        pass
    try:
        from thread_context import get_current_agent_id
        k = get_current_agent_id() or ""
        if k:
            return k
    except Exception:
        pass
    return fallback or ""


def open_turn(key: str, runner, message: str, history: list, execution_memory: str,
              consciousness_output: dict, repair: bool = False, aliases=(), task_id=None) -> Optional[TurnChannel]:
    """턴 시작 — 의식 산출물이 있을 때만 통로를 연다(규정이 없으면 재규정도 없다)."""
    if not key or not consciousness_output:
        return None
    try:
        from thread_context import get_current_registry_key
        rk = get_current_registry_key() or "default"
    except Exception:
        rk = "default"
    ch = TurnChannel(key, runner, message, history, execution_memory, consciousness_output, repair, rk)
    ch.task_id = execution_key(key, task_id)[1]
    ch.context.update(agent_id=key, task_id=ch.task_id)
    keys = {execution_key(agent, ch.task_id) for agent in (key, *(aliases or ())) if agent}
    with _lock:
        if any(k in _channels for k in keys):
            raise RuntimeError("이미 열린 작업의 재규정 통로입니다")
        for k in keys:
            _channels[k] = ch
    return ch


def current(key: str, task_id=None) -> Optional[TurnChannel]:
    with _lock:
        ch = _channels.get(execution_key(key or "", task_id))
    if ch and time.time() - ch.opened_at > _TTL_SECONDS:
        close_turn(key, task_id, expected=ch)
        return None
    return ch


def close_turn(key: str, task_id=None, *, expected=None) -> Optional[TurnChannel]:
    """턴 종료 — 통로를 걷고 그 통로를 돌려준다(파이프라인이 갱신 규정을 회수)."""
    with _lock:
        channel_key = execution_key(key or "", task_id)
        ch = _channels.get(channel_key)
        if expected is not None and ch is not expected:
            return None
        if ch is not None:
            ch.closed = True
            for k in [k for k, v in _channels.items() if v is ch]:
                _channels.pop(k, None)
    return ch


# ── 핵심: 의식 재호출 ─────────────────────────────────────────────────────────

def _revise(ch: TurnChannel, trigger: str, broken: str, evidence: str, progress: str, kind: str) -> dict:
    """재진입 워커도 원래 작업의 신원·궤적·비용을 쓰며 호출자 문맥을 복원한다."""
    from providers.base import adopt_turn_token_ledger
    previous = snapshot()
    try:
        restore(ch.context)
        with ch.lock, adopt_turn_token_ledger(ch.key, ch.task_id):
            return _revise_in_context(ch, trigger, broken, evidence, progress, kind)
    finally:
        restore(previous)


def _revise_in_context(ch: TurnChannel, trigger: str, broken: str, evidence: str, progress: str, kind: str) -> dict:
    """의식을 다시 깨워 규정을 갱신. 반환 = 결과 봉투(dict). 상한·실패는 봉투로 정직하게."""
    from consciousness_agent import ConsciousnessCallSkipped

    if ch.closed or getattr(ch, "cancel_check", lambda: False)():
        return {"revised": False, "reason": "이미 종료된 실행입니다"}
    if ch.revisions >= MAX_REVISIONS:
        return {"revised": False, "reason": f"이 턴의 재규정 상한({MAX_REVISIONS}회)에 닿았다",
                "directive": ("더는 재규정하지 않는다. 지금까지 확보한 사실로 가능한 만큼만 마무리하고, "
                              "무엇이 왜 안 됐는지(깨진 전제·근거)를 최종 보고에 그대로 적어라.")}
    revision = {
        "trigger": trigger,
        "kind": kind or "other",
        "previous_framing": ch.current.get("task_framing", ""),
        "previous_assumptions": ch.current.get("assumptions") or [],
        "previous_criteria": ch.current.get("achievement_criteria", ""),
        "previous_contract": ch.current,
        "previous_request_intent": ch.current.get("request_intent", getattr(ch, "request_intent", "task")),
        "previous_research_plan": ch.current.get("_research_plan"),
        "broken_assumption": (broken or "").strip()[:2000],
        "evidence": (evidence or "").strip()[:4000],
        "progress": (progress or "").strip()[:4000],
        "revision_no": ch.revisions + 1,
    }
    runner = ch.runner
    try:
        out = runner._run_consciousness(ch.message, ch.history, ch.execution_memory,
                                        repair=ch.repair, revision=revision)
    except ConsciousnessCallSkipped as exc:
        return {"revised": False, "model_called": False, "stop_kind": exc.kind,
                "reason": f"의식 재규정 호출 생략: {exc}",
                "directive": ("새 규정이나 추가 권한은 부여되지 않았다. 기존 목표·권한 안에서 "
                              "깨진 전제에 의존하지 않는 작업만 마무리하고, 해결하지 못한 제약과 "
                              "호출 생략 사유를 최종 보고에 적어라.")}
    except TypeError:
        # 옛 서명(시험 대역 등) — revision 없이라도 의식은 깨운다
        out = runner._run_consciousness(ch.message, ch.history, ch.execution_memory)
    except Exception as e:
        return {"revised": False, "reason": f"의식 재호출 실패: {e}",
                "directive": "현재 규정으로 가능한 만큼 진행하고 깨진 전제를 최종 보고에 적어라."}
    if not out or not (out.get("task_framing") or "").strip():
        return {"revised": False, "reason": "의식이 새 규정을 내지 못했다",
                "directive": "현재 규정으로 가능한 만큼 진행하고 깨진 전제를 최종 보고에 적어라."}

    return accept_revision(ch, out, revision)


# 중간감사는 최초 의식과 같은 필드만 수정한다. 내부 영수증·권한은 하네스 소유다.
REVISION_FIELDS = frozenset({
    "task_framing", "achievement_criteria", "criteria", "assumptions", "expert_choice",
    "capability_focus", "guide_files", "history_summary", "needs_clarification",
    "clarification_question", "deep_research", "independent_review",
    "request_intent", "request_intent_reason", "research_plan_action",
    "research_plan_patch", "research_plan",
})


def merge_revision(current, update):
    """생략은 계승하고 변경 필드는 교체한다. 의미 판단은 같은 의식이 소유한다."""
    from consciousness_agent import project_framing, validate_framing_focus
    update = project_framing(update)
    result = copy.deepcopy({**(current or {}), **update})
    validate_framing_focus(result)
    if not isinstance(result.get("task_framing"), str) or not result["task_framing"].strip():
        raise ValueError("현재 수행할 요청 task_framing이 필요합니다")
    if ("criteria" in update or ("achievement_criteria" in update and (current or {}).get("criteria"))):
        if not {"criteria", "achievement_criteria"} <= update.keys():
            raise ValueError("criteria와 achievement_criteria는 함께 갱신해야 합니다")
    for key in ("achievement_criteria", "expert_choice", "history_summary", "clarification_question"):
        if key in update and not isinstance(update[key], str):
            raise ValueError(f"{key}는 문자열이어야 합니다")
    for key in ("criteria", "assumptions", "guide_files"):
        if key in update and not isinstance(update[key], list):
            raise ValueError(f"{key}는 목록이어야 합니다")
    for row in result.get("criteria", []):
        if not isinstance(row, dict) or not isinstance(row.get("text"), str) or not row["text"].strip():
            raise ValueError("criteria에 text가 있는 기준 객체가 필요합니다")
    for key in ("needs_clarification", "deep_research", "independent_review"):
        if key in update and not isinstance(update[key], bool):
            raise ValueError(f"{key}는 참/거짓이어야 합니다")
    return result


def accept_revision(ch, update, revision, prepare=None):
    """이미 내려진 의식 판단을 채택하는 단일 경로. 모델을 다시 호출하지 않는다."""
    with ch.lock:
        if ch.closed or getattr(ch, "cancel_check", lambda: False)():
            return {"revised": False, "reason": "종료된 실행의 규정은 변경하지 않습니다"}
        out = merge_revision(ch.current, update)
        if prepare is not None:
            out = prepare(out)
        if out.get("needs_repair") and not ch.repair:
            out["needs_repair"] = False
            out["_repair_declared_mid_turn"] = True
        if "_repair_policy" in ch.current:
            out["_repair_policy"] = ch.current["_repair_policy"]
        out["_revision"] = {"trigger": revision["trigger"], "kind": revision.get("kind", "wrong_problem"),
                            "revision_no": ch.revisions + 1,
                            "broken_assumption": revision.get("broken_assumption", "")}
        out["_framing_origin"] = ch.original.get("task_framing", "")
        out["_framing_source"] = "fresh_consciousness_revision"
        ch.current = out
        ch.revisions += 1
        ch.log.append({**out["_revision"], "ts": time.time()})
        env = {"revised": True, "output": out, "user_message": ch.message}
        if ch.on_change and ch.on_change(out):
            env["scope_revision"] = "task"
        try:
            from episode_logger import record_trajectory_event
            record_trajectory_event("framing.revised", {
                **out["_revision"], "evidence": revision.get("evidence", "")[:2000],
                "new_framing": out["task_framing"][:3000],
                "new_criteria": out.get("achievement_criteria", "")[:2000],
            })
        except Exception:
            pass  # 관측 기록 실패가 이미 채택한 규정을 되돌리지 않는다.
        return env


def render_for_executor(env: dict) -> str:
    """실행자가 도구 결과로 읽을 본문 — 새 규정을 명령 어조로."""
    if not env.get("revised"):
        return json.dumps({"revised": False, "reason": env.get("reason", ""),
                           "directive": env.get("directive", ""),
                           **{key: env[key] for key in ("model_called", "stop_kind") if key in env}},
                          ensure_ascii=False, indent=2)
    from consciousness_agent import project_framing
    out = project_framing(env["output"])
    lines = ["[재규정] 의식이 깨진 전제를 반영해 문제를 다시 규정했다. 지금부터는 아래 규정을 따른다 — "
             "처음부터 다시 시작하지 말고, 이미 확보한 사실은 그대로 쓴다."]
    if env.get("scope_revision") == "task":
        lines.append("실행 의도를 작업 요청으로 정정했다. 기존 도구 권한 안에서 새 규정의 사용자 요청을 이어서 수행한다.")
    if out.get("needs_clarification") and (out.get("clarification_question") or "").strip():
        lines.append("★멈춤: 이 문제는 사용자 확인 없이는 진행할 수 없다. 더 실행하지 말고, 지금까지 확인한 "
                     "사실을 짧게 정리한 뒤 다음 질문으로 응답을 마무리하라:\n" + out["clarification_question"].strip())
    from prompt_builder import compile_user_command
    lines.append(compile_user_command(env.get("user_message", ""), out))
    if out.get("_repair_declared_mid_turn"):
        lines.append("재규정은 전역 수리 권한을 발급하지 않는다. 원래 목적을 유지하며 다른 명령·도구·지역 함수·Script로 "
                     "계속하라. 등록된 순수 변환 부품은 현재 사용자 업무의 파일 수정→self:patch apply로 한정 수리할 수 있다. "
                     "파서·재시작 제어·일반 패키지 구현은 self:patch propose(path, reason)로 진단부터 맡겨라. 관련 파일은 paths로 명시하라. pending_repair 뒤 턴을 끝내면 원래 업무로 자동 복귀한다. "
                     "호스트가 범위를 거절하면 그 근거를 보존하고 가능한 다른 방법을 실행하라. 자기 지침·권한은 바꾸지 않는다.")
    return json.dumps({"revised": True, "revision_no": out.get("_revision", {}).get("revision_no", 1),
                       "content": "\n\n".join(lines)}, ensure_ascii=False, indent=2)


def execute_reframe(tool_input: dict, agent_id: str, task_id: str = None) -> str:
    """도구 진입점(두 경로 공용). 반환 = JSON 문자열."""
    tool_input = tool_input or {}
    from supervision_bus import current as supervisor_current
    supervisor = supervisor_current(agent_id, task_id)
    if supervisor:
        return supervisor.reframe(tool_input)
    ch = current(agent_id or "", task_id)
    if ch is None:
        return json.dumps({"revised": False,
                           "reason": "이 턴에는 재규정 통로가 없다(의식 규정 없이 시작한 턴이거나 이미 닫힘)",
                           "directive": "현재 정보로 가능한 만큼 진행하고, 깨진 전제가 있으면 최종 보고에 적어라."},
                          ensure_ascii=False, indent=2)
    broken = str(tool_input.get("broken_assumption") or "").strip()
    evidence = str(tool_input.get("evidence") or "").strip()
    if not broken or not evidence:
        return json.dumps({"revised": False, "reason": "broken_assumption 과 evidence 가 모두 필요하다"},
                          ensure_ascii=False)
    env = _revise(ch, trigger="executor", broken=broken, evidence=evidence,
                  progress=str(tool_input.get("progress") or ""), kind=str(tool_input.get("kind") or "other"))
    return render_for_executor(env)
