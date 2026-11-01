"""첫 증거를 보존하고 복원 재연결·보완 재시험을 추가한다. 모델 호출 없음."""
import hashlib
import json
import shutil
import sqlite3
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUTPUT = ROOT / "outputs/long_sentence_imagination/2026-11-01_108회차"


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


evidence = read(HERE / "evidence.json")
cases = {c["id"]: c for c in read(HERE / "cases.json")}
refined = read(HERE / "refinement_cases.json")
cases.update({c["id"]: c for c in refined})
db = sqlite3.connect(f"file:{ROOT}/data/world_pulse.db?mode=ro", uri=True)
keep = {
    "request.received", "research.guide_supplied", "research.plan_saved",
    "research.plan_failed", "framing.revised", "model.usage",
    "consciousness.contract_invalid", "consciousness.contract_corrected",
    "consciousness.contract_failed",
}
for group, specs in [
    ("recovery_relinked", [("R03", "R03_relinked")]),
    ("refinement", [(c["id"], c["id"] + "_refined") for c in refined]),
]:
    evidence[group] = []
    for cid, attempt in specs:
        source = OUTPUT / attempt
        receipt = read(source / "receipt.json")
        assert receipt["status"] == "completed", attempt
        dest = HERE / group / cid
        dest.mkdir(parents=True, exist_ok=True)
        names = [
            "receipt.json", "framing.json", "research_plan.md", "calls.json",
            "recovery_input.json", "recovery_response.json", "recovered_framing.json",
            "recovered_plan.md",
        ]
        for name in names:
            if (source / name).exists():
                shutil.copyfile(source / name, dest / name)
        for path in source.glob("call_*_response.txt"):
            shutil.copyfile(path, dest / path.name)
        events = [
            {"timestamp": ts, "kind": kind, "data": json.loads(data)}
            for ts, kind, data in db.execute(
                "select ts,kind,data from trajectory_event where episode_id=? order by event_seq",
                (receipt["episode_id"],),
            ) if kind in keep
        ]
        (dest / "events.json").write_text(json.dumps(events, ensure_ascii=False, indent=2) + "\n")
        audits = []
        for path in sorted(source.glob("call_*_input.txt")):
            text = path.read_text()
            marker = "<research_planning_guide>\n"
            guide = text.split(marker, 1)[1].split("\n</research_planning_guide>", 1)[0] if marker in text else None
            audits.append({
                "file": path.name, "sha256": sha(path),
                "guide_sha256": hashlib.sha256(guide.encode()).hexdigest() if guide else None,
                "operator_check_text_present": any(x in text for x in cases[cid]["checks"]),
            })
        raw = [json.loads(line) for line in (source / "supervision/events.jsonl").read_text().splitlines()]
        evidence[group].append({
            "id": cid, "attempt": attempt, "episode_id": receipt["episode_id"],
            "episode_source": db.execute("select source from episode_log where id=?", (receipt["episode_id"],)).fetchone()[0],
            "status": receipt["status"], "initial_calls": receipt["initial_calls"],
            "calls": receipt["calls"], "seconds": receipt["seconds"], "model": receipt["model"],
            "usage": {k: v for k, v in receipt["usage"].items() if k != "calls"},
            "input_audit": audits,
            "tool_events": [x for x in raw if x["kind"] in ["model.native_tool", "tool.started", "tool.finished"]],
            "artifact_sha256": {p.name: sha(p) for p in dest.iterdir() if p.is_file()},
        })
keys = ["requests", "measured_requests", "unmeasured_requests", "input", "output", "cache_read", "cache_create", "reasoning"]
groups = ["cases", "preliminary", "recovery_relinked", "refinement"]
evidence.setdefault("phase1_total_usage", evidence["total_usage"])
evidence["phase1_usage"] = evidence["final_usage"]
evidence["refinement_usage"] = {k: sum(c["usage"][k] for c in evidence["refinement"]) for k in keys}
evidence["total_usage"] = {k: sum(c["usage"][k] for g in groups for c in evidence[g]) for k in keys}
evidence["source_sha256_final"] = {f: sha(ROOT / f) for f in evidence["start"]["after_sha256"]}
evidence["refinement_cases_sha256"] = sha(HERE / "refinement_cases.json")
evidence["refinement_applied"] = read(HERE / "refinement.json")
(HERE / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"entries": sum(len(evidence[g]) for g in groups), "usage": evidence["total_usage"]}, ensure_ascii=False))
