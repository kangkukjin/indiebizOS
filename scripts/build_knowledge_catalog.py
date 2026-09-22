#!/usr/bin/env python3
"""검토한 카탈로그의 FTS 색인 생성. --check는 정본·원본·색인 일치를 검사한다."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: E402,F401
import argparse  # noqa: E402
from knowledge_catalog import build_index, check_index, search  # noqa: E402


def branch_gate(snapshot):
    """가지 관문 (docs/TREE_MEMORY_RECALL_COMMON_DESIGN §6·§9-4, 2026-09-18) → (실패, 경고).

    회상은 가지 사전(branches.yaml)으로 가지를 먼저 고른다 — 사전이 트리와 어긋나면 그 가지는 이름만으로
    골라진다. 실패: 사전에 없는 가지 · `gist`(요약) 없는 가지 · 트리에 없는 경로를 가리키는 사전 항목·see_also.
    경고: 1~2항목 가지(167가지 중 103개가 그랬다 — 상위·이웃 가지로 합칠 것, ID 는 두고 path 만)."""
    from collections import Counter
    import yaml
    tree = Counter(tuple(e.path[:2]) for e in snapshot.entries if e.path)
    doc = yaml.safe_load((ROOT / "data/knowledge_catalog/branches.yaml").read_text(encoding="utf-8")) or {}
    rows = {tuple(r.get("path") or ()): r for r in doc.get("branches") or []}
    fails = [f"사전에 없는 가지: {'/'.join(p)}" for p in sorted(tree) if p not in rows]
    fails += [f"요약(gist) 없는 가지: {'/'.join(p)}" for p in sorted(tree) if p in rows and not str(rows[p].get("gist") or "").strip()]
    fails += [f"트리에 없는 사전 항목: {'/'.join(p)}" for p in sorted(rows) if p not in tree]
    fails += [f"{'/'.join(p)} 의 see_also 가 없는 가지를 가리킨다: {'/'.join(s)}"
              for p, r in sorted(rows.items()) for s in (r.get("see_also") or []) if tuple(s) not in tree]
    warns = [f"항목 {n}개뿐인 가지: {'/'.join(p)}" for p, n in sorted(tree.items()) if n <= 2]
    return fails, warns


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
    if args.check:
        fails, warns = branch_gate(snapshot)
        from audit_world_map_coverage import audit
        fails.extend(audit(ROOT)["errors"])
        for w in warns:
            print(f"catalog: 경고 — {w}", file=sys.stderr)
        for f in fails:
            print(f"catalog: 가지 관문 실패 — {f}", file=sys.stderr)
        if fails:
            return 1
        print(f"catalog: 가지 관문 통과 ✓ (가지 사전 = 트리, 요약 전부 있음, 단독 가지 경고 {len(warns)})")
    if args.query:
        rows, mode = search(ROOT, snapshot, args.query)
        print(mode)
        for entry, score in rows[:4]:
            print(f"{entry.id}: {entry.name} — {entry.hint} ({score})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
