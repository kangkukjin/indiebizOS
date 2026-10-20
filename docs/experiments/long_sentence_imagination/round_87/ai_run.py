"""Send the task to the system AI (origin=training) and recover evidence from world_pulse.db."""
import json, sqlite3, sys, time, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "outputs/long_sentence_imagination/2026-10-20_87회차/ai"
DB = ROOT / "data/world_pulse.db"

def last_episode():
    with sqlite3.connect(f"file:{DB}?mode=ro", uri=True) as db:
        return db.execute("select max(id) from episode_log").fetchone()[0]

def send(message):
    body = {"message": message, "origin": "training"}
    req = urllib.request.Request("http://127.0.0.1:8765/system-ai/chat", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    t0 = time.time()
    with urllib.request.urlopen(req, timeout=3600) as r: res = json.load(r)
    return res, time.time() - t0

def evidence(since_id):
    with sqlite3.connect(f"file:{DB}?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        eps = [dict(r) for r in db.execute("select id,total_ms,source,task_id,run_id from episode_log where id>? order by id", (since_id,))]
        out = {"episodes": eps, "tools": [], "usage": [], "recall": []}
        for ep in eps:
            for r in db.execute("select kind,data as payload from trajectory_event where episode_id=? order by event_seq", (ep["id"],)):
                k = r["kind"]; p = json.loads(r["payload"]) if r["payload"] else {}
                if k == "supervision.tool.started":
                    inp = p.get("input") or {}
                    code = inp.get("code") if isinstance(inp, dict) else None
                    out["tools"].append({"ep": ep["id"], "tool": p.get("tool") or p.get("name"), "code_head": (code or json.dumps(inp, ensure_ascii=False))[:400]})
                elif k == "model.usage":
                    out["usage"].append({"ep": ep["id"], **{kk: p.get(kk) for kk in ("role", "input", "cache_read", "cache_create", "output", "accounting")}})
                elif k in ("recall.presented", "recall.used", "supervision.cost.summary", "context.compacted"):
                    out["recall"].append({"ep": ep["id"], "kind": k, "payload": json.dumps(p, ensure_ascii=False)[:600]})
        return out

if __name__ == "__main__":
    if sys.argv[1] == "send":
        since = last_episode(); (OUT / "since.json").write_text(json.dumps({"since": since, "started": time.time()}))
        res, sec = send((OUT / "message.txt").read_text())
        (OUT / "response.json").write_text(json.dumps({"seconds": sec, "response": res}, ensure_ascii=False, indent=1))
        print(json.dumps({"seconds": sec, "keys": list(res)[:10], "answer_head": str(res.get("response") or res.get("answer") or res)[:800]}, ensure_ascii=False))
    else:
        since = json.loads((OUT / "since.json").read_text())["since"]
        ev = evidence(since); (OUT / "evidence.json").write_text(json.dumps(ev, ensure_ascii=False, indent=1))
        print(json.dumps({"episodes": ev["episodes"], "tool_count": len(ev["tools"]), "tools": [(t["tool"], t["code_head"][:120]) for t in ev["tools"]], "usage": ev["usage"][:20]}, ensure_ascii=False, indent=1)[:6000])
