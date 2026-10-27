"""101회차 — POST /system-ai/chat {message, origin:"training", background:true} → status_url 폴링(wait=20) → 종료 회수.
보내기 전 episode_log 마지막 id·conversations(source=rehearsal) 마지막 id 를 적어 새 증거를 찾는다. 결과 JSON 한 장.
사용: send_ai.py <out.json> <message.txt> [max_s]"""
import json, sqlite3, sys, time, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parents[4]; OUT = Path(sys.argv[1]); MSG = Path(sys.argv[2]).read_text(encoding="utf-8")
MAX = int(sys.argv[3]) if len(sys.argv) > 3 else 1500
BASE = "http://127.0.0.1:8765"
def call(method, path, body=None, timeout=60):
    req = urllib.request.Request(path if path.startswith("http") else BASE + path, data=json.dumps(body).encode() if body is not None else None, method=method, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r: return json.load(r)
wp = sqlite3.connect(f"file:{ROOT/'data/world_pulse.db'}?mode=ro", uri=True)
mem = sqlite3.connect(f"file:{ROOT/'data/system_ai_memory.db'}?mode=ro", uri=True)
ep_before = wp.execute("select max(id) from episode_log").fetchone()[0]
conv_before = mem.execute("select max(id) from conversations where source='rehearsal'").fetchone()[0]
log = {"message_file": sys.argv[2], "episode_before": ep_before, "conversation_before": conv_before, "sent_at": time.strftime("%Y-%m-%d %H:%M:%S"), "t0": time.time(), "polls": []}
acc = call("POST", "/system-ai/chat", {"message": MSG, "origin": "training", "background": True}, timeout=120)
log["accepted"] = acc
status_url = acc.get("status_url"); task_id = acc.get("task_id")
log["task_id"] = task_id; log["status_url"] = status_url
final = None
while time.time() - log["t0"] < MAX and status_url:
    try: st = call("GET", (status_url if status_url.startswith("http") else BASE + status_url) + ("&" if "?" in status_url else "?") + "wait=20", timeout=40)
    except Exception as e: log["polls"].append({"t": round(time.time()-log["t0"],1), "error": str(e)[:160]}); time.sleep(5); continue
    s = st.get("state") or st.get("status"); log["polls"].append({"t": round(time.time()-log["t0"],1), "state": s})
    if s in ("succeeded", "failed", "cancelled", "expired"): final = st; break
log["final_state"] = (final or {}).get("state"); log["final"] = final
log["seconds"] = round(time.time() - log["t0"], 1); log["finished_at"] = time.strftime("%Y-%m-%d %H:%M:%S")
log["episode_after"] = wp.execute("select max(id) from episode_log").fetchone()[0]
log["new_episodes"] = [dict(zip(("id","started_at","ended_at","source","agent","task_id","total_ms"), r)) for r in wp.execute("select id, started_at, ended_at, source, agent, task_id, total_ms from episode_log where id > ? order by id", (ep_before,)).fetchall()]
log["new_conversations"] = [dict(zip(("id","role","timestamp","session_id","chars"), r)) for r in mem.execute("select id, role, timestamp, session_id, length(content) from conversations where source='rehearsal' and id > ? order by id", (conv_before,)).fetchall()]
OUT.write_text(json.dumps(log, ensure_ascii=False, indent=1, default=str)); print(json.dumps({k: log[k] for k in ("task_id","seconds","final_state","episode_before","episode_after")}, ensure_ascii=False))
