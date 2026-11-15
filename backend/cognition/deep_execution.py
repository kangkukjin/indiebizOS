"""심층실행 — 주문한 단계만큼 실행 도중에 의식이 돌아와 되돌아본다.

설계와 근거: docs/DEEP_EXECUTION_DESIGN_2026_11_15.md.

- 단계는 THINK·EXECUTE 분기(THINK면 말이 없어도 1단계)와 사용자의 주문에서만 정한다. 의식은
  주문을 옮겨 적을 뿐이고, 여기서도 도구 호출 수나 시간으로 단계를 올리지 않는다.
- 실행자는 첫 걸음을 마치면 알게 된 것을 적어 돌아온다(reframe 도구, kind=checkpoint). 의식은
  그것만 보고 길을 다시 꼽은 뒤 실행자가 한 일·하려는 일과 대조해 판정하고, 다음에 돌아올
  지점을 정한다. 답이 올 때까지 실행자는 기다린다.
- 실행자가 돌아오지 않고 오래 가면 하네스가 실행 기록을 읽혀 '알게 된 것'을 대신 적고
  되돌아본다. 호출 수 상한은 이 경우에만 쓰인다.
- 갈래를 그만두라는 지시는 하지 않는다(시험 T1에서 그 지시는 16건 중 9건이 틀렸다). 값이
  의심되는 일은 질문으로 전한다.
- 착수 메모와 되돌아보기는 작업 메모 하나에 쌓인다. 다음 되돌아보기와 끝내기 전 확인이 읽는다.
- 끝내기 직전에 현행 감독 지문으로 한 번 확인하고, 교정이 있으면 실행자를 한 번 잇는다.

끄려면 world_pulse_config.json 의 conscious_supervisor.deep_execution.enabled 를 false 로 둔다.
"""
import json
import re
import threading
import time
import uuid
from contextlib import contextmanager

DEFAULTS = {
    "enabled": True,          # THINK 로 간 일은 말이 없어도 1단계다
    "default_depth": 1,
    "max_depth": 5,
    "ceilings": [8, 16, 32],  # 실행자가 돌아오지 않을 때: 지난 되돌아보기 뒤 이만큼 호출이 지나면 하네스가 대신 본다
    "final_check": True,
    "hold_s": 150,            # 하네스가 대신 되돌아보는 동안 실행자의 다음 도구 호출을 붙잡는 상한
    "result_chars": 2500,     # 하네스가 '알게 된 것'을 적을 때 호출 결과마다 보는 앞부분
    "trace_chars": 90000,
}

_cache = {"mtime": None, "value": {}}


def _file_settings():
    """world_pulse_config.json 의 conscious_supervisor.deep_execution. 파일이 바뀌면 다시 읽는다."""
    try:
        from world_pulse import PULSE_CONFIG_PATH
        mtime = PULSE_CONFIG_PATH.stat().st_mtime
        if mtime != _cache["mtime"]:
            raw = json.loads(PULSE_CONFIG_PATH.read_text(encoding="utf-8"))
            _cache.update(mtime=mtime, value=(raw.get("conscious_supervisor") or {}).get("deep_execution") or {})
    except (OSError, ValueError, ImportError):
        _cache.update(mtime=None, value={})
    return dict(_cache["value"])


def settings(config=None):
    """기본값 ← 감독이 기동 때 읽은 설정 ← 지금의 파일. 파일이 이기므로 재기동 없이 켜고 끈다."""
    own = (config or {}).get("deep_execution") or {}
    return {**DEFAULTS, **own, **_file_settings()}


def depth_of(framing, cfg):
    """단계 = 사용자의 주문(의식이 옮겨 적은 수), 없으면 THINK 기본값. 꺼져 있으면 0."""
    if not cfg["enabled"] or not isinstance(framing, dict) or not framing:
        return 0
    if framing.get("needs_clarification") or str(framing.get("_framing_source", "")).startswith("repair"):
        return 0
    ordered = framing.get("deep_execution")
    if isinstance(ordered, str) and ordered.strip().isdigit():
        ordered = int(ordered.strip())
    if isinstance(ordered, (int, float)) and not isinstance(ordered, bool) and ordered >= 0:
        return int(min(ordered, cfg["max_depth"]))
    if framing.get("deep_research"):
        return 0  # 심층연구는 지금의 방식 그대로 둔다
    return int(cfg["default_depth"])


