#!/usr/bin/env python3
"""판정 어휘의 검증된 용례를 해마·다음 학습 JSON에 멱등 등록한다(.venv 실행)."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: F401, E402

import argparse
import json
import shutil
import sqlite3


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    seeds = json.loads((ROOT / "data/packages/installed/tools/ai-ops/judge_examples.json").read_text())
    from ibl_param_vocab import code_syntax_error, check_code_params
    from ibl_typecheck import typecheck_code
    for seed in seeds:
        code = seed["ibl_code"]
        assert not code_syntax_error(code), seed["intent"]
        assert not check_code_params(code), seed["intent"]
        checked = typecheck_code(code)
        assert not checked.get("syntax_error"), checked
        assert not any(i.get("severity", i.get("level")) == "error" for i in checked.get("issues", [])), checked
    print(f"판정 용례 문법·인자·통화 검사: {len(seeds)}건 통과")
    if not args.apply:
        return
    from ibl_usage_db import IBLUsageDB
    db = IBLUsageDB()
    backup = ROOT / "data/_backups/2026-09-21_jev_judgment"
    backup.mkdir(parents=True, exist_ok=True)
    with db._get_connection() as con:
        if not (backup / "ibl_usage.db").exists():
            with sqlite3.connect(backup / "ibl_usage.db") as dest:
                con.backup(dest)
        existing_rows = list(con.execute(
            "SELECT id, intent, ibl_code FROM ibl_examples WHERE source=?", ("judge_2026_09_21",)))
    wanted = {(s["intent"], s["ibl_code"]) for s in seeds}
    stale = [r for r in existing_rows if (r[1], r[2]) not in wanted]
    stale_pairs = {(r[1], r[2]) for r in stale}
    if stale:
        db._delete_examples([r[0] for r in stale])
    existing = {(r[1], r[2]) for r in existing_rows} - stale_pairs
    pending = [dict(s, source="judge_2026_09_21", tags="ai-ops,judge,판정,Jev", topic="판정")
               for s in seeds if (s["intent"], s["ibl_code"]) not in existing]
    if pending:
        assert db._load_model_sync(), "해마 임베딩 모델을 로드하지 못했습니다."
        assert db.add_examples_batch(pending) == len(pending)
    path = ROOT / "data/training/ibl_distilled.json"
    raw = path.read_text()
    training = [s for s in json.loads(raw) if (s.get("intent"), s.get("ibl_code")) not in stale_pairs]
    pairs = {(s.get("intent"), s.get("ibl_code")) for s in training}
    additions = [{"intent": s["intent"], "ibl_code": s["ibl_code"]} for s in seeds
                 if (s["intent"], s["ibl_code"]) not in pairs]
    if additions or stale:
        if not (backup / path.name).exists():
            shutil.copy2(path, backup / path.name)
        assert path.read_text() == raw, "학습 원장이 바뀌었습니다. 재실행하세요."
        path.write_text(json.dumps(training + additions, ensure_ascii=False, indent=2) + "\n")
    print(f"해마 +{len(pending)}, 학습 JSON +{len(additions)}")
    if pending:
        print(f"임베딩 재색인: {db.rebuild_index()}")
    for query in ("환불 요청 여부를 판정해줘", "관련성과 광고성을 한 번에 판정해줘"):
        hits = db.search_hybrid(query, top_k=5)
        print(f"회상 {query}: judge 적중="
              f"{any('[table:judge]' in getattr(h, 'ibl_code', '') for h in hits)}")


if __name__ == "__main__":
    main()
