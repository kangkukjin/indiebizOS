"""조언성 감사의 등록·주기·결과 계약. 상태 파일의 독립 복구 경계는 유지한다."""
import json
from datetime import datetime, timedelta

AUDITS = [
    ("data_ownership", "data_ownership", "run_data_ownership_check"),
    ("doc_drift", "doc_drift", "run_doc_drift_check"),
    ("store_waste", "store_waste_audit", "run_store_waste_check"),
    ("vocab_overlap", "vocab_overlap_audit", "run_vocab_overlap_check"),
]
CADENCE_HOURS = 168
MAX_CADENCE_HOURS = 672


def read_state(path):
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
        return state if isinstance(state, dict) else {}
    except (OSError, ValueError):
        return {}


def due(path, force=False, *, fingerprint=None, now=None):
    """실패·미관측은 다음 유지보수 때 재시도. 입력이 바뀌면 감쇠 대기를 무시한다."""
    if force:
        return True
    state = read_state(path)
    if not state or state.get("error") or state.get("unchecked"):
        return True
    if fingerprint is not None and state.get("fingerprint") != fingerprint:
        return True
    hours = CADENCE_HOURS
    if (fingerprint is not None and state.get("outcome") == "clean"
            and state.get("coverage") == "complete"):
        configured = state.get("cadence_hours", CADENCE_HOURS)
        if type(configured) is int:
            hours = min(MAX_CADENCE_HOURS, max(CADENCE_HOURS, configured))
    try:
        return (now or datetime.now()) - datetime.fromisoformat(state["last_run"]) >= timedelta(hours=hours)
    except (KeyError, TypeError, ValueError):
        return True


def next_cadence(previous, *, fingerprint, clean, complete):
    """충분히 검사한 같은 입력에서만 3회 단위로 최대 4주까지 감쇠한다."""
    same = previous.get("fingerprint") == fingerprint
    prior = previous.get("clean_streak", 0)
    prior = max(0, prior) if type(prior) is int else 0
    streak = (prior if same else 0) + 1 if clean and complete else 0
    hours = min(MAX_CADENCE_HOURS, CADENCE_HOURS * (2 ** min(streak // 3, 2)))
    return {"clean_streak": streak, "cadence_hours": hours}


def normalize_result(result):
    """0건·생략·실패·관측 부족을 분리한다. 성공을 선언하지 않은 결과는 clean이 아니다."""
    if not isinstance(result, dict):
        raise ValueError("감사가 결과 객체를 반환하지 않았습니다")
    out = dict(result)
    if out.get("skipped"):
        status = "skipped"
    elif out.get("error"):
        status = "failed"
    elif out.get("unchecked"):
        status = "insufficient"
    elif out.get("flags") or out.get("orphans"):
        status = "findings"
    elif out.get("success") is True:
        status = "clean"
    elif out.get("data_quality") == "audit_incomplete":
        status = "failed"
    else:
        status = "insufficient"
    out["audit_status"] = status
    if status in {"failed", "insufficient"}:
        out["success"] = False
        out["data_quality"] = "audit_incomplete"
        out["error_message"] = out.get("error_message") or "감사를 완료하지 못했습니다"
    return out
