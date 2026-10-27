"""표본기: /ibl/execute 를 ticket 과 함께 띄우고, 끝날 때까지 /ibl/recover 를 짧은 간격으로 폴링한다.
사용: python3 sampler.py <이름> <ibl파일> [--parallel N] [--reuse RUN_ID] [--list N] [--interval 0.1]
결과: ai_out/samples/<이름>.json (요청 요약·표본 시계열·결말 요약)."""
import json, os, re, secrets, sys, threading, time, urllib.request, argparse

BASE = "http://127.0.0.1:8765"
HERE = os.path.dirname(os.path.abspath(__file__))
SUBJ = os.path.join(os.path.dirname(HERE), "subjects")


def post(path, body, timeout):
    req = urllib.request.Request(BASE + path, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read())


ap = argparse.ArgumentParser()
ap.add_argument("name"); ap.add_argument("program")
ap.add_argument("--parallel", type=int); ap.add_argument("--reuse")
ap.add_argument("--list", type=int); ap.add_argument("--interval", type=float, default=0.1)
a = ap.parse_args()

code = open(os.path.join(SUBJ, a.program), encoding="utf-8").read()
if a.parallel is not None:
    code = code.replace("parallel:$병렬", f"parallel:{a.parallel}")
inputs = {"본문": open(os.path.join(SUBJ, "sleeper.py"), encoding="utf-8").read(),
          "파일": os.path.join(SUBJ, "fixture.txt")}
if a.list:
    inputs["목록"] = list(range(1, a.list + 1))
ticket = secrets.token_hex(8)
body = {"code": code, "edition": 2, "inputs": inputs, "origin": "training", "project_id": "수동모드", "ticket": ticket}
if a.reuse:
    body["reuse"] = {"run_id": a.reuse}

final = {}
def run():
    t0 = time.time()
    try:
        final["envelope"] = post("/ibl/execute", body, 300)
    except Exception as e:
        final["error"] = repr(e)
    final["wall_s"] = round(time.time() - t0, 3)

samples = []
start = time.time()
th = threading.Thread(target=run); th.start()
while True:
    t = time.time()
    try:
        r = post("/ibl/recover", {"ticket": ticket}, 10)
    except Exception as e:
        r = {"_poll_error": repr(e)}
    s = {"t": round(t - start, 3), "wall": time.strftime("%H:%M:%S", time.localtime(t)) + f".{int((t % 1) * 1000):03d}"}
    for k in ("status", "state", "progress", "note", "updated_at", "started_at"):
        if k in r:
            s[k] = r[k]
    if "success" in r and "status" not in r:
        s["status"] = "done(envelope)"
    if "_poll_error" in r:
        s["poll_error"] = r["_poll_error"]
    samples.append(s)
    if not th.is_alive():
        break
    time.sleep(a.interval)
th.join()
# 결말 직후 recover 한 번 더(결말 봉투에 progress/note 가 남는지)
try:
    post_final = post("/ibl/recover", {"ticket": ticket}, 10)
except Exception as e:
    post_final = {"_poll_error": repr(e)}

env = final.get("envelope") or {}
def run_id_of(e):
    m = re.search(r'"run_id":\s*"([0-9a-f]{32})"', json.dumps(e, ensure_ascii=False))
    return m.group(1) if m else None
summary = {
    "success": env.get("success"), "run_status": env.get("run_status"), "run_id": run_id_of(env),
    "value": env.get("value"), "error": env.get("error"), "diagnostic": env.get("diagnostic"),
    "resumed": env.get("resumed"), "continuation": env.get("continuation"), "resume": env.get("resume"),
    "recordings": env.get("recordings"), "usage": env.get("usage"), "http_error": final.get("error"),
    "wall_s": final.get("wall_s"),
}
post_keys = {k: post_final.get(k) for k in ("status", "progress", "note", "updated_at") if k in post_final}
post_keys["top_keys"] = sorted(post_final.keys())[:40]
out = {"name": a.name, "program": a.program, "parallel": a.parallel, "reuse": a.reuse, "list_n": a.list,
       "ticket": ticket, "interval_s": a.interval, "sample_count": len(samples),
       "first_sample_t": samples[0]["t"] if samples else None, "last_sample_t": samples[-1]["t"] if samples else None,
       "samples": samples, "final": summary, "recover_after_end": post_keys}
os.makedirs(os.path.join(HERE, "samples"), exist_ok=True)
with open(os.path.join(HERE, "samples", a.name + ".json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=1, default=str)
print(json.dumps({"name": a.name, "samples": len(samples), "success": summary["success"], "run_id": summary["run_id"],
                  "run_status": summary["run_status"], "wall_s": summary["wall_s"]}, ensure_ascii=False))
