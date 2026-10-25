#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""items 선언의 실제 Record 목록 반환 검사.

성공 값은 wire에서 읽고 실행 실패는 별도로 센다. items를 약속하지 않은
Record·List는 그 자체로 정상 값이며 items 병기를 요구하지 않는다.
사용: .venv/bin/python scripts/currency_items_sweep.py [--limit N]
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


from ibl_check_client import execute as _execute, value_of as _final_envelope, item_rows


def _dict_list_keys(env: dict):
    """items 아닌 키 아래의 dict 목록(1개 이상) — 병기 누락 후보."""
    hits = []
    for k, v in env.items():
        if k == "items" or k.startswith("_"):
            continue
        if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
            hits.append((k, len(v)))
    return hits


def main():
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])
    from returns_drift_sweep import _load_declarations, _declared_of
    decl, decl_op, default_op, _, _ = _load_declarations()
    fixtures = json.load(open(ROOT / "data" / "ibl_fixtures.json"))["fixtures"]
    flagged, ok, failed = [], 0, []
    for i, (name, code) in enumerate(sorted(fixtures.items())):
        if limit and i >= limit:
            break
        try:
            resp = _execute(code)
            env = _final_envelope(resp)
        except Exception as e:
            failed.append((name, f"실행 불능: {str(e)[:80]}"))
            continue
        declared, _ = _declared_of(name, decl, decl_op, default_op, code)
        if declared != "items":
            continue
        rows = item_rows(env)
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            hits = _dict_list_keys(env) if isinstance(env, dict) else []
            flagged.append((name, hits))
            print(f"  🚩 {name}: items 선언과 값 불일치, 다른 dict 목록 키 = {hits}")
        else:
            ok += 1
    print("\n==== 통화 병기 스윕 결과 ====")
    print(f"검사 {ok + len(flagged) + len(failed)} · 준수 {ok} · 🚩 병기 누락 {len(flagged)} · 실행 불능 {len(failed)}")
    for name, hits in flagged:
        print(f"  🚩 {name}: {hits}")
    if failed:
        print("  (실행 불능은 판정 아님 — 픽스처·환경 문제)")
        for name, why in failed[:10]:
            print(f"    · {name}: {why}")

    return 1 if flagged or failed or not ok else 0


if __name__ == "__main__":
    raise SystemExit(main())
