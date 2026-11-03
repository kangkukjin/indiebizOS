"""Read-only episode audit; exports metadata, not private conversation bodies.

Run from the canonical repository root. Historical events are not re-executed.
Flags are retrieval candidates, never automatic behavioral diagnoses.
"""
import collections
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs/failure_recovery_research_2026-11-03"
DB = ROOT / "data/world_pulse.db"
COHORT = list(range(5747, 5768))
CONTRAST = [5663, 5664, 5785, 5787, 5789, 5792, 5793, 5794, 5795, 5801]


def read_events(conn, episode):
    rows = conn.execute(
        "SELECT run_id,event_seq,kind,data FROM trajectory_event "
        "WHERE episode_id=? ORDER BY event_seq", (episode,))
    return [(run, seq, kind, json.loads(raw)) for run, seq, kind, raw in rows]


def audit(conn, episode):
    record = dict(conn.execute(
        "SELECT id,started_at,ended_at,agent,source,run_id,task_id,"
        "parent_run_id,length(log) log_chars,total_ms FROM episode_log WHERE id=?",
        (episode,)).fetchone())
    events = read_events(conn, episode)
    calls, failures, endings, repeated = {}, [], [], collections.defaultdict(list)
    observations = collections.Counter(kind for _, _, kind, _ in events)
    stores = set()
    for run, seq, kind, data in events:
        if data.get("store"):
            stores.add(data["store"])
        if kind == "cognition.route":
            record["route"] = data.get("request_type")
        if kind == "supervision.tool.started":
            calls[data["id"]] = data
        if kind == "supervision.tool.finished":
            flagged = bool(data.get("is_error") or data.get("operation_failures")
                           or data.get("source_failures"))
            if flagged:
                start = calls.get(data.get("id"), {})
                item = {"seq": seq, "tool": data.get("name"),
                        "is_error": data.get("is_error"),
                        "source_failures": data.get("source_failures", 0),
                        "input_ref": start.get("input", {}).get("id"),
                        "result_ref": data.get("evidence", {}).get("id"),
                        "store": data.get("store")}
                failures.append(item)
                if data.get("is_error") and item["input_ref"]:
                    repeated[(item["tool"], item["input_ref"])].append(seq)
        if kind == "supervision.evaluation.finished":
            decision = data.get("decision", {})
            endings.append({"seq": seq, "kind": kind,
                            "review_status": decision.get("status"),
                            "goal_status": decision.get("goal_status"),
                            "reason": decision.get("goal_reason"),
                            "remaining": decision.get("remaining", [])})
        if kind == "supervision.repair.completion":
            endings.append({"seq": seq, "kind": kind,
                            "status": data.get("status"),
                            "reason_chars": len(data.get("reason", ""))})
    record.update(event_count=len(events), tool_finish_count=observations[
        "supervision.tool.finished"], flagged_tool_count=len(failures),
        flagged_tools=failures, judgments=endings,
        repeated_error_input_groups=[{"tool": key[0], "input_ref": key[1], "seqs": seqs}
                                     for key, seqs in repeated.items() if len(seqs) > 1],
        event_counts={k: observations[k] for k in [
            "cognition.task_continuation", "capability.judged", "capability.resumed",
            "supervision.situation.delivered", "supervision.situation.observed",
            "supervision.instruction.delivered", "repair.user_resumed", "run.failed",
            "model.usage", "distillation.cost"]},
        stores=sorted(stores))
    return record


def main():
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("BEGIN")
    cohort = [audit(conn, eid) for eid in COHORT]
    contrast = [audit(conn, eid) for eid in CONTRAST]
    assert all(r["source"] == "usage" and r["started_at"].startswith("2026-11-02")
               for r in cohort)
    actual_ids = [r[0] for r in conn.execute(
        "SELECT id FROM episode_log WHERE started_at >= '2026-11-02' "
        "AND started_at < '2026-11-03' AND source='usage' ORDER BY id")]
    assert actual_ids == COHORT
    summary = {"cohort_runs": len(cohort),
               "runs_with_flagged_tool": sum(r["flagged_tool_count"] > 0 for r in cohort),
               "flagged_tool_events": sum(r["flagged_tool_count"] for r in cohort),
               "tool_finished_events": sum(r["tool_finish_count"] for r in cohort),
               "same_input_error_runs": [r["id"] for r in cohort if r["repeated_error_input_groups"]],
               "continuation_runs": [r["id"] for r in cohort
                                     if r["event_counts"]["cognition.task_continuation"]],
               "routes": dict(collections.Counter(r.get("route") for r in cohort))}
    document = {"method": "Fixed previous complete local day; usage only; one row per run, not goal.",
                "database": str(DB), "snapshot_max_episode": conn.execute(
                    "SELECT MAX(id) FROM episode_log").fetchone()[0],
                "git_head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT,
                                                     text=True).strip(),
                "summary": summary, "cohort": cohort, "purposive_contrast": contrast}
    conn.close()
    path = OUT / "episode_audit.json"
    path.write_text(json.dumps(document, ensure_ascii=False, separators=(",", ":")) + "\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print("metadata_sha256", hashlib.sha256(path.read_bytes()).hexdigest())


if __name__ == "__main__":
    main()