def execution_block(framing):
    """실행자에게 전하는 안내. 단계가 없으면 빈 문자열이다."""
    try:
        depth = depth_of(framing, settings())
    except Exception:
        return ""
    if depth <= 0:
        return ""
    first = str((framing or {}).get("first_step") or "").strip()
    lines = [f"심층실행 {depth}단계: 실행 도중 {depth}번, 정해진 지점에서 방향 담당자에게 돌아가 방향을 다시 받는다."]
    if first:
        lines.append("첫 걸음(내부 제안): " + json.dumps({"source": "consciousness", "field": "first_step",
                                                         "text": first}, ensure_ascii=False))
    lines += [
        "먼저 첫 걸음만 한다. 첫 걸음에서 요청이 다 끝나는 가벼운 일이면 돌아가지 않고 마친다.",
        "첫 걸음을 마치면 reframe 도구를 kind=\"checkpoint\" 로 부른다. evidence 에 지금까지 알게 된 것"
        "(확인된 사실·수치·상태와 막힌 것), progress 에 다음에 하려는 것을 적는다. broken_assumption 은 비워 둔다.",
        "답이 올 때까지 다음 작업을 시작하지 않는다. 답에는 방향에 대한 판단과 다음에 돌아올 지점이 들어 있다. "
        "남은 횟수만큼 그 지점에서 같은 방법으로 돌아간다.",
        "판단은 지금 상태에 비춰 확인한다. 따르지 않으면 최종 보고에 이유를 적는다. "
        "돌아가지 않고 오래 가면 하네스가 실행 기록으로 대신 되돌아본다.",
    ]
    return "\n".join(lines)


# ── 지문 ───────────────────────────────────────────────────────────────────────

SYSTEM = ("당신은 진행 중인 일의 방향을 잡는 담당자다. 주어진 자료만으로 답한다. "
          "도구를 쓰지 않고 파일도 열지 않는다. 한국어로 간결하게 쓴다.")

NOTE = """실행자가 정해진 지점에서 돌아오지 않았다. 아래 실행 기록(도구 호출과 결과 앞부분)을 읽고, 방향을 다시 보기 위한 자료로 **지금까지 알게 된 것**을 대신 적는다.
- 결과에서 실제로 확인된 사실·수치·상태만 적는다. 짐작은 '추정'이라고 표시한다.
- 아직 확인하지 못한 것과 막힌 것도 적는다.
- 앞으로 무엇을 할지와 평가는 적지 않는다.
- 항목으로, 1,200자 안팎.

[사용자 요청 원문]
{message}

[문제 규정]
{framing}

[지금까지의 실행 기록 — 도구 호출 {k}회. 결과는 앞부분만 보인다]
{trace}
"""

R1 = """실행자가 한 구간을 마쳤다. 아래는 그때까지 알게 된 것이다. 실행자가 무엇을 어떻게 했는지는 아직 보지 않는다. 알게 된 것만 놓고 문제를 다시 생각한다.

[사용자 요청 원문]
{message}

[문제 규정]
{framing}

[완료 기준]
{criteria}

[작업 메모 — 착수할 때 적어 둔 것과 지난 되돌아보기]
{memo}

[지금까지 알게 된 것 — {by}]
{note}

다음을 쓴다(전체 900자 안팎).
1. 알게 된 것으로 지금까지의 생각과 달라진 점(깨진 가정, 새로 드러난 사실). 없으면 '없음'.
2. 이 문제를 지금 처음 받았다면 갈 수 있는 서로 다른 길(2~4개). 길마다 얻는 것과 드는 것을 한 줄씩. 앞서 본 길 가운데 닫힌 것과, 알게 된 것 때문에 새로 열린 것을 표시한다.
3. 지금 가장 값진 다음 걸음 하나.
"""

