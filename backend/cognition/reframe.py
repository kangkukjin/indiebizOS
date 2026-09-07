"""reframe.py — 턴 안 재규정 (2026-09-06, 사용자 판정 '한번 해봐')

의식은 턴 시작에 한 번 문제를 규정한다. 그 규정이 성립하려면 참이어야 하는 전제
(assumptions)가 실행 중 반증되면 — 그 틀 안에서는 풀 수 없거나, 위험하거나, 문제가
다른 것이었음이 드러나면 — 실행자가 깨진 전제와 근거를 들고 **의식에게 되묻는다**.
의식은 이미 확보된 사실을 제약으로 흡수해 처음부터 다시 규정하고, 새 규정이 실행자의
도구 결과로 같은 대화에 돌아온다. 대화는 끊기지 않는다 — 새 규정이 가장 최근 메시지가
될 뿐이다(연속 메타인식이 아니라 *놀랐을 때 다시 묻기*).

두 방아쇠:
  ① 실행자의 판단 — 도구 `reframe` (자기 관리 도구 부류: ask_user_question 과 같은 자리.
     IBL 어휘가 아니다 — 의식↔실행자 이음매 신호는 해마 코퍼스에 섞이면 안 된다).
  ② 판단 없는 기계 방아쇠 — 평가 루프가 치명(severity 3)이거나 두 번째 라운드도 미달이면
     평가자의 피드백을 근거로 재규정(cognitive_eval.revise_from_eval).
상한: 한 턴에 MAX_REVISIONS 회 — 의식과 실행자가 서로 떠넘기며 도는 것을 막는다.

두-경로 대칭(read_guide·조향과 같다): 인프로세스 프로바이더는 system_tools 디스패치,
Claude Code 는 mcp_server.reframe → /ibl/reframe 로 같은 execute_reframe 에 닿는다.
채널은 키(agent_id)별 — 같은 에이전트의 동시 턴은 마지막에 연 턴이 받는다(조향 인박스와
같은 한계, 정직하게 적어 둔다).
"""
import json
import threading
import time
from typing import Dict, Optional

MAX_REVISIONS = 2
_TTL_SECONDS = 3600 * 3   # 턴이 닫히지 않고 죽은 채널의 유령 방지

_channels: Dict[str, "TurnChannel"] = {}
_lock = threading.Lock()

TOOL_SCHEMA = {
    "name": "reframe",
    "description": (
        "규정(현재 태스크·이 계획의 전제)이 실행 중 사실이 아니게 됐을 때 의식에게 재규정을 요청한다. "
        "전제가 깨졌거나, 이 틀 안에서는 풀 수 없거나, 그대로 하면 위험하다는 것을 알게 됐을 때 부른다. "
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
        self.runner = runner
        self.message = message
        self.history = list(history or [])
        self.execution_memory = execution_memory or ""
        self.original = dict(consciousness_output or {})
        self.current = dict(consciousness_output or {})
        self.repair = bool(repair)
        self.registry_key = registry_key or "default"
        self.revisions = 0
        self.log: list = []          # [{trigger, broken, kind, ts}]
        self.opened_at = time.time()

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
              consciousness_output: dict, repair: bool = False, aliases=()) -> Optional[TurnChannel]:
    """턴 시작 — 의식 산출물이 있을 때만 통로를 연다(규정이 없으면 재규정도 없다)."""
    if not key or not consciousness_output:
        return None
    try:
        from thread_context import get_current_registry_key
        rk = get_current_registry_key() or "default"
    except Exception:
        rk = "default"
    ch = TurnChannel(key, runner, message, history, execution_memory, consciousness_output, repair, rk)
    with _lock:
        _channels[key] = ch
        for a in aliases or ():
            if a and a != key:
                _channels[a] = ch
    return ch


def current(key: str) -> Optional[TurnChannel]:
    with _lock:
        ch = _channels.get(key or "")
    if ch and time.time() - ch.opened_at > _TTL_SECONDS:
        close_turn(key)
        return None
    return ch


def close_turn(key: str) -> Optional[TurnChannel]:
    """턴 종료 — 통로를 걷고 그 통로를 돌려준다(파이프라인이 갱신 규정을 회수)."""
    with _lock:
        ch = _channels.pop(key or "", None)
        if ch is not None:
            for k in [k for k, v in _channels.items() if v is ch]:
                _channels.pop(k, None)
    return ch


# ── 핵심: 의식 재호출 ─────────────────────────────────────────────────────────

def _revise(ch: TurnChannel, trigger: str, broken: str, evidence: str, progress: str, kind: str) -> dict:
    """의식을 다시 깨워 규정을 갱신. 반환 = 결과 봉투(dict). 상한·실패는 봉투로 정직하게."""
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
        "broken_assumption": (broken or "").strip()[:2000],
        "evidence": (evidence or "").strip()[:4000],
        "progress": (progress or "").strip()[:4000],
        "revision_no": ch.revisions + 1,
    }
    runner = ch.runner
    try:
        out = runner._run_consciousness(ch.message, ch.history, ch.execution_memory,
                                        repair=ch.repair, revision=revision)
    except TypeError:
        # 옛 서명(시험 대역 등) — revision 없이라도 의식은 깨운다
        out = runner._run_consciousness(ch.message, ch.history, ch.execution_memory)
    except Exception as e:
        return {"revised": False, "reason": f"의식 재호출 실패: {e}",
                "directive": "현재 규정으로 가능한 만큼 진행하고 깨진 전제를 최종 보고에 적어라."}
    if not out or not (out.get("task_framing") or "").strip():
        return {"revised": False, "reason": "의식이 새 규정을 내지 못했다",
                "directive": "현재 규정으로 가능한 만큼 진행하고 깨진 전제를 최종 보고에 적어라."}

    # 권한은 재규정으로 늘지 않는다 — 수리 승격은 턴 시작의 파이프라인 판단이다.
    if out.get("needs_repair") and not ch.repair:
        out["needs_repair"] = False
        out["_repair_declared_mid_turn"] = True
    out["_revision"] = {k: revision[k] for k in ("trigger", "kind", "revision_no", "broken_assumption")}
    out["_framing_origin"] = ch.original.get("task_framing", "")
    ch.current = out
    ch.revisions += 1
    ch.log.append({"trigger": trigger, "kind": kind, "broken": revision["broken_assumption"][:200],
                   "ts": time.time()})

    # 재고(framing 캐시) 갱신 — 다음 턴의 fit 게이트가 옛 지도를 들지 않도록
    try:
        from cognitive_consciousness import framing_cache_set
        if not out.get("needs_clarification"):
            framing_cache_set(ch.registry_key, out)
    except Exception:
        pass
    try:
        from episode_logger import record_trajectory_event
        record_trajectory_event("framing.revised", {
            "trigger": trigger, "kind": kind, "revision_no": ch.revisions,
            "broken_assumption": revision["broken_assumption"][:1000],
            "evidence": revision["evidence"][:2000],
            "new_framing": (out.get("task_framing") or "")[:3000],
            "new_criteria": (out.get("achievement_criteria") or "")[:2000],
        })
    except Exception:
        pass
    print(f"[재규정] {trigger} #{ch.revisions} ({kind}): {revision['broken_assumption'][:80]}")
    return {"revised": True, "output": out}


