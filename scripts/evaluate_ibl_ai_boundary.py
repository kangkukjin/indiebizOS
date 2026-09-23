#!/usr/bin/env python3
"""Read-only replay of saved AI-tips inputs/responses. No IBL/model execution.

Usage: .venv/bin/python3 scripts/evaluate_ibl_ai_boundary.py --run-dir PATH --output PATH
The report case lives here, never in the shared contract or inspection modules.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import boot_paths  # noqa: E402,F401
from common.currency import coerce_items_payload  # noqa: E402
from common.ai_input_inspection import inspect_inputs  # noqa: E402
from common.item_contract import (  # noqa: E402
    ContractError, check_inputs, check_outputs, validate_contract,
)


def evaluate(run_dir):
    contract = {"covers": [{"input": "input.candidates", "output": "result.decisions",
                            "key": "candidate_id", "required": ["verdict", "reason", "matched_ids"],
                            "allowed": {"verdict": ["novel", "duplicate"]}}]}
    validate_contract(contract)
    coverage = {"covers": [{k: v for k, v in contract["covers"][0].items() if k != "allowed"}]}
    report = {"model_calls": 0, "contract": contract, "inputs": [], "cases": {},
              "coverage_failures": [], "value_failures": []}
    for name in ("comparison-without-context.json", "input-compared.json"):
        path = run_dir / name
        raw = path.read_bytes()
        rows = coerce_items_payload(json.loads(raw))
        if rows is None:
            raise ValueError(f"Missing items: {path}")
        check_inputs(rows, contract)
        projected = [{k: row[k] for k in ("task", "input")} for row in rows]
        started = time.perf_counter()
        inspection = inspect_inputs(projected, mode="each", limit_chars=60000)
        elapsed = (time.perf_counter() - started) * 1000
        report["cases"][name] = {**inspection, "inspection_elapsed_ms": round(elapsed, 3)}
        report["inputs"].append({"path": str(path.resolve()), "sha256": hashlib.sha256(raw).hexdigest()})
        if name == "input-compared.json":
            for row in rows:
                for declaration, key in ((coverage, "coverage_failures"), (contract, "value_failures")):
                    try:
                        check_outputs([row], [row], declaration)
                    except ContractError as exc:
                        report[key].append({"batch_id": row["batch_id"], "error": str(exc), **exc.details})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = evaluate(args.run_dir)
    encoded = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
        print(args.output.resolve())
        for name, case in report["cases"].items():
            print(name, case["planned_requests"], "requests;", case["total_payload_chars"],
                  "chars;", case["inspection_elapsed_ms"], "ms")
        print("coverage failures:", len(report["coverage_failures"]),
              "all-contract failures:", len(report["value_failures"]), "model calls: 0")
    else:
        print(encoded, end="")


if __name__ == "__main__":
    main()
