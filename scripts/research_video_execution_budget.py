#!/usr/bin/env python3
"""Read-only episode 3364 executor audit and offline display deduplication.

No model calls, production imports, DB writes, or raw user content in the output.
The optional recovered CLI prompt is temporary: pass --prompt-file if available.
Character savings are measured on stored JSON, not claimed token/cost savings.
"""
import argparse
import ast
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sqlite3
import sys

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE / "backend"))
import boot_paths  # noqa: E402,F401
from research_supervisor_budget import FIELDS, episode, git, sha, totals  # noqa: E402

SLIDE_SEQS = (207, 212, 216, 220, 225, 229, 245, 249, 254, 259, 263)
DUPLICATE_SEQS = (75, 99, 111, 125, 132)
SOURCE_FILES = (
    "backend/ibl/ibl_envelope.py", "backend/ibl/ibl_access.py",
    "backend/common/spill.py", "backend/providers/claude_code.py",
    "backend/providers/cli_provider.py", "backend/providers/base.py",
    "backend/cognition/conscious_supervisor.py",
    "backend/cognition/supervisor_runtime.py",
    "data/packages/installed/tools/lecture_workspace/slide_ai.py",
)


def display_comparison(event):
    data = event["data"]
    ref = data["evidence"]
    raw = (Path(data["store"]) / (ref["id"] + ".txt")).read_text()
    assert sha(raw.encode()) == ref["id"]
    envelope = json.loads(raw)
    assert len(raw) == ref["chars"]
    final = envelope["final_result"]
    projected = json.loads(raw)
    replacements = 0
    for step in projected["results"]:
        if step.get("result") == final:
            step["result"] = {"ref": "final_result"}
            replacements += 1
    # Retain the whole canonical result, including every nested failure/evidence.
    assert projected["final_result"] == envelope["final_result"]
    for old, new in zip(envelope["results"], projected["results"]):
        assert {k: v for k, v in old.items() if k != "result"} == {
            k: v for k, v in new.items() if k != "result"}
    assert {k: v for k, v in envelope.items() if k != "results"} == {
        k: v for k, v in projected.items() if k != "results"}
    before = json.dumps(envelope, ensure_ascii=False, indent=2)
    after = json.dumps(projected, ensure_ascii=False, indent=2)
    assert before == raw and replacements == 1
    return {"finish_seq": event["event_seq"], "sha256": ref["id"],
            "before_chars": len(before), "after_chars": len(after),
            "saved_chars": len(before) - len(after), "exact_copies_replaced": replacements}


def prompt_sizes(path, log):
    if path is None:
        return {"available": False, "note": "Optional temporary prompt not supplied."}
    text = path.read_text()
    match = re.search(r"\[ClaudeCode/스토리텔러\] call: session=(\S+) "
                      r"system_prompt=(\d+)자 message=(\d+)자", log)
    assert match and match[1] == "new"
    system_chars = int(match[2])
    # Bind the recovery to the observed lengths/sections, not merely its filename.
    assert len(text) == 104300 and system_chars == 102721
    ranges = {}
    for name in ("system_structure", "ibl_executor", "ibl_actions", "ibl_idioms", "project_memory"):
        start = re.search(r"^<" + name + r"[ >]", text, re.MULTILINE).start()
        end = text.index("</" + name + ">", start) + len("</" + name + ">")
        ranges[name] = {"start_char": start, "end_char": end, "chars": end - start}
    ibl_chars = sum(ranges[k]["chars"] for k in ("ibl_executor", "ibl_actions", "ibl_idioms"))
    assert 0 < ibl_chars < system_chars
    return {"available": True, "path": str(path.resolve()), "sha256": sha(text.encode()),
            "mtime_utc": datetime.fromtimestamp(path.stat().st_mtime, timezone.utc).isoformat(),
            "file_chars": len(text), "logged_system_chars": system_chars,
            "logged_message_chars": int(match[3]), "session": match[1],
            "sections": ranges, "ibl_chars": ibl_chars,
            "ibl_share_of_logged_system": ibl_chars / system_chars,
            "appended_cli_policy_chars": len(text) - system_chars,
            "note": "Character accounting of recovered appended prompt; CLI base/tool tokens not separable."}


