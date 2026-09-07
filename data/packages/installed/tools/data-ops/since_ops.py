"""since_ops.py — [table:since] 검침(시간 차분) 변환자. handler.py 에서 분할(1500줄 관문).

★왜 여기로 나왔나: handler.py 는 스스로 "통화 대수(관계대수)만" 이라고 선언하는데
since 는 유일하게 **원장을 쥔** 변환자다(data/table_since.db — 스트림별 기준선). 다른
동사들은 입력만 보고 답을 내지만 since 의 답은 '지난번에 무엇을 봤는가'에 달려 있다.
순수한 대수와 상태를 가진 검침이 한 파일에 있던 것이 원래 이상이었다.

통화 입출력 도우미(get_items/emit_items·진단)는 handler 가 인자로 넘긴다 —
형제 모듈이 handler 를 되부르면 순환이 되므로(branch_protocol 선례).
"""

import json

# 변화 판정도 공통 값 의미론에 직접 위임한다.
from common import value_semantics as _wdsl


_SINCE_CAP = 5000                     # 스트림당 기준선 키 상한 — 초과분은 오래 안 보인 것부터 정리
_SINCE_ID_CANDIDATES = ("url", "id", "link", "title")


def since_conn():
    """검침 원장 연결 — 스트림별 last-seen 키·감시값 (data/table_since.db, WAL).

    사라진 키를 지우지 않고 누적한다: 회전 소스(검색·RSS '최근 N개 창')에서 빠졌다
    재등장한 행을 '새 것'으로 오보하지 않기 위해 (warehouse_feed 의 RSS 스냅샷 누적 선례).
    """
    import sqlite3
    from pathlib import Path
    path = Path(__file__).resolve().parents[5] / "data" / "table_since.db"   # notebook_core 선례
    conn = sqlite3.connect(str(path), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        "CREATE TABLE IF NOT EXISTS since_seen ("
        " stream TEXT NOT NULL, k TEXT NOT NULL, watched TEXT,"
        " first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,"
        " PRIMARY KEY (stream, k))")
    return conn


