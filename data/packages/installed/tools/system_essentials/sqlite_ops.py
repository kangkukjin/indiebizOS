"""[sense:sqlite] — SQLite 파일 읽기 전용 조회 (2026-09-05, 사용자 판정 "어휘는 만들자").

왜: 새 요청 289건의 도구 호출 절반이 Bash 였고 그중 sqlite3 셸이 65회 — 모델이 몸의 원장(.db)을 보려고
IBL 밖으로 나갔다. Bash 로 나간 조회는 해마·타입 검사·관용구 귀속 밖이라 다음 주행이 배우지 못한다.
이 낱말은 *접근*(sqlite 파일 열기·SQL 실행·행 dict 통화)을 캡슐화한다. 분석 관습은 어휘에 넣지 않는다.

계약(읽기 전용, 파괴 불가):
  · 연결은 `mode=ro` URI — 쓰기 SQL 은 엔진이 거절하고, 그 전에 문장 머리 관문이 SELECT/WITH/PRAGMA/EXPLAIN 만 통과시킨다.
  · op=query(기본): path·query(·params 목록·limit 기본 200, 상한 2000) → items(행 dict) + columns + truncated(limit 에 걸렸을 때).
  · op=tables: path → items(name·rows) — 표 목록과 행 수(빠른 지도).
  · op=schema: path·table → items(cid·name·type·notnull·pk) — 열 목록(PRAGMA table_info).
  · 경로는 `~workspace/`·절대·상대(저장소 루트 기준). 저장소 밖도 읽기는 허용(사용자 파일) — 쓰기가 없으니 위험이 없다.
  · 열 이름은 데이터가 정한다(`columns_from: data`) — 정적 검사기는 fixture 열을 이 낱말의 열로 쓰지 않는다.
"""
import re
import sqlite3
from pathlib import Path

from runtime_utils import expand_body_path  # 경로 펼침 단일 해소점 (~workspace/·~)

_ROOT = Path(__file__).resolve().parents[5]  # indiebizOS/
_READ_HEAD = re.compile(r"^\s*(select|with|pragma|explain)\b", re.IGNORECASE)
_FORBIDDEN = re.compile(r"\b(insert|update|delete|drop|alter|create|replace|attach|detach|vacuum|reindex)\b", re.IGNORECASE)
LIMIT_DEFAULT = 200
LIMIT_MAX = 2000


def _db_path(tool_input):
    raw = str(tool_input.get("path") or "").strip()
    if not raw:
        return None, {"success": False, "items": [], "error": "path 가 필요합니다 — SQLite 파일 경로(~workspace/data/….db 등)."}
    s = expand_body_path(raw)
    p = Path(s)
    if not p.is_absolute():
        p = (_ROOT / p).resolve()
    if not p.is_file():
        return None, {"success": False, "items": [], "error": f"SQLite 파일이 없습니다: {raw} (해석: {p})",
                      "hint": "파일 위치가 불확실하면 [self:file_find]{pattern: \"*.db\"} 로 먼저 찾으세요."}
    return p, None


def _connect(p: Path):
    conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=5)
    conn.row_factory = sqlite3.Row
    return conn


def _limit(tool_input):
    try:
        n = int(tool_input.get("limit") or LIMIT_DEFAULT)
    except (TypeError, ValueError):
        n = LIMIT_DEFAULT
    return max(1, min(n, LIMIT_MAX))  # clamp-ok: 표본 상한 — 초과는 truncated 로 신고


def op_query(tool_input):
    p, err = _db_path(tool_input)
    if err:
        return err
    q = str(tool_input.get("query") or "").strip().rstrip(";")
    if not q:
        return {"success": False, "items": [], "error": "query 가 필요합니다 — SELECT 문(읽기 전용)."}
    if not _READ_HEAD.match(q) or _FORBIDDEN.search(q):
        return {"success": False, "items": [],
                "error": "읽기 전용 낱말입니다 — SELECT/WITH/PRAGMA/EXPLAIN 만 실행합니다(INSERT·UPDATE·DELETE·DDL 거절).",
                "hint": "원장을 고쳐야 하면 그 원장의 낱말([self:ledger]·[self:business] 등)이나 등록 스크립트를 쓰세요."}
    params = tool_input.get("params")
    if params is None:
        params = []
    if not isinstance(params, (list, tuple)):
        return {"success": False, "items": [], "error": "params 는 목록이어야 합니다 — query 의 ? 자리에 순서대로 들어갑니다."}
    limit = _limit(tool_input)
    try:
        conn = _connect(p)
        try:
            cur = conn.execute(q, tuple(params))
            cols = [d[0] for d in (cur.description or [])]
            rows = cur.fetchmany(limit + 1)
        finally:
            conn.close()
    except sqlite3.Error as e:
        return {"success": False, "items": [], "error": f"SQL 오류: {e}", "path": str(p),
                "hint": "표·열 이름이 불확실하면 op:\"tables\" / op:\"schema\" 로 먼저 보세요."}
    truncated = len(rows) > limit
    rows = rows[:limit]
    items = [{c: r[i] for i, c in enumerate(cols)} for r in rows]
    out = {"success": True, "op": "query", "path": str(p), "columns": cols, "count": len(items), "items": items}
    if truncated:
        out["truncated"] = True
        out["note"] = f"limit {limit} 에 걸렸습니다 — 더 보려면 limit 을 올리거나 WHERE 로 좁히세요(상한 {LIMIT_MAX})."
    return out


def op_tables(tool_input):
    p, err = _db_path(tool_input)
    if err:
        return err
    try:
        conn = _connect(p)
        try:
            names = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' ORDER BY name")]
            items = []
            for n in names:
                try:
                    cnt = conn.execute(f'SELECT COUNT(*) FROM "{n}"').fetchone()[0]
                except sqlite3.Error:
                    cnt = None
                items.append({"name": n, "rows": cnt})
        finally:
            conn.close()
    except sqlite3.Error as e:
        return {"success": False, "items": [], "error": f"SQLite 열기 실패: {e}", "path": str(p)}
    return {"success": True, "op": "tables", "path": str(p), "count": len(items), "items": items}


def op_schema(tool_input):
    p, err = _db_path(tool_input)
    if err:
        return err
    table = str(tool_input.get("table") or "").strip()
    if not table or not re.match(r"^[\w가-힣]+$", table):
        return {"success": False, "items": [], "error": "table 이 필요합니다(표 이름 하나) — 목록은 op:\"tables\"."}
    try:
        conn = _connect(p)
        try:
            rows = conn.execute(f'PRAGMA table_info("{table}")').fetchall()
        finally:
            conn.close()
    except sqlite3.Error as e:
        return {"success": False, "items": [], "error": f"SQLite 열기 실패: {e}", "path": str(p)}
    if not rows:
        return {"success": False, "items": [], "error": f"표가 없습니다: {table}", "path": str(p),
                "hint": "op:\"tables\" 로 이름을 확인하세요."}
    items = [{"cid": r["cid"], "name": r["name"], "type": r["type"], "notnull": bool(r["notnull"]),
              "default": r["dflt_value"], "pk": bool(r["pk"])} for r in rows]
    return {"success": True, "op": "schema", "path": str(p), "table": table, "count": len(items), "items": items}
