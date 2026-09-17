#!/usr/bin/env python3
"""트리 기억 공통 회상의 평가 — 심층기억 가지 고르기 (docs/TREE_MEMORY_RECALL_COMMON_DESIGN §7-1).

정답 = AI 가 에피소드에서 실제로 연 가지(`[self:memory]{op:"recall", node}`). 낙관 편향을 없애려고 회상 대상은
**그 에피소드가 시작되기 전에 생긴 기억만**으로 자른다(created_at 절단). 모델 호출은 임베딩뿐이다.
읽기 전용 — 기억 DB·에피소드 DB 를 고치지 않는다(회상 색인 data/recall_index/ 만 갱신).
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: E402,F401
import argparse  # noqa: E402
import glob  # noqa: E402
import json  # noqa: E402
import re  # noqa: E402
import sqlite3  # noqa: E402

sys.path.insert(0, str(ROOT / "data/packages/installed/tools/memory"))
import tree_recall  # noqa: E402
from recall_store import DeepMemoryStore  # noqa: E402

RECALL_RE = re.compile(r'\[self:memory\]\{([^}]*?recall[^}]*?)\}')
NODE_RE = re.compile(r'node:\s*\\?"([^"\\]+)')


def opened_nodes(since: str):
    db = sqlite3.connect(f"file:{ROOT / 'data/world_pulse.db'}?mode=ro", uri=True)
    for ep, started, agent, msg, log in db.execute(
            "SELECT id, started_at, agent, user_message, log FROM episode_log WHERE started_at >= ?", (since,)):
        code = "\n".join(l for l in (log or "").split("\n") if "IBL_DEBUG" in l[:20])
        for body in RECALL_RE.findall(code):
            m = NODE_RE.search(body)
            if m and "실행" not in body and msg:
                yield ep, started, agent, msg, m.group(1).strip()
                break


def memory_dbs():
    paths = [str(ROOT / "data/system_ai_state/memory_system_ai.db")] + glob.glob(str(ROOT / "projects/*/memory_*.db"))
    return [p for p in paths if "None" not in p and "self_check" not in p and ":" not in Path(p).name]


def db_for(agent: str, node: str, dbs):
    hits = []
    for p in dbs:
        try:
            c = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
            n = c.execute("SELECT COUNT(*) FROM memories WHERE node = ? OR node LIKE ?", (node, node + "/%")).fetchone()[0]
            c.close()
        except sqlite3.Error:
            continue
        if n and (("system_ai_state" in p) == (agent == "system_ai")):
            hits.append(p)
    return hits[0] if hits else None


def related(a, b):
    return a[:len(b)] == b or b[:len(a)] == a


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--since", default="2026-09-03")
    ap.add_argument("--no-cut", action="store_true", help="created_at 절단 없이(낙관 편향 확인용)")
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()
    dbs = memory_dbs()
    rows, at1, at2, item_hit, empty = [], 0, 0, 0, 0
    for ep, started, agent, msg, node in opened_nodes(args.since):
        p = db_for(agent, node, dbs)
        if not p:
            continue
        store = DeepMemoryStore(p, before="" if args.no_cut else started)
        if not store.items():
            empty += 1
            continue
        r = tree_recall.recall(store, msg, wait=True)
        target = tuple(node.split("/"))
        b = [tuple(x) for x in r["branches"]]
        ok1, ok2 = bool(b[:1]) and related(b[0], target), any(related(x, target) for x in b[:2])
        got = any(related(it.path, target) for it in r["items"] + r["outside"])
        at1 += ok1; at2 += ok2; item_hit += got
        rows.append({"episode": ep, "agent": agent, "opened": node, "chosen": ["/".join(x) for x in b],
                     "branch_at1": ok1, "branch_at2": ok2, "item_from_opened_branch": got, "status": r["status"]})
    n = len(rows)
    report = {"kind": "deep_memory_branch_routing", "cut": not args.no_cut, "cases": n, "skipped_empty_before_cut": empty,
              "branch_at1": at1, "branch_at2": at2, "item_from_opened_branch": item_hit,
              "threshold_at2": 0.85, "passed": bool(n) and at2 / n >= 0.85, "rows": rows}
    text = json.dumps(report, ensure_ascii=False, indent=1)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "rows"}, ensure_ascii=False))
    for row in rows:
        if not row["branch_at2"]:
            print("  ✗", row["episode"], row["agent"], "| 연 가지:", row["opened"], "| 고른:", row["chosen"])
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
