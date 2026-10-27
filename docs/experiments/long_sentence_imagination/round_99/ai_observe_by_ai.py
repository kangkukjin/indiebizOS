"""실행 중 /ibl/recover 표본 수집기 — 한 프로그램을 ticket 과 함께 띄우고 0.2초 간격으로 회수한다."""
import json, sys, threading, time, secrets, urllib.request
from pathlib import Path
BASE = "http://127.0.0.1:8765"
ROOT = Path(__file__).resolve().parent
SUB = ROOT.parent / "subjects"

def post(path, body, timeout):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())

def run(name, prog, inputs, project_id, reuse=None, interval=0.2):
    ticket = secrets.token_hex(12)
    body = {"code": (SUB / prog).read_text(), "inputs": inputs, "ticket": ticket,
            "project_id": project_id, "origin": "training"}
    if reuse: body["reuse"] = reuse
    box = {}
    def go():
        t = time.time()
        try: box["result"] = post("/ibl/execute", body, 300)
        except Exception as e: box["error"] = repr(e)
        box["wall_s"] = round(time.time() - t, 3)
    th = threading.Thread(target=go); t0 = time.time(); th.start()
    samples = []
    while True:
        try: env = post("/ibl/recover", {"ticket": ticket}, 10)
        except Exception as e: env = {"status": "poll_error", "error": repr(e)}
        p = env.get("progress") or {}
        d = p.get("detail") if isinstance(p.get("detail"), dict) else {}
        s = {"t": round(time.time() - t0, 3), "status": env.get("status"),
             "step": p.get("step"), "of": p.get("of"), "action": p.get("action"),
             "row": d.get("row"), "rows": d.get("rows"), "detail": d or None,
             "updated_at": p.get("updated_at"), "note": env.get("note"), "recovered": bool(env.get("_recovered_from_ticket"))}
        if env.get("status") == "done" or env.get("_recovered_from_ticket"):
            s["envelope_keys"] = sorted((env.get("envelope") or {}).keys()) if isinstance(env.get("envelope"), dict) else None
            samples.append(s); final = env; break
        samples.append(s)
        if not th.is_alive() and time.time() - t0 > 1 and env.get("status") != "running":
            final = env; break
        time.sleep(interval)
    th.join()
    out = {"name": name, "program": prog, "ticket": ticket, "interval_s": interval, "reuse": reuse,
           "wall_s": box.get("wall_s"), "execute_error": box.get("error"),
           "result": box.get("result"), "recover_final": final, "samples": samples}
    (ROOT / "raw" / f"{name}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    r = box.get("result") or {}
    print(name, "samples", len(samples), "wall", box.get("wall_s"), "success", r.get("success"),
          "run_id", r.get("run_id") or (r.get("result_ref") or {}).get("run_id"), "keys", sorted(r.keys())[:30])
    return out

if __name__ == "__main__":
    a = json.loads(sys.argv[1])
    run(**a)