def slide_caller_contract():
    """Inspect actual caller flags and execute ONLY the pure command-building method.

    Runtime/config values are dummy placeholders. Never import/init/run a provider.
    """
    source = (BASE / SOURCE_FILES[-1]).read_text()
    tree = ast.parse(source)
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_get_slide_ai")
    assigned = sorted({n.targets[0].attr for n in ast.walk(fn)
                       if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Attribute)
                       and isinstance(n.targets[0].value, ast.Name)
                       and n.targets[0].value.id == "provider"})
    provider_source = (BASE / "backend/providers/claude_code.py").read_text()
    cls = next(n for n in ast.parse(provider_source).body
               if isinstance(n, ast.ClassDef) and n.name == "ClaudeCodeProvider")
    method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "_build_command")
    # Strip annotations only; the command-branch implementation remains unchanged.
    method.returns = None
    for arg in method.args.args:
        arg.annotation = None
    scope = {"json": json}
    exec(compile(ast.Module(body=[method], type_ignores=[]), "command-audit", "exec"), scope)
    class Dummy:
        _binary_path = "not-executed"
        agent_role = "execution"
        model = "selected-execution-model"
        system_prompt = "task-prompt"
        EAGER_BUILTIN_TOOLS = ["Read", "Bash"]
        EAGER_TOOLS = ["Read", "Bash", "mcp__indiebizos__execute_ibl"]
        DISALLOWED_TOOLS = ["DummyDisallowed"]
        TOOL_POLICY = "dummy-tool-policy"

        def shadow_hook_settings(self):
            return {}
    variants = {}
    for mode in (None, "none", "read"):
        cmd = scope["_build_command"](Dummy(), mcp_config_path="dummy.json", tools_mode=mode)
        variants[str(mode)] = {
            "tools": cmd[cmd.index("--tools") + 1],
            "loads_mcp_config": "--mcp-config" in cmd,
            "sets_empty_setting_sources": "--setting-sources" in cmd
                and cmd[cmd.index("--setting-sources") + 1] == "",
        }
    return {"assigned_provider_flags": assigned, "command_variants": variants,
            "note": "Pure command construction with dummy settings; no inference token A/B measurement."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt-file", type=Path)
    parser.add_argument("--output", type=Path, default=BASE / "outputs/research/video-execution-3364.json")
    args = parser.parse_args()
    with sqlite3.connect((BASE / "data/world_pulse.db").as_uri() + "?mode=ro", uri=True) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("BEGIN")
        audit, events = episode(conn, 3364)
        log = conn.execute("SELECT log FROM episode_log WHERE id=3364").fetchone()[0]
        timing = dict(conn.execute("SELECT started_at, ended_at, total_ms FROM episode_log WHERE id=3364").fetchone())
    by_seq = {e["event_seq"]: e for e in events}
    responses = {}
    for e in events:
        if e["kind"] != "model.response_snapshot" or e["event_seq"] >= audit["first_run_ended_seq"]:
            continue
        d = e["data"]
        row = responses.setdefault(d["response_id"], {"first_seq": e["event_seq"], "role": d["role"]})
        for key in FIELDS:
            row[key] = max(row.get(key, 0), d.get(key, 0))
    rounds = sorted((r for r in responses.values() if r["role"] == "execution" and r["input"] >= 100000),
                    key=lambda r: r["first_seq"])
    main_usage = next(r for r in audit["usage"] if r["seq"] == 436)
    assert len(rounds) == 22 and sum(r["input"] for r in rounds) == main_usage["input"] == 6239640
    groups = {
        "main_executor": [r for r in audit["usage"] if r["seq"] == 436],
        "slide_generation": [r for r in audit["usage"] if r["seq"] in SLIDE_SEQS],
        "supervisor": [r for r in audit["usage"] if r.get("role") == "consciousness"],
        "image_review": [r for r in audit["usage"] if r.get("role") == "oneshot:execution"],
    }
    # Attribute audio by its unique observed usage signature, not a nearby tool finish.
    groups["audio"] = [r for r in audit["usage"] if r["input"] == 857 and r["output"] == 0]
    used_seqs = {r["seq"] for rows in groups.values() for r in rows}
    groups["classify_background"] = [r for r in audit["usage"] if r["seq"] not in used_seqs]
    flat = [r for rows in groups.values() for r in rows]
    assert len(flat) == len({r["seq"] for r in flat}) == len(audit["usage"])
    assert len(groups["slide_generation"]) == 11 and len(groups["image_review"]) == 6
    assert totals(flat) == audit["totals"]
    phases = []
    for label, start, end in (("protocol_and_source", 1, 6), ("draft_and_length", 7, 11),
                              ("final_draft_and_slides", 12, 13), ("notes_tts_qa_wait", 14, 16),
                              ("render_and_final_checks", 17, 22)):
        phases.append({"label": label, "rounds": [start, end],
                       "input": sum(r["input"] for r in rounds[start - 1:end])})
    comparisons = [display_comparison(by_seq[n]) for n in DUPLICATE_SEQS]
    comparison_totals = {k: sum(r[k] for r in comparisons)
                         for k in ("before_chars", "after_chars", "saved_chars")}
    result = {
        "observed_at_utc": datetime.now(timezone.utc).isoformat(),
        "episode_id": 3364, "events_sha256": audit["events_sha256"],
        "head_at_audit": git("rev-parse", "HEAD").strip(), "timing": timing,
        "source_sha256": {p: sha((BASE / p).read_bytes()) for p in SOURCE_FILES},
        "totals": audit["totals"], "post_run_totals": audit["post_run_totals"],
        "by_purpose": {k: totals(v) for k, v in groups.items()},
        "main_reported_reasoning": main_usage.get("reasoning"),
        "main_rounds": [{"round": i, "first_seq": r["first_seq"], "input": r["input"]}
                        for i, r in enumerate(rounds, 1)],
        "main_phases_annotated": phases,
        "arithmetic": {"first_context_times_rounds": rounds[0]["input"] * len(rounds),
                       "growth_above_first_context": main_usage["input"] - rounds[0]["input"] * len(rounds),
                       "input_before_first_draft_round": sum(r["input"] for r in rounds[:6])},
        "first_draft_tool_seq": 142, "first_draft_tool_at": by_seq[142]["ts"],
        "first_draft_elapsed_s": (datetime.fromisoformat(by_seq[142]["ts"]) -
                                  datetime.fromisoformat(timing["started_at"])).total_seconds(),
        "prompt": prompt_sizes(args.prompt_file, log),
        "duplicate_envelope_comparison": comparisons, "duplicate_totals": comparison_totals,
        "slide_caller_contract": slide_caller_contract(),
        "limitations": ["One task, no controlled inference replay or promised savings.",
                        "Usage snapshots partition main input only, never added to aggregate usage.",
                        "Phase annotations refer to outer decisions; nested tool latency overlaps.",
                        "Cached input, non-cache input, reasoning, output and GPU time are distinct."],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(args.output), "by_purpose": result["by_purpose"],
                      "phases": phases, "duplicate_totals": comparison_totals,
                      "prompt": result["prompt"], "contract": result["slide_caller_contract"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
