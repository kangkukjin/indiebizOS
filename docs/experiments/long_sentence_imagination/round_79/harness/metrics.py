"""에피소드 id 범위의 역할별 model.usage·시간·route·reflex 사건을 world_pulse.db(읽기 전용)에서 모은다."""
import json, sqlite3, sys
DB = "/Users/kangkukjin/Desktop/AI/indiebizOS/data/world_pulse.db"
def collect(ids):
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True); out = []
    for eid in ids:
        e = con.execute("select id, started_at, ended_at, total_ms, source, user_message, task_id from episode_log where id=?", (eid,)).fetchone()
        if not e: continue
        row = {"episode": eid, "started_at": e[1], "ended_at": e[2], "total_ms": e[3], "source": e[4], "task_id": e[6],
               "message": (e[5] or "")[:120], "roles": {}, "route": None, "reflex": [], "tools": [], "usage": {"input":0,"output":0,"cache_read":0,"cache_create":0}}
        for (kind, data) in con.execute("select kind, data from trajectory_event where episode_id=? order by event_seq", (eid,)):
            d = json.loads(data) if data else {}
            if kind == "model.usage":
                r = row["roles"].setdefault(d.get("role"), {"calls":0,"input":0,"output":0,"cache_read":0,"cache_create":0,"latency_ms":0,"phase":d.get("phase"),"model":d.get("model")})
                r["calls"] += 1
                for k in ("input","output","cache_read","cache_create"): r[k] += int(d.get(k) or 0); row["usage"][k] += int(d.get(k) or 0)
                r["latency_ms"] += int(d.get("latency_ms") or 0)
            elif kind == "cognition.route": row["route"] = d
            elif kind.startswith("cognition.reflex"): row["reflex"].append({"kind": kind, **d})
            elif kind == "supervision.tool.finished":
                row["tools"].append({"elapsed_s": d.get("elapsed_s"), "check_rejected": d.get("check_rejected"), "excerpt": (d.get("evidence") or {}).get("excerpt","")[:160]})
            elif kind == "model.input" and d.get("role") == "execution":
                row.setdefault("exec_input_shape", []).append({k: d.get(k) for k in ("system_chars","history_chars","message_chars","tool_schema_chars","model")})
        out.append(row)
    return out
if __name__ == "__main__":
    ids = [int(x) for x in sys.argv[1:]]
    print(json.dumps(collect(ids), ensure_ascii=False, indent=1))
