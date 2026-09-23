#!/usr/bin/env python3
"""Audit edition boundaries and seed reviewed v2 examples without rewriting v1."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import boot_paths  # noqa: E402,F401
import argparse
import json
from ibl_edition import source_edition, explicit_source


def inventory():
    from ibl_usage_db import IBLUsageDB
    from ibl_v2_adapters import load_registry
    registry = load_registry()
    with IBLUsageDB()._get_connection() as conn:
        rows = [dict(r) for r in conn.execute("SELECT id, alias, ibl_code FROM ibl_examples")]
    return {"examples": {str(e): sum(source_edition(r["ibl_code"]) == e for r in rows) for e in (1, 2)},
            "functions": [{"id": r["id"], "name": r["alias"], "edition": source_edition(r["ibl_code"]),
                           "v2_connection": "native" if source_edition(r["ibl_code"]) == 2 else
                           ("legacy-envelope" if f'fn:{r["alias"]}' in registry else "requires_review")}
                          for r in rows if r["alias"]],
            "actions": {"native": sorted(k for k, a in registry.items() if not a.contract.get("compatibility")),
                        "compatibility": sorted(k for k, a in registry.items() if a.contract.get("compatibility"))},
            "changed": False}


def seed(path, apply=False):
    from ibl_usage_db import IBLUsageDB
    from ibl_v2_learning import check_source
    from ibl_v2_store import definition_name
    db = IBLUsageDB()
    examples = json.loads(Path(path).read_text())
    if not isinstance(examples, list):
        raise ValueError("seed 파일은 용례 목록이어야 합니다.")
    with db._get_connection() as conn:
        known = {(r[0], r[1]) for r in conn.execute("SELECT intent, ibl_code FROM ibl_examples")}
    pending = []
    for example in examples:
        code = explicit_source(example["ibl_code"], 2)
        why = check_source(code, bool(example.get("alias")))
        if why:
            raise ValueError(why)
        if example.get("alias") and definition_name(code) != example["alias"]:
            raise ValueError("등록 이름과 [def:] 이름이 다릅니다.")
        key = example["intent"], code
        if key not in known:
            pending.append({**example, "ibl_code": code})
            known.add(key)
    # CLI ingestion is explicit and may wait for the existing local encoder.
    # A daemon cold load can otherwise outlive this process, leaving FTS rows
    # present but invisible to semantic-only recall.
    vector_ready = apply and db._check_sqlite_vec() and db._load_model_sync()
    inserted = db.add_examples_batch(pending) if apply else 0
    if apply and inserted != len(pending):
        raise RuntimeError(f"원장 입구 거절: {inserted}/{len(pending)}")
    indexed = 0
    if vector_ready:
        with db._get_connection() as conn:
            rows = [dict(row) for ex in examples for row in conn.execute(
                "SELECT id,intent,ibl_code FROM ibl_examples WHERE intent=? AND ibl_code=?",
                (ex['intent'], explicit_source(ex['ibl_code'], 2)))]
        vec = db._get_vec_connection()
        try:
            db._ensure_vec_table(vec)
            missing = [row for row in rows if not vec.execute(
                "SELECT rowid FROM ibl_examples_vec WHERE rowid=?", (row['id'],)).fetchone()]
        finally:
            vec.close()
        if missing:
            db._index_batch([r['id'] for r in missing], missing)
        vec = db._get_vec_connection()
        try:
            indexed = sum(bool(vec.execute("SELECT rowid FROM ibl_examples_vec WHERE rowid=?", (r['id'],)).fetchone()) for r in rows)
        finally:
            vec.close()
        if indexed != len(rows):
            raise RuntimeError(f"시맨틱 색인 미완료: {indexed}/{len(rows)}")
    return {"pending": len(pending), "inserted": inserted, "changed": inserted > 0,
            "semantic_indexed": indexed, "index_mode": "semantic+fts" if vector_ready else "fts_or_preview",
            "legacy_rewritten": 0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["inventory", "seed"])
    parser.add_argument("source", nargs="?", default=str(Path(__file__).resolve().parents[1] / "data/idioms/ibl_v2_seeds.json"))
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args()
    result = inventory() if args.command == "inventory" else seed(args.source, args.apply)
    raw = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        Path(args.output).write_text(raw)
    else:
        print(raw)


if __name__ == "__main__":
    main()
