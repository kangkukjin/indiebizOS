"""Work verdicts survive successful script calls without interpreting business data."""
import importlib.util
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest

from ibl_v2_adapters import Adapted, Adapter, decode_envelope
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime
from test_conscious_supervisor import supervisor  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / 'data/packages/installed/tools/system_essentials'


def load(path):
    spec = importlib.util.spec_from_file_location('outcome_' + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def ops(tmp_path, monkeypatch):
    module = load(PKG / 'script_ops.py')
    scripts = tmp_path / 'scripts'
    scripts.mkdir()
    script = scripts / 'check.py'
    script.write_text('print("unused")')
    monkeypatch.setattr(module, '_SCRIPT_DIR', scripts)
    monkeypatch.setattr(module, '_RUN_DIR', tmp_path / 'runs')
    monkeypatch.setattr(module, '_JOB_DIR', tmp_path / 'jobs')
    monkeypatch.setattr(module, '_read_registry', lambda: {'check': {'file': 'check.py', 'interpreter': 'python'}})
    monkeypatch.setattr(module, '_update_state', lambda *a, **kw: None)
    monkeypatch.setattr(module, '_child_env', lambda mode: {})
    return module


def verdict(failed=True):
    return {'ok': not failed, 'items': [{'exit_code': int(failed), 'stdout': 'full diagnostics'}],
            'operation_outcome': {'status': 'failed' if failed else 'passed', 'message': 'check verdict'}}


@pytest.mark.parametrize('edition', [1, 2])
@pytest.mark.parametrize('failed', [False, True])
def test_foreground_keeps_value_and_declares_work_verdict(ops, monkeypatch, edition, failed):
    payload = verdict(failed)
    monkeypatch.setattr('script_process.run_process', lambda *a, **kw: {
        'exit_code': 0, 'stdout': json.dumps(payload), 'stderr': '', 'timed_out': False})
    out = ops.op_run({'id': 'check', '_ibl_edition': edition})
    assert out['success'] is True and out['exit_code'] == 0
    assert (out['value'] if edition == 2 else out)['items'] == payload['items']
    assert out['operation_outcomes'][0]['status'] == payload['operation_outcome']['status']
    assert out['operation_outcomes'][0]['id'].endswith(out['log'])


@pytest.mark.parametrize('payload', [
    {'ok': False, 'items': [{'exit_code': 1}]},
    {'items': [{'operation_outcome': {'status': 'failed'}}]},
    {'result': {'operation_outcome': {'status': 'failed'}}},
])
def test_business_fields_are_not_work_verdicts(ops, monkeypatch, payload):
    monkeypatch.setattr('script_process.run_process', lambda *a, **kw: {
        'exit_code': 0, 'stdout': json.dumps(payload), 'stderr': '', 'timed_out': False})
    out = ops.op_run({'id': 'check', '_ibl_edition': 2})
    assert out['success'] and out['value'] == payload
    assert 'operation_outcomes' not in out


def test_malformed_explicit_declaration_fails_contract(ops, monkeypatch):
    payload = {'operation_outcome': {'status': False}}
    monkeypatch.setattr('script_process.run_process', lambda *a, **kw: {
        'exit_code': 0, 'stdout': json.dumps(payload), 'stderr': '', 'timed_out': False})
    out = ops.op_run({'id': 'check', '_ibl_edition': 2})
    assert not out['success'] and 'operation_outcome' in out['error']
    ops._JOB_DIR.mkdir()
    (ops._JOB_DIR / 'bad.json').write_text(json.dumps({
        'job_id': 'bad', 'id': 'check', 'status': 'failed', 'result': payload,
        'error': out['error']}))
    status = ops.op_status({'job_id': 'bad'})
    assert not status['success'] and status['result'] == payload
    assert 'operation_outcomes' not in status


def test_typed_script_value_is_not_a_legacy_declaration(ops, monkeypatch):
    contract = {'version': 1, 'params': {}, 'result': 'Record', 'effects': ['read_external'],
                'adapter': {'protocol': 'ibl-script/2'}}
    monkeypatch.setattr(ops, '_read_registry', lambda: {
        'check': {'file': 'check.py', 'interpreter': 'python', 'callable_contract': contract}})
    value = {'operation_outcome': {'status': False}, 'ok': False}
    monkeypatch.setattr('script_process.run_process', lambda *a, **kw: {
        'exit_code': 0, 'stdout': json.dumps({'protocol': 'ibl-script/2', 'ok': True, 'value': value}),
        'stderr': '', 'timed_out': False})
    out = ops.op_run({'id': 'check', '_ibl_edition': 2})
    assert out['success'] and out['value'] == value
    assert 'operation_outcomes' not in out


def test_member_script_uses_the_same_explicit_work_contract(ops):
    def exchange(command):
        if command.get('action') == 'list':
            return {'script_protocols': ['ibl-script/2'], 'items': [{'id': 'check'}]}
        return {'success': True, 'stdout': json.dumps(verdict())}
    out = ops._runtime.member_value_script({'id': 'check'}, {}, exchange)
    assert out['success'] and out['value'] == verdict()
    assert out['operation_outcomes'][0]['status'] == 'failed'


def test_background_notice_reports_work_failure_without_changing_process_status(monkeypatch):
    monkeypatch.syspath_prepend(str(PKG))
    runner = load(PKG / '_bg_runner.py')
    sent = []
    monkeypatch.setattr('urllib.request.urlopen', lambda req, **kw:
                        sent.append(json.loads(req.data)) or SimpleNamespace(read=lambda: b''))
    runner._announce({'status': 'done', 'result': verdict(), 'id': 'check', 'job_id': 'job'})
    assert sent[0]['type'] == 'error' and 'check verdict' in sent[0]['message']
    runner._announce({'status': 'done', 'result': {'ok': False}, 'id': 'data', 'job_id': 'job2'})
    assert sent[1]['type'] == 'info'


def test_background_verdict_survives_lookup_list_composition_and_supervision(
        ops, tmp_path, monkeypatch, supervisor):
    monkeypatch.syspath_prepend(str(PKG))
    runner = load(PKG / '_bg_runner.py')
    monkeypatch.setattr(runner, '_announce', lambda job: None)
    ops._JOB_DIR.mkdir()
    for name, payload in [('failed', verdict()), ('passed', verdict(False))]:
        script = tmp_path / (name + '.py')
        script.write_text('print(' + repr(json.dumps(payload)) + ')')
        job = {'job_id': name, 'id': 'check', 'status': 'starting', 'script': str(script),
               'interpreter': sys.executable, 'log': str(tmp_path / (name + '.log')), 'timeout': 10}
        path = ops._JOB_DIR / (name + '.json')
        path.write_text(json.dumps(job))
        monkeypatch.setattr(sys, 'argv', ['runner', str(path)])
        runner.main()
        stored = json.loads(path.read_text())
        assert stored['status'] == 'done' and stored['result'] == payload
    single = ops.op_status({'job_id': 'failed'})
    grouped = ops.op_status({'id': 'check'})
    assert single['success'] and grouped['success']
    assert single['result'] == verdict()
    assert len(grouped['operation_outcomes']) == 2

    import model_result_view as view
    monkeypatch.setattr(view, 'evidence_store', lambda: supervisor.store)
    schema = {'protocol': 'legacy-envelope', 'value_path': ''}
    contract = {'version': 1, 'params': {}, 'result': 'Record', 'effects': ['read_external']}

    def project(envelope):
        registry = {'test:status': Adapter(contract, lambda rt, a: Adapted(*decode_envelope(envelope, schema)))}
        # Discard the returned data: the execution evidence must still survive.
        result = Runtime(compile_program('[test:status]{}; return 7', registry)).run()
        assert result['success'] and result['value'] == 7
        replayed = Runtime(compile_program('[test:status]{}; return 7', registry),
                           recordings=result['recordings'], replay=True).run()
        assert replayed['success'] and replayed['value'] == 7
        assert view.project_v2_result(replayed)['evidence_summary']['operation_failures'] == 1
        return view.project_v2_result(result)

    for envelope in (single, grouped, single):
        shown = project(envelope)
        assert shown['evidence_summary']['operation_failures'] == 1
        assert shown['evidence_summary']['tool_failures'] == 0
        key = supervisor._start('execute_ibl', {'code': 'test'})
        supervisor._finish(key, shown)
    assert supervisor.store.cost['operation_failures'] == 1
    assert supervisor.store.cost['operations_observed'] == 2
    assert supervisor.store.cost['execution_failures'] == 0
    assert supervisor.store.cost['internal_tool_failures'] == 0
    assert any(e.get('operation_failures') == 1 for e in supervisor.recent)
    # A fresh execution is a distinct failure even with identical output.
    second = {**single, 'operation_outcomes': [{**single['operation_outcomes'][0], 'id': 'script:new-job'}]}
    key = supervisor._start('execute_ibl', {'code': 'test'})
    supervisor._finish(key, project(second))
    assert supervisor.store.cost['operation_failures'] == 2


@pytest.mark.parametrize('failed', [False, True])
@pytest.mark.parametrize('producer', ['시험', '빌드검증', 'spreadsheet'])
def test_check_producers_explicitly_report_work_verdicts(producer, failed, tmp_path, monkeypatch, capsys):
    if producer == 'spreadsheet':
        module = load(ROOT / 'scripts/verify_spreadsheet_followup.py')
        args = {'mode': 'unit'}
        monkeypatch.setattr(module.subprocess, 'run', lambda *a, **kw: SimpleNamespace(
            returncode=int(failed), stdout='test output', stderr=''))
    elif producer == '빌드검증':
        module = load(ROOT / 'data/scripts/빌드검증.py')
        args = {'gates': ['layers']}
        monkeypatch.setattr(module.subprocess, 'run', lambda *a, **kw: SimpleNamespace(
            returncode=int(failed), stdout='gate output', stderr=''))
    else:
        module = load(ROOT / 'data/scripts/시험.py')
        (tmp_path / 'test_sample.py').write_text('')
        monkeypatch.setattr(module, 'ROOT', tmp_path)
        args = {'files': ['test_sample.py']}
        monkeypatch.setattr(module, '_run', lambda *a: (
            {'passed': int(not failed), 'failed': int(failed), 'errors': 0, 'skipped': 0},
            ['test_sample'] if failed else [], int(failed), 'diagnostic'))
    monkeypatch.setattr(sys, 'stdin', io.StringIO(json.dumps(args)))
    monkeypatch.setattr(sys, 'argv', ['check'])
    module.main()
    result = json.loads(capsys.readouterr().out)
    assert result['ok'] is not failed
    assert result['operation_outcome']['status'] == ('failed' if failed else 'passed')
    assert result['items']


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
