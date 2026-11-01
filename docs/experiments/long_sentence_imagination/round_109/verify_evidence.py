"""출력·입력 차이·판정 인용·호출·비용을 검증. 의미 판정은 review.json의 수동 감사다."""
import hashlib
import json
import sqlite3
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUTPUT = ROOT / "outputs/long_sentence_imagination/2026-11-01_109회차"
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
assert sha(HERE / "candidate_research_planning.py") == meta["candidate_sha256"]
assert sha(HERE / "prior_framing.json") == meta["prior_sha256"]
for name, expected in meta["frozen_files"].items():
    assert sha(HERE / name) == expected
assert evidence["live_source_sha256_after_experiment"] == meta["source_sha256"]
assert len(evidence["attempts"]) == 26
assert len(review["rows"]) == 18
assert len({(r["case"], r["arm"]) for r in review["rows"]}) == 18
ids = []
local_count = 0
for entry in evidence["attempts"]:
    name = entry["case"] + "_" + entry["arm"]
    dest = HERE / "results" / name
    source = OUTPUT / name
    receipt = read(dest / "receipt.json")
    calls = read(dest / "calls.json")
    assert receipt["status"] == "completed" or (name in {"D1_C", "D2_C"} and receipt["status"] == "failed"), name
    assert receipt["origin"] == entry["episode_source"] == "training"
    assert receipt["runner_sha256"] in {sha(HERE / "run_experiment.py"), sha(HERE / "run_experiment_v0.py")}
    assert receipt["model"]["provider"] == "claude_code" and receipt["model"]["model"] == "opus"
    assert len(calls) == receipt.get("calls", len(calls)) == receipt["usage"]["requests"]
    assert receipt["usage"]["unmeasured_requests"] == 0
    assert not entry["tool_events"]
    assert not any(a["checks_leaked"] for a in entry["inputs"])
    ids.extend(c["call_id"] for c in receipt["usage"]["calls"])
    for filename, expected in entry["artifacts"].items():
        assert sha(dest / filename) == expected
    for call in calls:
        assert sha(dest / f"call_{call['index']}_response.txt") == call["response_sha256"]
        if source.exists():
            for suffix in ["input", "system"]:
                assert sha(source / f"call_{call['index']}_{suffix}.txt") == call[suffix + "_sha256"]
    events = read(dest / "events.json")
    assert sum(x["kind"] == "model.usage" for x in events) == len(calls)
    if source.exists():
        local_count += 1
    if receipt["status"] == "failed":
        assert "AssertionError" in receipt["traceback"] and len(calls) == 1
        continue
    frame = read(dest / "framing.json")
    if entry["arm"] == "S":
        assert "_research_plan" not in frame
    else:
        plan = frame["_research_plan"]
        assert plan["author"] == "consciousness"
        assert plan["body"] == (dest / "research_plan.md").read_text()
        assert plan["sha256"] == sha(dest / "research_plan.md")
        assert plan["guide_sha256"] == sha(HERE / "deep_research.md")
        if source.exists():
            assert sha(Path(plan["path"])) == plan["sha256"]
    if entry["arm"].startswith("C"):
        payload = read(dest / "review_input.json")
        base = read(HERE / "results" / (entry["case"] + "_B") / "framing.json")
        expected = {k: v for k, v in base.items() if k != "_research_plan"}
        expected["research_plan"] = base["_research_plan"]["body"]
        assert payload["candidate"] == expected
        issues = read(dest / "review.json")["issues"]
        review_call_count = len(calls)
        if entry["arm"] == "C_recovered":
            reuse = read(dest / "reused_review.json")
            assert reuse["response_sha256"] == sha(HERE / "results" / (entry["case"] + "_C") / "call_0_response.txt")
            review_call_count += 1
        if not issues:
            assert frame == base and review_call_count == 1
        else:
            assert review_call_count == 2
            assert frame["_research_plan"]["previous_path"] == base["_research_plan"]["path"]

