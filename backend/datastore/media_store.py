"""media_store.py — 미디어 세션 최소 이력 (2026-10-13).

설계 정본: docs/MEDIA_COMMUNICATION_DESIGN_2026_10_13.md §8 '세션 인증' 마지막 문단, §10.
남기는 것 = 시작·종료 시각, 참가 장치, 허가 근거, 경로, 품질 지표, 오류. 영상·음성 원본·인증 토큰·SDP·ICE
원문은 **절대** 저장하지 않는다. 활성 연결은 영속 복원 대상이 아니다(재시작 = 전부 종료).
저장소: data/media/state.db (INDIEBIZ_RUNTIME_STATE_DIR 가 있으면 그 아래 — 시험 격리).
"""
import json
import os
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, List, Optional

_lock = threading.Lock()
_SCHEMA = """
CREATE TABLE IF NOT EXISTS media_sessions (
    id TEXT PRIMARY KEY, kind TEXT NOT NULL, purpose TEXT NOT NULL, basis TEXT NOT NULL,
    role TEXT NOT NULL, peer TEXT, device TEXT, participants TEXT NOT NULL, tracks TEXT NOT NULL,
    delivery TEXT NOT NULL, created REAL NOT NULL, connected REAL, ended REAL, end_reason TEXT,
    path TEXT, quality TEXT, error TEXT, route TEXT);
CREATE INDEX IF NOT EXISTS media_sessions_created ON media_sessions(created);
CREATE TABLE IF NOT EXISTS media_blocks (pubkey TEXT PRIMARY KEY, created REAL NOT NULL, note TEXT);
"""


def _root() -> Path:
    state = os.environ.get("INDIEBIZ_RUNTIME_STATE_DIR")
    if state:
        return Path(state) / "media"
    from runtime_utils import get_data_path
    return Path(get_data_path()) / "media"


def _db_path() -> Path:
    root = _root()
    root.mkdir(parents=True, exist_ok=True)
    return root / "state.db"


@contextmanager
def _db():
    path = _db_path()
    conn = sqlite3.connect(str(path), timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(_SCHEMA)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        with conn:
            yield conn
    finally:
        conn.close()


def _j(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True)


def record_start(session: Dict) -> None:
    """세션 생성 시 1행. 토큰·SDP 가 들어오지 않도록 받는 칸을 명시한다."""
    with _lock, _db() as db:
        db.execute("INSERT OR REPLACE INTO media_sessions(id,kind,purpose,basis,role,peer,device,participants,tracks,"
                   "delivery,created,route) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
                   (session["session_id"], session["kind"], session["purpose"], session["authorization_basis"],
                    session.get("local_role") or "", session.get("peer"), session.get("device"),
                    _j(session.get("participants") or []), _j([{k: t.get(k) for k in ("id", "kind", "source", "from", "to")}
                                                              for t in session.get("tracks") or []]),
                    session.get("delivery") or "realtime", float(session.get("created_at") or time.time()),
                    (session.get("signaling") or {}).get("route")))


def record_connected(session_id: str, path: Optional[str]) -> None:
    with _lock, _db() as db:
        db.execute("UPDATE media_sessions SET connected=COALESCE(connected,?), path=? WHERE id=?",
                   (time.time(), path, session_id))


def record_quality(session_id: str, quality: Dict, path: Optional[str] = None) -> None:
    q = {k: quality.get(k) for k in ("rtt_ms", "loss", "jitter_ms", "bitrate_kbps", "fps", "width", "height", "dropped")}
    with _lock, _db() as db:
        if path:
            db.execute("UPDATE media_sessions SET quality=?, path=? WHERE id=?", (_j(q), path, session_id))
        else:
            db.execute("UPDATE media_sessions SET quality=? WHERE id=?", (_j(q), session_id))


def record_end(session_id: str, reason: str, error: Optional[Dict] = None) -> None:
    with _lock, _db() as db:
        db.execute("UPDATE media_sessions SET ended=COALESCE(ended,?), end_reason=?, error=? WHERE id=?",
                   (time.time(), reason, _j({"code": error.get("code"), "message": error.get("message")}) if error else None,
                    session_id))


HISTORY_LIMIT_MAX = 500


def history(limit: int = 50, peer: Optional[str] = None, device: Optional[str] = None) -> List[Dict]:
    """이력 조회. 요청 개수가 상한을 넘으면 깎되 각 행의 메타가 아니라 호출자에게 알리도록 clamped 표식을 돌려준다."""
    requested = int(limit or 50)
    limit = max(1, min(HISTORY_LIMIT_MAX, requested))
    sql, args = "SELECT * FROM media_sessions", []
    where = []
    if peer:
        where.append("peer=?"); args.append(peer)
    if device:
        where.append("device=?"); args.append(device)
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY created DESC LIMIT ?"
    args.append(limit)
    with _lock, _db() as db:
        rows = [dict(r) for r in db.execute(sql, args)]
    for r in rows:
        for key in ("participants", "tracks", "quality", "error"):
            if r.get(key):
                try:
                    r[key] = json.loads(r[key])
                except ValueError:
                    pass
        r["duration_s"] = round((r["ended"] or time.time()) - (r["connected"] or r["created"]), 1) if r.get("connected") else None
    if requested != limit:
        rows = list(rows)
        rows.append({"clamped": True, "requested": requested, "limit": limit})
    return rows


def block(pubkey: str, note: str = "") -> None:
    with _lock, _db() as db:
        db.execute("INSERT OR REPLACE INTO media_blocks(pubkey,created,note) VALUES(?,?,?)", (pubkey, time.time(), note))


def unblock(pubkey: str) -> None:
    with _lock, _db() as db:
        db.execute("DELETE FROM media_blocks WHERE pubkey=?", (pubkey,))


def is_blocked(pubkey: str) -> bool:
    if not pubkey:
        return False
    with _lock, _db() as db:
        return db.execute("SELECT 1 FROM media_blocks WHERE pubkey=?", (pubkey,)).fetchone() is not None


def blocked() -> List[Dict]:
    with _lock, _db() as db:
        return [dict(r) for r in db.execute("SELECT * FROM media_blocks ORDER BY created DESC")]
