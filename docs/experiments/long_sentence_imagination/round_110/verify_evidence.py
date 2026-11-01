"""모델 재호출 없이 판본·인용·5개 점검·경로 비용을 대조한다. 의미 판정은 수동이다."""
import hashlib
import json
import sqlite3
import statistics
import sys
from pathlib import Path

from five_principle_gate import PRINCIPLES, digest, parse_json, releasable, validate_checks

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUTPUT = ROOT / "outputs/long_sentence_imagination/2026-11-01_110회차"
LIVE = "--live" in sys.argv


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


meta = read(HERE / "start.json")
evidence = read(HERE / "evidence.json")
review = read(HERE / "review.json")
cases = read(HERE / "cases.json")
assert evidence["start"] == meta
assert sha(HERE / "cases.json") == meta["cases_sha256"]
assert sha(HERE / "prior_framing.json") == meta["prior_sha256"]
assert sha(HERE / "five_principle_gate.py") == meta["candidate_sha256"]
for name, expected in meta["frozen_files"].items():
    assert sha(HERE / name) == expected, name
assert evidence["live_source_sha256_after_experiment"] == meta["source_sha256"]
assert len(evidence["attempts"]) == 12
assert {(x["case"], x["arm"]) for x in evidence["attempts"]} == {
    (c["id"], arm) for c in cases for arm in ["S", "A", "R"]}
assert len(review["rows"]) == 8
assert {(x["case"], x["arm"]) for x in review["rows"]} == {
    (c["id"], arm) for c in cases for arm in ["A", "R"]}
ids, receipts = [], {}
local_count = 0
for entry in evidence["attempts"]:
    name = entry["case"] + "_" + entry["arm"]
    dest = HERE / "results" / name
    source = OUTPUT / name
    receipt = read(dest / "receipt.json")
    receipts[(entry["case"], entry["arm"])] = receipt
    calls = read(dest / "calls.json")
    assert receipt["status"] == "completed", name
    assert receipt["origin"] == entry["episode_source"] == "training"
    assert receipt["runner_sha256"] == sha(HERE / "run_experiment.py")
    assert receipt["model"]["provider"] == "claude_code"
    assert receipt["model"]["model"] == "opus"
    assert len(calls) == receipt["calls"] == receipt["usage"]["requests"]
    assert receipt["usage"]["unmeasured_requests"] == 0
    assert not entry["tool_events"]
    assert not any(a["checks_leaked"] for a in entry["inputs"])
    ids.extend(c["call_id"] for c in receipt["usage"]["calls"])
    for filename, expected in entry["artifacts"].items():
        assert sha(dest / filename) == expected, (name, filename)
    for call in calls:
        assert sha(dest / f"call_{call['index']}_response.txt") == call["response_sha256"]
        if source.exists():
            for suffix in ["input", "system"]:
                assert sha(source / f"call_{call['index']}_{suffix}.txt") == call[suffix + "_sha256"]
    events = read(dest / "events.json")
    assert sum(x["kind"] == "model.usage" for x in events) == len(calls)
    if source.exists():
        local_count += 1
    frame = read(dest / "framing.json")
    if receipt["has_plan"]:
        plan = frame["_research_plan"]
        assert plan["author"] == "consciousness"
        assert plan["body"] == (dest / "research_plan.md").read_text()
        assert plan["sha256"] == sha(dest / "research_plan.md")
        assert plan["guide_sha256"] == sha(HERE / "deep_research.md")
        if source.exists():
            assert sha(Path(plan["path"])) == plan["sha256"]
    else:
        assert "_research_plan" not in frame
        assert not (dest / "research_plan.md").exists()

