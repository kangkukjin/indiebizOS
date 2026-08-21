#!/usr/bin/env python3
"""데이터 소유 감사 수동 실행 — 주인 없는 파일 보고 (backend/cognition/data_ownership.py 의 CLI).

주간 카덴스와 무관하게 즉시 전수 감사한다. 보고만, 삭제 없음.

    python3 scripts/check_data_ownership.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
import boot_paths  # noqa: E402,F401

from data_ownership import run_data_ownership_check  # noqa: E402


def main():
    r = run_data_ownership_check(force=True)
    orphans = r.get("orphans") or []
    stale = r.get("stale_backups") or []
    if r.get("error_message") and not orphans:
        print(f"✗ {r['error_message']}")
        return 2
    if orphans:
        print(f"주인 없는 항목 {len(orphans)}건:")
        for o in orphans:
            mb = o["size"] / 1_000_000
            size = f"{mb:.1f}MB" if mb >= 0.1 else f"{o['size']}B"
            kind = "📁" if o["dir"] else "📄"
            print(f"  {kind} {o['path']}  ({size}, {o['mtime']}) — {o['hint']}")
    else:
        print("✓ 주인 없는 항목 없음 — 소유 선언 완전")
    if stale:
        print(f"\n30일 지난 백업 {len(stale)}건 (삭제 후보 — 실삭제=사용자):")
        for s in stale:
            print(f"  🗄 {s['path']}  ({s['mtime']})")
    return 1 if orphans else 0


if __name__ == "__main__":
    sys.exit(main())
