"""보존 파일·호출 계보·인용·시간을 대조한다. 의미 자동 채점이나 모델 호출 없음."""
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUTPUT = ROOT / "outputs/long_sentence_imagination/2026-11-01_108회차"
LIVE = "--live" in sys.argv


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


evidence = read(HERE / "evidence.json")
start = read(HERE / "start.json")
refine = read(HERE / "refinement.json")
review = read(HERE / "review.json")
assert evidence["start"] == start
assert sha(HERE / "cases.json") == start["cases_sha256"] == evidence["cases_sha256_end"]
assert sha(HERE / "refinement_cases.json") == refine["inputs_sha256"] == evidence["refinement_cases_sha256"]
assert sha(HERE / "recovered_context.json") == start["fixture_sha256"]
assert sha(HERE / "refined_consciousness_prompt.md") == refine["prompt_sha256"]
assert sha(HERE / "refined_deep_research.md") == refine["guide_sha256"]
assert (HERE / "refined_deep_research.md").stat().st_size <= 36000
assert (HERE / "r01_guide.md").read_text().replace("이 가이드는 **의식", "**의식", 1) == (HERE / "deep_research.md").read_text()
for path, expected in start["after_sha256"].items():
    assert evidence["source_sha256_end"][path] == expected
    if path.startswith("backend/"):
        assert expected == start["before_sha256"][path] == evidence["source_sha256_final"][path]

groups = {"cases": "results", "preliminary": "preliminary", "recovery_relinked": "recovery_relinked", "refinement": "refinement"}
assert [len(evidence[g]) for g in groups] == [9, 2, 1, 6]
all_calls = []
local_checked = []
for group, folder in groups.items():
    for entry in evidence[group]:
        dest = HERE / folder / entry["id"]
        original = OUTPUT / entry["attempt"]
        receipt = read(dest / "receipt.json")
        calls = read(dest / "calls.json")
        assert receipt["status"] == entry["status"] == "completed"
        assert receipt["origin"] == entry["episode_source"] == "training"
        assert receipt["model"]["provider"] == "claude_code" and receipt["model"]["model"] == "opus"
        assert len(calls) == entry["calls"] == receipt["usage"]["requests"]
        assert receipt["usage"]["unmeasured_requests"] == 0
        all_calls.extend(c["call_id"] for c in receipt["usage"]["calls"])
        assert not entry["tool_events"]
        assert not any(a["operator_check_text_present"] for a in entry["input_audit"])
        for name, expected in entry["artifact_sha256"].items():
            assert sha(dest / name) == expected, (group, entry["id"], name)
        for call in calls:
            assert sha(dest / f"call_{call['index']}_response.txt") == call["response_sha256"]
        kinds = [x["kind"] for x in read(dest / "events.json")]
        assert kinds.count("model.usage") == len(calls)
        assert not any("failed" in k or "invalid" in k for k in kinds)
        expected_guide = sha(HERE / ("refined_deep_research.md" if group == "refinement" else "preliminary_guide.md" if group == "preliminary" else "r01_guide.md" if entry["attempt"] == "R01_final" else "deep_research.md"))
        for audit in entry["input_audit"]:
            if audit["guide_sha256"]:
                assert audit["guide_sha256"] == expected_guide, entry["attempt"]
        for framing_file, plan_file in [("framing.json", "research_plan.md"), ("recovered_framing.json", "recovered_plan.md")]:
            if not (dest / framing_file).exists():
                continue
            plan = read(dest / framing_file).get("_research_plan")
            if not plan:
                assert entry["id"] == "N05"
                continue
            assert plan["author"] == "consciousness"
            assert (dest / plan_file).read_text() == plan["body"]
            assert sha(dest / plan_file) == plan["sha256"]
            assert plan["guide_sha256"] == expected_guide
            if original.exists():
                assert sha(Path(plan["path"])) == plan["sha256"]
        if original.exists():
            for call in calls:
                for suffix, key in [("input", "prompt_sha256"), ("system", "system_sha256")]:
                    assert sha(original / f"call_{call['index']}_{suffix}.txt") == call[key]
                snapshot = "refined_consciousness_prompt.md" if group == "refinement" else "consciousness_prompt.md"
                assert (HERE / snapshot).read_text().strip() in (original / f"call_{call['index']}_system.txt").read_text()
            local_checked.append(entry["attempt"])

assert len(all_calls) == len(set(all_calls)) == evidence["total_usage"]["requests"]
prior = read(HERE / "results/N03/framing.json")["_research_plan"]
for folder, cid in [("results", "N04"), ("results", "N06"), ("refinement", "N04")]:
    assert read(HERE / folder / cid / "framing.json")["_research_plan"]["previous_path"] == prior["path"]
initial = read(HERE / "results/R03/framing.json")["_research_plan"]
assert read(HERE / "recovery_relinked/R03/framing.json")["_research_plan"] == initial
assert read(HERE / "results/R03/recovered_framing.json")["_research_plan"]["previous_path"] is None
assert read(HERE / "recovery_relinked/R03/recovered_framing.json")["_research_plan"]["previous_path"] == initial["path"]

quote_count = 0
for phase, folder, cases_file in [("phase1", "results", "cases.json"), ("refinement", "refinement", "refinement_cases.json")]:
    cases = {c["id"]: c for c in read(HERE / cases_file)}
    assert {r["id"] for r in review[phase]} == set(cases)
    for row in review[phase]:
        assert len(row["checks"]) == len(cases[row["id"]]["checks"])
        for quote in row["quotes"]:
            path = HERE / folder / row["id"] / quote["file"]
            source = read(path)[quote["field"]] if quote.get("field") else path.read_text()
            if not isinstance(source, str):
                source = json.dumps(source, ensure_ascii=False)
            assert quote["text"] in source, (phase, row["id"], quote["text"])
            quote_count += 1

keys = ["requests", "measured_requests", "unmeasured_requests", "input", "output", "cache_read", "cache_create", "reasoning"]
assert evidence["total_usage"] == {k: sum(e["usage"][k] for g in groups for e in evidence[g]) for k in keys}
counter = read(HERE / "counterexamples.json")
for case in counter["N01"]:
    assert sum(case["current"]) / sum(case["previous"]) == 0.6
assert counter["N01"][0]["previous"][:8] == counter["N01"][0]["current"][:8]
assert sum(counter["N01"][1]["current"][:8]) < sum(counter["N01"][1]["previous"][:8])
for key in ["baseline", "fewer_visits", "lower_conversion"]:
    row = counter["R01_proxy"][key]
    assert row["visits"] * row["conversion"] == row["transactions"]
    assert row["transactions"] * row["spend_per_transaction"] == row["sales"]
if LIVE:
    assert len(local_checked) == 18
    for path, expected in evidence["source_sha256_final"].items():
        assert sha(ROOT / path) == expected
    db = sqlite3.connect(f"file:{ROOT}/data/world_pulse.db?mode=ro", uri=True)
    for group in groups:
        for entry in evidence[group]:
            assert db.execute("select source from episode_log where id=?", (entry["episode_id"],)).fetchone()[0] == "training"
            count = db.execute("select count(*) from trajectory_event where episode_id=? and kind='model.usage'", (entry["episode_id"],)).fetchone()[0]
            assert count == entry["calls"]
print(json.dumps({"status": "passed", "attempts": 18, "model_calls": len(all_calls), "quotes": quote_count, "local_attempts_checked": len(local_checked), "semantic_review": "manual_not_automated"}, ensure_ascii=False))
