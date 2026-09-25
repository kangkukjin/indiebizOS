"""Compare semantic values and source coverage in the recorded HTTP evidence."""
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent


def results(phase):
    rows = json.loads((HERE / f"{phase}.json").read_text())
    out = {}
    for row in rows:
        request = row["request"]
        assert request["origin"] == "training" and request["project_id"] == "컨텐츠"
        result = row["response"].get("result", row["response"])
        if request["check"]:
            assert result["status"] in {"valid", "incomplete"}, result
        else:
            assert result["success"], result
            out[row["name"]] = result
    assert len(rows) == 18 and len(out) == 8
    return out


before, after = results("before"), results("after")
expected_invokes = {"T02": 1, "T03": 1, "T04": 1, "T05": 2, "T06": 1}
summary = {}
for name, expected in expected_invokes.items():
    count = lambda result: sum(e["kind"] == "invoke" for e in result["value"]["proof"]["events"])
    assert count(before[name]) < expected
    assert count(after[name]) == expected
    assert {k: v for k, v in before[name]["value"].items() if k != "proof"} == {
        k: v for k, v in after[name]["value"].items() if k != "proof"}
    summary[name] = {"invokes_before": count(before[name]), "invokes_after": count(after[name])}
assert after["T01"]["value"] == [{"video": "v1", "score": 8}]
assert after["T08"]["value"] == {"total": 10, "ready": True}
assert after["T05"]["source_complete"] is False
assert after["T07"]["source_complete"] is False
assert [r["ok"] for r in after["T07"]["value"]] == [True, False, True]
assert after["T07"]["value"][0]["value"]["unit"] == 50
assert after["T07"]["value"][2]["value"]["unit"] == 25
(HERE / "verification.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
print("10 checks, 8 executions, 5 repaired evidence paths: passed")
