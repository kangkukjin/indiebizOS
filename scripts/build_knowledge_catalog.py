#!/usr/bin/env python3
"""검토한 카탈로그의 FTS 색인 생성. --check는 정본·원본·색인 일치를 검사한다."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: E402,F401
import argparse  # noqa: E402
from knowledge_catalog import build_index, check_index, search  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--query", help="이름·설명 검색 확인 (추가 AI 호출 없음)")
    args = parser.parse_args()
    try:
        snapshot = check_index(ROOT) if args.check else build_index(ROOT)
    except Exception as exc:
        print(f"catalog: {exc}", file=sys.stderr)
        return 1
    print(f"catalog: {len(snapshot.entries)} entries, {snapshot.revision[:12]}")
    if args.query:
        rows, mode = search(ROOT, snapshot, args.query)
        print(mode)
        for entry, score in rows[:4]:
            print(f"{entry.id}: {entry.name} — {entry.hint} ({score})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
