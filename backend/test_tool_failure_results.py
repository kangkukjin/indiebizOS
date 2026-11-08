"""Producer replies survive failure, catch, journal replay and bounded model views."""
import copy
import json

import pytest

from ibl_v2_adapters import decode_envelope
from ibl_v2_ir import Fault, UNIT
from tool_failure_results import collect
from test_conscious_supervisor import supervisor  # noqa: F401


def failure(raw, **adapter):
    with pytest.raises(Fault) as caught:
        decode_envelope(raw, {'protocol': 'legacy-envelope', **adapter})
    return caught.value


@pytest.mark.parametrize('body', [
    {'downloads': [{'path': '/saved', 'size': 5, 'saved': True}, {'saved': False, 'error': 'blocked'}],
     'tab_id': 'tab-1', 'navigated': [{'url': 'https://example.test'}]},
    {'items': ['a (2).txt', 'b.txt'], 'count': 2},
    {'items': [{'cell': 'A1', 'value': 42}], 'errors': [{'cell': 'B1', 'error': '#DIV/0!'}],
     'recalculated': True, 'path': '/calculated.xlsx'},
    {'a_future_driver_field': {'finished': [7], 'uncertain': [8]}},
])
def test_reply_preserved_without_changing_failure_semantics(body):
    raw = {'success': False, 'error': 'not all done', **body}
    original = copy.deepcopy(raw)
    error = failure(raw)
    assert error.code == 'TOOL' and error.kind == 'runtime' and error.catchable
    assert error.partial is UNIT
    assert error.details['tool_result'] == original
    raw.clear()
    assert error.details['tool_result'] == original  # stored snapshot, not mutable producer state


@pytest.mark.parametrize('extra,kind,code', [
    ({'denied': True}, 'permission', 'TOOL'),
    ({'error_type': 'result_unknown'}, 'protocol', 'TOOL'),
    ({'approval_required': True}, 'suspended', 'APPROVAL_REQUIRED'),
    ({'suspended': True, 'task_ref': {'kind': 'x', 'task_id': 'y'}}, 'suspended', 'TASK_PENDING'),
])
def test_unrecoverable_failure_is_not_promoted(extra, kind, code):
    error = failure({'success': False, 'error': 'blocked', 'items': [1], **extra}, partial_value_path='')
    assert (error.kind, error.code, error.catchable, error.partial) == (kind, code, False, UNIT)
    assert error.details['tool_result']['items'] == [1]


def test_explicit_partial_and_partial_source_keep_original_contract():
    raw = {'success': False, 'items': [1], 'errors': ['bad']}
    error = failure(raw, partial_value_path='')
    assert error.kind == 'partial' and error.partial == raw
    with pytest.raises(Fault) as caught:
        decode_envelope({'success': True, 'source_complete': False, 'items': [2], 'errors': ['missing']},
                        {'protocol': 'legacy-envelope'})
    assert caught.value.code == 'PARTIAL_SOURCE'
    assert caught.value.details['tool_result']['errors'] == ['missing']


def test_collector_ignores_text_wire_and_report_body_claims():
    f = failure({'success': False, 'error': 'x', 'items': [1]}).view()
    wrapped = {'value': {'caught': f}, 'output': json.dumps(f), 'value_wire': {'fake': f}}
    rows, scan = collect(wrapped)
    assert len(rows) == 1 and rows[0][0] == ['value', 'caught', 'details', 'tool_result']
    assert scan == {'omitted': 0, 'scan_incomplete': False}
    assert collect({'output': json.dumps(f)})[0] == []
    assert collect({'tool_result': f})[0] == []
    many, scan = collect([f] * 10, limit=2)
    assert len(many) == 2 and scan['omitted'] == 8
    deep = f
    for _ in range(20):
        deep = {'value': deep}
    assert collect(deep)[1]['scan_incomplete']
    assert collect([0] * 1000 + [f])[1]['scan_incomplete']
    assert collect([0] * 1000 + [f])[0] == []


