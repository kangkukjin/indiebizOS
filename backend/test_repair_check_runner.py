"""Go 검사부터 기존 계획 호환·정본 적용까지 실제 수리 사본에서 확인한다."""
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
    result = st.op_apply({"_repo_root": str(root), "_grant_key": session["key"],
                          "active_verify_cmd": shlex.quote(sys.executable) + " -c " + shlex.quote(
                              'from pathlib import Path; assert Path("a.txt").read_text() == "fixed"'),
                          "verification_plan": [{"criterion_id": "C1", "method": method, "command": cmd}]})
    assert result.get("complete"), result
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
    result = policy.prepare(controller, str(root), session, st.verify, st._candidate)
    assert not result["success"] and result["stage"] == "test"
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


def test_interrupted_scope_preserves_unrun_and_narrow_pass_cannot_erase_failure(repair):
    root, wt, st, session, controller = repair
    (wt / 'test_scope.py').write_text('def test_a(): assert False\ndef test_b(): pass\n')
    cmd = shlex.quote(sys.executable) + ' -m pytest test_scope.py -x'
    failed = execute(str(root), session, st._candidate, cmd, controller)
    scope = failed['test_report']['scope']
    assert scope['failed'] == ['test_scope.py::test_a']
    assert scope['not_run'] == ['test_scope.py::test_b']
    narrow = execute(str(root), session, st._candidate,
                     shlex.quote(sys.executable) + ' -m pytest test_scope.py::test_b', controller)
    assert narrow['status'] == 'passed'
    remaining = policy.unresolved_checks(session, narrow['candidate_hash'], narrow['environment_hash'])
    assert [r['id'] for r in remaining] == [failed['id']]


@pytest.mark.parametrize('kind', ['permission', 'cancel', 'timeout', 'changed'])
def test_failure_diagnosis_preserves_missing_report(repair, monkeypatch, kind):
    import subprocess
    root, wt, st, session, controller = repair
    def fail(*args, **kwargs):
        if kind == 'changed':
            (wt / 'a.txt').write_text('changed during check')
            return subprocess.CompletedProcess([], 0, 'partial', '')
        if kind == 'timeout':
            raise subprocess.TimeoutExpired('pytest', 1, output='original output')
        if kind == 'cancel':
            monkeypatch.setattr(controller, 'cancelled', lambda: True)
        raise PermissionError('original permission failure')
    monkeypatch.setattr('repair_process.run', fail)
    row = execute(str(root), session, st._candidate, 'python -m pytest test.py', controller)
    assert row['failure_kind'] == {'permission': 'environment', 'cancel': 'cancelled',
                                  'timeout': 'timeout', 'changed': 'candidate_changed'}[kind]
    assert row['test_report']['error']
    assert row['status'] != 'passed'


def test_selected_scope_is_recorded_without_shell_substitution(repair):
    root, wt, st, session, controller = repair
    (wt / 'scripts').mkdir(exist_ok=True)
    (wt / 'scripts/select_tests.py').write_text("import sys\nprint('test_selected.py')\nprint('selected from changed files', file=sys.stderr)\n")
    (wt / 'test_selected.py').write_text('def test_selected(): pass\n')
    python = shlex.quote(sys.executable)
    command = f'{python} -m pytest $({python} scripts/select_tests.py --explain)'
    record = execute(str(root), session, st._candidate, command, controller)
    assert record['status'] == 'passed', record
    assert record['selection']['selected'] == ['test_selected.py']
    assert 'changed files' in record['selection']['selector_diagnostic']
    assert record['test_report']['scope']['collected'] == ['test_selected.py::test_selected']
    assert record['command'] == command


def test_changed_candidate_does_not_force_old_plan_commands(repair):
    root, wt, st, session, controller = repair
    (wt / 'test_required.py').write_text('def test_a(): assert False\ndef test_b(): pass\n')
    command = shlex.quote(sys.executable) + ' -m pytest test_required.py -x'
    session['verification_plan'] = [{'criterion_id': 'C1', 'command': command}]
    failed = policy.prepare(controller, str(root), session, st.verify, st._candidate)
    assert not failed['success']
    (wt / 'a.txt').write_text('new candidate')
    session['verification_plan'] = [{'criterion_id': 'C1', 'command': command.replace('test_required.py -x', 'test_required.py::test_b')}]
    result = policy.prepare(controller, str(root), session, st.verify, st._candidate)
    assert result['success']  # 새 후보의 검사 범위는 실행자가 선택한다. 옛 계획을 강제 재실행하지 않는다.
    assert session['execution_checks'][0]['status'] == 'failed'
    assert session['execution_checks'][-1]['test_report']['scope']['collected'] == ['test_required.py::test_b']