def op_since(prev, params, get_items, emit_items,
             no_currency_error, field_missing_error, value_semantics, since_conn):
    """items → 지난 검침 이후 새 행만 (+watch 필드 변화 행). 기준선은 스트림(key)별.

    warehouse_feed 의 seed/new/changed diff 를 통화 변환자로 일반화 — 모든 items
    생산자에 곱해져 감시자가 된다. 첫 검침은 기준선만 저장하고 빈 items 를 정직하게
    반환한다(첫 실행에 전부를 '새 것'으로 쏟으면 트리거 알림이 스팸이 된다).
    """
    key = params.get("key")
    if not key or not str(key).strip():
        return {"success": False, "error": (
            "since: key(검침 스트림 이름)가 필요합니다 — 감시 파이프마다 고유한 이름을 주세요. "
            '예: [sense:feed]{url:...} >> [table:since]{key: "하다뉴스"}')}
    key = str(key).strip()

    recs, env = get_items(prev)
    if recs is None:
        return no_currency_error("since", prev)
    rows = [r for r in recs if isinstance(r, dict)]

    by = params.get("by")
    if by:
        by = str(by)
        if rows and not any(by in r for r in rows):
            return field_missing_error("since", [by], rows)
    else:
        by = next((c for c in _SINCE_ID_CANDIDATES
                   if rows and all(r.get(c) not in (None, "") for r in rows)), None)
        if rows and not by:
            avail = sorted({f for r in rows for f in r.keys()})
            return {"success": False, "error": (
                "since: 행 식별 필드를 못 골랐습니다(후보 url/id/link/title 이 모든 행에 없음). "
                f"by 로 지정하세요. 사용 가능한 필드: {avail[:12]}")}

    watch = params.get("watch") or []
    if isinstance(watch, str):
        watch = [watch]
    watch = [str(w) for w in watch if w]
    if watch and rows:
        missing = [w for w in watch if not any(w in r for r in rows)]
        if missing:
            return field_missing_error("since", missing, rows)
    peek = bool(params.get("peek"))

    from datetime import datetime
    now = datetime.now().isoformat(timespec="seconds")
    conn = since_conn()
    trimmed = 0
    try:
        # 구조형 키는 순서 독립 정본 키로 읽고 쓴다. 구버전이 str(dict) 로 남긴
        # 원장도 별칭으로 함께 색인해 필드 순서가 바뀐 같은 실체를 거짓 new 로
        # 오보하지 않는다 (Codex 흡수, 2026-08-26).
        seen, legacy_seen = value_semantics.persisted_seen(conn.execute(
            "SELECT k, watched FROM since_seen WHERE stream=?", (key,)))
        first_run = not seen
        out, n_new, n_changed = [], 0, 0
        _missing = object()
        for r in rows:
            rk, legacy_rk = value_semantics.persistent_keys(r.get(by))
            previous = seen.get(rk, _missing)
            if previous is _missing and legacy_rk != rk:  # vj-ok: 정본 키 비교
                previous = seen.get(legacy_rk, _missing)  # 옛 str(dict) 원장 호환
            if previous is _missing:
                if not first_run:
                    out.append({**r, "_since": "new"})
                    n_new += 1
            elif watch:
                try:
                    prev_wv = json.loads(previous) if previous else None
                except Exception:
                    prev_wv = None
                cur_wv = {w: r.get(w) for w in watch}
                # 감시 시작 전 키(prev_wv 없음)는 변화 판정 불가 — 거짓 changed 금지.
                # 변화 판정은 조건 언어의 동등성 한 벌 — 원시 != 는 생산자의 표기 변경
                # (1 → "1")을 값 변화로 오보한다(46회차 후속 census).
                if prev_wv is not None and not _wdsl.values_equal(cur_wv, prev_wv):
                    out.append({**r, "_since": "changed", "_since_prev": prev_wv})
                    n_changed += 1
        if not peek:
            for r in rows:
                rk, legacy_rk = value_semantics.persistent_keys(r.get(by))
                wjson = (json.dumps({w: r.get(w) for w in watch},
                                    ensure_ascii=False, sort_keys=True)
                         if watch else None)
                conn.execute(
                    "INSERT INTO since_seen (stream,k,watched,first_seen,last_seen)"
                    " VALUES (?,?,?,?,?) ON CONFLICT(stream,k) DO UPDATE SET"
                    " watched=excluded.watched, last_seen=excluded.last_seen",
                    (key, rk, wjson, now, now))
                value_semantics.migrate_since_keys(conn, key, rk, legacy_rk, legacy_seen)
            total = conn.execute(
                "SELECT COUNT(*) FROM since_seen WHERE stream=?", (key,)).fetchone()[0]
            if total > _SINCE_CAP:
                trimmed = total - _SINCE_CAP
                conn.execute(
                    "DELETE FROM since_seen WHERE rowid IN (SELECT rowid FROM since_seen"
                    " WHERE stream=? ORDER BY last_seen ASC LIMIT ?)", (key, trimmed))
            conn.commit()
        baseline = conn.execute(
            "SELECT COUNT(*) FROM since_seen WHERE stream=?", (key,)).fetchone()[0]
    finally:
        conn.close()

    result = emit_items(env, out)
    result["since_key"] = key
    result["since_by"] = by
    result["baseline_total"] = baseline
    if first_run:
        if peek:
            result["note"] = (f"첫 검침(peek) — 기준선 저장 안 함({len(rows)}행 미기록). "
                              "peek 없이 호출하면 기준선이 저장됩니다.")
        else:
            # ★P1 (2026-08-20, B15-2): 기계 판별용 플래그 — note 산문만으론 트리거·후속
            # 파이프가 "첫 회라 0행"과 "고장이라 0행"을 구별할 수 없다. 2회차부턴 미표기.
            result["seeded"] = True
            result["note"] = (f"첫 검침 — 기준선 {len(rows)}행 저장(스트림 '{key}'). "
                              "다음 호출부터 지난 검침 이후 새 행만 흐릅니다.")
    elif not out:
        result["note"] = f"지난 검침 이후 새 항목 없음 (기준선 {baseline}행)."
    else:
        parts = ([f"새 {n_new}건"] if n_new else []) + ([f"변경 {n_changed}건"] if n_changed else [])
        result["note"] = "지난 검침 이후 " + "·".join(parts) + "."
    if trimmed:
        result["note"] += f" (기준선 상한 {_SINCE_CAP} 초과 — 오래 안 보인 {trimmed}키 정리)"
    if peek and not first_run:
        result["note"] += " (peek — 기준선 안 올림)"
    return result