R2 = """방금 알게 된 것만 놓고 문제를 다시 생각했다([다시 생각한 것]). 이제 실행자가 지금까지 한 일의 목록과 실행자가 다음에 하려는 것을 본다. 작업은 끝나지 않았고 실행자는 계속 일한다.
실행자를 감싸지도 깎지도 말고 판정한다. 이미 쓴 노력은 돌아오지 않으니 앞으로의 노력만 본다.
실행자가 하고 있는 일을 그만두라고 지시하지 않는다. 그 일이 무엇에 쓰이는지는 실행자가 더 잘 안다. 값이 의심되면 질문으로 적는다.
이번이 되돌아보기 {round}번째이고 모두 {depth}번이다.

[사용자 요청 원문]
{message}

[다시 생각한 것]
{r1}

[지금까지 한 일 — 도구 호출 {k}회, 그중 실패 {errors}회]
{actions}

[실행자가 다음에 하려는 것]
{stated}

다음을 쓴다.
1. 실행자가 가고 있는 길은 다시 생각한 길 가운데 어디에 해당하는가. 한두 문장.
2. 옮기거나 새로 열 갈래: 있으면 항목마다 얻는 것 / 추가로 드는 것(도구 호출 수·시간의 대략) / 이 판단을 뒤집을 관측. 실행자가 어차피 하게 될 일은 적지 않는다. 없으면 '없음'.
3. 실행자에게 물을 것: 값이 의심되는 일이 있으면 "이 일은 무엇에 쓰이는가" 꼴의 질문으로 적는다. 없으면 '없음'.
마지막 두 줄은 반드시 아래 형식으로 끝낸다.
NEXT: 실행자가 무엇까지 확인하고 다시 돌아오면 되는지 한 문장
VERDICT: KEEP 또는 SWITCH 또는 WRAP — 이유 한 문장
KEEP=지금 길로 계속한다. SWITCH=다른 길로 옮기거나 새 갈래를 연다. WRAP=더 해도 이득이 작으니 한계를 밝히고 마무리한다.
"""


# ── 상태와 작업 메모 ────────────────────────────────────────────────────────────

def _state(controller):
    state = getattr(controller, "_deep", None)
    if state is None:
        cfg = settings(getattr(controller, "config", None))
        eligible = (getattr(controller, "enabled", False) and not getattr(controller, "repair_granted", False)
                    and getattr(controller, "request_intent", "task") == "task")
        state = controller._deep = {"cfg": cfg, "depth": depth_of(controller.framing, cfg) if eligible else 0,
                                    "done": 0, "last_calls": 0, "next": "", "memo": [],
                                    "final_done": False, "busy": threading.Event()}
        if state["depth"]:
            controller.log("deep.started", role="harness", depth=state["depth"], ceilings=cfg["ceilings"])
    return state


@contextmanager
def _turn_context(controller):
    """턴의 실행 문맥(궤적 손잡이 포함)을 이 스레드에 잠깐 입힌다.

    실행자가 CLI 면 되돌아보기 요청은 MCP 재진입 스레드에서 온다. 그 스레드에는 턴의 궤적이 없어
    사건이 원장에 남지 않는다(2026-11-15 실측: deep.reflection 이 턴 저장소에만 남았다).
    """
    from thread_context import restore, snapshot
    previous = snapshot()
    restore(controller.context)
    try:
        yield
    finally:
        restore(previous)


def _ceiling(cfg, index):
    gaps = cfg["ceilings"] or DEFAULTS["ceilings"]
    return gaps[index] if index < len(gaps) else gaps[-1] * 2 ** (index - len(gaps) + 1)


