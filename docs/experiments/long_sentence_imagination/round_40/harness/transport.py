"""HTTP transport only; preserve each request, terminal response and wall time."""
import argparse
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[5]
OUT = ROOT / "outputs/long_sentence_imagination/2026-10-09_40회차"


def main():
    p = argparse.ArgumentParser()
    p.add_argument("label")
    p.add_argument("request")
    p.add_argument("--endpoint", default="/ibl/execute")
    p.add_argument("--timeout", type=int, default=1200)
    a = p.parse_args()
    payload = json.loads(Path(a.request).read_text()) if a.request != "-" else None
    started = time.time()
    req = urllib.request.Request(
        "http://127.0.0.1:8765" + a.endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode() if payload is not None else None,
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=a.timeout) as response:
            result = json.load(response)
    except urllib.error.HTTPError as exc:
        result = {"http_status": exc.code, "body": exc.read().decode()}
    record = {"request": payload, "endpoint": a.endpoint, "started": started,
              "ended": time.time(), "response": result}
    (OUT / "runs").mkdir(parents=True, exist_ok=True)
    (OUT / "runs" / (a.label + ".json")).write_text(json.dumps(record, ensure_ascii=False, indent=2))
    print(json.dumps({"label": a.label, "elapsed": round(record["ended"] - started, 3),
                      "response": {k: v for k, v in result.items() if k not in
                                   {"execute_args", "revise_args", "functions", "dependencies",
                                    "canonical_code", "results", "runtime_checks", "value_wire"}}},
                     ensure_ascii=False)[:12000])


if __name__ == "__main__":
    main()
