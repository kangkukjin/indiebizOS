#!/usr/bin/env python3
"""지도 없음/이름/구조의 입력을 재현하고 검색·구조·추정 예산을 측정한다. 모델 평가는 아니다."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: E402,F401
import argparse  # noqa: E402
import json  # noqa: E402
import time  # noqa: E402
import yaml  # noqa: E402
from catalog_recall import render  # noqa: E402
from knowledge_catalog import load_snapshot, search  # noqa: E402
from world_context import assemble, estimate_tokens  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    snapshot = load_snapshot(ROOT)
    cases = yaml.safe_load((ROOT / "data/knowledge_catalog/evaluation.yaml").read_text())["cases"]
    rows = []
    for case in cases:
        started = time.perf_counter()
        candidates, mode = search(ROOT, snapshot, case["query"])
        names, _, _ = render(candidates)
        context, structure = assemble(snapshot, candidates)
        ids = {n["id"] for n in context["nodes"]}
        passed = set(case["expected_nodes"]) <= ids and (not case.get("empty") or not ids)
        rows.append({"query": case["query"], "passed": passed,
                     "expected_nodes": case["expected_nodes"], "retrieved_nodes": sorted(ids),
                     "retrieval_mode": mode, "elapsed_ms": round((time.perf_counter() - started) * 1000, 3),
                     "none": "", "names": names, "structure": structure,
                     "names_token_estimate": estimate_tokens(names),
                     "structure_token_estimate": estimate_tokens(structure), "context": context})
    report = {"revision": snapshot.revision, "kind": "deterministic_retrieval_and_context",
              "model_calls": 0, "behavioral_quality_measured": False,
              "token_estimator": "utf8_bytes/2_estimate", "cases": len(rows),
              "passed": sum(r["passed"] for r in rows), "results": rows}
    output = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "results"}, ensure_ascii=False))
    for row in rows:
        if not row["passed"]:
            print(json.dumps(row, ensure_ascii=False))
    return 0 if all(r["passed"] for r in rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
