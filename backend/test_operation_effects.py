"""Effect claims preserve identity, failures and exact source paths without text promotion."""
import json

import boot_paths  # noqa: F401
import pytest
from operation_effects import bind, collect, make, summaries, valid


def observation(**kw):
    args = dict(driver='test_driver', implementation=__file__, resource={'kind': 'setting', 'id': 'volume'},
                scope='os_setting', requested={'volume': 3}, actual={'volume': 3},
                checks=[{'name': 'volume', 'matched': True}], request_id='request', step_id='step')
    return make(**{**args, **kw})


def test_unknown_partial_and_mismatch_are_not_confirmed():
    assert observation(checks=[{'name': 'one', 'matched': None}])['status'] == 'unknown'
    assert observation(checks=[{'name': 'one', 'matched': False}])['status'] == 'mismatch'
    assert not valid({**observation(), 'checks': []})
    assert not valid({**observation(), 'checks': [{'name': 'one', 'matched': 1}]})
    assert not valid({**observation(), 'contract': 'operation-effect/2'})


def test_collect_never_promotes_stdout_and_retains_failed_partial():
    obs = observation()
    value = {'success': False, 'output': json.dumps({'observation': obs}),
             'diagnostic': {'details': {'execution_result': {'stopped': {'observation': obs}}}}}
    rows, _ = collect(value)
    assert len(rows) == 1
    assert rows[0][0] == ['diagnostic', 'details', 'execution_result', 'stopped', 'observation']
    assert collect({'output': json.dumps(obs)}) == ([], 0)


def test_binding_does_not_mutate_original_or_hide_identity_conflict():
    obs = observation(target={'device_id': 'other', 'generation': 'old'})
    raw = {'value': {'observation': obs}}
    result = bind(raw, device='device', generation='gen', job_id='job', request_id='req', received_at=123)
    effect = result['value']['observation']
    assert obs['status'] == 'confirmed'
    assert effect['status'] == 'unknown' and effect['reason'] == 'observation_target_conflict'
    assert effect['target']['device_id'] == 'other'
    assert effect['transport_ref']['device_id'] == 'device'


def test_duplicate_delivery_preserves_receipt_and_source_path():
    obs = observation()
    raw = bind({'value': {'observation': obs}}, device='device', generation='gen', job_id='job', request_id='req', received_at=123)
    rows, omitted = summaries({'value': raw, 'details': raw}, {'id': 'evidence'})
    assert len(rows) == 1 and not omitted
    assert rows[0]['source_ref']['path'] == ['value', 'value', 'observation']
    assert rows[0]['basis'] == 'driver_report'
    assert rows[0]['target'] == {'device_id': 'device', 'generation': 'gen'}


def test_situation_folds_same_observation_from_sync_and_watcher():
    from execution_situation import Situation
    from situation_evidence import observe_result
    situation = Situation('owner', 'task', lambda *a, **kw: None, lambda v: {'id': 'e'})
    obs = observation()
    observe_result(situation, {'value': {'observation': obs}}, {'id': 'sync'}, 'call')
    observe_result(situation, {'result': {'observation': obs}}, {'id': 'watch'}, 'resident:job')
    records = [r for r in situation.snapshot()['observations'] if r['latest']['facet'] == 'reported_effect']
    assert len(records) == 1
    assert records[0]["latest"]["basis"] == "tool_claim"


def test_malformed_status_does_not_break_model_result_projection():
    assert not valid({**observation(), 'status': {'unexpected': True}})


def test_effect_survives_large_result_preview_with_exact_reference(tmp_path, monkeypatch):
    from supervision_store import TurnStore
    import model_result_view as view
    store = TurnStore(tmp_path / 'evidence')
    monkeypatch.setattr(view, 'evidence_store', lambda: store)
    obs = observation()
    original = {'edition': 2, 'success': False, 'diagnostic': {'details': {
        'execution_result': {'verbose': 'x' * 25000, 'observation': obs}}}}
    shown = view.project_result(original)
    assert shown['operation_observations'][0]['status'] == 'confirmed'
    assert shown['operation_observations'][0]['source_ref']['path'] == [
        'diagnostic', 'details', 'execution_result', 'observation']
    assert shown['success'] is False
    assert original['diagnostic']['details']['execution_result']['observation'] == obs


def test_failure_conversion_preserves_local_and_nested_remote_observation():
    import pytest
    from ibl_v2_adapters import decode_envelope
    from ibl_v2_ir import Fault
    obs = observation(status='unknown', reason='readback_failed')
    for extra in ({'observation': obs}, {'details': {'execution_result': {'observation': obs}}}):
        with pytest.raises(Fault) as raised:
            decode_envelope({'success': False, 'error': 'failed', **extra}, {'protocol': 'legacy-envelope'})
        rows, _ = collect(raised.value.details)
        assert len(rows) == 1 and rows[0][1]['status'] == 'unknown'


