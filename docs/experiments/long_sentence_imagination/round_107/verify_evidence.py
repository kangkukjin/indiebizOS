"""보존 산출물·실제 호출 계보를 검사한다. 모델 호출과 의미 자동 채점은 없다."""

import ast
import hashlib
import json
import sqlite3
import sys
from pathlib import Path


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUTPUT = ROOT / "outputs/long_sentence_imagination/2026-11-01_107회차"
LIVE = "--live" in sys.argv


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


evidence = read(HERE / "evidence.json")
cases = read(HERE / "cases.json")
start = read(HERE / "start.json")
review = read(HERE / "review.json")
assert len(cases) == len(evidence["cases"]) == len(review["cases"]) == 10
assert start == evidence["start"]
assert sha(HERE / "cases.json") == start["cases_sha256"]
assert start["cases_sha256"] == evidence["cases_sha256_after"]
assert start["source_sha256"] == evidence["source_sha256_after"]
assert sha(HERE / "deep_research.md") == start["source_sha256"]["data/guides/deep_research.md"]
assert sha(HERE / "consciousness_prompt.md") == start["source_sha256"]["data/common_prompts/consciousness_prompt.md"]
assert {c["id"] for c in cases} == {c["id"] for c in review["cases"]}
prior = read(HERE / "results/C05/framing.json")["_research_plan"]
local_checked = []
local_missing = []
all_call_ids = []

for entry in evidence["cases"] + evidence["invalid_attempts"]:
    invalid = entry in evidence["invalid_attempts"]
    folder = HERE / ("invalid_attempts" if invalid else "results") / entry["id"]
    attempt = entry["id"] if invalid else entry["attempt"]
    original = OUTPUT / attempt
    receipt = read(folder / "receipt.json")
    framing = read(folder / "framing.json")
    calls = read(folder / "calls.json")
    assert receipt["status"] == entry["status"] == "completed"
    assert receipt["origin"] == entry["episode_source"] == "training"
    assert receipt["model"]["provider"] == "claude_code"
    assert receipt["model"]["model"] == "opus"
    assert len(calls) == receipt["calls"] == receipt["usage"]["requests"]
    assert receipt["usage"]["unmeasured_requests"] == 0
    all_call_ids.extend(c["call_id"] for c in receipt["usage"]["calls"])
    for name, expected in entry["artifact_sha256"].items():
        assert sha(folder / name) == expected, (attempt, name)
    for call in calls:
        assert sha(folder / f"call_{call['index']}_response.txt") == call["response_sha256"]
    plan = framing.get("_research_plan")
    if plan:
        assert plan["author"] == "consciousness"
        assert (folder / "research_plan.md").read_text() == plan["body"]
        assert sha(folder / "research_plan.md") == plan["sha256"]
        assert plan["guide_sha256"] == sha(HERE / "deep_research.md")
    else:
        assert entry["id"] in {"C07", "C08"}
        assert not (folder / "research_plan.md").exists()
    if not invalid:
        events = read(folder / "events.json")
        kinds = [event["kind"] for event in events]
        assert kinds.count("model.usage") == len(calls)
        assert not entry["tool_events"]
        assert not any(audit["operator_checks_present"] for audit in entry["input_audit"])
        assert [audit["guide_supplied"] for audit in entry["input_audit"]] == ([False, True] if plan else [False])
        assert kinds.count("research.guide_supplied") == kinds.count("research.plan_saved") == int(bool(plan))
        assert not any("invalid" in kind or "failed" in kind for kind in kinds)
        if plan:
            assert kinds.index("research.guide_supplied") < kinds.index("research.plan_saved")
        if entry["id"] in {"C09", "C10"}:
            assert plan["previous_path"] == prior["path"]
    else:
        assert entry["previous_read_error"]
        assert plan["previous_path"] is None

    if original.exists():
        for call in calls:
            index = call["index"]
            for suffix, key in [("input", "prompt_sha256"), ("system", "system_sha256")]:
                assert sha(original / f"call_{index}_{suffix}.txt") == call[key]
        if entry["id"] in {"C09", "C10"}:
            text = (original / "call_1_input.txt").read_text()
            assert ("연구계획이 현재 작업공간 밖에 있습니다" in text) == invalid
        if plan:
            assert sha(Path(plan["path"])) == plan["sha256"]
        raw_events = [json.loads(line) for line in (original / "supervision/events.jsonl").read_text().splitlines()]
        assert not any(item["kind"] in {"model.native_tool", "tool.started", "tool.finished"} for item in raw_events)
        local_checked.append(attempt)
    else:
        local_missing.append(attempt)

assert len(all_call_ids) == len(set(all_call_ids)) == 22
for key, expected in evidence["total_usage"].items():
    assert sum(entry["usage"][key] for entry in evidence["cases"] + evidence["invalid_attempts"]) == expected
for key, expected in evidence["valid_attempt_usage"].items():
    assert sum(entry["usage"][key] for entry in evidence["cases"]) == expected

quote_count = 0
for case in review["cases"]:
    for quote in case.get("quotes", []):
        text = (HERE / "results" / quote["file"]).read_text()
        if quote.get("field"):
            text = json.loads(text)
            for key in quote["field"].split("."):
                text = text[key]
        assert quote["text"] in text, quote
        quote_count += 1

counter = read(HERE / "counterexample.json")
before = counter["prior_monthly"]
after = counter["only_after_opening"]
earlier = counter["decline_before_opening"]
assert sum(after) == sum(earlier) == 420 and sum(before) == 600
assert sum(after[:4]) == sum(before[:4]) > sum(earlier[:4])
handoff = read(HERE / "handoff_probe.json")
assert handoff["expert_choice_propagates"] and handoff["source_guard_present"]
assert sha(HERE / "handoff_compiled.txt") == handoff["compiled_sha256"]
assert handoff["quote"] in (HERE / "handoff_compiled.txt").read_text()

if LIVE:
    assert not local_missing
    for name, expected in start["source_sha256"].items():
        assert sha(ROOT / name) == expected, name
    with sqlite3.connect(f"file:{ROOT}/data/world_pulse.db?mode=ro", uri=True) as database:
        for entry in evidence["cases"] + evidence["invalid_attempts"]:
            assert database.execute("select source from episode_log where id=?", (entry["episode_id"],)).fetchone() == ("training",)

for path in HERE.rglob("*.py"):
    ast.parse(path.read_text(), filename=str(path))
assert all(len(path.read_text().splitlines()) <= 1500 for path in HERE.rglob("*") if path.is_file())
print(json.dumps({"status": "passed", "semantic_auto_grading": False,
                  "valid_cases": 10, "invalid_attempts_preserved": 2,
                  "unique_model_calls": len(all_call_ids), "exact_quotes": quote_count,
                  "local_attempts_checked": local_checked,
                  "local_attempts_missing": local_missing, "live_source_and_db_checked": LIVE},
                 ensure_ascii=False, indent=2))
