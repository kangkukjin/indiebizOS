"""증류 건강 감사 — 죽은 학습 고리를 한 주 안에 드러낸다 (2026-11-14, docs/MEMORY_REPAIR_PLAN_2026_11_14.md R1).

왜 있나: 통합 증류는 "0건 저장은 정상 성공"이라, 결과를 못 읽어서 0건인 것과 배울 것이 없어서 0건인
것이 같은 모습이다. 2026-10-31 부터 두 주 동안 실행기억 증류가 0건이었는데 아무 경보도 없었다
(같은 부류 세 번째: 08-07 고점수 회상 유실, 10-03 회상 사용 거짓 0).

이 감사는 저장 건수를 재지 않는다. **성공한 실행의 결과를 읽을 수 있었는가**와 **후보가 하나라도
만들어졌는가**만 본다. 보고만 하고 고치지 않는다.
"""
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict

logger = logging.getLogger(__name__)

_ROOT = Path(__file__).resolve().parent.parent.parent
_STATE_PATH = _ROOT / "data" / ".distill_health_state.json"
WINDOW_DAYS = 7
MIN_CALLS = 20            # 성공한 실행이 이보다 적은 주는 판정하지 않는다(관측 부족)
MIN_TURNS = 20            # 후보 0건 신고에 필요한, 성공한 실행이 있었던 턴 수
UNREADABLE_SHARE = 0.2    # 성공한 실행 결과 중 이 비율을 넘게 못 읽으면 신고


def measure(rows) -> Dict:
    """rows = (payload JSON, prepared JSON) 의 나열. 모델 호출·쓰기 없음."""
    calls = unreadable = turns = with_candidates = 0
    by_provider: Dict[str, list] = {}
    for payload, prepared in rows:
        try:
            job = json.loads(payload)
        except (ValueError, TypeError):
            continue
        model = job.get("model")
        provider = str((model.get("provider") if isinstance(model, dict) else model) or "?")
        seen = 0
        for tc in job.get("tool_calls") or []:
            if (not isinstance(tc, dict) or tc.get("tool_name") != "execute_ibl"
                    or tc.get("success") is not True or (tc.get("input") or {}).get("check")):
                continue
            seen += 1
            row = by_provider.setdefault(provider, [0, 0])
            row[0] += 1
            result = tc.get("result")
            if isinstance(result, str):
                try:
                    json.loads(result)
                except ValueError:
                    unreadable += 1
                    row[1] += 1
        if not seen:
            continue
        calls += seen
        turns += 1
        try:
            sections = (json.loads(prepared) if prepared else {}).get("sections") or {}
            with_candidates += "execution" in sections
        except (ValueError, TypeError, AttributeError):
            pass
    flags = []
    if calls >= MIN_CALLS and unreadable / calls > UNREADABLE_SHARE:
        flags.append({"kind": "unreadable_results", "calls": calls, "unreadable": unreadable,
                      "by_provider": {k: {"calls": v[0], "unreadable": v[1]}
                                      for k, v in by_provider.items() if v[1]}})
    if turns >= MIN_TURNS and not with_candidates:
        flags.append({"kind": "no_execution_candidates", "turns_with_successful_runs": turns})
    return {"calls": calls, "unreadable": unreadable, "turns": turns,
            "turns_with_candidates": with_candidates, "flags": flags,
            "unchecked": [] if calls >= MIN_CALLS else ["successful_runs_below_minimum"]}


def _recent_rows():
    from pulse_db import _get_pulse_db
    since = (datetime.now(timezone.utc) - timedelta(days=WINDOW_DAYS)).isoformat()
    conn = _get_pulse_db()
    try:
        return conn.execute("SELECT payload, prepared FROM distill_jobs WHERE updated_at >= ?",
                            (since,)).fetchall()
    finally:
        conn.close()


def run_distill_health_check(force: bool = False) -> Dict:
    """주간 카덴스로 증류 고리의 생사를 보고 self_checks 형식 1건을 반환."""
    from audit_lifecycle import due
    if not due(_STATE_PATH, force):
        return {"skipped": "cadence"}
    started = datetime.now()
    seen: Dict = {"flags": [], "unchecked": []}
    error = None
    try:
        seen = measure(_recent_rows())
    except Exception as e:
        # 측정 실패도 실패다 — 못 본 것을 '건강함'으로 보고하면 이 감사가 같은 병에 걸린다.
        error = f"측정 실패: {e}"
    flags, unchecked = seen["flags"], seen["unchecked"]
    try:
        _STATE_PATH.write_text(json.dumps({
            "last_run": started.isoformat(), "flag_count": len(flags),
            "unchecked": unchecked, "error": error,
        }, ensure_ascii=False), encoding="utf-8")
    except Exception as e:
        error = f"{error + '; ' if error else ''}상태 저장 실패: {e}"
    message = None
    if flags:
        kinds = ", ".join(f["kind"] for f in flags)
        message = (f"증류 고리 이상({kinds}) — 성공한 실행 {seen.get('calls', 0)}건 중 "
                   f"{seen.get('unreadable', 0)}건의 결과를 읽지 못했고, 후보가 만들어진 턴은 "
                   f"{seen.get('turns_with_candidates', 0)}/{seen.get('turns', 0)}")
    elif error:
        message = error
    elif unchecked:
        message = f"지난 {WINDOW_DAYS}일 성공한 실행이 {MIN_CALLS}건 미만 — 판정 보류"
    if message:
        logger.warning(f"[DistillHealth] {message}")
    return {
        "node": "__static__", "action": "distill_health",
        "success": not flags and not error and not unchecked,
        "response_ms": int((datetime.now() - started).total_seconds() * 1000),
        "data_quality": ("ok" if not flags and not error and not unchecked
                         else "dead_loop" if flags else "audit_incomplete"),
        "error_message": message, "flags": flags, "unchecked": unchecked, "error": error,
        **{k: seen[k] for k in ("calls", "unreadable", "turns", "turns_with_candidates") if k in seen},
    }
