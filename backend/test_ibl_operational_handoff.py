"""Operational handoff: use the advertised arguments without reconstructing values."""
import json
import sqlite3

import boot_paths  # noqa: F401
import pytest

from test_ibl_general_capabilities import boundary, adapter  # noqa: F401
from test_execution_trace import trace, pages  # noqa: F401
from test_ibl_composition_teaching import current, EXAMPLES  # noqa: F401


def test_typed_reference_defaults_to_value_and_roundtrips_without_read(boundary, tmp_path):
    from system_tools_ibl import _execute_ibl_unified_impl as run
    from model_result_view import read_result
    first = json.loads(run({"edition": 2, "code": 'return {rows:[{n:2},{n:3}],body:"' + '본문' * 3000 + '"}'}, str(tmp_path)))
    ref = first['result_ref']
    assert ref['read_args']['path'] == ['value']
    assert all(p['path'][0] == 'value' for p in ref['paths'])
    second = json.loads(run({'edition': 2, 'code': 'return len($입력.rows)', 'inputs': ref['input_args']}, str(tmp_path)))
    assert second['success'] and second['value'] == 2
    page = read_result({'id': ref['id'], 'path': ['value', 'rows'], 'limit': 5})
    assert page['next_read']
    third = json.loads(run({'edition': 2, 'code': 'return $입력[0]',
                            'inputs': page['input_args']}, str(tmp_path)))
    assert third['success'] and third['value'] == {'n': 2}, third


def test_misplaced_reference_explains_named_input_before_execution(boundary, tmp_path, monkeypatch):
    import ibl_v2_entry
    from system_tools_ibl import _execute_ibl_unified_impl
    monkeypatch.setattr(ibl_v2_entry, 'handle_request', lambda *a, **kw: pytest.fail('must not execute'))
    result = json.loads(_execute_ibl_unified_impl({'code': 'return 1',
                          'inputs': {'$ref': 'record-id', 'path': ['value']}}, str(tmp_path)))
    assert not result['success'] and result['executed'] is False
    assert '"inputs": {"입력": {"$ref": "record-id"' in result['error']


def test_advertised_reuse_repairs_only_changed_computation(boundary, tmp_path, monkeypatch):
    import ibl_v2_adapters
    from system_tools_ibl import _execute_ibl_unified_impl as run
    calls = []
    monkeypatch.setattr(ibl_v2_adapters, 'load_registry', lambda *a: {
        't:read': adapter(lambda *_: calls.append(1) or 7)})
    first = json.loads(run({'edition': 2, 'code': '$x=[t:read]{}; return $x / 0'}, str(tmp_path)))
    assert not first['success']
    args = first['continuation']['reuse_args']
    second = json.loads(run({'edition': 2, 'code': '$x=[t:read]{}; return $x * 2', **args}, str(tmp_path)))
    assert second['success'] and second['value'] == 14
    assert calls == [1] and second['reuse']['reused_calls'] == 1


def test_failed_or_pure_calls_do_not_advertise_read_reuse(boundary, tmp_path, monkeypatch):
    import ibl_v2_adapters
    from ibl_v2_ir import Fault
    from system_tools_ibl import _execute_ibl_unified_impl as run
    def fail(*_):
        raise Fault('TOOL', 'unavailable')
    monkeypatch.setattr(ibl_v2_adapters, 'load_registry', lambda *a: {'t:read': adapter(fail)})
    for code in ['return 1', 'return [t:read]{}']:
        assert 'continuation' not in json.loads(run({'edition': 2, 'code': code}, str(tmp_path)))


def test_unfinished_effect_suppresses_reuse_advice(boundary, tmp_path, monkeypatch):
    import ibl_v2_adapters
    from system_tools_ibl import _execute_ibl_unified_impl as run
    def read(runtime, _):
        runtime.journal.begin('unconfirmed-external-work', 'request')
        return 7
    monkeypatch.setattr(ibl_v2_adapters, 'load_registry', lambda *a: {'t:read': adapter(read)})
    result = json.loads(run({'edition': 2, 'code': 'return [t:read]{}'}, str(tmp_path)))
    assert result['run_status'] == 'uncertain'
    assert 'continuation' not in result


def test_transport_keeps_advertised_input_and_reuse_arguments(boundary):
    from ibl_result_transport import fit_tool_result
    from model_result_view import project_v2_result
    source = {'edition': 2, 'success': True, 'value': list(range(10000)),
              'continuation': {'reuse_args': {'reuse': {'run_id': 'a' * 32}}, 'read_calls': 1}}
    projected = project_v2_result(source)
    projected['large_diagnostic'] = 'detail' * 10000
    delivered = json.loads(fit_tool_result(json.dumps(projected), 4000))
    assert delivered['result_ref']['input_args'] == projected['result_ref']['input_args']
    assert delivered['continuation'] == source['continuation']


@pytest.mark.parametrize('kind,data,status', [
    ('cognition.evaluation', {'path': 'none'}, 'not_evaluated'),
    ('validation.completed', {'validator': 'goal_eval', 'status': 'UNKNOWN', 'achieved': False}, 'unknown'),
    ('validation.completed', {'validator': 'goal_eval', 'status': 'NOT_ACHIEVED'}, 'not_achieved'),
    ('supervision.evaluation.finished', {'decision': {'status': 'APPROVED', 'response_version': 2}}, 'achieved'),
])
def test_completed_task_and_recorded_goal_evaluation_are_separate_across_pages(trace, kind, data, status):
    from episode_logger import trajectory_run_id
    svc, root = trace
    with sqlite3.connect(root / 'data/world_pulse.db') as db:
        db.execute('INSERT INTO trajectory_event VALUES(?,?,?,?,?,?,?,?,?)',
                   (trajectory_run_id('shared-task'), 99, 1, 'shared-task', '', '', kind, json.dumps(data), 'usage'))
    results = pages(svc, episode_id=1, limit=2)
    state = results[-1]['state']
    assert state['task'] == 'completed'
    assert state['goal_evaluations'][0]['status'] == status
    assert state['goal_evaluations'][0]['source_ref']
    assert 'lifecycle_only' in state['task_status_scope']


def test_no_evaluation_record_is_unknown_not_achieved(trace):
    svc, _ = trace
    assert pages(svc, episode_id=1)[-1]['state']['goal_evaluations'][0]['status'] == 'unknown'


@pytest.mark.parametrize('second,complete,source_complete', [('ok', True, True), ('', False, True), (None, False, False)])
def test_document_completion_example_preserves_missing_empty_and_confirmed(current, tmp_path, second, complete, source_complete):
    (tmp_path / 'outputs/source-a.txt').write_text('first')
    if second is not None:
        (tmp_path / 'outputs/source-b.txt').write_text(second)
    result = current(EXAMPLES['document_completion'])
    assert result['success'] is True
    assert result['value']['complete'] is complete
    assert result['source_complete'] is source_complete
    assert result['value']['checked'] == 2
    assert len(result['value']['missing']) == (0 if complete else 1)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
