"""Independent, read-only comparison of saved reports and execution journals."""
from collections import Counter
from datetime import datetime
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[4]
DOC = Path(__file__).resolve().parent
OUT = ROOT / "outputs/long_sentence_imagination/2026-10-20_86회차"
ACTIONS = ["status", "presence", "display", "power", "apps", "network"]


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def top_scalar(value, key):
    """Inspect only scalar record fields; never flatten Unit into null."""
    if value[0] != "record":
        return None
    field = dict(value[1]).get(key)
    return field[1] if field and field[0] == "scalar" else None


def journal(response):
    run_id = response["resume"]["run_id"]
    paths = list((ROOT / "data/ibl_runs").rglob(run_id + ".sqlite"))
    assert len(paths) == 1
    with sqlite3.connect(f"file:{paths[0]}?mode=ro", uri=True) as db:
        db.row_factory = sqlite3.Row
        life = dict(db.execute("select * from lifecycle").fetchone())
        rows = list(db.execute("select receipt,call_info,state_change from calls"))
    assert life["ended"] is not None
    calls, natives, errors, changes = Counter(), [], [], Counter()
    for row in rows:
        receipt, info = json.loads(row["receipt"]), json.loads(row["call_info"])
        action = info["action"]
        calls[action] += 1
        if row["state_change"]:
            changes[action] += 1
        if "error" in receipt:
            errors.append(receipt["error"]["code"])
        elif action == "self:script":
            value = receipt["value"]
            if top_scalar(value, "protocol") == "pc-control/1":
                natives.append(top_scalar(value, "action"))
    return {"status": life["status"], "ended": life["ended"],
            "calls": dict(calls), "native_pc_actions": natives,
            "write_actions": dict(changes), "errors": errors}


def main():
    base = read(OUT / "trainer/base_v0.json")
    variant = read(OUT / "trainer/variation_v0.json")
    boundary = read(OUT / "trainer/boundaries_v1.json")
    assert base["pc"]["ordered"] and base["pc"]["actual_count"] == 6
    assert base["pc"]["verified_count"] == 6 and base["pc"]["all_verified"]
    assert [r["action"] for r in base["pc"]["items"]] == ACTIONS
    for row in base["pc"]["items"]:
        raw = row["raw"]
        assert row["verified"] and raw["verified"] and raw["status"] == "completed"
        assert raw["target"] == "__local__"
        assert raw["result"]["action"] == row["action"]
        assert raw["result"]["condition"] == {"needs_front": False, "shared_state": False}
    assert variant["pc"]["ordered"] and variant["pc"]["actual_count"] == 6
    assert variant["pc"]["verified_count"] == 0
    for row in variant["pc"]["items"]:
        raw = row["raw"]
        assert not row["verified"] and not raw["verified"]
        assert raw["status"] == "failed" and raw["result"] is None
        assert raw["target"] == "L86_missing_pc_20261020"
        assert raw["failure"]["stage"] == "target" and raw["task_ref"] is None
    for report in [base, variant]:
        safari = report["safari"]
        assert not safari["verified"] and not safari["target_checked"]
        assert safari["same_revision"] is None and safari["page_loaded"] is None
        failure = safari["error"]["details"]["failure"]
        assert failure["code"] == "OBSERVATION_FAILED"
        assert failure["stage"] == "observation" and not failure["state_change_possible"]
        assert not report["all_reads_verified"] and not report["mutations_executed"]
        assert report["physical_audio"] == "미검증" and report["user_presence"] == "미확정"
    assert variant["safari"]["requested_window"] == 2147483646
    for key in ["empty", "invalid"]:
        assert not boundary[key]["all_verified"] and boundary[key]["items"] == []
        assert boundary[key]["error"]["code"] == "ASSERTION_FAILED"
    assert boundary["invalid"]["error"]["has_partial"]
    assert boundary["invalid"]["error"]["partial_preserved"] is False
    assert boundary["invalid"]["error"]["details"]["coverage"] == ["ok", "failed"]
    assert boundary["lost"]["status"] == "unknown" and not boundary["lost"]["verified"]
    assert boundary["lost"]["failure"]["stage"] == "verification"
    assert boundary["prior_summary"] == {
        "pc_verified": 6, "safari_verified": False, "all_reads_verified": False}
    preservation = read(OUT / "base_preservation.json")
    assert sha(OUT / "trainer/base_v0.json") == preservation["before"]

    summary = {}
    for label in ["base_v0", "variation_v0", "boundaries_v0", "boundaries_v1",
                  "minimal_v0", "minimal_v1"]:
        saved = read(OUT / "runs" / f"{label}.json")
        response = saved["response"]
        assert saved["request"]["origin"] == "training"
        evidence = journal(response)
        assert not any(action.startswith(("engines:", "others:"))
                       or action in {"table:ai", "table:brief", "table:judge"}
                       for action in evidence["calls"])
        assert not any(action != "self:write" for action in evidence["write_actions"])
        if label in {"base_v0", "variation_v0", "boundaries_v1"}:
            assert response["success"] and response["run_status"] == "completed"
            assert response["value"]["reread_equal"]
            assert evidence["write_actions"] == {"self:write": 1}
        if label == "base_v0":
            assert evidence["native_pc_actions"] == ACTIONS
            assert evidence["calls"].get("self:limb", 0) == 0
        elif label == "variation_v0":
            assert evidence["native_pc_actions"] == []
            assert evidence["calls"]["self:limb"] == 1
        elif label.startswith("boundaries"):
            assert evidence["native_pc_actions"] == []
            assert evidence["calls"].get("self:limb", 0) == 0
            assert evidence["calls"].get("limbs:guestpc", 0) == 0
            assert evidence["calls"].get("self:task", 0) == 0
        if label in {"boundaries_v0", "minimal_v1"}:
            assert not response["success"]
            assert response["diagnostic"]["code"] == "NON_JSON_RESULT"
            assert "Unit" in response["error"]
        if label == "boundaries_v1":
            assert response["reuse"]["reused_calls"] == 1
        summary[label] = {
            "run_id": response["resume"]["run_id"], "http_seconds": saved["seconds"],
            "engine_ms": response["usage"]["elapsed_ms"],
            "source_complete": response["source_complete"],
            "source_sha256": hashlib.sha256(saved["request"]["code"].encode()).hexdigest(),
            "reuse_count": response.get("reuse", {}).get("reused_calls", 0),
            **evidence,
        }
    tests = {}
    for filename in ["driver_tests.xml", "runtime_tests_final.xml"]:
        suite = ET.parse(OUT / filename).getroot().find("testsuite")
        assert suite is not None
        attrs = dict(suite.attrib)
        assert attrs["failures"] == "0" and attrs["errors"] == "0"
        tests[filename] = {k: attrs[k] for k in ["tests", "failures", "errors", "skipped", "time"]}
    start = read(OUT / "start.json")
    changed = [path for path, expected in start["files"].items() if sha(ROOT / path) != expected]
    result = {
        "verified_at": datetime.now().astimezone().isoformat(),
        "head_start": start["head"],
        "head_end": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "tracked_driver_source_changes_during_round": changed,
        "base_sha256_preserved": preservation["before"],
        "runs": summary, "tests": tests,
        "program_model_calls": 0, "author_tokens": "미측정",
        "all_assertions_passed": True,
    }
    path = DOC / "evidence.json"
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"all_assertions_passed": True, "tests": tests,
                      "driver_source_changes": changed}, ensure_ascii=False))


if __name__ == "__main__":
    main()
