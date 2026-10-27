"""99회차 보조 실행부 — IBL inputs Text 로 ~turn 에 쓰여 [self:script]{path} 로 돈다.
좁은 도우미만: /ibl/execute(ticket) POST 를 스레드로 띄우고 /ibl/recover 를 폴링해 running 스냅샷을 구조화한다.
값 전달·판정·보고는 IBL. args(stdin JSON): {op:"launch", code, inputs, reuse?, poll_s?, timeout?, label}
→ INDIEBIZ_SCRIPT_RESULT 에 {ticket, run_id, snapshots:[...], final:{...}, polls, seconds}. 큰 정수 금지(JSON 경계)."""
import json, os, sys, threading, time, urllib.error, urllib.request, uuid
args = json.load(sys.stdin)
BASE = "http://127.0.0.1:8765"

def post(path, body, timeout):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return {"success": False, "http_error": e.code, "error": e.read().decode()[:500]}
    except Exception as e:
        return {"success": False, "transport_error": str(e)[:300]}

def find_key(obj, key, depth=0):
    if depth > 4: return None
    if isinstance(obj, dict):
        if key in obj: return obj[key]
        for v in obj.values():
            f = find_key(v, key, depth + 1)
            if f is not None: return f
    return None

def launch(a):
    ticket = uuid.uuid4().hex
    body = {"code": a["code"], "inputs": a.get("inputs") or {}, "ticket": ticket, "origin": "training", "edition": 2, "project_id": "study"}
    if a.get("reuse"):
        body["reuse"] = {"run_id": a["reuse"]}
    box = {}
    def run():
        box["env"] = post("/ibl/execute", body, a.get("timeout", 120))
    t0 = time.time(); th = threading.Thread(target=run); th.start()
    snaps, polls, poll_s = [], 0, float(a.get("poll_s", 0.15))
    last_sig = None
    while th.is_alive():
        time.sleep(poll_s); polls += 1
        rec = post("/ibl/recover", {"ticket": ticket}, 10)
        if rec.get("status") != "running": continue
        prog = rec.get("progress") if isinstance(rec.get("progress"), dict) else {}
        note = rec.get("note") or ""
        sig = (prog.get("step"), prog.get("action"), json.dumps(prog.get("detail"), sort_keys=True), prog.get("updated_at"))
        if sig == last_sig:
            snaps[-1]["repeat"] = snaps[-1].get("repeat", 0) + 1; continue
        last_sig = sig
        prev = snaps[-1] if snaps else {}
        snaps.append({"t": round(time.time() - t0, 2), "idx": len(snaps) + 1, "step_prev": prev.get("step"), "step": prog.get("step"), "of": prog.get("of"), "action": prog.get("action"),
                      "detail": prog.get("detail"), "row": (prog.get("detail") or {}).get("row"), "rows": (prog.get("detail") or {}).get("rows"),
                      "row_label": (prog.get("detail") or {}).get("row_label"), "updated_at": prog.get("updated_at"), "has_progress": bool(prog), "repeat": 0,
                      "note_has_action": bool(prog.get("action")) and str(prog.get("action")) in note,
                      "note_head": note[:90]})
    th.join()
    env = box.get("env") or {}
    err = env.get("error")
    run_id = env.get("run_id") or find_key(env, "run_id")
    final = {"success": env.get("success"), "run_id": run_id, "error": (err if isinstance(err, str) else json.dumps(err, ensure_ascii=False))[:400] if err else None,
             "receipt_reused": find_key(env, "receipt_reused"), "reused_calls": find_key(env, "reused_calls"),
             "coverage": find_key(env, "coverage"), "successful_indices": find_key(env, "successful_indices"),
             "value": env.get("value") if not isinstance(env.get("value"), dict) or len(json.dumps(env.get("value"))) < 600 else "(생략)",
             "http_error": env.get("http_error"), "transport_error": env.get("transport_error"),
             "env_keys": sorted(env.keys())[:40], "reuse_info": json.dumps(env.get("reuse"), ensure_ascii=False)[:300] if env.get("reuse") is not None else None,
             "usage": json.dumps(env.get("usage"), ensure_ascii=False)[:400] if env.get("usage") is not None else None}
    after = post("/ibl/recover", {"ticket": ticket}, 10)
    return {"label": a.get("label"), "ticket": ticket, "snapshots": snaps, "polls": polls, "seconds": round(time.time() - t0, 2),
            "final": final, "after_status": after.get("status") or ("done" if after.get("_recovered_from_ticket") else "?"),
            "after_has_error": bool(after.get("error")), "run_id": run_id}

out = launch(args) if args.get("op", "launch") == "launch" else {"error": "unknown op"}
p = os.environ["INDIEBIZ_SCRIPT_RESULT"]; tmp = p + ".tmp"
open(tmp, "w").write(json.dumps(out, ensure_ascii=False)); os.replace(tmp, p)
