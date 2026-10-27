"""독립 AI 실행의 채팅 표면 관측(99회차). /chat-sessions 에 세션을 만들고 메시지를 보낸 뒤 스냅샷을 0.5초마다 읽어
turn.progress(action/step/detail/age_s)·사건(interim_text/tool_start/tool_result)·상태 변화를 기록한다. origin 필드 없음(표식 없는 실사용 턴)."""
import json, sys, time, urllib.request
from pathlib import Path
BASE = "http://127.0.0.1:8765"; OUT = Path(sys.argv[1]); MSG = Path(sys.argv[2]).read_text(encoding="utf-8")
def call(method, path, body=None):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode() if body is not None else None, method=method,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r: return json.load(r)
sess = call("POST", "/chat-sessions", {"target": "system_ai", "title": "긴문장 99회차 독립 AI — 진행 표면"})
sid = sess.get("id") or sess.get("session_id") or sess.get("session", {}).get("id")
log = {"session": sess, "sid": sid, "sent_at": time.strftime("%H:%M:%S"), "progress_trace": [], "events": [], "states": []}
acc = call("POST", f"/chat-sessions/{sid}/messages", {"target": "system_ai", "message": MSG})
log["accepted"] = acc; t0 = time.time(); last_prog = None; seen_events = 0; last_state = None
while time.time() - t0 < 900:
    time.sleep(0.5)
    try: snap = call("GET", f"/chat-sessions/{sid}?target=system_ai")
    except Exception as e: log["states"].append({"t": round(time.time()-t0,1), "poll_error": str(e)[:100]}); continue
    turn = snap.get("turn") or {}; state = turn.get("state"); prog = turn.get("progress")
    if state != last_state: log["states"].append({"t": round(time.time()-t0,1), "state": state}); last_state = state
    sig = json.dumps(prog, sort_keys=True) if prog else None
    key = json.dumps({k: (prog or {}).get(k) for k in ("action","step","detail")}, sort_keys=True) if prog else None
    if key != (log["progress_trace"][-1]["key"] if log["progress_trace"] else None):
        log["progress_trace"].append({"t": round(time.time()-t0,1), "key": key, "progress": prog})
    evs = snap.get("events") or []
    for e in evs[seen_events:]:
        log["events"].append({"t": round(time.time()-t0,1), "type": e.get("type"), "name": e.get("name"), "content": (e.get("content") or "")[:160] if isinstance(e.get("content"), str) else None,
                              "input": json.dumps(e.get("input"), ensure_ascii=False)[:200] if e.get("input") else None, "is_error": e.get("is_error")})
    seen_events = max(seen_events, len(evs))
    if state in ("completed", "failed", "cancelled") and time.time() - t0 > 5: break
log["finished_at"] = time.strftime("%H:%M:%S"); log["seconds"] = round(time.time()-t0,1); log["final_turn"] = {k: turn.get(k) for k in ("id","state","error")}
OUT.write_text(json.dumps(log, ensure_ascii=False, indent=1)); print("done", sid, log["seconds"], last_state)
