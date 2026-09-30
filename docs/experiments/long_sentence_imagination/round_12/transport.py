"""Public HTTP transport only; task calculation remains in the saved IBL."""
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
number, mode, label = sys.argv[1:4]
HERE = ROOT / f"docs/experiments/long_sentence_imagination/round_{number}"
LOCAL = ROOT / f"outputs/long_sentence_imagination/2026-09-30_{number}회차"
if mode == "system":
    payload = {"message": (HERE / "request.txt").read_text() +
               f"\n입력: {LOCAL}/system_inputs\n출력: {LOCAL}/system_output",
               "origin": "training"}
    endpoint = "system-ai/chat"
else:
    payload = {"code": (HERE / "main.ibl").read_text(), "edition": 2,
               "origin": "training", "project_path": str(ROOT / "projects/하드웨어"),
               "inputs": {"folder": str(LOCAL / mode), "out": str(LOCAL / label)},
               "budget": {"steps": 600000, "rows": 20000},
               "check": label.endswith("check")}
    endpoint = "ibl/execute"
start = time.time()
request = urllib.request.Request("http://127.0.0.1:8765/" + endpoint,
                                 data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
with urllib.request.urlopen(request, timeout=1800) as response:
    result = json.load(response)
record = {"elapsed_seconds": time.time()-start, "request": payload, "response": result}
(LOCAL / (label + ".json")).write_text(json.dumps(record, ensure_ascii=False, indent=2))
print(json.dumps({"saved": label, "elapsed": record["elapsed_seconds"],
                  "response": {k: result[k] for k in ("success", "ok", "status", "diagnostic", "issues", "source_complete") if k in result}}, ensure_ascii=False)[:4000])
