"""되풀이 실패 감사 — 같은 실행 실패가 여러 날 되풀이되면 신고한다 (2026-11-14, docs/MEMORY_REPAIR_PLAN_2026_11_14.md R5).

왜 있나: 2026-10-15~11-14 실측에서 실행 실패 221종 가운데 34종이 3일 이상 되풀이되며 실패의 55%를 차지했고,
그 99%는 같은 턴 안에서 스스로 풀렸다 — 같은 문제를 날마다 새로 풀고 있었다. 그 3분의 2는 쓰는 법(문법·인자·타입)
이라 AI 가 외울 일이 아니라 언어·교재가 받을 몫이다(예: `[self:task]` 에 `task_ref:` — 접수증 칸 이름을 그대로 되넣음).

이 감사는 **신고만 한다**. 무엇이 여러 날 되풀이되는지를 꼴과 함께 적어 둘 뿐, 별칭을 받을지 교재를 고칠지 오류문을
바꿀지는 읽는 쪽이 정한다. 깃발은 data/recurring_failure_flags.json 에 남는다.
"""
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent.parent
_STATE_PATH = _ROOT / "data" / ".recurring_failure_state.json"
_FLAGS_PATH = _ROOT / "data" / "recurring_failure_flags.json"
WINDOW_DAYS = 14
MIN_DAYS = 3              # 이 날 수 이상에 걸쳐 나온 꼴만 '되풀이'
MIN_RUNS = 50             # 실행이 이보다 적은 기간은 판정하지 않는다(관측 부족)
MAX_FLAGS = 30
_DECODER = json.JSONDecoder()
_CALL = re.compile(r'\[([a-z_]+:[a-z_0-9]+)\]\s*\{([^}]*)\}')
_ACTION = re.compile(r'\[([a-z_]+:[a-z_0-9]+)\]')


def _head(result):
    """결과의 앞 객체. 옛 기록(2026-10-31~11-14)은 결과 뒤에 실행 상황 블록이 붙어 있어 통째로는 읽히지 않는다."""
    if isinstance(result, dict):
        return result
    if not isinstance(result, str):
        return None
    try:
        return _DECODER.raw_decode(result.lstrip())[0]
    except ValueError:
        return None


def _error(data):
    error = data.get("error") or data.get("message") or ""
    if isinstance(error, dict):
        error = error.get("message") or json.dumps(error, ensure_ascii=False)
    return " ".join(str(error).split())


def signature(error: str, code: str):
    """(꼴, 부류). 손댈 수 있을 만큼 구체적으로 — 어느 액션의 어느 인자인지, 어느 칸인지."""
    actions = _ACTION.findall(code or "")
    found = re.search(r"알 수 없는 인자: ([\w, ]+?)\.", error)
    if found:
        wrong = found.group(1).split(",")[0].strip()
        owner = next((name for name, body in _CALL.findall(code or "")
                      if re.search(r"\b" + re.escape(wrong) + r"\s*:", body)), actions[0] if actions else "?")
        return f"알 수 없는 인자 {owner}.{wrong}", "쓰는 법"
    found = re.search(r"선언된 필드가 없습니다: ([\w$\[\]]+)", error)
    if found:
        return f"선언된 필드 없음 .{found.group(1)}", "쓰는 법"
    found = re.search(r"select 입력 \d+번 행에 열이 없습니다: \[?([^\].]+)\]?", error)
    if found:
        source = next((a for a in actions if not a.startswith("table:")), "?")
        return f"select 없는 열 {source}: {found.group(1).strip()[:40]}", "쓰는 법"
    text = re.sub(r"'[^']*'|\"[^\"]*\"|`[^`]*`|\$\w+", "Q", error)
    text = re.sub(r"(?<![\w가-힣])/[\w./-]+", "P", text)      # 경로만 — `has/get`·`읽기/쓰기` 의 빗금은 건드리지 않는다
    text = re.sub(r"\d+", "#", text)[:60].strip()
    if any(mark in error for mark in ("실행 전", "검사에서 거절", "따옴표", "순수 식", "병렬 가지", "문자열로 바꿀", "줄바꿈")):
        return text, "쓰는 법"
    if any(mark in error for mark in ("HTTP", "봇 차단", "브라우저", "deadline", "exit status", "시간 안에", "연결")):
        return text, "바깥 사정"
    if any(mark in error for mark in ("범위 밖", "저장소 안", "권한", "승인")):
        return text, "경계·권한"
    return text, "기타"


