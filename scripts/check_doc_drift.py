#!/usr/bin/env python3
"""문서 드리프트 감사 수동 실행 — 산문 속 낡은 주장 보고 (backend/cognition/doc_drift.py 의 CLI).

주간 카덴스와 무관하게 즉시 전수 감사한다. 보고만, 고침 없음.

    python3 scripts/check_doc_drift.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
import boot_paths  # noqa: E402,F401

from doc_drift import run_doc_drift_check  # noqa: E402


def main():
    r = run_doc_drift_check(force=True)
    flags = r.get("flags") or []
    unchecked = r.get("unchecked") or []
    if r.get("data_quality") == "audit_incomplete":
        print(f"⚠ 측정 실패: {r.get('error_message')}")
        return 2
    if not flags:
        print("✓ 문서 드리프트 깃발 0 (복합 수치·죽은 참조·날짜 모순 없음)")
    else:
        print(f"✗ 문서 드리프트 {len(flags)}건 — data/doc_drift_flags.json")
        for f in flags:
            loc = f"{f['doc']}:{f['line']}" if f.get("line") else f["doc"]
            print(f"  [{f['kind']}] {loc} — {f['claim']}"
                  + (f" (실측 {f['actual']})" if f.get("actual") else ""))
            print(f"      ↳ {f['hint']}")
    if unchecked:
        print(f"⚠ 미검사 {len(unchecked)}건: {', '.join(unchecked)}")
    return 1 if flags else 0


if __name__ == "__main__":
    sys.exit(main())