def render_for_executor(env: dict) -> str:
    """실행자가 도구 결과로 읽을 본문 — 새 규정을 명령 어조로."""
    if not env.get("revised"):
        return json.dumps({"revised": False, "reason": env.get("reason", ""),
                           "directive": env.get("directive", "")}, ensure_ascii=False, indent=2)
    out = env["output"]
    lines = ["[재규정] 의식이 깨진 전제를 반영해 문제를 다시 규정했다. 지금부터는 아래 규정을 따른다 — "
             "처음부터 다시 시작하지 말고, 이미 확보한 사실은 그대로 쓴다."]
    if out.get("needs_clarification") and (out.get("clarification_question") or "").strip():
        lines.append("★멈춤: 이 문제는 사용자 확인 없이는 진행할 수 없다. 더 실행하지 말고, 지금까지 확인한 "
                     "사실을 짧게 정리한 뒤 다음 질문으로 응답을 마무리하라:\n" + out["clarification_question"].strip())
    lines.append("현재 태스크:\n" + (out.get("task_framing") or "").strip())
    try:
        from prompt_builder import _expert_choice_line
        _ex = _expert_choice_line(out)
    except Exception:
        _ex = ""
    if _ex:
        lines.append("전문가의 선택: " + _ex)
    try:
        from prompt_builder import _assumption_lines
        a = _assumption_lines(out)
    except Exception:
        a = ""
    if a:
        lines.append("이 계획의 전제(첫 확인에서 검증하라):\n" + a)
    cf = out.get("capability_focus") or {}
    hint = (cf.get("hint") or "").strip()
    if hint:
        lines.append("수행 절차: " + hint)
    hl = cf.get("highlight_actions") or []
    if hl:
        lines.append("쓸 수 있는 IBL 액션: " + ", ".join(hl) + " (이 밖의 액션도 가능)")
    crit = (out.get("achievement_criteria") or "").strip()
    if crit:
        lines.append("충족 기준(갱신): " + crit)
    if out.get("_repair_declared_mid_turn"):
        lines.append("주의: 새 규정은 시스템 코어 수정이 필요하다고 봤지만 이 턴에는 수리 권한이 없다 — "
                     "코어를 고치지 말고 진단·제안까지만 하고, 수리는 사용자에게 #repair 로 다시 명령받으라고 보고하라.")
    return json.dumps({"revised": True, "revision_no": out.get("_revision", {}).get("revision_no", 1),
                       "content": "\n\n".join(lines)}, ensure_ascii=False, indent=2)


def execute_reframe(tool_input: dict, agent_id: str) -> str:
    """도구 진입점(두 경로 공용). 반환 = JSON 문자열."""
    tool_input = tool_input or {}
    ch = current(agent_id or "")
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


def revise_from_eval(key: str, criteria: str, feedback: str, severity: int, round_num: int) -> Optional[dict]:
    """평가 루프의 기계 방아쇠 — 판단 없이 조건만. 반환 = 새 의식 산출물 또는 None."""
    ch = current(key or "")
    if ch is None:
        return None
    if not (int(severity or 0) >= 3 or int(round_num or 0) >= 2):
        return None
    env = _revise(ch, trigger="goal_eval",
                  broken=f"달성 기준이 현재 규정 안에서 {round_num}라운드째 충족되지 않는다(severity={severity})",
                  evidence=(feedback or "")[:3000],
                  progress=f"평가 중이던 달성 기준: {criteria}",
                  kind="impossible" if int(severity or 0) >= 3 else "other")
    return env.get("output") if env.get("revised") else None