def measure(rows) -> Dict:
    """rows = (payload JSON, updated_at) 의 나열. 모델 호출·쓰기 없음."""
    runs = failures = 0
    seen: Dict[str, Dict] = {}
    for payload, updated_at in rows:
        try:
            job = json.loads(payload)
        except (ValueError, TypeError):
            continue
        day = str(job.get("recorded_at") or updated_at or "")[:10]
        calls = [tc for tc in job.get("tool_calls") or [] if isinstance(tc, dict)
                 and tc.get("tool_name") == "execute_ibl" and not (tc.get("input") or {}).get("check")]
        runs += len(calls)
        outcomes = []
        for tc in calls:
            data = _head(tc.get("result"))
            failed = isinstance(data, dict) and (data.get("success") is False
                                                 or (bool(data.get("error")) and data.get("success") is not True))
            outcomes.append((tc, data, failed))
        in_turn = set()
        for index, (tc, data, failed) in enumerate(outcomes):
            if not failed:
                continue
            error = _error(data)
            if not error:
                continue
            failures += 1
            key, kind = signature(error, (tc.get("input") or {}).get("code") or "")
            if key in in_turn:
                continue
            in_turn.add(key)
            row = seen.setdefault(key, {"signature": key, "kind": kind, "turns": 0, "days": set(),
                                        "recovered": 0, "example": error[:240]})
            row["turns"] += 1
            row["days"].add(day)
            row["recovered"] += any(not later for _, _, later in outcomes[index + 1:])
    flags = [{**row, "days": len(row["days"]), "first": min(row["days"]), "last": max(row["days"])}
             for row in seen.values() if len(row["days"]) >= MIN_DAYS]
    flags.sort(key=lambda row: (-row["turns"], row["signature"]))
    return {"runs": runs, "failures": failures, "kinds": len(seen), "recurring": len(flags),
            "flags": flags[:MAX_FLAGS], "unchecked": [] if runs >= MIN_RUNS else ["executions_below_minimum"]}


def _recent_rows():
    from pulse_db import _get_pulse_db
    since = (datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)).isoformat()
    conn = _get_pulse_db()
    try:
        return conn.execute("SELECT payload, updated_at FROM distill_jobs WHERE updated_at >= ?", (since,)).fetchall()
    finally:
        conn.close()


def run_recurring_failure_check(force: bool = False) -> Dict:
    """주간 카덴스로 되풀이되는 실행 실패를 모아 self_checks 형식 1건을 반환. 보고만 하고 고치지 않는다."""
    from audit_lifecycle import due
    if not due(_STATE_PATH, force):
        return {"skipped": "cadence"}
    started = datetime.now()
    seen: Dict = {"flags": [], "unchecked": []}
    error = None
    try:
        seen = measure(_recent_rows())
    except Exception as e:
        error = f"측정 실패: {e}"
    flags, unchecked = seen["flags"], seen["unchecked"]
    try:
        _FLAGS_PATH.write_text(json.dumps({
            "measured_at": started.isoformat(), "window_days": WINDOW_DAYS, "min_days": MIN_DAYS,
            **{k: seen[k] for k in ("runs", "failures", "kinds", "recurring") if k in seen},
            "flags": flags, "unchecked": unchecked, "error": error,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
        _STATE_PATH.write_text(json.dumps({
            "last_run": started.isoformat(), "flag_count": len(flags),
            "unchecked": unchecked, "error": error,
        }, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        error = f"{error + '; ' if error else ''}상태 저장 실패: {e}"
    message = None
    if flags:
        top = flags[0]
        message = (f"되풀이되는 실행 실패 {seen.get('recurring', len(flags))}종 — 가장 잦은 것: {top['signature']} "
                   f"({top['turns']}턴·{top['days']}일) — recurring_failure_flags.json")
    elif error:
        message = error
    elif unchecked:
        message = f"지난 {WINDOW_DAYS}일 실행이 {MIN_RUNS}건 미만 — 판정 보류"
    if message:
        logger.warning(f"[RecurringFailure] {message}")
    return {
        "node": "__static__", "action": "recurring_failure",
        "success": not flags and not error and not unchecked,
        "response_ms": int((datetime.now() - started).total_seconds() * 1000),
        "data_quality": ("ok" if not flags and not error and not unchecked
                         else "recurring" if flags else "audit_incomplete"),
        "error_message": message, "flags": flags, "unchecked": unchecked, "error": error,
        **{k: seen[k] for k in ("runs", "failures", "kinds", "recurring") if k in seen},
    }
