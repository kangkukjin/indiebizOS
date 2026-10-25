"""운영 검사기 모두가 현행 실행/표시/원형 조회 계약을 사용하는지 검증한다."""
import importlib
import json
import sys
from pathlib import Path

import boot_paths  # noqa: F401
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import ibl_check_client as client
from ibl_v2_ir import pack
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime
from supervision_store import TurnStore


def packet(value):
    return {'edition': 2, 'success': True, 'executed': True, 'value': value,
            'value_wire': {'protocol': 'ibl-value/1', 'data': pack(value)}}


@pytest.mark.parametrize('module', ['returns_drift_sweep', 'ibl_shape_sweep',
                                   'currency_items_sweep', 'honesty_invariants_sweep'])
def test_every_sweep_reads_real_agent_projection_once(module, monkeypatch, tmp_path):
    import model_result_view as view
    monkeypatch.setattr(view, 'evidence_store', lambda: TurnStore(tmp_path / 'evidence'))
    value = {'items': [{'body': '본문' * 40000}], 'result': '업무 필드', 'success': False, '_protocol_error': '업무 값'}
    shown = view.project_result(packet(value))
    calls = []

    def request(fields, pid, **kwargs):
        calls.append(fields)
        if fields['code']:
            return shown
        return view.read_result({**fields['read_result'], 'limit': 2000})

    monkeypatch.setattr(client, 'request', request)
    sweep = importlib.import_module(module)
    result = sweep._execute('return value')
    decode = getattr(sweep, '_final_envelope', None) or sweep.final_of
    assert decode(result) == value
    assert sum(bool(call['code']) for call in calls) == 1
    assert len(calls) > 2


@pytest.mark.parametrize('response', [
    {'_transport_error': '503'}, {'success': False, 'executed': False, 'error': 'syntax'},
    {'success': False, 'executed': True, 'error': 'offline'},
    {'success': True, 'value': {'items': [{}]}},
])
def test_failed_or_preview_only_response_never_becomes_a_value(response):
    with pytest.raises(client.CheckFailure):
        client.value_of(response)


def test_honesty_main_executes_current_fixtures_and_parallel_probes(monkeypatch, capsys, tmp_path):
    import honesty_invariants_sweep as sweep
    (tmp_path / 'data').mkdir()
    (tmp_path / 'data/ibl_fixtures.json').write_text(json.dumps({'fixtures': {'x:y': 'return {items:[{n:1}]}'}}))
    monkeypatch.setattr(sweep, 'ROOT', tmp_path)
    monkeypatch.setattr(sweep, '_load_declarations', lambda: ({'x:y': 'items'}, {}, {}, {}, {}))
    monkeypatch.setattr(sweep, '_execute', lambda code: Runtime(compile_program(code, {})).run())
    monkeypatch.setattr(sweep, 'static_bare_error_returns', lambda: {})
    assert sweep.main(['--strict']) == 0
    marker = next(line for line in capsys.readouterr().out.splitlines() if line.startswith('@@HONESTY@@'))
    report = json.loads(marker.split(' ', 1)[1])
    assert report['checked'] == 4 and report['failed'] == 0 and report['violations'] == []
    monkeypatch.setattr(sweep, '_execute', lambda code: {'success': False, 'executed': False, 'error': 'syntax'})
    assert sweep.main(['--strict']) == 1


def test_current_business_records_are_not_unwrapped_or_judged_as_execution(tmp_path, monkeypatch):
    import model_result_view as view
    from cognitive_trace import _unwrap_payload
    from ibl_distill_gates import empty_final_items
    from client_workflows import _value
    value = {'success': False, 'result': {'message': 'Error: quoted'}, 'items': []}
    original = packet(value)
    monkeypatch.setattr(view, 'evidence_store', lambda: TurnStore(tmp_path / 'evidence'))
    shown = view.project_result(original)
    assert _value(original) == value and _unwrap_payload(original) == original
    assert empty_final_items(original)
    resolved, _ = view.resolve_input_refs({'data': {'$ref': shown['result_ref']['id']}})
    assert resolved['data'] == value
    assert not empty_final_items({'edition': 2, 'success': False, 'value': value})


