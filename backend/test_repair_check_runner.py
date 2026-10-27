"""Go 검사부터 의미 근거·정본 적용까지 실제 수리 사본에서 확인한다."""
import shlex
import shutil
import sys

import boot_paths  # noqa: F401
import pytest
import repair_policy as policy
from repair_check_runner import execute
from test_repair_receipt_flow import repair  # noqa: F401
from test_repair_workspace_completion import setup  # noqa: F401
from test_conscious_supervisor import supervisor  # noqa: F401


@pytest.mark.parametrize("method", ["test", "semantic"])
def test_real_go_receipt_applies_and_commits_without_retesting(repair, monkeypatch, method):
    root, wt, st, session, controller = repair
    go = shutil.which("go")
    if not go:
        pytest.skip("Go toolchain unavailable")
    (wt / "a.txt").write_text("fixed")
    (wt / "go.mod").write_text("module example/repair\n\ngo 1.20\n")
    (wt / "repair_test.go").write_text('''package repair
import ("os"; "testing")
func TestChangedBehavior(t *testing.T) {
    data, err := os.ReadFile("a.txt")
    if err != nil || string(data) != "fixed" { t.Fatal("repair not applied", err) }
}
''')
    cmd = shlex.quote(go) + " test -run 'TestChangedBehavior|TestOther' ./..."
    record = execute(str(root), session, st._candidate, cmd, controller)
    assert record["status"] == "passed", record
    assert record["test_report"]["cases"] == ["example/repair::TestChangedBehavior"]
    assert record["changed_files"] == []
    assert not (wt / "repair").exists()
    st._save_session(str(root), session)
    monkeypatch.setattr("repair_check_runner.execute", lambda *a, **k: pytest.fail("duplicate Go test"))
    reviews = []
    def review(*args):
        reviews.append(1)
        return {"status": "APPROVED", "workspace_coverage": [
            {"criterion_id": "C1", "status": "passed", "evidence_ids": [record["id"]]}]}
    monkeypatch.setattr(policy, "semantic_review", review)
    result = st.op_apply({"_repo_root": str(root), "_grant_key": session["key"],
                          "active_verify_cmd": shlex.quote(sys.executable) + " -c " + shlex.quote(
                              'from pathlib import Path; assert Path("a.txt").read_text() == "fixed"'),
                          "verification_plan": [{"criterion_id": "C1", "method": method, "command": cmd}]})
    assert result.get("complete"), result
    assert len(reviews) == (method == "semantic")
    assert (root / "a.txt").read_text() == "fixed"
    assert policy.completion(st.read_session(str(root), session["key"]), {}, root)[0]


@pytest.mark.parametrize("status", ["unverified", "failed", "stale", "none"])
def test_semantic_without_current_pass_stops_before_model(repair, monkeypatch, status):
    root, wt, st, session, controller = repair
    stamp = st._candidate.digest(st._candidate.collect(str(root), session))
    session["execution_checks"] = [] if status == "none" else [{
        "id": "old-check", "command": "go test . | tail -1", "exit_code": 0,
        "status": "passed" if status == "stale" else status,
        "candidate_hash": "old" if status == "stale" else stamp, "before_hash": stamp,
        "environment_hash": st._candidate.environment(wt), "test_report": None}]
    session["verification_plan"] = [{"criterion_id": "C1", "method": "semantic"}]
    monkeypatch.setattr(policy, "semantic_review", lambda *a: pytest.fail("unusable evidence reviewed"))
    result = policy.prepare(controller, str(root), session, st.verify, st._candidate)
    assert not result["success"] and result["allowed_evidence_ids"] == []
    assert "go test" in result["error"] and result["missing_criteria"] == ["C1"]
    repeated = policy.prepare(controller, str(root), session, st.verify, st._candidate)
    assert repeated["reused"]


def test_leading_env_assignment_reaches_the_test_process(repair):
    """L97-1(97회차): 앞머리 `VAR=값` 대입이 시험 프로세스 환경에 닿아야 명시적으로 켜는 시험이 영수증을 남긴다."""
    root, wt, st, session, controller = repair
    (wt / "test_env_prefix_probe.py").write_text(
        "import os\n\n\ndef test_env_prefix():\n    assert os.environ.get('INDIEBIZ_TRAINING_PROBE') == 'on'\n")
    python = shlex.quote(sys.executable)
    without = execute(str(root), session, st._candidate, f"{python} -m pytest test_env_prefix_probe.py -q", controller)
    assert without["status"] == "failed", without
    record = execute(str(root), session, st._candidate,
                     f"INDIEBIZ_TRAINING_PROBE=on {python} -m pytest test_env_prefix_probe.py -q", controller)
    assert record["status"] == "passed", record
    assert record["test_report"]["tests"] == 1 and record["test_report"]["failures"] == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))


@pytest.mark.parametrize('command', ['false | cat', 'false; echo hidden'])
def test_shell_failure_is_not_hidden_by_last_success(repair, command):
    root, wt, st, session, controller = repair
    result = execute(str(root), session, st._candidate, command, controller)
    assert result['status'] == 'failed' and result['exit_code'] != 0
    assert 'hidden' not in result['output']


def test_explicit_shell_failure_recovery_remains_supported(repair):
    root, wt, st, session, controller = repair
    result = execute(str(root), session, st._candidate, 'false || echo recovered', controller)
    assert result['exit_code'] == 0 and 'recovered' in result['output']
    assert result['status'] == 'unverified'