def memo_text(state, framing):
    """착수와 지난 되돌아보기를 한 문서로. 다음 되돌아보기와 끝내기 전 확인이 읽는다."""
    framing = framing or {}
    lines = [f"# 작업 메모 (심층실행 {state['depth']}단계)", "", "## 착수"]
    first = str(framing.get("first_step") or "").strip()
    hint = str((framing.get("capability_focus") or {}).get("hint") or "").strip()
    lines.append("첫 걸음: " + (first or "(적지 않음)"))
    if hint:
        lines.append("접근: " + hint)
    for row in state["memo"]:
        writer = "실행자가 적음" if row["by"] == "executor" else "실행자가 돌아오지 않아 하네스가 적음"
        lines += ["", f"## 되돌아보기 {row['round']}/{state['depth']} (도구 호출 {row['calls']}회 뒤, {writer})",
                  "알게 된 것:", row["learned"], "", "다시 생각한 것:", row["rethink"], "",
                  f"판정: {row['verdict']} — {row['reason']}", row["judgment"], "다음 지점: " + (row["next"] or "(정하지 않음)")]
    return "\n".join(lines)


def _save_memo(controller, state):
    try:
        (controller.store.directory / "deep_memo.md").write_text(memo_text(state, controller.framing), encoding="utf-8")
    except OSError:
        pass  # 메모 파일은 관측용이다. 못 써도 되돌아보기는 이어진다.


# ── 되돌아보기 ─────────────────────────────────────────────────────────────────

def _clip(text, limit):
    text = re.sub(r"\s+", " ", str(text or "")).strip()
    return text if len(text) <= limit else text[:limit] + f"…(+{len(text) - limit}자)"


def _result_text(controller, ref, limit):
    try:
        return controller.store.read_evidence(ref["id"], 0, limit)["text"]
    except Exception:
        return ""


