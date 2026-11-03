"""시험·빌드검증의 후보 근거, _run 호환성 및 미실행 보존."""
import boot_paths  # noqa: F401
import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / 'data/scripts'


def load(name, monkeypatch):
    monkeypatch.syspath_prepend(str(SCRIPTS))
    spec = importlib.util.spec_from_file_location('development_test_' + name, SCRIPTS / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_plan_and_observe_preserve_failed_stale_and_remaining_commands(monkeypatch):
    module = load('development_checks', monkeypatch)
    commands = ['check-a', 'check-b', 'check-c']
    planned = module.plan(commands)
    assert not planned['ok'] and not planned['official_receipt']
    current = {'candidate_hash': 'candidate', 'environment_hash': 'environment'}
    passed = {'command': commands[0], 'candidate_hash': 'candidate', 'before_hash': 'candidate',
              'environment_hash': 'environment', 'status': 'passed', 'id': 'owner-receipt'}
    failed = {**passed, 'command': commands[1], 'status': 'failed'}
    observed = module.observe({'receipts': [passed, failed], 'current': current}, commands)
    assert observed['items'][0]['ok']
    assert observed['remaining'] == commands[1:]
    assert observed['history'] == [passed, failed]
    assert not observed['ok']
    for changed in ({}, {**current, 'candidate_hash': 'new'}, {**current, 'environment_hash': 'new'}):
        assert not module.observe({'receipts': [passed], 'current': changed}, commands[:1])['ok']


@pytest.mark.parametrize('body,expected', [
    ('def test_ok():\n    assert 2 + 2 == 4\n', True),
    ('def test_bad():\n    assert False\n', False),
    ('import pytest\n@pytest.mark.skip(reason="fixture")\ndef test_skip():\n    pass\n', False),
    ('VALUE = 1\n', False),
])
def test_real_pytest_run_preserves_tuple_and_observed_scope(tmp_path, monkeypatch, body, expected):
    module = load('시험', monkeypatch)
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    path = tmp_path / 'test_example.py'
    path.write_text(body)
    counts, failures, code, output = module._run(['test_example.py'], '', 30)
    assert isinstance(counts, dict) and isinstance(failures, list)
    assert isinstance(code, int) and isinstance(output, str)
    assert counts['test_report']['passed'] is expected
    assert counts['identity']['workspace'] == str(tmp_path)
    assert counts['identity']['selected_source_hashes']['test_example.py']
    assert counts['identity']['environment_hash']
    assert not counts['official_receipt']
    assert counts['evidence_kind'] == 'independent_execution'
    # The existing owner emits collection events only for non-empty collections.
    # An empty suite must retain both failed verdict and unknown collection scope.
    assert counts['scope_observed'] is (counts['collected'] > 0)
    if expected:
        assert counts['passed'] == counts['executed'] == counts['collected'] == 1
    else:
        assert counts['failed'] or counts['skipped'] or counts['collected'] == 0


def test_timeout_keeps_output_and_failure_kind(tmp_path, monkeypatch):
    module = load('development_checks', monkeypatch)
    (tmp_path / 'test_timeout.py').write_text('def test_timeout():\n    pass\n')
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], 1, output=b'partial evidence')
    monkeypatch.setattr(module.subprocess, 'run', timeout)
    counts, failures, code, output = module.independent_test(tmp_path, ['test_timeout.py'], '', 1)
    assert code == 124 and counts['failure_kind'] == 'timeout'
    assert 'partial evidence' in output and not counts['test_report']['passed']


def test_trial_main_retains_all_unrun_files_when_budget_exhausted(tmp_path, monkeypatch, capsys):
    module = load('시험', monkeypatch)
    monkeypatch.setattr(module, 'ROOT', tmp_path)
    monkeypatch.setattr(sys, 'stdin', io.StringIO(json.dumps({'files': ['one.py', 'two.py'], 'timeout': 1})))
    ticks = iter([0, 2, 3, 4])
    monkeypatch.setattr(module.time, 'time', lambda: next(ticks))
    assert module.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert not result['ok'] and result['operation_outcome']['status'] == 'failed'
    assert [row['file'] for row in result['items']] == ['one.py', 'two.py']
    assert all(row['state'] == 'not_run' for row in result['items'])


@pytest.mark.parametrize('name,args', [('시험', {'files': ['backend/test_development_checks.py']}),
                                      ('빌드검증', {'gates': ['build']})])
def test_existing_entrypoints_offer_plan_without_running_checks(monkeypatch, capsys, name, args):
    module = load(name, monkeypatch)
    monkeypatch.setattr(sys, 'stdin', io.StringIO(json.dumps({**args, 'op': 'plan'})))
    def unexpected(*args, **kwargs):
        raise AssertionError('plan must not run a subprocess')
    monkeypatch.setattr(module.subprocess, 'run', unexpected)
    assert module.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result['state'] == 'planned' and not result['ok']
    assert result['commands'] and result['items'][0]['state'] == 'not_run'


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