def test_weekly_summary_cannot_certify_zero_measurements(monkeypatch, tmp_path):
    import fixture_sweeps
    import world_pulse_health
    import subprocess
    # Keep the actual subprocess runner and state logic, replace only filesystem root and result.
    monkeypatch.setattr(fixture_sweeps, '__file__', str(tmp_path / 'backend/cognition/fixture_sweeps.py'))
    (tmp_path / 'data').mkdir()
    (tmp_path / 'scripts').mkdir()
    for name in ['returns_drift_sweep', 'honesty_invariants_sweep']:
        (tmp_path / f'scripts/{name}.py').touch()
    events = []
    monkeypatch.setattr(world_pulse_health, 'save_self_check', events.append)
    monkeypatch.setattr('runtime_work.parent_token', lambda: 'parent-contract')

    def run(args, **kwargs):
        assert kwargs['env']['INDIEBIZ_RUNTIME_PARENT'] == 'parent-contract'
        marker = '@@RETURNS_DRIFT@@' if 'returns_drift' in args[1] else '@@HONESTY@@'
        return subprocess.CompletedProcess(args, 0, marker + ' ' + json.dumps({'checked': 0, 'failed': 5}), '')

    monkeypatch.setattr(subprocess, 'run', run)
    fixture_sweeps.run_returns_drift_sweep()
    fixture_sweeps.run_honesty_sweep()
    assert len(events) == 2 and all(e['success'] is False and e['error_message'] for e in events)



def test_shape_checkers_measure_values_without_reinterpreting_business_status():
    import returns_drift_sweep as returns
    import ibl_shape_sweep as shape
    import currency_items_sweep as currency
    value = {'success': False, 'error': '인용문', 'results': [{'n': 1}]}
    assert shape._shape(value)[0] == 'scalar'
    assert 'success' in shape._shape(value)[1]
    assert returns._actual_shape({'items': [1]}) == 'invalid_items'
    assert returns._is_drift('items', 'invalid_items') == 'under'
    assert currency._dict_list_keys(value) == [('results', 1)]



@pytest.mark.parametrize('module', ['ibl_shape_sweep', 'currency_items_sweep'])
def test_sweep_main_does_not_certify_failed_measurements(module, monkeypatch, tmp_path):
    sweep = importlib.import_module(module)
    (tmp_path / 'data').mkdir()
    (tmp_path / 'data/ibl_fixtures.json').write_text(json.dumps({'fixtures': {'x:y': 'return 1'}}))
    monkeypatch.setattr(sweep, 'ROOT', tmp_path)
    monkeypatch.setattr(sys, 'argv', [module])
    if module == 'ibl_shape_sweep':
        monkeypatch.setattr(sweep, 'OUT', tmp_path / 'shape.json')
    else:
        import returns_drift_sweep as returns
        monkeypatch.setattr(returns, '_load_declarations', lambda: ({'x:y': 'items'}, {}, {}, {}, {}))
    monkeypatch.setattr(sweep, '_execute', lambda code: {'success': False, 'executed': False})
    assert sweep.main() == 1
    monkeypatch.setattr(sweep, '_execute', lambda code: packet({'items': [{'title': '자료'}]}))
    assert sweep.main() == 0



def test_native_record_list_is_current_currency():
    import ibl_health_check as health
    import returns_drift_sweep as returns
    import honesty_invariants_sweep as honesty
    import ibl_shape_sweep as shape
    rows = [{'name': '현행 List'}]
    assert health.classify_currency(packet(rows), 'items')[0] == 'GREEN'
    assert returns._actual_shape(rows) == 'items'
    assert honesty.check_envelope('x:y', 'items', rows) == []
    assert shape._shape(rows) == ('items', ['name'], 0)
    assert health.classify_currency(packet([1]), 'items')[0] == 'RED'


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