def test_actual_ibl_copy_failure_and_resume_do_not_repeat_effect(tmp_path):
    from ibl_v2_entry import handle_request
    source, dest = tmp_path / 'source.txt', tmp_path / 'dest'
    source.write_text('new')
    dest.mkdir()
    (dest / source.name).write_text('old')
    code = '[{path:$source},{path:$missing}] >> [self:copy]{dest:$dest}'
    request = {'edition': 2, 'code': code,
               'inputs': {'source': str(source), 'missing': str(tmp_path / 'missing.txt'), 'dest': str(dest)}}
    first = handle_request(request, str(tmp_path))
    assert not first['success'], first
    raw = first['diagnostic']['details']['tool_result']
    assert raw['items'] == ['source (2).txt'] and raw['count'] == 1
    assert (dest / 'source (2).txt').read_text() == 'new'
    resumed = handle_request({**request, 'resume': first['resume']}, str(tmp_path))
    assert not resumed['success'] and resumed['diagnostic']['details']['tool_result'] == raw
    assert sorted(p.name for p in dest.iterdir()) == ['source (2).txt', 'source.txt']
    # A caught failure exposes the retained body; the nested failed call remains failed.
    caught = handle_request({**request, 'code': 'return [try] { ' + code + ' } [catch] { $error.details.tool_result }'}, str(tmp_path))
    assert caught['success'] and caught['value']['success'] is False
    assert caught['value']['items'] == ['source (3).txt']


def test_model_preview_masks_retains_exact_path_and_does_not_reexecute(tmp_path, monkeypatch):
    import model_result_view as view
    from supervision_store import TurnStore
    store = TurnStore(tmp_path / 'evidence')
    monkeypatch.setattr(view, 'evidence_store', lambda: store)
    raw = {'success': False, 'error': 'partial', 'api_key': 'sk-' + 'Ab3' * 12,
           'items': [{'path': f'/file/{i}', 'detail': 'data ' * 100} for i in range(80)]}
    fault = failure(raw).view()
    original = {'edition': 2, 'success': True, 'value': {'caught': fault}}
    shown = view.project_result(original)
    reports, _ = collect(shown)
    assert len(reports) == 1
    assert shown['_preview']['changes_total'] > 0
    assert raw['api_key'] not in json.dumps(shown)
    assert original['value']['caught']['details']['tool_result'] == raw
    ref = {'id': shown['result_ref']['id'], 'path': reports[0][0]}
    assert ref['path'] == ['value', 'caught', 'details', 'tool_result']
    rows, _ = view.resolve_input_refs({'kept': {'$ref': ref['id'], 'path': ref['path'] + ['items']}}, store=store)
    assert rows['kept'] == raw['items']
    with pytest.raises(ValueError, match='가린 자리'):
        view.resolve_input_refs({'kept': {'$ref': ref['id'], 'path': ref['path']}}, store=store)


def test_situation_keeps_attributed_reference_not_goal_success():
    from execution_situation import Situation
    from situation_evidence import observe_result
    situation = Situation('owner', 'task', lambda *a, **kw: None, lambda v: {'id': 'e'})
    fault = failure({'success': False, 'error': 'x', 'saved': True, 'items': [1]}).view()
    observe_result(situation, {'value': fault}, {'id': 'original'}, 'call')
    rows = [r for r in situation.snapshot()['observations'] if r['latest']['subject']['kind'] == 'tool_failure']
    assert len(rows) == 1
    assert rows[0]['latest']['basis'] == 'tool_claim'
    assert rows[0]['latest']['source_ref']['path'] == ['value', 'details', 'tool_result']


