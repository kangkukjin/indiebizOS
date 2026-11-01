"""모델 재호출 없이 완료한 출력·이벤트·입력 지문과 실제/비교 경로 비용을 보존한다."""
import hashlib
import json
import shutil
import sqlite3
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUTPUT = ROOT / "outputs/long_sentence_imagination/2026-11-01_109회차"


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


cases = read(HERE / "cases.json")
db = sqlite3.connect(f"file:{ROOT}/data/world_pulse.db?mode=ro", uri=True)
evidence = {"start": read(HERE / "start.json"), "attempts": [], "paths": {}}
keys = ["requests", "measured_requests", "unmeasured_requests", "input", "output", "cache_read", "cache_create", "reasoning"]
records = {}
for case in cases:
    cid = case["id"]
    for arm in ["S", "A", "B", "C"] + (["C_recovered"] if (OUTPUT / f"{cid}_C_recovered").exists() else []):
        source = OUTPUT / f"{cid}_{arm}"
        receipt = read(source / "receipt.json")
        assert receipt["status"] != "running", source
        records[(cid, arm)] = receipt
        dest = HERE / "results" / f"{cid}_{arm}"
        dest.mkdir(parents=True, exist_ok=True)
        for name in ["receipt.json", "calls.json", "framing.json", "research_plan.md", "review.json", "review_input.json", "reused_review.json"]:
            if (source / name).exists():
                shutil.copyfile(source / name, dest / name)
        for path in source.glob("call_*_response.txt"):
            shutil.copyfile(path, dest / path.name)
        kinds = {"research.guide_supplied", "research.plan_saved", "research.plan_failed", "model.usage", "consciousness.contract_invalid", "consciousness.contract_failed"}
        events = [{"timestamp": ts, "kind": kind, "data": json.loads(data)} for ts, kind, data in db.execute(
            "select ts,kind,data from trajectory_event where episode_id=? order by event_seq", (receipt["episode_id"],)) if kind in kinds]
        (dest / "events.json").write_text(json.dumps(events, ensure_ascii=False, indent=2) + "\n")
        raw = [json.loads(line) for line in (source / "supervision/events.jsonl").read_text().splitlines()]
        inputs = []
        for path in sorted(source.glob("call_*_input.txt")):
            text = path.read_text()
            inputs.append({"file": path.name, "sha256": sha(path), "checks_leaked": any(x in text for x in case["checks"])})
        evidence["attempts"].append({"case": cid, "arm": arm, "status": receipt["status"], "episode_id": receipt["episode_id"],
            "episode_source": db.execute("select source from episode_log where id=?", (receipt["episode_id"],)).fetchone()[0],
            "inputs": inputs, "tool_events": [x for x in raw if x["kind"] in {"model.native_tool", "tool.started", "tool.finished"}],
            "artifacts": {p.name: sha(p) for p in dest.iterdir() if p.is_file()}})
for arm, components in [("A", ["S", "A"]), ("B", ["S", "B"]), ("C", ["S", "B", "C"])]:
    rows = []
    for case in cases:
        parts = [records[(case["id"], c)] for c in components]
        if arm == "C" and (case["id"], "C_recovered") in records:
            parts.append(records[(case["id"], "C_recovered")])
        usage = {k: sum(p["usage"][k] for p in parts) for k in keys}
        rows.append({"case": case["id"], "seconds": sum(p["seconds"] for p in parts), "usage": usage})
    evidence["paths"][arm] = {"cases": rows, "usage": {k: sum(r["usage"][k] for r in rows) for k in keys},
                              "median_seconds": statistics.median(r["seconds"] for r in rows)}
evidence["physical_usage"] = {k: sum(r["usage"][k] for r in records.values()) for k in keys}
evidence["time_note"] = "비교 경로 시간은 공통 S와 해당 단계의 실제 구간 합이다. A/B 사이 대기·훈련자 검토를 제외하며 운영 사용자 지연의 직접 측정이 아니다. 병렬 전체 경과와 구별한다."
evidence["physical_started"] = min(r["started"] for r in records.values())
evidence["physical_ended"] = max(r["ended"] for r in records.values())
evidence["live_source_sha256_after_experiment"] = {p: sha(ROOT / p) for p in evidence["start"]["source_sha256"]}
(HERE / "evidence.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n")
print(json.dumps({"attempts": len(records), "physical_usage": evidence["physical_usage"], "paths": {a: {"input_output": v["usage"]["input"] + v["usage"]["output"], "median_seconds": v["median_seconds"]} for a, v in evidence["paths"].items()}}, ensure_ascii=False))
