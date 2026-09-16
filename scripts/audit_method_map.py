#!/usr/bin/env python3
"""고정한 작업 질문으로 지도의 등재 공백과 검색 공백을 따로 측정한다."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: E402,F401
import argparse
import hashlib
import json
import shutil
import subprocess
import tempfile
from collections import Counter

from knowledge_catalog import CATALOG_PATH, _parse, build_index, search
from catalog_recall import render


def evaluate(raw, cases):
    snapshot = _parse(str(ROOT.resolve()), raw)
    # 두 판 모두 자기 정본으로 FTS를 빌드한다. 낡은 색인 폴백과의 비교를 피한다.
    with tempfile.TemporaryDirectory(prefix="method-map-audit-") as folder:
        root = Path(folder)
        for source in {e.source for e in snapshot.entries}:
            dest = root / source
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(ROOT / source, dest)
        path = root / CATALOG_PATH
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        build_index(root)
        available = {e.id for e in snapshot.entries}
        rows = []
        for case in cases:
            candidates, mode = search(root, snapshot, case["query"])
            snippet, ids, _ = render(candidates)
            acceptable = set(case["any_of"])
            negative = case["split"] == "negative"
            chosen = set(ids)
            registered = bool(acceptable & available)
            hit = bool(acceptable & chosen)
            if hit or (negative and not ids):
                gap = "none"
            elif negative:
                gap = "false_positive"
            else:
                gap = "retrieval" if registered else "catalog"
            rows.append({
                **case,
                "registered": registered,
                "selected": ids,
                "hit": hit,
                "abstained": not ids,
                "forbidden": sorted(set(case["reject"]) & chosen),
                "unjudged": sorted(chosen - acceptable - set(case["reject"])),
                "chars": len(snippet),
                "mode": mode,
                "gap": gap,
            })
    summary = {}
    for split in ("development", "validation", "negative"):
        selected = [r for r in rows if r["split"] == split]
        summary[split] = {
            "questions": len(selected),
            "registered": sum(r["registered"] for r in selected),
            "hit": sum(r["hit"] for r in selected),
            "abstained": sum(r["abstained"] for r in selected),
            "forbidden_rows": sum(bool(r["forbidden"]) for r in selected),
            "unjudged_rows": sum(bool(r["unjudged"]) for r in selected),
            "gaps": dict(Counter(r["gap"] for r in selected)),
        }
    return {
        "entries": len(snapshot.entries),
        "revision": snapshot.revision,
        "summary": summary,
        "rows": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    raw_cases = (ROOT / "data/knowledge_catalog/audit_cases.json").read_bytes()
    corpus = json.loads(raw_cases)
    baseline = subprocess.run(
        ["git", "show", f"{corpus['baseline_ref']}:{CATALOG_PATH}"],
        cwd=ROOT, check=True, capture_output=True,
    ).stdout
    report = {
        "protocol": corpus["protocol"],
        "baseline_ref": corpus["baseline_ref"],
        "cases_sha256": hashlib.sha256(raw_cases).hexdigest(),
        "before": evaluate(baseline, corpus["cases"]),
        "after": evaluate((ROOT / CATALOG_PATH).read_bytes(), corpus["cases"]),
    }
    destination = Path(args.output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8",
    )
    summaries = {p: report[p]["summary"] for p in ("before", "after")}
    print(json.dumps(summaries, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
