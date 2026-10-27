"""Preserve HTTP requests/responses; all task composition remains in .ibl. (100회차, 99 판 재사용 — 출력 폴더만 변경)"""
import argparse, json, time, uuid, urllib.error, urllib.request
from pathlib import Path
ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "outputs/long_sentence_imagination/2026-10-28_100회차"

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("request", type=Path); ap.add_argument("label")
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--out", type=Path, default=OUT)
    a = ap.parse_args()
    body = json.loads(a.request.read_text())
    body.setdefault("ticket", uuid.uuid4().hex); body.setdefault("origin", "training")
    body.setdefault("edition", 2); body.setdefault("project_id", "study")
    rec = {"request": body, "started": time.time()}
    path = a.out / "runs" / f"{a.label}.json"; path.parent.mkdir(parents=True, exist_ok=True); path.write_text(json.dumps(rec, ensure_ascii=False, indent=2))
    req = urllib.request.Request("http://127.0.0.1:8765/ibl/execute", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=a.timeout) as r: result = json.load(r)
    except urllib.error.HTTPError as e: result = {"http_error": e.code, "body": e.read().decode()}
    except (TimeoutError, urllib.error.URLError) as e: result = {"transport_unknown": True, "error": str(e)}
    rec.update(response=result, seconds=time.time() - rec["started"]); path.write_text(json.dumps(rec, ensure_ascii=False, indent=2))
    print(json.dumps({"label": a.label, "seconds": round(rec["seconds"], 2),
                      **{k: result[k] for k in ("ok", "success", "run_id", "run_status", "error", "issues", "http_error", "transport_unknown") if k in result}},
                     ensure_ascii=False)[:3000])
if __name__ == "__main__": main()
