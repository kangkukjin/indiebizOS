"""Preserve HTTP requests/responses; all task composition remains in .ibl."""
import argparse
import json
from pathlib import Path
import time
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[4]
OUT = ROOT / "outputs/long_sentence_imagination/2026-10-20_86회차"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("request", type=Path)
    parser.add_argument("label")
    args = parser.parse_args()
    body = json.loads(args.request.read_text())
    body.setdefault("ticket", uuid.uuid4().hex)
    body.setdefault("origin", "training")
    body.setdefault("edition", 2)
    body.setdefault("project_id", "study")
    record = {"request": body, "started": time.time()}
    path = OUT / "runs" / f"{args.label}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2))
    request = urllib.request.Request(
        "http://127.0.0.1:8765/ibl/execute",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        result = {"http_error": error.code, "body": error.read().decode()}
    except (TimeoutError, urllib.error.URLError) as error:
        result = {"transport_unknown": True, "error": str(error),
                  "note": "Recover this ticket; do not resubmit."}
    record.update(response=result, seconds=time.time() - record["started"])
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2))
    print(json.dumps({
        "label": args.label, "seconds": record["seconds"],
        **{k: result[k] for k in (
            "ok", "success", "run_id", "run_status", "error", "issues",
            "resume", "transport_unknown",
        ) if k in result},
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
