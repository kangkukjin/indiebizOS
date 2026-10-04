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
from collections import Counter
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
            "SELECT run_id, episode_id, event_seq, ts, kind, data FROM trajectory_event WHERE kind IN ('recall.presented','recall.used') AND ts >= ? "
            "ORDER BY ts, event_seq", (since,)).fetchall()
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


def summarize(rows):
    """회상 ID로 턴/증류 관측을 합친다. 옛 사건은 같은 run의 최근 제시에 결합한다."""
    groups, latest = {}, {}
    for index, row in enumerate(rows):
        try:
            data = json.loads(row["data"])
        except (ValueError, TypeError):
            continue
        if not isinstance(data, dict):
            continue
        run = (row["run_id"], dict(row).get("episode_id"))
        for block in data.get("blocks") or []:
            src = block.get("source")
            if src not in LABEL:
                continue
            recall_id = block.get("recall_id") or data.get("recall_id")
            if row["kind"] == "recall.presented":
                if data.get("channel") in {"preview", "sample"} or not block.get("ids"):
                    continue  # 문맥 미리보기에는 사용 턴 자체가 없다.
                key = (run, src, recall_id or ("legacy", index))
                group = groups.setdefault(key, {"source": src, "presented": set(), "used": set(),
                                                 "evidence": set(), "measured": False})
                group["presented"].update(block["ids"])
                latest[run, src] = key
            else:
                key = (run, src, recall_id) if recall_id else latest.get((run, src))
                group = groups.get(key)
                if group is None or block.get("error") or block.get("evidence") == "error":
                    continue
                # 짝이 틀린 오래된/손상된 관측은 미사용으로 덮지 않는다.
                if set(block.get("presented") or []) != group["presented"]:
                    continue
                group["measured"] = True
                group["used"].update(set(block.get("used") or []) & group["presented"])
                group["evidence"].update(e for e in (block.get("evidence") or "").split("+")
                                         if e and e != "none")
    return list(groups.values())


def report(days: int, top: int) -> int:
    rows = _rows(days)
    groups = summarize(rows)
    print(f"최근 {days}일 — 사건 {len(rows)}건 (프리뷰 제외·턴/증류 중복 제거)")
    print(f"{'기억':<16} {'제시':>5} {'관측':>5} {'미관측':>5} {'관측 항목':>9} {'사용 항목':>9} {'사용률':>7}  증거")
    for src, label in LABEL.items():
        selected = [g for g in groups if g["source"] == src]
        measured = [g for g in selected if g["measured"]]
        presented, used, evidence = Counter(), Counter(), Counter()
        for group in measured:
            presented.update(group["presented"])
            used.update(group["used"])
            evidence.update(group["evidence"])
        p_items, u_items = sum(presented.values()), sum(used.values())
        rate = f"{u_items / p_items:.0%}" if p_items else "-"
        ev = ", ".join(f"{k} {v}" for k, v in evidence.most_common())
        print(f"{label:<16} {len(selected):>5} {len(measured):>5} {len(selected)-len(measured):>5} "
              f"{p_items:>9} {u_items:>9} {rate:>7}  {ev}")
        never = [(i, n) for i, n in presented.most_common() if used[i] == 0][:top]
        if never:
            print(f"  관측된 범위에서 미사용(상위 {len(never)}):")
            for item_id, count in never:
                print(f"    {count:>3}회  {item_id}  {_name_of(src, item_id)}")
    print("사용률 분모는 활용 관측이 있는 제시 항목만. 미관측은 지연·누락이며 미사용이 아닙니다.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--top", type=int, default=8)
    a = ap.parse_args()
    return report(a.days, a.top)


if __name__ == "__main__":
    sys.exit(main())
