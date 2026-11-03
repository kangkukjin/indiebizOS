"""Failure/effect ownership, revision-checked judgments and bounded continuation."""
import boot_paths  # noqa: F401
import pytest

from recovery_projection import RecoveryProjection, requires_attention
from recovery_observation import observe


@pytest.fixture
def recovery():
    return RecoveryProjection('owner', 'task')


def failure(r, key='failed', **kw):
    observe(r, key, 'write', {}, {'success': False}, {'id': key}, **kw)
    return r.view()[-1]


def test_unrelated_success_and_duplicate_delivery_do_not_change_failure(recovery):
    row = failure(recovery)
    failure(recovery)
    observe(recovery, 'read', 'guide', {}, {'success': True}, {'id': 'guide'})
    assert recovery.view() == [row]
    assert requires_attention(row)


def test_partial_envelope_keeps_operation_and_source_failures(recovery):
    observe(recovery, 'batch', 'execute_ibl', {}, {'success': True, 'evidence_summary': {
        'source_failures': 1, 'operation_outcomes': [{'id': 'a', 'status': 'passed'},
                                                  {'id': 'b', 'status': 'failed'}]}}, {'id': 'result'})
    rows = recovery.view()
    assert len(rows) == 2 and all(requires_attention(r) for r in rows)
    assert rows[0]['detail']['operation_ref'] == 'b'


def test_successful_text_and_default_unknown_effect_are_not_failures(recovery):
    for value in ({'success': True, 'items': [{'error': 'quoted example'}]},
                  {'success': True, 'effect': 'unknown'}, {'items': []}):
        observe(recovery, 'read', 'read', {}, value, {'id': 'read'})
    assert recovery.view() == []


def test_receipt_resolves_only_its_operation_and_rejects_old_success(recovery):
    subject = {'kind': 'task', 'ref': {'kind': 'remote', 'task_id': 'one', 'owner': 'device-a'}}
    recovery.receipt(subject, {'state': 'running'}, {'task_ref': subject['ref']}, call_id='lost', cursor=1)
    row = failure(recovery, 'lost', unknown=True)
    failure(recovery, 'unrelated')
    recovery.receipt(subject, {'state': 'running'}, {}, cursor=2)
    assert all(requires_attention(r) for r in recovery.view())
    recovery.receipt(subject, {'state': 'succeeded'}, {}, cursor=1)
    assert all(requires_attention(r) for r in recovery.view())
    recovery.receipt(subject, {'state': 'succeeded'}, {}, cursor=3)
    rows = {r['incident_ref']: r for r in recovery.view()}
    assert not requires_attention(rows[row['incident_ref']])
    assert requires_attention(recovery.view()[1])


def test_decision_is_attributed_not_verified_and_stale_or_foreign_refs_rejected(recovery):
    row = failure(recovery)
    decision = {'incident_ref': row['incident_ref'], 'incident_revision': row['revision'],
                'disposition': 'irrelevant', 'basis_refs': ['proof'], 'reason': 'answer uses another source'}
    assert not recovery.assess(decision, actor='supervisor', valid_refs=set())
    assert recovery.assess(decision, actor='supervisor', valid_refs={'proof'})
    current = recovery.view()[0]
    assert current['resolution'] == 'unresolved' and not requires_attention(current)
    assert current['assessment']['basis'] == 'model_judgment'
    assert not recovery.assess(decision, actor='supervisor', valid_refs={'proof'})
    recovery.invalidate({'proof'})
    assert requires_attention(recovery.view()[0])
    decision.update(incident_revision=recovery.view()[0]['revision'], basis_refs=['fresh'])
    assert recovery.assess(decision, actor='supervisor', valid_refs={'fresh'})
    assert not requires_attention(recovery.view()[0])
    assert recovery.view()[0]['resolution'] == 'unresolved'


def test_pre_execution_resolution_does_not_resolve_runtime_failure(recovery):
    recovery.observe('compile', [{'signal': 'failure', 'pre_execution': True}], {'id': 'bad'}, repair_key='shape')
    recovery.observe('runtime', [{'signal': 'failure'}], {'id': 'runtime'}, repair_key='shape')
    recovery.resolve_pre_execution('shape', {'id': 'executed'})
    assert [requires_attention(r) for r in recovery.view()] == [False, True]


def test_poll_receipt_without_active_call_can_later_resolve(recovery):
    subject = {'kind': 'task', 'ref': {'kind': 'remote', 'task_id': 'one'}}
    recovery.receipt(subject, {'state': 'interrupted'}, {}, cursor=1)
    assert requires_attention(recovery.view()[0])
    recovery.receipt(subject, {'state': 'succeeded'}, {}, cursor=2)
    assert not requires_attention(recovery.view()[0])


def test_batch_receipt_success_cannot_resolve_another_operation_or_whole_call(recovery):
    a, b = {'kind': 'task', 'id': 'a'}, {'kind': 'task', 'id': 'b'}
    recovery.receipt(a, {'state': 'running'}, {}, call_id='batch', cursor=1)
    root = failure(recovery, 'batch', unknown=True)['incident_ref']
    recovery.receipt(b, {'state': 'failed'}, {}, call_id='batch', cursor=1)
    recovery.receipt(a, {'state': 'failed'}, {}, call_id='batch', cursor=2)
    recovery.receipt(b, {'state': 'succeeded'}, {}, call_id='poll', cursor=2)
    rows = recovery.view()
    assert len(rows) == 3
    assert requires_attention(next(r for r in rows if r['incident_ref'] == root))
    assert requires_attention(next(r for r in rows if r['receipt_subject'] == a))
    assert not requires_attention(next(r for r in rows if r['receipt_subject'] == b))


def test_restore_requires_same_owner_and_deduplicates(recovery):
    failure(recovery)
    snapshot = recovery.snapshot()
    other = RecoveryProjection('different', 'task')
    with pytest.raises(ValueError):
        other.restore(snapshot)
    resumed = RecoveryProjection('owner', 'next')
    resumed.restore(snapshot)
    resumed.restore(snapshot)
    assert len(resumed.view()) == 1
    assert resumed.view()[0]['origin']['task'] == 'task'


def test_restored_receipt_requires_new_observation_not_old_success(recovery):
    subject = {'kind': 'task', 'id': 'work'}
    recovery.receipt(subject, {'state': 'failed'}, {}, cursor=2)
    recovery.receipt(subject, {'state': 'succeeded'}, {}, cursor=3)
    resumed = RecoveryProjection('owner', 'resumed')
    resumed.restore(recovery.snapshot())
    for cursor in (1, 3):
        resumed.receipt(subject, {'state': 'succeeded'}, {}, cursor=cursor)
        assert requires_attention(resumed.view()[0])
    resumed.receipt(subject, {'state': 'succeeded'}, {}, cursor=4)
    assert not requires_attention(resumed.view()[0])


def test_overflow_keeps_an_unknown_range_instead_of_claiming_success(recovery, monkeypatch):
    monkeypatch.setattr('recovery_projection.MAX_INCIDENTS', 2)
    for i in range(10):
        failure(recovery, str(i))
    rows = recovery.view()
    assert len(rows) == 3 and rows[-1]['signal'] == 'unobserved_range'
    assert requires_attention(rows[-1])


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