def test_existing_verification_reuses_producer_time_and_step_identity():
    from operation_effects import verified_result, identity
    value = {'verified': True, 'volume': 3, 'observed_at': '2026-11-08T01:00:00+00:00'}
    args = dict(driver='test', implementation=__file__, requested={'action': 'volume', 'value': 3},
                request_id='request', target='device', scope='os_setting')
    first = verified_result(value, **args)['observation']
    second = verified_result(value, **args)['observation']
    assert identity(first) == identity(second)
    assert first['observed_at'] == value['observed_at']


# ── 허브 검증 결과의 운반 근거: 원 접수의 기기·세대·job, 장치 보고 결속과 구별 ──

def test_hub_verification_keeps_original_job_and_is_distinct_from_device_report_binding():
    from operation_effects import carried, verified_result
    accepted = {'limb': 'pc-1', 'generation': 'gen-job', 'request_id': 'req-1',
                'task_ref': {'kind': 'guestpc', 'task_id': 'job-1'}}
    ledger = {'task_ref': accepted['task_ref'], 'limb': 'pc-1', 'generation': 'gen-job',
              'request_id': 'req-1', 'result_received_at': 1700000000.5, 'state': 'succeeded'}
    transport, conflict = carried(accepted, ledger)
    assert conflict is None
    assert transport == {'device_id': 'pc-1', 'generation': 'gen-job', 'job_id': 'job-1', 'request_id': 'req-1',
                         'received_at': 1700000000.5, 'basis': 'hub_task_ledger',
                         'result_ref': {'task_ref': accepted['task_ref']}}
    value = verified_result({'verified': True, 'volume': 3}, driver='test', implementation=__file__,
                            requested={'action': 'volume', 'value': 3}, request_id='req-1', target='pc-1',
                            scope='os_setting', transport=transport,
                            resource={'kind': 'audio_output', 'id': 'out-7'})
    obs = value['observation']
    assert valid(obs) and obs['status'] == 'confirmed'
    assert obs['target'] == {'device_id': 'pc-1', 'generation': 'gen-job'}  # 조회 시점 등록값이 아니라 원 job 의 세대
    assert obs['resource'] == {'kind': 'audio_output', 'id': 'out-7'}
    assert obs['source']['driver'] == 'test' and obs['source']['method'] == 'existing_driver_verification'
    # 장치의 원 보고를 결속하는 bind 의 basis 와 섞이지 않는다.
    reported = bind({'observation': observation()}, device='pc-1', generation='gen-job', job_id='job-1',
                    request_id='req-1', received_at=1.0)['observation']
    assert reported['transport_ref']['basis'] == 'authenticated_job_report' != obs['transport_ref']['basis']


@pytest.mark.parametrize('field,other', [('limb', 'pc-2'), ('generation', 'gen-new'), ('request_id', 'req-2'),
                                         ('task_ref', {'kind': 'guestpc', 'task_id': 'job-2'})])
def test_mixed_job_device_or_generation_is_a_conflict_not_a_merge(field, other):
    from operation_effects import carried
    accepted = {'limb': 'pc-1', 'generation': 'gen-job', 'request_id': 'req-1',
                'task_ref': {'kind': 'guestpc', 'task_id': 'job-1'}}
    ledger = {'task_ref': accepted['task_ref'], 'limb': 'pc-1', 'generation': 'gen-job', 'request_id': 'req-1',
              field: other}
    transport, conflict = carried(accepted, ledger)
    assert conflict and conflict.startswith('transport_') and transport['basis'] == 'accepted_receipt'


def test_receipt_without_generation_is_limited_evidence_and_action_name_is_not_an_identity():
    from operation_effects import carried, verified_result
    old = {'limb': 'pc-1', 'request_id': 'req-1', 'task_ref': {'kind': 'guestpc', 'task_id': 'job-1'}}
    transport, conflict = carried(old)
    assert conflict is None and transport['generation'] is None and transport['basis'] == 'accepted_receipt'
    assert transport['received_at'] is None
    obs = verified_result({'verified': None}, driver='test', implementation=__file__,
                          requested={'action': 'clipboard'}, request_id='req-1', target='pc-1',
                          scope='driver_postcondition', transport=transport)['observation']
    assert obs['status'] == 'unknown' and obs['target']['generation'] is None  # 미검증을 confirmed 로 올리지 않는다
    assert obs['resource'] == {'kind': 'device_control', 'id': None, 'action': 'clipboard',
                               'identity': 'not_reported_by_driver'}
    # 원장이 아는 세대는 구형 영수증의 빈 칸만 채운다.
    filled, _ = carried(old, {'task_ref': old['task_ref'], 'generation': 'gen-job', 'result_received_at': 2.0})
    assert filled['generation'] == 'gen-job' and filled['basis'] == 'hub_task_ledger'