assert len(ids) == len(set(ids)) == evidence["physical_usage"]["requests"]
audit_count = 0
for case in cases:
    cid = case["id"]
    directory = HERE / "results" / (cid + "_R")
    initial = read(directory / "initial_candidate.json")
    base = read(HERE / "results" / (cid + "_A") / "framing.json")
    expected = {k: v for k, v in base.items() if not k.startswith("_")}
    expected["research_plan"] = base["_research_plan"]["body"].split("\n", 1)[1].rstrip()
    assert initial == expected, (cid, "R must start from exact A")
    outcome = read(directory / "gate_outcome.json")
    versions = [initial]
    if outcome["revisions"]:
        versions.append(read(directory / "repaired_candidate.json"))
    assert len(outcome["revisions"]) <= 1
    assert len(outcome["audits"]) <= 2
    calls = read(directory / "calls.json")
    audit_calls = [c for c in calls if c["phase"].startswith("five_principles_")]
    assert len(audit_calls) == len(outcome["audits"])
    texts = [case["request"], case.get("prior_request", "")]
    for audit, call in zip(outcome["audits"], audit_calls):
        version = versions[audit["revision"]]
        parsed = parse_json((directory / f"call_{call['index']}_response.txt").read_text())
        assert audit["checks"] == validate_checks(parsed, version, texts)
        assert audit["candidate_sha256"] == digest(version)
        audit_count += 1
    if outcome["revisions"]:
        assert outcome["revisions"][0] == {
            "from_sha256": digest(versions[0]), "to_sha256": digest(versions[1])}
        assert not releasable(versions[0], outcome["audits"][0])
    assert outcome["candidate"] == versions[-1]
    assert (directory / "candidate_plan.md").read_text().rstrip() == versions[-1]["research_plan"]
    frame = read(directory / "framing.json")
    assert outcome["release_allowed"] == releasable(versions[-1], outcome["audits"][-1])
    assert receipts[(cid, "R")]["has_plan"] == outcome["release_allowed"]
    if outcome["release_allowed"]:
        assert frame["_research_plan"]["body"].split("\n", 1)[1].rstrip() == versions[-1]["research_plan"]
        assert frame["_research_plan"]["previous_path"] == base["_research_plan"]["path"]
    if case.get("prior_request"):
        original = read(HERE / "prior_framing.json")["_research_plan"]["sha256"]
        for arm in ["S", "A"]:
            source = OUTPUT / (cid + "_" + arm)
            if source.exists():
                assert sha(source / "outputs/research_plans/prior/research_plan.md") == original

quote_count = 0
for row in review["rows"]:
    assert len(row["checks"]) == 4
    assert tuple(row["principles"]) == PRINCIPLES
    path = HERE / "results" / (row["case"] + "_" + row["arm"])
    for q in row["quotes"]:
        source = (path / q["file"]).read_text()
        if q.get("field"):
            source = read(path / q["file"])[q["field"]]
            if not isinstance(source, str):
                source = json.dumps(source, ensure_ascii=False)
        assert q["text"] in source, (row["case"], row["arm"], q["text"])
        quote_count += 1
    for defect in row["defects"]:
        assert any(q["text"] == defect["quote"] for q in row["quotes"])

keys = list(evidence["physical_usage"])
assert evidence["physical_usage"] == {k: sum(r["usage"][k] for r in receipts.values()) for k in keys}
for arm, components in [("A", ["S", "A"]), ("R", ["S", "A", "R"])]:
    path = evidence["paths"][arm]
    for row in path["cases"]:
        parts = [receipts[(row["case"], a)] for a in components]
        assert row["usage"] == {k: sum(r["usage"][k] for r in parts) for k in keys}
        assert row["seconds"] == sum(r["seconds"] for r in parts)
        assert row["wall_seconds"] == parts[-1]["ended"] - parts[0]["started"]
    assert path["median_seconds"] == statistics.median(r["seconds"] for r in path["cases"])
    assert path["median_wall_seconds"] == statistics.median(r["wall_seconds"] for r in path["cases"])
    assert path["usage"] == {k: sum(r["usage"][k] for r in path["cases"]) for k in keys}
assert evidence["physical_started"] == min(r["started"] for r in receipts.values())
assert evidence["physical_ended"] == max(r["ended"] for r in receipts.values())
if LIVE:
    assert {p: sha(ROOT / p) for p in meta["source_sha256"]} == meta["source_sha256"]
    assert local_count == 12
    db = sqlite3.connect(f"file:{ROOT}/data/world_pulse.db?mode=ro", uri=True)
    for entry in evidence["attempts"]:
        assert db.execute("select source from episode_log where id=?", (entry["episode_id"],)).fetchone()[0] == "training"
print(json.dumps({"status": "passed", "attempts": 12, "calls": len(ids), "manual_quotes": quote_count,
                  "five_principle_audits": audit_count, "exact_A_inputs": len(cases),
                  "semantic_grading": "manual_not_automated", "live_checked": LIVE}, ensure_ascii=False))
