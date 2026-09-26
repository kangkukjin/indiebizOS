"""관용구 반환 관측(2026-09-26) — 성공한 실행이 *실제로* 돌려준 최상위 필드를 정의 행(`returns_observed`)에 병합하고,
회상 줄·어휘 병기·describe 가 같은 표시(`→ Record⟨관측: a·b⟩`)로 싣는다.

선언(returns)이 아니라 흔적이다. 4018 실측: 회상 줄이 `[fn:AI팁보고서쓰기]{} → Record` 만 말해 모델이 반환 계약을
describe 로 한 번 더 확인했다 — 이상은 호출 1회이므로 그 근거를 여기서 없앤다.
정본: docs/IBL_INCREMENTAL_EXECUTION_2026_09_26.md §5
"""
import json
import time

OBSERVED_KEYS_CAP = 40
DISPLAY_KEYS = 16   # 완료 증거 필드(shared_report·published)가 관측 순서상 뒤에 오는 보고서 관용구 15필드가 다 보이는 폭


def merge_observed_returns(existing: str, keys, kind: str = "record", source: str = "run") -> str:
    """병합 — 먼저 본 순서를 지키고 새 키는 뒤에, 상한 40(넘치면 more 에 수)."""
    try:
        cur = json.loads(existing) if existing else {}
    except ValueError:
        cur = {}
    if not isinstance(cur, dict):
        cur = {}
    seen = [k for k in (cur.get("keys") or []) if isinstance(k, str)]
    for k in keys or []:
        if isinstance(k, str) and k not in seen:
            seen.append(k)
    return json.dumps({"kind": kind or cur.get("kind") or "record", "keys": seen[:OBSERVED_KEYS_CAP],
                       "more": max(0, len(seen) - OBSERVED_KEYS_CAP), "runs": int(cur.get("runs") or 0) + 1,
                       "observed": time.strftime("%Y-%m-%d"), "source": source}, ensure_ascii=False)


def returns_display(returns: str, observed: str) -> str:
    """선언(returns) 뒤에 관측 필드를 `⟨관측: a·b⟩` 로 붙인다. 선언이 이미 필드를 말하면(`{…}`·`⟨…⟩`) 덮지 않는다."""
    returns = (returns or "").strip()
    try:
        obs = json.loads(observed) if observed else {}
    except ValueError:
        obs = {}
    keys = [k for k in (obs.get("keys") or []) if isinstance(k, str)] if isinstance(obs, dict) else []
    if not keys or "⟨" in returns or "{" in returns:
        return returns
    shown = "·".join(keys[:DISPLAY_KEYS]) + ("…" if len(keys) > DISPLAY_KEYS or obs.get("more") else "")
    if obs.get("kind") == "list":
        return f"List<Record⟨관측: {shown}⟩>"
    return f"{returns or 'Record'}⟨관측: {shown}⟩"


def record_observed_returns(db, ibl_code: str, keys, kind: str = "record", source: str = "run") -> bool:
    """ibl_code 정확 일치(update_success_by_code 와 같은 귀속)의 최신 행에 병합. 성공 실행만 부른다. 반환: 갱신 여부."""
    if not ibl_code or not keys:
        return False
    with db._get_connection() as conn:
        row = conn.execute(
            "SELECT id, COALESCE(returns_observed,'') AS o FROM ibl_examples WHERE ibl_code = ? ORDER BY updated_at DESC LIMIT 1",
            (ibl_code,)).fetchone()
        if not row:
            return False
        conn.execute("UPDATE ibl_examples SET returns_observed=? WHERE id=?",
                     (merge_observed_returns(row["o"], keys, kind, source), row["id"]))
        conn.commit()
    return True
