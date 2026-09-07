#!/usr/bin/env python3
"""저장소 낭비 감사 수동 실행 — 빈 vec0 청크·미회수 프리페이지 보고
(backend/datastore/store_waste_audit.py 의 CLI).

주간 카덴스와 무관하게 즉시 전수 감사한다. 보고만, 고침 없음.

    python3 scripts/check_db_waste.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
import boot_paths  # noqa: E402,F401

from store_waste_audit import run_store_waste_check  # noqa: E402


def main():
    r = run_store_waste_check(force=True)
    flags = r.get("flags") or []
    unchecked = r.get("unchecked") or []
    structural = r.get("structural") or []
    if r.get("data_quality") == "audit_incomplete":
        print(f"⚠ 측정 실패: {r.get('error_message')}")
        return 2
    if not flags:
        print("✓ 저장소 낭비 깃발 0 (vec0 청크 잔재·미회수 프리페이지 없음)")
    else:
        print(f"✗ 저장소 낭비 {len(flags)}건 / 회수 가능 {r.get('reclaim_mb')}MB — data/store_waste_flags.json")
        for f in flags:
            where = f["db"] + (f" [{f['table']}]" if f.get("table") else "")
            print(f"  [{f['kind']}] {where} — {f['detail']} → 회수 {f.get('reclaim_mb')}MB")
            print(f"      ↳ {f['hint']}")
    if structural:
        total = sum(s["reclaim_mb"] for s in structural)
        print(f"ℹ 구조적 최소 할당(청크 1개, 재구성해도 안 줄어듦) {len(structural)}건 / 합 {total:.0f}MB")
    if unchecked:
        print(f"⚠ 미검사 {len(unchecked)}건: {', '.join(unchecked[:5])}")
    return 1 if flags else 0


if __name__ == "__main__":
    sys.exit(main())