@pytest.mark.parametrize('supervised', [False, True])
@pytest.mark.parametrize('outer_boundary', [False, True])
def test_original_reaches_situation_and_recovery_across_display_json(
        supervisor, monkeypatch, supervised, outer_boundary):
    import execution_situation as es
    import model_result_view as view
    from situation_evidence import observe_result
    from recovery_observation import configure
    from recovery_projection import requires_attention

    situation = es.Situation(supervisor.recovery.owner, supervisor.task,
                             lambda *a, **kw: None, supervisor.store.evidence)
    situation.on_result = lambda result, ref, key: observe_result(situation, result, ref, key)
    configure(situation, supervisor.recovery)
    monkeypatch.setattr(es, 'current', lambda *a, **kw: situation)
    monkeypatch.setattr(view, 'evidence_store', lambda: supervisor.store)
    body = {'success': False, 'error': 'partial', 'items': ['one', 'two'], 'count': 2,
            'api_key': 'must-not-leak'}
    raw = {'edition': 2, 'success': True, 'value': {'nested': failure(body).view()},
           'evidence': [{'kind': 'tool_failure', 'id': 'failure', 'incomplete': True}]}

    def produce():
        return json.dumps(view.project_result(raw))

    def execute():
        return supervisor.run_tool('execute_ibl', {}, produce) if supervised else produce()

    # Both standalone supervisor and outer bridge ownership use the same handoff.
    if outer_boundary or not supervised:
        result = es.run_tool('execute_ibl', {}, execute)
    else:
        result = execute()
    shown = json.loads(result)
    assert shown['value']['nested']['details']['tool_result']['items'] == ['one', 'two']
    rows = [r['latest'] for r in situation.snapshot()['observations']
            if r['latest']['subject']['kind'] == 'tool_failure']
    assert len(rows) == 1 and rows[0]['basis'] == 'tool_claim'
    assert 'items' in rows[0]['value']['fields']
    ref = rows[0]['source_ref']
    stored = json.loads(supervisor.store.read_evidence(ref['id'], limit=None)['text'])
    assert stored['value']['nested']['details']['tool_result']['items'] == ['one', 'two']
    assert ref['path'] == ['value', 'nested', 'details', 'tool_result']
    incidents = situation.recovery_view()
    assert incidents and all(requires_attention(row) for row in incidents)
    for row in incidents:
        assert row['revision'] == 1  # supervisor/bridge do not overwrite with display refs
        assert row['detail']['reported_results'][0]['source_ref'] == {
            'id': ref['id'], 'path': ref['path']}
        assert row['detail']['effect_scope'] == 'effect_confirmation_not_returned_data'
        assert row['effect'] == 'unknown'  # claims are not independent effect proofs
    assert 'must-not-leak' not in json.dumps(situation.snapshot())
    assert not situation.result_sources and not situation.call_inputs


def test_result_handoff_is_call_scoped_and_cleared_on_exception(monkeypatch):
    import execution_situation as es
    situation = es.Situation('owner', 'task', lambda *a, **kw: None, lambda v: {'id': 'e'})
    monkeypatch.setattr(es, 'current', lambda *a, **kw: situation)
    with pytest.raises(RuntimeError):
        with es.tool_call('write', {}, call_id='one'):
            situation.retain_result('unrelated', {'items': [0]}, {'id': 'wrong'})
            assert not situation.result_sources
            situation.retain_result('one', {'items': [1]}, {'id': 'original'})
            raise RuntimeError('transport lost')
    assert not situation.result_sources
    assert situation.recovery_view()[0]['signal'] == 'result_missing'
    es.run_tool('read', {}, lambda: {'items': [2]})
    assert not situation.result_sources


def test_nested_projection_cannot_replace_a_different_outer_result(monkeypatch):
    import execution_situation as es
    s = es.Situation('owner', 'task', lambda *a, **kw: None, lambda v: {'id': 'e'})
    monkeypatch.setattr(es, 'current', lambda *a, **kw: s)
    observed = []
    s.on_result = lambda value, ref, key: observed.append(value)

    def produce():
        s.retain_result(es.active_call_id(), {'inner': [1]}, {'id': 'inner'}, display={'preview': 1})
        return json.dumps({'success': False, 'error': 'outer failed'})

    result = es.run_tool('outer', {}, produce)
    assert observed == [result] and not s.result_sources
