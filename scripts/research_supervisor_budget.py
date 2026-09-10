#!/usr/bin/env python3
"""Read-only episode 3364 budget audit; no model calls or production mutations.

Run from the repository root. The output contains counts and evidence fingerprints,
not user messages, tool-result bodies, credentials, or model reasoning.
"""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "backend"))
import boot_paths  # noqa: E402,F401

BASELINE = "ce5d8a91f0f03a650fc655a241bb83c299ae87a4"
FIELDS = ("input", "output", "cache_read", "cache_create")


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.check_output(["git", *args], cwd=BASE).decode()


def totals(rows):
    result = {key: sum(row.get(key, 0) for row in rows) for key in FIELDS}
    result["usage_records"] = len(rows)
    result["non_cache_read_input"] = result["input"] - result["cache_read"]
    return result


def episode(connection, episode_id):
    rows = [dict(row) for row in connection.execute(
        "SELECT event_seq, ts, kind, data FROM trajectory_event "
        "WHERE episode_id=? ORDER BY event_seq", (episode_id,))]
    fingerprint = sha(json.dumps(rows, ensure_ascii=False, sort_keys=True).encode())
    for row in rows:
        row["data"] = json.loads(row["data"])
    ends = [row["event_seq"] for row in rows if row["kind"] == "run.ended"]
    end = min(ends) if ends else None
    usage = [{"seq": row["event_seq"], **row["data"]} for row in rows
             if row["kind"] == "model.usage" and (end is None or row["event_seq"] < end)]
    after = [row["data"] for row in rows
             if row["kind"] == "model.usage" and end is not None and row["event_seq"] > end]
    roles = sorted({row.get("role", "unknown") for row in usage})
    result = {
        "episode_id": episode_id, "event_count": len(rows), "events_sha256": fingerprint,
        "first_run_ended_seq": end, "usage": usage, "totals": totals(usage),
        "by_role": {role: totals([row for row in usage if row.get("role", "unknown") == role])
                    for role in roles},
        "post_run_totals": totals(after),
    }
    return result, rows


def isolated_budget_class(source):
    """Compile only pure budget methods; importing the live supervisor is unnecessary."""
    tree = ast.parse(source)
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "Supervisor")
    methods = [node for node in cls.body if isinstance(node, ast.FunctionDef)
               and node.name in {"model_budget_available", "model_budget_remaining"}]
    cls.body = methods
    cls.bases = []
    scope = {}
    exec(compile(ast.Module(body=[cls], type_ignores=[]), "budget-audit", "exec"), scope)
    config = next(ast.literal_eval(node.value) for node in tree.body
                  if isinstance(node, ast.Assign)
                  and any(isinstance(target, ast.Name) and target.id == "DEFAULTS" for target in node.targets))
    return scope["Supervisor"], config


def simulate_budget(source, plan_inputs, final_inputs):
    cls, config = isolated_budget_class(source)
    controller = cls()
    controller.config = config
    controller.call_metrics = None
    controller.usage = {"input": 0, "output": 0}
    controller.final_usage = {"input": 0, "output": 0}
    traces = {}
    for phase, inputs in (("plan", plan_inputs), ("final", final_inputs)):
        controller.finalizing = phase == "final"
        cumulative = 0
        traces[phase] = []
        for value in inputs:
            cumulative += value
            controller.call_usage = {"input": cumulative, "output": 0}
            row = {"request_input": value, "phase_cumulative_input": cumulative,
                   "allowed_after_observation": controller.model_budget_available()}
            if hasattr(controller, "model_budget_remaining"):
                row["remaining"] = controller.model_budget_remaining()
            traces[phase].append(row)
        controller.usage["input"] += cumulative
        if controller.finalizing:
            controller.final_usage["input"] += cumulative
    return {"config": config, "traces": traces,
            "note": "Input-only trace replay, holding observed requests fixed; no outcome prediction."}


