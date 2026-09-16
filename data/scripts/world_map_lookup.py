#!/usr/bin/env python3
"""세계지도 — 전체 어휘 search/browse/open/neighbors/ancestors, 읽기 전용 items 반환."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: E402,F401
import json  # noqa: E402
from knowledge_catalog import lookup  # noqa: E402


def main():
    try:
        args = json.load(sys.stdin)
        if not isinstance(args, dict):
            raise ValueError("args must be an object")
        if set(args) - {"op", "query", "id", "offset", "limit", "revision", "path"}:
            raise ValueError("unknown world map argument")
        result = lookup(ROOT, op=args.get("op", "search"), query=args.get("query", ""),
                        id=args.get("id", ""), offset=args.get("offset", 0),
                        limit=args.get("limit", 10), revision=args.get("revision", ""),
                        path=args.get("path", []))
    except Exception as exc:
        result = {"items": [], "status": "error", "success": False,
                  "error": str(exc), "error_type": type(exc).__name__}
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