assert len(ids) == len(set(ids)) == evidence["physical_usage"]["requests"]
for case in cases:
    left = OUTPUT / (case["id"] + "_A")
    right = OUTPUT / (case["id"] + "_B")
    if left.exists() and right.exists():
        a = (left / "call_0_input.txt").read_text().replace(str(left), "@workspace@")
        b = (right / "call_0_input.txt").read_text().replace(str(right), "@workspace@")
        b = b.replace((HERE / "planning_check.txt").read_text(), "", 1)
        b = b.replace("미검증 AI 판단과 이전 계획 후보(사용자 원문이 우선, 기존 해석·예시도 대조):", "이전 판단과 계획 후보(현재 사용자 요청이 우선):")
        assert a == b, (case["id"], "uncontrolled planning input difference")
        assert (left / "call_0_system.txt").read_bytes() == (right / "call_0_system.txt").read_bytes()
        if case.get("prior_request"):
            original = read(HERE / "prior_framing.json")["_research_plan"]["sha256"]
            for directory in [left, right, OUTPUT / (case["id"] + "_S")]:
                assert sha(directory / "outputs/research_plans/prior/research_plan.md") == original
quote_count = 0
for row in review["rows"]:
    assert len(row["checks"]) == 4
    path = HERE / "results" / (row["case"] + "_" + row["arm"])
    if row["arm"] == "C" and (HERE / "results" / (row["case"] + "_C_recovered")).exists():
        path = HERE / "results" / (row["case"] + "_C_recovered")
    for q in row["quotes"]:
        source = (path / q["file"]).read_text()
        if q.get("field"):
            source = read(path / q["file"])[q["field"]]
            if not isinstance(source, str):
                source = json.dumps(source, ensure_ascii=False)
        assert q["text"] in source, (row["case"], row["arm"], q["text"])
        quote_count += 1
audit_pairs = {(r["case"], r["issue"]) for r in review["reviewer_audit"]}
expected_pairs = set()
for case in cases:
    directory = HERE / "results" / (case["id"] + "_C")
    if (HERE / "results" / (case["id"] + "_C_recovered")).exists():
        directory = HERE / "results" / (case["id"] + "_C_recovered")
    issues = read(directory / "review.json")["issues"]
    payload = read(directory / "review_input.json")["candidate"]
    text = json.dumps(payload, ensure_ascii=False) + payload["research_plan"]
    for i, issue in enumerate(issues):
        assert issue["quote"] in text
        expected_pairs.add((case["id"], i))
assert audit_pairs == expected_pairs and len(audit_pairs) == len(review["reviewer_audit"])
keys = list(evidence["physical_usage"])
receipts = {(e["case"], e["arm"]): read(HERE / "results" / (e["case"] + "_" + e["arm"]) / "receipt.json") for e in evidence["attempts"]}
assert evidence["physical_usage"] == {k: sum(r["usage"][k] for r in receipts.values()) for k in keys}
for arm, components in [("A", ["S", "A"]), ("B", ["S", "B"]), ("C", ["S", "B", "C"])]:
    path = evidence["paths"][arm]
    for row in path["cases"]:
        cid = row["case"]
        parts = [receipts[(cid, a)] for a in components]
        if arm == "C" and (cid, "C_recovered") in receipts:
            parts.append(receipts[(cid, "C_recovered")])
        assert row["usage"] == {k: sum(r["usage"][k] for r in parts) for k in keys}
        assert row["seconds"] == sum(r["seconds"] for r in parts)
    assert path["median_seconds"] == statistics.median(r["seconds"] for r in path["cases"])
    assert path["usage"] == {k: sum(r["usage"][k] for r in path["cases"]) for k in keys}
if LIVE:
    assert {p: sha(ROOT / p) for p in meta["source_sha256"]} == meta["source_sha256"]
    assert local_count == 26
    db = sqlite3.connect(f"file:{ROOT}/data/world_pulse.db?mode=ro", uri=True)
    for entry in evidence["attempts"]:
        assert db.execute("select source from episode_log where id=?", (entry["episode_id"],)).fetchone()[0] == "training"
print(json.dumps({"status": "passed", "attempts": 26, "calls": len(ids), "quotes": quote_count,
                  "paired_inputs_differ_only_by_candidate_and_workspace": local_count == 26,
                  "semantic_grading": "manual_not_automated"}, ensure_ascii=False))
