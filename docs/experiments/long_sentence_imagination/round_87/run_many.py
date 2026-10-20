"""Run several IBL programs in parallel threads via transport.py semantics; preserve each."""
import json, sys, time, uuid, urllib.request, urllib.error, threading
from pathlib import Path
ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "outputs/long_sentence_imagination/2026-10-20_87회차"

def run(label, code, extra=None, timeout=900):
    body = {"code": code, "edition": 2, "origin": "training", "project_id": "study", "ticket": uuid.uuid4().hex}
    if extra: body.update(extra)
    rec = {"request": body, "started": time.time()}
    req = urllib.request.Request("http://127.0.0.1:8765/ibl/execute", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r: res = json.load(r)
    except urllib.error.HTTPError as e: res = {"http_error": e.code, "body": e.read().decode()}
    except Exception as e: res = {"transport_unknown": True, "error": str(e)}
    rec.update(response=res, seconds=time.time() - rec["started"])
    (OUT / "runs" / f"{label}.json").write_text(json.dumps(rec, ensure_ascii=False, indent=2))
    return label, rec

if __name__ == "__main__":
    jobs = json.loads(Path(sys.argv[1]).read_text())  # [{label, code, extra?}]
    results = {}
    def w(j): results[j["label"]] = run(j["label"], j["code"], j.get("extra"))[1]
    ts = [threading.Thread(target=w, args=(j,)) for j in jobs]
    [t.start() for t in ts]; [t.join() for t in ts]
    for k, rec in results.items():
        r = rec["response"]
        print(f"== {k} {rec['seconds']:.1f}s success={r.get('success')} error={str(r.get('error') or r.get('issues') or r.get('body') or '')[:300]}")
        print(json.dumps(r.get("value"), ensure_ascii=False)[:1500])
