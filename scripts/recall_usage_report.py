#!/usr/bin/env python3
"""제시→사용 보고 — 에피소드 궤적의 `recall.presented`·`recall.used` 사건을 모아 기억별로 제시 대비 사용을 센다.

공통 흐름(associative_recall)이 남긴 두 사건이 원장이다. 여기서는 읽기만 한다(점수·성공률을 고치지 않는다).
기억별로 따로 본다 — 합산 평균은 보지 않는다(2026-09-18 판정). 증거 종류(executed / mentioned / expanded / confirmed)는
같은 값이 아니다: 해마의 executed 는 실행 증거, 세계의 mentioned 는 약한 증거(모델이 이미 알던 이름일 수 있다).

    .venv/bin/python3 scripts/recall_usage_report.py            # 최근 7일
    .venv/bin/python3 scripts/recall_usage_report.py --days 30 --top 10
"""
import argparse
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
import boot_paths  # noqa: E402,F401

LABEL = {"hippocampus": "실행기억(해마)", "recalled_memory": "심층기억(선택)", "method_map": "세계 지도(글자)",
         "world_memory": "세계의 기억(의미)"}


def _rows(days: int):
    from episode_logger import _get_db
    since = (datetime.now() - timedelta(days=days)).isoformat()
    conn = _get_db()
    try:
        return conn.execute(
            "SELECT run_id, ts, kind, data FROM trajectory_event WHERE kind IN ('recall.presented','recall.used') AND ts >= ? "
            "ORDER BY ts", (since,)).fetchall()
    finally:
        conn.close()


def _name_of(source: str, item_id: str) -> str:
    """보고용 이름 — 기억별 저장소에서 읽는다(실패하면 id 그대로)."""
    try:
        if source == "hippocampus":
            from ibl_usage_db import IBLUsageDB
            if not item_id.isdigit():
                return item_id
            conn = IBLUsageDB()._get_connection()
            try:
                row = conn.execute("SELECT intent FROM ibl_examples WHERE id=?", (int(item_id),)).fetchone()
            finally:
                conn.close()
            return (row[0] if row else item_id)[:50]
        if source in ("method_map", "world_memory"):
            from knowledge_catalog import load_snapshot
            from runtime_utils import get_base_path
            for e in load_snapshot(get_base_path()).entries:
                if e.id == item_id:
                    return e.name
    except Exception:
        pass
    return item_id


def report(days: int, top: int) -> int:
    rows = _rows(days)
    turns_presented = Counter()
    presented = defaultdict(Counter)
    used = defaultdict(Counter)
    evidence = defaultdict(Counter)
    turns_used = Counter()
    for r in rows:
        try:
            data = json.loads(r["data"])
        except Exception:
            continue
        if r["kind"] == "recall.presented":
            for b in data.get("blocks") or []:
                if b.get("ids") and b.get("source") in LABEL:
                    turns_presented[b["source"]] += 1
                    for i in b["ids"]:
                        presented[b["source"]][i] += 1
        else:
            for b in data.get("blocks") or []:
                src = b.get("source")
                if src not in LABEL:
                    continue
                turns_used[src] += 1
                for i in b.get("used") or []:
                    used[src][i] += 1
                for e in (b.get("evidence") or "").split("+"):
                    if e and e != "none":
                        evidence[src][e] += 1
    print(f"최근 {days}일 — 사건 {len(rows)}건")
    print(f"{'기억':<16} {'제시 턴':>7} {'결합 턴':>7} {'제시 항목':>9} {'사용 항목':>9} {'사용률':>7}  증거")
    for src, label in LABEL.items():
        p_items = sum(presented[src].values()); u_items = sum(used[src].values())
        rate = f"{u_items / p_items:.0%}" if p_items else "-"
        ev = ", ".join(f"{k} {v}" for k, v in evidence[src].most_common())
        print(f"{label:<16} {turns_presented[src]:>7} {turns_used[src]:>7} {p_items:>9} {u_items:>9} {rate:>7}  {ev}")
    for src, label in LABEL.items():
        never = [(i, n) for i, n in presented[src].most_common() if used[src][i] == 0][:top]
        if never:
            print(f"\n{label} — 자주 제시됐지만 한 번도 안 쓰인 항목(상위 {len(never)}):")
            for i, n in never:
                print(f"  {n:>3}회  {i}  {_name_of(src, i)}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--top", type=int, default=8)
    a = ap.parse_args()
    return report(a.days, a.top)


if __name__ == "__main__":
    sys.exit(main())
