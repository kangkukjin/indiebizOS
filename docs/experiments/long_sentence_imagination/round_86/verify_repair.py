"""Read-only scenario checks; emit sanitized evidence without replacing the baseline."""
import json
import subprocess
import xml.etree.ElementTree as ET

from verify import ACTIONS, DOC, OUT, ROOT, journal, read, sha


def main():
    post = OUT / "post_repair"
    labels = [
        "repair_base", "repair_variation", "repair_boundary_v0",
        "repair_boundary_v1", "repair_boundary_reverse", "repair_minimal_ready",
        "repair_guide", "repair_guide_variation",
    ]
    runs = {}
    for label in labels:
        saved = read(OUT / "runs" / f"{label}.json")
        response = saved["response"]
        receipt = journal(response)
        assert saved["request"]["origin"] == "training"
        assert all(action in {"self:script", "self:limb", "self:read", "self:write"}
                   for action in receipt["calls"])
        assert set(receipt["write_actions"]) <= {"self:write"}
        runs[label] = {
            "run_id": response["resume"]["run_id"],
            "seconds": saved["seconds"], "success": response["success"],
            "source_complete": response["source_complete"], **receipt,
        }
        if label in {"repair_boundary_v0", "repair_minimal_ready"}:
            diagnostic = response["diagnostic"]
            assert not response["success"] and receipt["status"] == "interrupted"
            assert diagnostic["code"] == "NON_JSON_RESULT"
            assert diagnostic["details"]["reason"] == "unsupported_type"
            assert diagnostic["details"]["value_type"] == "Unit"
            assert "round(" not in diagnostic["hint"] and "value_wire" in diagnostic["hint"]
            runs[label]["diagnostic_details"] = diagnostic["details"]
        else:
            assert response["success"] and receipt["status"] == "completed"
        if label == "repair_base":
            assert receipt["native_pc_actions"] == ACTIONS
            assert response["value"]["reread_equal"]
        elif label == "repair_variation":
            assert receipt["native_pc_actions"] == []
            assert receipt["calls"]["self:limb"] == 1
            assert response["value"]["reread_equal"]
        elif label == "repair_boundary_v1":
            assert response["reuse"]["reused_calls"] == 1
            runs[label]["reused_calls"] = 1
        if label.startswith("repair_boundary"):
            assert receipt["native_pc_actions"] == []
        if label in {"repair_guide", "repair_guide_variation"}:
            count = 1 if label == "repair_guide" else 2
            value = response["value"]
            report = json.loads(value["report_json"])
            original = value["original_error"]
            assert report["code"] == original["code"] == "ASSERTION_FAILED"
            assert report["has_partial"] and not report["partial_preserved"]
            assert report["evidence"] == original["evidence"]
            fields = dict(response["value_wire"]["data"][1])
            assert dict(fields["original_error"][1])["partial"] == ["list", [["unit"]] * count]
            assert receipt["calls"] == {} and not response["source_complete"]
            runs[label]["preserved_units"] = count

    base = read(post / "trainer/base_v0.json")
    assert base["pc"]["verified_count"] == 6 and base["pc"]["all_verified"]
    assert base["safari"]["verified"] and base["safari"]["raw"]["window_count"] == 0
    assert base["all_reads_verified"] and not base["mutations_executed"]
    assert base["safari"]["page_loaded"] is None and not base["safari"]["target_checked"]
    variant = read(post / "trainer/variation_v0.json")
    assert not variant["all_reads_verified"] and variant["pc"]["verified_count"] == 0
    assert variant["pc"]["actual_count"] == 6
    assert all(row["raw"]["failure"]["stage"] == "target" for row in variant["pc"]["items"])
    assert variant["safari"]["error"]["details"]["error_code"] == "TARGET_MISSING"
    for name, coverage in [("boundaries_v1", ["ok", "failed"]),
                           ("boundaries_reverse", ["failed", "pending"])]:
        report = read(post / "trainer" / f"{name}.json")
        assert not report["empty"]["all_verified"] and not report["invalid"]["all_verified"]
        assert report["invalid"]["error"]["details"]["coverage"] == coverage
        assert report["invalid"]["error"]["partial_preserved"] is False
        assert report["lost"]["status"] == "unknown" and not report["lost"]["verified"]
        assert report["prior_summary"]["pc_verified"] == 6
    preservation = read(OUT / "base_preservation.json")
    assert sha(OUT / "trainer/base_v0.json") == preservation["before"]
    baseline_files = ["evidence.json", "base_v0.ibl", "boundaries_v0.ibl",
                      "boundaries_v1.ibl", "unit_error_minimal_v0.ibl",
                      "unit_error_minimal_v1.ibl"]
    for name in baseline_files:
        path = DOC / name
        original = subprocess.check_output(
            ["git", "show", f"0ed67d936fdbc99f9f07a7e990dad37a9f40a002:{path.relative_to(ROOT)}"],
            cwd=ROOT)
        assert path.read_bytes() == original
    tests = {}
    for path in sorted(post.glob("*.xml")):
        tree = ET.parse(path).getroot()
        cases = list(tree.iter("testcase"))
        failures = [f"{case.get('classname')}::{case.get('name')}" for case in cases
                    if case.find("failure") is not None or case.find("error") is not None]
        skipped = sum(case.find("skipped") is not None for case in cases)
        tests[path.stem] = {
            "passed": len(cases) - len(failures) - skipped, "failed": len(failures),
            "skipped": skipped, "failures": failures,
        }
    result = {
        "scenario_checks_passed": True, "baseline_preserved": True, "runs": runs,
        "tests": tests,
        "limitations": [
            "JUnit counts do not certify the separate live-store exit guard.",
            "Full-suite failures under concurrent PC/phone edits are retained, not counted as passes.",
            "Safari already responded before the fix; zero windows does not verify tab mutations.",
            "No causal latency/token saving measured; no model calls in these scenarios.",
        ],
    }
    (DOC / "evidence_post_repair.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"scenario_checks_passed": True, "runs": len(runs),
                      "baseline_preserved": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
