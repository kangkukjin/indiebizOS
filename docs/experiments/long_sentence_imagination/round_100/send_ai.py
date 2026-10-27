"""100회차 독립 AI 1회 — POST /system-ai/chat {message, origin:"training", background:true} → task_id/status_url → GET ?wait=20 폴링.
보내기 전 episode_log 마지막 id 를 적어 새 에피소드를 찾는다. 결과 JSON 한 장(ai_run.json)."""
import json, sqlite3, sys, time, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parents[4]; OUT = Path(sys.argv[1]); MSG = Path(sys.argv[2]).read_text(encoding="utf-8")
BASE = "http://127.0.0.1:8765"
def call(method, path, body=None, timeout=60):
    req = urllib.request.Request(path if path.startswith("http") else BASE + path, data=json.dumps(body).encode() if body is not None else None, method=method, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r: return json.load(r)
con = sqlite3.connect(f"file:{ROOT/'data/world_pulse.db'}?mode=ro", uri=True)
ep_before = con.execute("select max(id) from episode_log").fetchone()[0]
log = {"episode_before": ep_before, "sent_at": time.strftime("%Y-%m-%d %H:%M:%S"), "t0": time.time(), "polls": []}
acc = call("POST", "/system-ai/chat", {"message": MSG, "origin": "training", "background": True}, timeout=120)
log["accepted"] = acc
status_url = acc.get("status_url") or (acc.get("task") or {}).get("status_url")
task_id = acc.get("task_id") or (acc.get("task") or {}).get("task_id")
log["task_id"] = task_id; log["status_url"] = status_url
final = None
while time.time() - log["t0"] < 1500 and status_url:
    try: st = call("GET", (status_url if status_url.startswith("http") else BASE + status_url) + ("&" if "?" in status_url else "?") + "wait=20", timeout=40)
    except Exception as e: log["polls"].append({"t": round(time.time()-log["t0"],1), "error": str(e)[:160]}); time.sleep(5); continue
    s = st.get("state") or st.get("status"); log["polls"].append({"t": round(time.time()-log["t0"],1), "status": s})
    if s in ("succeeded", "failed", "cancelled", "expired", "completed"): final = st; break
log["final"] = final; log["seconds"] = round(time.time() - log["t0"], 1)
log["episode_after"] = con.execute("select max(id) from episode_log").fetchone()[0]
log["new_episodes"] = [dict(zip(("id","started_at","source","total_ms"), r)) for r in con.execute("select id, started_at, source, total_ms from episode_log where id > ? order by id", (ep_before,)).fetchall()]
OUT.write_text(json.dumps(log, ensure_ascii=False, indent=1)); print(json.dumps({k: log[k] for k in ("task_id","seconds","episode_before","episode_after")}, ensure_ascii=False), (final or {}).get("status"))
