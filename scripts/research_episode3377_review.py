#!/usr/bin/env python3
"""Read-only audit of episode 3377 supervision, repair rounds and response reuse.

Uses stored evidence and pure budget functions; no inference or production writes.
Outputs counts/hashes, never raw research sources, instructions or response bodies.
"""
import argparse
from datetime import datetime, timezone
import difflib
import json
from pathlib import Path
import sqlite3
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "backend"))
import boot_paths  # noqa: E402,F401
from research_supervisor_budget import (  # noqa: E402
    FIELDS, episode, git, isolated_budget_class, sha, totals,
)

SOURCE_FILES = (
    "backend/cognition/conscious_supervisor.py",
    "backend/cognition/supervisor_runtime.py",
    "backend/datastore/supervision_store.py",
    "backend/base/episode_logger.py",
    "backend/ibl/ibl_envelope.py",
)


def read_ref(store, ref):
    raw = (store / (ref["id"] + ".txt")).read_text()
    assert len(raw) == ref["chars"] and sha(raw.encode()) == ref["id"]
    return raw


def budget_replay(calls):
    source = (BASE / SOURCE_FILES[0]).read_text()
    cls, config = isolated_budget_class(source)
    controller = cls()
    controller.config = config
    controller.call_metrics = None
    controller.usage = {"input": 0, "output": 0}
    controller.final_usage = {"input": 0, "output": 0}
    rows = []
    for call in calls:
        controller.finalizing = call["phase"] == "final"
        controller.call_usage = {}
        row = {"phase": call["phase"], "start_seq": call["start_seq"],
               "input_remaining_before": controller.model_budget_remaining()["input"],
               "input_requests": [r["input"] for r in call["responses"]]}
        controller.call_usage = {"input": call["usage"]["input"], "output": call["usage"]["output"]}
        row["input_remaining_after"] = controller.model_budget_remaining()["input"]
        row["allowed_after_observation"] = controller.model_budget_available()
        rows.append(row)
        for key in ("input", "output"):
            controller.usage[key] += call["usage"][key]
            if controller.finalizing:
                controller.final_usage[key] += call["usage"][key]
    return {"config": config, "calls": rows,
            "note": "Observed inputs held fixed; current pure policy replay, not model behavior replay."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=BASE / "outputs/research/episode3377-plan-review.json")
    args = parser.parse_args()
    with sqlite3.connect((BASE / "data/world_pulse.db").as_uri() + "?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN")
        audit, events = episode(conn, 3377)
        summary = dict(conn.execute(
            "SELECT episode_id,started_at,agent,execution_rounds,total_ms,evaluation_result "
            "FROM episode_summary WHERE episode_id=3377").fetchone())
        latest = conn.execute("SELECT MAX(id) FROM episode_log").fetchone()[0]
    store = Path(next(e["data"]["store"] for e in events if e["kind"] == "supervision.turn.opened"))
    events = [e for e in events if e["event_seq"] <= audit["first_run_ended_seq"]]
    calls, main_segments, pending_exec, inputs, results, patches = [], [], {}, {}, [], []
    active = None
    for e in events:
        d, kind, seq = e["data"], e["kind"], e["event_seq"]
        if kind == "supervision.model.started":
            assert active is None
            active = {"phase": d["phase"], "start_seq": seq, "responses": {}}
        elif kind == "model.response_snapshot":
            target = active["responses"] if d["role"] == "consciousness" else (
                pending_exec if d["role"] == "execution" else None)
            if target is not None:
                row = target.setdefault(d["response_id"], {"first_seq": seq})
                for key in FIELDS:
                    row[key] = max(row.get(key, 0), d.get(key, 0))
        elif kind == "model.usage" and d["role"] == "execution":
            assert sum(r["input"] for r in pending_exec.values()) == d["input"]
            main_segments.append({"usage_seq": seq, "rounds": len(pending_exec), "usage": d,
                                  "first_input": next(iter(pending_exec.values()))["input"],
                                  "last_input": list(pending_exec.values())[-1]["input"]})
            pending_exec = {}
        elif kind == "supervision.model.finished":
            active.update(end_seq=seq, elapsed_s=d["elapsed_s"], usage=d["usage"],
                          output_chars=d["output"]["chars"])
            active["responses"] = list(active["responses"].values())
            assert sum(r["input"] for r in active["responses"]) == d["usage"]["input"]
            calls.append(active)
            active = None
        elif kind == "supervision.tool.started":
            inputs[d["id"]] = json.loads(read_ref(store, d["input"]))
        elif kind == "supervision.tool.finished":
            raw = read_ref(store, d["evidence"])
            row = {"finish_seq": seq, "name": d["name"], "chars": len(raw),
                   "is_error": d["is_error"], "sha256": d["evidence"]["id"],
                   "verbose": inputs[d["id"]].get("verbose", False)}
            try:
                obj = json.loads(raw)
                if isinstance(obj, dict) and "final_result" in obj:
                    row["final_json_chars"] = len(json.dumps(obj["final_result"], ensure_ascii=False))
                    row["steps_json_chars"] = len(json.dumps(obj.get("results"), ensure_ascii=False))
            except ValueError:
                pass
            results.append(row)
        elif kind == "supervision.response.operation" and d["operation"] == "patch":
            obj = json.loads(read_ref(store, d["input"]))
            patches.append({"seq": seq, "base_version": obj["version"],
                            "blocks": [{"id": p["id"], "replacement_chars": len(p["text"])}
                                       for p in obj["patches"]]})
    assert active is None and not pending_exec
    comparisons = []
    for v in (1, 2):
        old = (store / f"response-v{v}.txt").read_text()
        new = (store / f"response-v{v + 1}.txt").read_text()
        matched = sum(b.size for b in difflib.SequenceMatcher(None, old, new, autojunk=False).get_matching_blocks())
        comparisons.append({"base_version": v, "old_chars": len(old), "new_chars": len(new),
                            "old_sha256": sha(old.encode()), "new_sha256": sha(new.encode()),
                            "matching_chars": matched, "matching_share_of_new": matched / len(new),
                            "note": "SequenceMatcher alignment; not exact token savings or semantic equivalence."})
    decisions = [{"seq": e["event_seq"], "phase": e["data"]["phase"],
                  "status": e["data"]["decision"]["status"],
                  "reason_sha256": sha(e["data"]["decision"]["reason"].encode()),
                  "response_version": e["data"].get("response", {}).get("version")}
                 for e in events if e["kind"] == "supervision.decision"]
    stale = [{"seq": e["event_seq"], "reviewed_revision": e["data"]["reviewed_revision"],
              "current_revision": e["data"]["current_revision"]}
             for e in events if e["kind"] == "supervision.decision.stale"]
    main_total = totals([r["usage"] for r in main_segments])
    repair_total = totals([r["usage"] for r in main_segments[1:]])
    assert [r["rounds"] for r in main_segments] == [17, 11, 10]
    assert main_total["input"] == 11250302 and repair_total["input"] == 7391316
    assert repair_total["non_cache_read_input"] == 60449
    assert audit["totals"]["input"] + audit["totals"]["output"] == 11646685
    assert audit["post_run_totals"]["input"] + audit["post_run_totals"]["output"] == 16553
    report_path = BASE / "projects/정보센터/outputs/블루칼라_구조해체_검증_20260910.md"
    report = report_path.read_text()
    data = {
        "observed_at_utc": datetime.now(timezone.utc).isoformat(), "latest_episode_id_at_snapshot": latest,
        "episode_id": 3377, "events_sha256": audit["events_sha256"], "head_at_audit": git("rev-parse", "HEAD").strip(),
        "source_sha256": {p: sha((BASE / p).read_bytes()) for p in SOURCE_FILES},
        "summary": summary, "totals": audit["totals"], "by_role": audit["by_role"],
        "post_run_totals": audit["post_run_totals"], "supervisor_calls": calls,
        "budget_replay": budget_replay(calls), "decisions": decisions, "stale_decisions": stale,
        "delivered_middle_instructions": sum(e["kind"] == "supervision.instruction.delivered" for e in events),
        "main_segments": main_segments, "actual_main_responses": sum(r["rounds"] for r in main_segments),
        "main_total": main_total, "repair_total": repair_total,
        "repair_share_of_main_input": repair_total["input"] / main_total["input"],
        "tool_results": results, "tool_result_chars": sum(r["chars"] for r in results),
        "large_results_39000_chars": [r for r in results if r["chars"] >= 39000],
        "patches": patches, "response_comparisons": comparisons,
        "final_review_status": json.loads((store / "review_status.json").read_text()),
        "current_report": {"path": str(report_path), "sha256": sha(report.encode()), "chars": len(report),
                           "mtime_utc": datetime.fromtimestamp(report_path.stat().st_mtime, timezone.utc).isoformat(),
                           "contains_old_unique_claim": "농업 외 직역에서 이름·수치·시점이 확인된 유일한 사례다" in report,
                           "contains_third_sector": "### (5) 요식" in report},
        "limitations": ["Different task/model from episode 3364; no controlled efficiency comparison.",
                        "Tokens include cache reads; partial cancelled usage is not full generation measurement.",
                        "Research-source truth was not independently rechecked; internal contradictions were inspected.",
                        "Shared controller phase may label concurrent executor events as review; roles kept separate."],
    }
    # Keep original goal text private in the store; counts and provenance suffice here.
    data["final_review_status"].pop("original_goal", None)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(args.output), "totals": data["totals"], "rounds": data["actual_main_responses"],
                      "repair_share": data["repair_share_of_main_input"], "budget": data["budget_replay"]["calls"],
                      "events_sha256": data["events_sha256"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