def input_price_proxy(row, base, write, read):
    fresh = row["input"] - row["cache_read"] - row["cache_create"]
    return (fresh * base + row["cache_create"] * write + row["cache_read"] * read) / 1_000_000


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=BASE / "outputs/research/supervisor-budget-3364.json")
    args = parser.parse_args()
    with sqlite3.connect((BASE / "data/world_pulse.db").as_uri() + "?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN")  # One consistent read snapshot, without locking writers.
        audit, events = episode(conn, 3364)
        comparisons = [episode(conn, n)[0] for n in (3352, 3332, 3322)]
        log = conn.execute("SELECT log FROM episode_log WHERE id=3364").fetchone()[0]
        timing = dict(conn.execute(
            "SELECT started_at, ended_at, total_ms FROM episode_log WHERE id=3364").fetchone())
    by_response = {}
    for event in events:
        if event["kind"] != "model.response_snapshot":
            continue
        data = event["data"]
        row = by_response.setdefault(data["response_id"], {
            "first_seq": event["event_seq"], "role": data["role"], "model": data["model"]})
        for key in FIELDS:
            row[key] = max(row.get(key, 0), data.get(key, 0))
    plan = [r for r in by_response.values() if r["role"] == "consciousness" and r["first_seq"] < 100]
    final = [r for r in by_response.values() if r["role"] == "consciousness" and r["first_seq"] > 400]
    # Explicit episode-specific attribution, checked against the outer CLI log.
    main_execution = next(r for r in audit["usage"] if r["seq"] == 436)
    main_rounds = [r for r in by_response.values()
                   if r["role"] == "execution" and r["input"] >= 100000]
    assert len(main_rounds) == 22
    assert sum(r["input"] for r in main_rounds) == main_execution["input"]
    assert sum(r["input"] for r in plan) == 253964
    assert sum(r["input"] for r in final) == 64020
    assert audit["totals"]["input"] + audit["totals"]["output"] == 7053764
    assert audit["post_run_totals"]["input"] + audit["post_run_totals"]["output"] == 14934
    store = Path(next(e["data"]["store"] for e in events if e["kind"] == "supervision.turn.opened"))
    stored_events = [json.loads(line) for line in (store / "events.jsonl").read_text().splitlines()]
    tool_results = []
    for event in stored_events:
        if event.get("phase") != "plan" or event["kind"] != "tool.supervisor":
            continue
        ref = event["result"]
        raw = (store / (ref["id"] + ".txt")).read_text()
        assert sha(raw.encode()) == ref["id"]
        tool_results.append({"store_seq": event["seq"], "op": event["operation"],
                             "chars": ref["chars"], "sha256": ref["id"]})
    crawl_ref = next(e["result"] for e in stored_events if e["seq"] == 7)
    crawl = json.loads((store / (crawl_ref["id"] + ".txt")).read_text())
    paragraph_texts = [r["text"] for r in crawl["items"] if r.get("text")]
    old_source = git("show", BASELINE + ":backend/cognition/conscious_supervisor.py")
    current_source = (BASE / "backend/cognition/conscious_supervisor.py").read_text()
    plan_inputs = [r["input"] for r in plan]
    final_inputs = [r["input"] for r in final]
    audit.update({
        "observed_at_utc": datetime.now(timezone.utc).isoformat(), "timing": timing,
        "baseline_commit": BASELINE, "head_at_audit": git("rev-parse", "HEAD").strip(),
        "working_supervisor_sha256": sha(current_source.encode()),
        "working_runtime_sha256": sha((BASE / "backend/cognition/supervisor_runtime.py").read_bytes()),
        "snapshot_note": "Snapshots are deduplicated by response ID, not added to model.usage.",
        "supervisor_rounds": {"plan": plan, "final": final},
        "main_executor": {"usage": main_execution, "rounds": len(main_rounds),
                          "first_context": main_rounds[0]["input"], "last_context": main_rounds[-1]["input"]},
        "prompt_size_log_lines": re.findall(r"^.*call: session=.*$", log, flags=re.MULTILINE),
        "supervisor_plan_tool_results": tool_results,
        "crawl_duplicate": {"text_chars": len(crawl["text"]), "paragraphs": len(paragraph_texts),
                            "paragraph_chars": sum(map(len, paragraph_texts)),
                            "all_paragraphs_also_in_text": all(t in crawl["text"] for t in paragraph_texts)},
        "baseline_budget_replay": simulate_budget(old_source, plan_inputs, final_inputs),
        "working_budget_replay": simulate_budget(current_source, plan_inputs, final_inputs),
        "plan_baseline_arithmetic": {"first_context_times_four": plan_inputs[0] * len(plan),
                                     "growth_above_first_context": sum(plan_inputs) - plan_inputs[0] * len(plan)},
        "input_only_price_proxy_usd": {
            "assumptions": "2026-09-10 published API rates, 5m writes, no output/tools; NOT the actual CLI bill or subscription quota.",
            "plan": input_price_proxy(totals(plan), 10, 12.5, 0.25),
            "final": input_price_proxy(totals(final), 5, 6.25, 0.5),
            "main_executor": input_price_proxy(main_execution, 10, 12.5, 0.25)},
        "comparisons": comparisons,
    })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(args.output), "task_totals": audit["totals"],
                      "supervisor": audit["by_role"]["consciousness"],
                      "price_proxy": audit["input_only_price_proxy_usd"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
