"""지정한 Codex 롤아웃으로 누락된 실행 라운드를 복구한다. 기본은 dry-run."""
import boot_paths  # noqa: F401
import argparse
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from model_call_context import count_execution_rounds


def stamp(text):
    return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()


def read_turns(path):
    turns = {}
    current = None
    for line in path.open():
        row = json.loads(line)
        data = row.get("payload", {})
        if row["type"] == "event_msg" and data.get("type") == "task_started":
            current = data["turn_id"]
            turns[current] = {"started": stamp(row["timestamp"]), "messages": [],
                              "responses": {}, "path": str(path), "turn_id": current}
        elif current and row["type"] == "response_item" and data.get("role") == "user":
            turns[current]["messages"].append("\n".join(p.get("text", "") for p in data.get("content", [])))
        elif row["type"] == "token_usage_record" and data.get("turn_id") in turns:
            turns[data["turn_id"]]["responses"][data["response_id"]] = {**data, "ts": row["timestamp"]}
    return list(turns.values())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rollout", type=Path, action="append", required=True)
    parser.add_argument("--since", required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parent.parent
    db = root / "data/world_pulse.db"
    conn = sqlite3.connect(db, timeout=10)
    conn.row_factory = sqlite3.Row
    turns = [turn for path in args.rollout for turn in read_turns(path)]
    plans = []
    episodes = conn.execute("SELECT e.*, s.steps FROM episode_log e JOIN episode_summary s "
        "ON s.episode_id=e.id WHERE e.started_at>=? AND e.ended_at IS NOT NULL "
        "AND COALESCE(e.source,'usage')='usage' AND s.execution_rounds IS NULL", (args.since,)).fetchall()
    for ep in episodes:
        calls = [(row, json.loads(row["data"])) for row in conn.execute(
            "SELECT * FROM trajectory_event WHERE episode_id=? AND kind='model.call_started'", (ep["id"],))]
        calls = [(r, d) for r, d in calls if d.get("provider") == "Codex" and d.get("role") == "execution"]
        if len(calls) != 1:
            continue  # 여러 실행 호출을 시간 추측으로 합치지 않는다.
        matches = [t for t in turns if stamp(ep["started_at"]) <= t["started"] <= stamp(ep["ended_at"])
                   and t["responses"] and any(ep["user_message"] in m for m in t["messages"])]
        if len(matches) != 1:
            continue
        turn = matches[0]
        steps = json.loads(ep["steps"] or "[]")
        call = calls[0][1]
        rounds = []
        for index, response in enumerate(turn["responses"].values(), 1):
            rounds.append({**call, "event": "round", "round": index, "round_index": index,
                "budget": 0, "response_id": response["response_id"], "turn_id": turn["turn_id"],
                "observed_at": response["ts"], "restored_from": turn["path"]})
        steps.extend(rounds)
        plans.append((ep, rounds, steps))
        print(json.dumps({"episode_id": ep["id"], "rounds": len(rounds)}, ensure_ascii=False))
    if args.apply and plans:
        backup = root / "data/_backups" / (datetime.now().strftime("%Y-%m-%d_%H%M%S") + "_codex_journal")
        backup.mkdir(parents=True)
        with sqlite3.connect(backup / "world_pulse.db", timeout=10) as target:
            conn.backup(target)
        with conn:
            for ep, rounds, steps in plans:
                conn.execute("UPDATE episode_summary SET steps=?, execution_rounds=? WHERE episode_id=?",
                             (json.dumps(steps, ensure_ascii=False), count_execution_rounds(steps), ep["id"]))
                seq = conn.execute("SELECT COALESCE(MAX(event_seq),0) FROM trajectory_event WHERE run_id=?",
                                   (ep["run_id"],)).fetchone()[0]
                for offset, data in enumerate(rounds, 1):
                    conn.execute("INSERT INTO trajectory_event (run_id,event_seq,episode_id,task_id,ts,kind,data,source) "
                                 "VALUES (?,?,?,?,?,'model.round',?,'usage')",
                                 (ep["run_id"], seq + offset, ep["id"], ep["task_id"], datetime.now().isoformat(),
                                  json.dumps(data, ensure_ascii=False)))
        print(f"restored={len(plans)} backup={backup}")
    conn.close()


if __name__ == "__main__":
    main()
