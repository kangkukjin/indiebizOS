"""계획 조회는 실행하지 않으며 선택기·검사는 같은 취소/시간과 자식 정리를 쓴다."""
import boot_paths  # noqa: F401
import subprocess
import sys
from types import SimpleNamespace as NS

import pytest
import capability_change_checks as checks


def test_plan_reports_full_selection_without_running_build_or_tests(tmp_path, monkeypatch):
    path = tmp_path / 'backend/base/sample.py'
    path.parent.mkdir(parents=True)
    path.write_text('VALUE = 1')
    calls = []
    def run(root, argv, deadline, cancel):
        calls.append(argv)
        assert 'select_tests.py' in argv[1]
        return subprocess.CompletedProcess(argv, 0, 'backend/', 'hub selection')
    monkeypatch.setattr(checks, '_run', run)
    result = checks.check(tmp_path, ['backend/base/sample.py'], plan_only=True)
    assert result['ok'] and result['plan_only'] and result['full_regression']
    assert [s['step'] for s in result['steps']] == ['layers', 'tests']
    assert not result['behavior_verified'] and result['estimated_seconds'] is None
    assert len(calls) == 1 and path.read_text() == 'VALUE = 1'


def test_selector_timeout_is_a_failed_plan_not_an_empty_success(tmp_path, monkeypatch):
    def run(*args):
        raise subprocess.TimeoutExpired('selector', .01)
    monkeypatch.setattr(checks, '_run', run)
    result = checks.check(tmp_path, ['owned.py'], plan_only=True)
    assert not result['ok'] and not result['behavior_verified']
    assert result['items'][0]['step'] == 'selection'


def test_selector_and_all_steps_share_deadline_and_cancel(tmp_path, monkeypatch):
    calls = []
    cancel = lambda: False
    monkeypatch.setattr('execution_turn.current', lambda: NS(cancel_check=cancel))
    def run(root, argv, deadline, check):
        calls.append((deadline, check))
        return subprocess.CompletedProcess(argv, 0, 'backend/test_sample.py', '')
    monkeypatch.setattr(checks, '_run', run)
    result = checks.check(tmp_path, ['backend/base/sample.py'], timeout=5)
    assert result['ok'] and len(calls) == 3
    assert len({d for d, _ in calls}) == 1 and all(c is cancel for _, c in calls)


def test_real_selector_child_timeout_is_reaped(tmp_path):
    import time
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    (scripts / 'select_tests.py').write_text('import time\ntime.sleep(30)\n')
    started = time.monotonic()
    result = checks.check(tmp_path, ['owned.py'], plan_only=True, timeout=.1)
    assert not result['ok'] and result['items'][0]['step'] == 'selection'
    assert time.monotonic() - started < 5
