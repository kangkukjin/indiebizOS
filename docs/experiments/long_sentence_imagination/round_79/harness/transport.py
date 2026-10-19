"""HTTP transport only; preserve each request, response and wall time (79회차)."""
import argparse, json, time, urllib.error, urllib.request
from pathlib import Path
OUT = Path(__file__).resolve().parent
def main():
    p = argparse.ArgumentParser(); p.add_argument("label"); p.add_argument("request")
    p.add_argument("--endpoint", default="/ibl/execute"); p.add_argument("--timeout", type=int, default=1200)
    a = p.parse_args()
    payload = json.loads(Path(a.request).read_text()) if a.request != "-" else None
    started = time.time()
    req = urllib.request.Request("http://127.0.0.1:8765" + a.endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None,
        headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=a.timeout) as r: result = json.load(r)
    except urllib.error.HTTPError as exc: result = {"http_status": exc.code, "body": exc.read().decode()}
    rec = {"request": payload, "endpoint": a.endpoint, "started": started, "ended": time.time(), "response": result}
    (OUT/"runs").mkdir(exist_ok=True); (OUT/"runs"/(a.label+".json")).write_text(json.dumps(rec, ensure_ascii=False, indent=2))
    print(json.dumps({"label": a.label, "elapsed": round(rec["ended"]-started, 3),
        "summary": {k: result[k] for k in ("success","error","status","task_id","status_url","state","result") if k in result}}, ensure_ascii=False)[:1500])
if __name__ == "__main__": main()
