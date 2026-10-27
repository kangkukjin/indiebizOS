"""100회차 — 표식 있는(/system-ai/chat origin:training) 독립 AI 턴의 채팅 표면 관측.
rehearsal 소유자 세션의 최신 턴을 data/system_ai_memory.db(읽기 전용)에서 0.5초마다 읽어 progress(action/step/detail/age)·state 변화를 기록한다.
사용: ai_observe_db.py <out.json> <시작 시각 epoch> [최대 초]"""
import json, sqlite3, sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[4]; OUT = Path(sys.argv[1]); T0 = float(sys.argv[2]); MAX = int(sys.argv[3]) if len(sys.argv) > 3 else 1500
DB = ROOT / "data/system_ai_memory.db"
def q(sql, args=()):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True); con.row_factory = sqlite3.Row
    try: return [dict(r) for r in con.execute(sql, args).fetchall()]
    finally: con.close()
log = {"progress_trace": [], "states": [], "turn": None, "started": time.strftime("%H:%M:%S")}
turn_id = None; last_key = None; last_state = None; t_start = time.time()
while time.time() - t_start < MAX:
    time.sleep(0.5)
    try:
        if turn_id is None:
            rows = q("SELECT t.id, t.state, t.started_at, t.session_id FROM conversation_turns t JOIN conversation_sessions s ON s.id=t.session_id WHERE s.owner='rehearsal' ORDER BY t.started_at DESC LIMIT 1")
            if not rows: continue
            # 관측 시작 이후 열린 턴만
            r = rows[0]
            st = r.get("started_at")
            from datetime import datetime, timezone
            try: st_f = float(st)
            except Exception:
                try:
                    dt = datetime.fromisoformat(str(st)); st_f = (dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)).timestamp()
                except Exception: st_f = time.time()
            if st_f < T0 - 5: continue
            turn_id = r["id"]; log["turn"] = r; log["states"].append({"t": round(time.time()-t_start,1), "found_turn": turn_id})
        rows = q("SELECT state, progress, finished_at, error FROM conversation_turns WHERE id=?", (turn_id,))
        if not rows: continue
        r = rows[0]; state = r["state"]
        if state != last_state: log["states"].append({"t": round(time.time()-t_start,1), "state": state}); last_state = state
        prog = None
        if r["progress"]:
            try: prog = json.loads(r["progress"])
            except Exception: prog = {"raw": r["progress"][:200]}
        key = json.dumps({k: (prog or {}).get(k) for k in ("action","step","of","detail")}, sort_keys=True) if prog else None
        if key != last_key:
            log["progress_trace"].append({"t": round(time.time()-t_start,1), "key": key, "progress": prog}); last_key = key
        if state in ("completed", "failed", "cancelled") and r["finished_at"]:
            log["final"] = r; break
    except Exception as e:
        log["states"].append({"t": round(time.time()-t_start,1), "error": str(e)[:160]}); time.sleep(2)
log["seconds"] = round(time.time()-t_start, 1)
ev = q("SELECT payload FROM conversation_events WHERE turn_id=? ORDER BY id", (turn_id,)) if turn_id else []
kinds = {}
for e in ev:
    try: k = json.loads(e["payload"]).get("type")
    except Exception: k = "?"
    kinds[k] = kinds.get(k, 0) + 1
log["event_kinds"] = kinds; log["events_total"] = len(ev)
log["progress_nonnull"] = sum(1 for p in log["progress_trace"] if p["progress"])
OUT.write_text(json.dumps(log, ensure_ascii=False, indent=1, default=str)); print("observe done turn", turn_id, "progress transitions", len(log["progress_trace"]), "nonnull", log["progress_nonnull"], "events", kinds)