def trace_of(controller, cfg, *, per_result=None):
    """(호출 수, 실패 수, 결과를 담은 기록, 한 줄씩의 목록). per_result=0 이면 결과를 읽지 않는다."""
    rows = controller.store.tool_index(limit=400)
    k = len(rows)
    per = max(600, min(cfg["result_chars"], cfg["trace_chars"] // max(k, 1))) if per_result is None else per_result
    full, brief = [], []
    for index, row in enumerate(rows, 1):
        name = str(row.get("name", "")).rsplit("__", 1)[-1]
        failed = " 실패" if row.get("is_error") else ""
        given = _clip((row.get("input") or {}).get("excerpt", ""), 240)
        if per:
            full.append(f"[{index}] {name}{failed}\n  입력: {given}\n"
                        f"  결과(앞 {per}자): {_clip(_result_text(controller, row.get('result') or {}, per + 200), per)}")
        brief.append(f"[{index}] {name}{failed} — {_clip(given, 110)}")
    return k, sum(bool(r.get("is_error")) for r in rows), "\n".join(full), "\n".join(brief)


def _ask(controller, prompt):
    from supervisor_runtime import invoke
    return invoke(controller, prompt, planning_prompt=SYSTEM, phase="reflect") or ""


def parse_verdict(text):
    found = re.findall(r"VERDICT:\s*\**\s*(KEEP|SWITCH|WRAP)\s*\**\s*(?:—|–|-)?\s*(.*)", text or "")
    return (found[-1][0], found[-1][1].strip()) if found else ("KEEP", "")


def parse_next(text):
    found = re.findall(r"^\s*\**NEXT\**:\s*(.+)$", text or "", flags=re.M)
    return found[-1].strip() if found else ""


def _criteria_text(framing):
    rows = (framing or {}).get("criteria") or []
    if not isinstance(rows, list):
        return str(rows)
    return "\n".join("- " + (r.get("text", "") if isinstance(r, dict) else str(r)) for r in rows) or "(없음)"


def _round(controller, state, *, note, by, stated=""):
    """되돌아보기 한 번. 잠금은 부르는 쪽이 쥔다. note 가 None 이면 하네스가 실행 기록에서 대신 적는다."""
    state["done"] += 1  # 호출이 실패해도 같은 지점을 되풀이하지 않는다
    cfg, framing = state["cfg"], controller.framing or {}
    task = str(framing.get("task_framing") or "")
    k, errors, trace, actions = trace_of(controller, cfg, per_result=None if note is None else 0)
    state["last_calls"] = k
    if note is None:
        note = _ask(controller, NOTE.format(message=controller.message, framing=task, k=k, trace=trace))
        if not note.strip():
            raise RuntimeError("알게 된 것을 적는 호출이 빈 응답을 냈다")
    rethink = _ask(controller, R1.format(message=controller.message, framing=task, criteria=_criteria_text(framing),
                                         memo=memo_text(state, framing), note=note,
                                         by="실행자가 적음" if by == "executor" else "하네스가 실행 기록에서 적음"))
    judgment = _ask(controller, R2.format(message=controller.message, r1=rethink, k=k, errors=errors,
                                          actions=actions or "(아직 없음)", stated=stated or "(적지 않음)",
                                          round=state["done"], depth=state["depth"]))
    verdict, reason = parse_verdict(judgment)
    body = re.sub(r"\n?\s*\**(NEXT|VERDICT)\**:.*$", "", judgment.strip(), flags=re.S).strip()
    row = {"round": state["done"], "by": by, "calls": k, "learned": note.strip(), "rethink": rethink.strip(),
           "verdict": verdict, "reason": reason, "judgment": body, "next": parse_next(judgment)}
    state["memo"].append(row)
    state["next"] = row["next"]
    _save_memo(controller, state)
    controller.log("deep.reflection", role="consciousness", round=row["round"], depth=state["depth"], calls=k,
                   by=by, verdict=verdict, reason=reason, next=row["next"],
                   learned=controller.store.evidence(note), rethink=controller.store.evidence(rethink),
                   judgment=controller.store.evidence(judgment))
    return row


def _guidance(row, state):
    """실행자가 읽을 본문 — 판단, 다음 지점, 남은 횟수."""
    left = state["depth"] - row["round"]
    head = {"KEEP": "지금 길로 계속한다.",
            "SWITCH": "방향을 옮기거나 새 갈래를 연다.",
            "WRAP": "더 해도 이득이 작다. 한계를 밝히고 마무리한다."}[row["verdict"]]
    lines = [f"[심층실행 되돌아보기 {row['round']}/{state['depth']}] {head}"
             + (f" 이유: {row['reason']}" if row["reason"] else "")]
    if row["verdict"] != "KEEP" and row["judgment"]:
        lines.append(row["judgment"])
    if row["verdict"] != "WRAP":
        if left > 0:
            lines.append("다음 지점: " + (row["next"] or "다음 구간에서 새로 알게 된 것이 생겼을 때")
                         + f" — 거기에 닿으면 reframe 도구를 kind=\"checkpoint\" 로 다시 부른다(남은 되돌아보기 {left}번).")
        else:
            lines.append("되돌아보기를 모두 마쳤다. 끝까지 진행하고, 끝내기 전에 한 번 확인받는다.")
    lines.append("이 판단은 지금 상태에 비춰 확인한다. 따르지 않으면 최종 보고에 이유를 적는다.")
    return "\n".join(lines)


def checkpoint(controller, payload):
    """실행자가 알게 된 것을 적어 돌아왔다(reframe, kind=checkpoint). 답을 줄 때까지 실행자는 기다린다."""
    def reply(**fields):
        return json.dumps(fields, ensure_ascii=False, indent=2)
    try:
        state = _state(controller)
    except Exception as exc:
        return reply(checkpoint=False, reason=str(exc), directive="하던 방향으로 진행한다.")
    learned = str((payload or {}).get("evidence") or "").strip()
    stated = str((payload or {}).get("progress") or "").strip()
    if state["depth"] <= 0:
        return reply(checkpoint=False, directive="이 턴에는 되돌아보기가 없다. 그대로 진행한다.")
    if state["done"] >= state["depth"]:
        return reply(checkpoint=False, directive="되돌아보기를 모두 마쳤다. 끝까지 진행하고, 끝내기 전에 한 번 확인받는다.")
    if not learned:
        return reply(checkpoint=False, reason="evidence 에 지금까지 알게 된 것을 적어야 한다")
    with controller.review_lock:  # 하네스의 대신 되돌아보기·중간검토와 겹치지 않는다
        if state["done"] >= state["depth"]:
            return reply(checkpoint=False, directive="되돌아보기를 모두 마쳤다. 끝까지 진행한다.")
        if controller.cancelled() or controller.finalizing:
            return reply(checkpoint=False, directive="실행이 끝나는 중이다. 새 작업을 시작하지 않는다.")
        state["busy"].set()
        with controller.lock:
            paused = controller.executor_paused
            controller.executor_paused = True
        try:
            with _turn_context(controller):
                try:
                    row = _round(controller, state, note=learned, by="executor", stated=stated)
                except Exception as exc:  # 되돌아보기가 실패해도 실행은 그대로 간다
                    controller.log("deep.error", role="consciousness", stage="checkpoint", error=str(exc))
                    return reply(checkpoint=False, reason="되돌아보기를 하지 못했다: " + str(exc),
                                 directive="하던 방향으로 진행한다.")
        finally:
            with controller.lock:
                controller.executor_paused = paused
                controller.phase = "execute"
            state["busy"].clear()
    return reply(checkpoint=True, round=f"{row['round']}/{state['depth']}", verdict=row["verdict"],
                 content=_guidance(row, state))


def tick(controller):
    """감시 주기마다 불린다. 실행자가 돌아오지 않은 채 상한을 넘었으면 대신 되돌아보고 True 를 돌려준다.

    이 기능의 오류가 기존 감독을 멈추게 하지 않는다 — 여기서 난 예외는 False 로 삼킨다.
    """
    try:
        state = _state(controller)
        if state["depth"] <= 0 or state["done"] >= state["depth"]:
            return False
        if controller.store.cost["execution_calls"] - state["last_calls"] < _ceiling(state["cfg"], state["done"]):
            return False
        return reflect(controller, state)
    except Exception as exc:
        try:
            controller.log("deep.error", role="harness", stage="tick", error=str(exc))
        except Exception:
            pass
        return False


def reflect(controller, state):
    """실행자가 돌아오지 않았을 때 하네스가 대신 되돌아본다. 판단은 다음 도구 경계에서 전달된다."""
    from supervision_store import digest
    if not controller.review_lock.acquire(blocking=False):
        return False
    state["busy"].set()  # run_tool 이 이 동안 실행자의 다음 도구 호출을 붙잡는다
    try:
        if controller.finalizing or controller.cancelled() or state["done"] >= state["depth"]:
            return False
        revision = controller.exec_revision
        goal = digest(json.dumps(controller.framing or {}, sort_keys=True, ensure_ascii=False))
        row = _round(controller, state, note=None, by="harness")
        if controller.cancelled() or controller.finalizing:
            return True
        if row["verdict"] == "KEEP" and state["done"] >= state["depth"]:
            return True  # 바꿀 것도, 다시 돌아올 지점도 없다
        notice = {"id": uuid.uuid4().hex, "reason": row["reason"] or row["verdict"], "source": "deep_execution",
                  "target": {"agent": controller.owner, "task": controller.task},
                  "sequence": controller.store.sequence, "expires_at": None, "review": row["round"],
                  "revision": revision,
                  "conditions": {"trigger": "deep_reflection", "call_signature": "", "goal": goal,
                                 "issues": {}, "incidents": {}, "active": [], "jobs": {}},
                  "findings": [{"id": f"deep-{row['round']}", "scope": "goal",
                                "reason": f"심층실행 되돌아보기 {row['round']}/{state['depth']} — "
                                          "정해진 지점에서 돌아오지 않아 실행 기록으로 대신 되돌아봤다",
                                "instruction": _guidance(row, state), "resolved_when": "", "evidence_ids": [],
                                "needs_recheck": False}]}
        with controller.lock:
            controller.pending = notice
            controller.log("instruction.queued", role="harness", instruction=notice)
        return True
    except Exception as exc:  # 되돌아보기가 실패해도 실행은 그대로 간다
        controller.log("deep.error", role="consciousness", stage="reflect", error=str(exc))
        return True
    finally:
        controller.phase = "execute"
        controller.executor_paused = False
        state["busy"].clear()
        controller.review_lock.release()


def hold(controller):
    """하네스가 대신 되돌아보는 동안 실행자의 다음 도구 호출을 잠깐 붙잡는다. 잠금은 쥐지 않는다."""
    state = getattr(controller, "_deep", None)
    if not state or not state["busy"].is_set():
        return
    try:
        deadline = time.monotonic() + float(state["cfg"]["hold_s"])
        while state["busy"].is_set() and time.monotonic() < deadline and not controller.cancelled():
            time.sleep(0.25)
    except Exception:
        return


# ── 끝내기 직전 ────────────────────────────────────────────────────────────────

RESUME = """[심층실행 — 끝내기 전 확인]
방향 담당자가 지금까지의 작업과 응답 초안을 사용자 요청과 대조했다. 아래 지적을 현재 상태에 비춰 확인한다.
맞는 것은 고치거나 마저 한다. 고치지 않는 것은 이유와 남은 한계를 밝힌다. 이미 끝낸 부작용은 반복하지 않는다.
새 조사를 크게 열지 말고 지적에 필요한 일만 한다. 끝나면 사용자에게 전할 최종 응답 전체를 다시 쓴다.

"""


def final_check(runner, controller, message, response, history, *, collect, images=None, cancel_check=None):
    """끝내기 직전 한 번. 교정이 있으면 실행자를 한 번 잇는다. 해당 없으면 응답을 그대로 돌려준다."""
    if False:
        yield  # 제너레이터로 만든다
    try:
        if controller is None or not getattr(controller, "enabled", False) or not (response or "").strip():
            return response
        state = _state(controller)
        if (state["depth"] <= 0 or not state["cfg"]["final_check"] or state["final_done"]
                or controller.store.cost["execution_calls"] < 1 or controller.cancelled()):
            return response
        state["final_done"] = True
        from supervisor_interventions import review_findings
        from supervisor_runtime import invoke, parse_decision
        with controller.review_lock:
            controller.executor_paused = True  # 실행자가 멈춘 때다. 필요한 원문을 읽을 수 있게 한다
            try:
                k, errors, digest_text, _ = trace_of(controller, state["cfg"], per_result=300)
                packet = {"trigger": "completion", **controller.state(),
                          "tool_calls": k, "tool_failures": errors,
                          "events_digest": digest_text[:state["cfg"]["trace_chars"]],
                          "deep_memo": memo_text(state, controller.framing) if state["memo"] else "",
                          "response_draft": response[:20000]}
                decision = parse_decision(invoke(controller, json.dumps(packet, ensure_ascii=False, default=str),
                                                 phase="review"))
            finally:
                controller.phase = "execute"
                controller.executor_paused = False
        rows = [r for r in review_findings(decision) if r["instruction"].strip()] if decision["status"] == "REWORK" else []
        controller.log("deep.final_check", role="consciousness", status=decision["status"], findings=len(rows),
                       reason=decision.get("reason", ""))
        if not rows or controller.cancelled():
            return response
        from task_continuation import execution_available
        if not execution_available(controller):
            return response
        instruction = RESUME + "\n".join(f"- {r['reason']}\n  → {r['instruction']}" for r in rows)
        from repair_readiness import execution_stream
        stream = execution_stream(runner.ai.process_message_stream(
            message_content=instruction, history=history, images=images, cancel_check=cancel_check))
    except Exception as exc:  # 확인이 실패해도 실행자의 응답은 그대로 전달한다
        try:
            controller.log("deep.error", role="consciousness", stage="final", error=str(exc))
        except Exception:
            pass
        return response
    candidate = ""
    try:
        for event in stream:
            collect(event)
            controller.observe_native(event)
            if event.get("type") == "final":
                if (event.get("content") or "").strip():
                    candidate = event["content"]
            elif event.get("type") != "text":
                yield event
    finally:
        stream.close()
    controller.log("deep.final_resumed", role="harness", rewritten=bool(candidate))
    return candidate or response
