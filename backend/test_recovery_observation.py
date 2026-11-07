"""The real supervisor's optional decisions retain evidence and goal scope."""
import json

import boot_paths  # noqa: F401
import pytest
from recovery_observation import observe, assess, configure
from recovery_projection import requires_attention
from supervision_store import digest
from test_conscious_supervisor import supervisor, verdict, trigger_verdict  # noqa: F401


def failed(controller):
    key = controller._start('write', {'path': '/report'})
    controller._finish(key, {'success': False, 'error': 'output unavailable'}, True)
    row = controller.recovery.view()[0]
    ref = controller.store.evidence({'alternative': 'complete report'})['id']
    return {'incident_ref': row['incident_ref'], 'incident_revision': row['revision'],
            'disposition': 'satisfied', 'basis_refs': [ref], 'reason': 'alternative output satisfies the request'}


def test_existing_review_consumes_optional_assessment_without_certifying_goal(supervisor, monkeypatch):
    decision = failed(supervisor)
    monkeypatch.setattr('supervisor_runtime.invoke', lambda c, *a, **kw: verdict(
        c, incident_assessments=[decision]))
    supervisor.review('milestone', paused=True)
    row = supervisor.recovery.view()[0]
    assert row['assessment']['actor'] == supervisor.supervisor_id
    assert row['resolution'] == 'unresolved' and not requires_attention(row)
    assert supervisor.framing['criteria'] == [{'text': '실제 증거 확인'}]


def test_continue_assessment_keeps_its_own_corrective_instruction(supervisor, monkeypatch):
    decision = failed(supervisor)
    decision['disposition'] = 'continue'
    def review(c, *a, **kw):
        result = json.loads(trigger_verdict(c, 'use another available writer'))
        result['incident_assessments'] = [decision]
        return json.dumps(result)
    monkeypatch.setattr('supervisor_runtime.invoke', review)
    supervisor.review('milestone', paused=True)
    assert supervisor.boundary() is not None
    assert requires_attention(supervisor.recovery.view()[0])


@pytest.mark.parametrize('change', ['goal', 'reference', 'revision', 'cancel'])
def test_stale_review_cannot_settle_incident(supervisor, monkeypatch, change):
    decision = failed(supervisor)
    goal = digest(json.dumps(supervisor.framing, sort_keys=True, ensure_ascii=False))
    if change == 'goal':
        supervisor.framing['achievement_criteria'] = 'new criterion'
    elif change == 'reference':
        decision['basis_refs'] = ['another-store-reference']
    elif change == 'revision':
        decision['incident_revision'] -= 1
    else:
        monkeypatch.setattr(supervisor, 'cancelled', lambda: True)
    assess(supervisor, {'incident_assessments': [decision]}, goal)
    assert requires_attention(supervisor.recovery.view()[0])
    assert supervisor.recovery.view()[0]['assessment'] is None


def test_shared_callback_delivers_each_fact_once(supervisor):
    from execution_situation import Situation
    situation = Situation(supervisor.recovery.owner, supervisor.task,
                          lambda *a, **kw: None, supervisor.store.evidence)
    configure(situation, supervisor.recovery)
    payload, result = {}, {'success': False}
    situation.tool_started('one', 'write', payload)
    situation.tool_finished('one', result, error=True)
    observe(supervisor.recovery, 'one', 'write', payload, result,
            supervisor.store.evidence(result), error=True)
    assert len(supervisor.recovery.view()) == 1
    assert supervisor.recovery.view()[0]['revision'] == 1


def test_raw_ibl_evidence_preserves_collected_failure(supervisor):
    observe(supervisor.recovery, 'batch', 'execute_ibl', {}, {
        'success': True, 'evidence': [
            {'kind': 'tool_failure', 'id': 'source', 'incomplete': True},
            {'kind': 'tool_evidence', 'operation_outcomes': [{'id': 'op', 'status': 'failed'}]},
        ]}, {'id': 'raw-result'})
    rows = supervisor.recovery.view()
    assert len(rows) == 3 and all(requires_attention(row) for row in rows)
    assert rows[0]['detail']['operation_ref'] == 'op'


@pytest.mark.parametrize('change_before_assessment', [True, False])
def test_snapshot_judgment_requires_current_source_version(supervisor, monkeypatch, change_before_assessment):
    from execution_situation import Situation
    situation = Situation(supervisor.recovery.owner, supervisor.task,
                          lambda *a, **kw: None, supervisor.store.evidence)
    configure(situation, supervisor.recovery)
    monkeypatch.setattr('execution_situation.current', lambda *a, **kw: situation)
    decision = failed(supervisor)
    subject = {'kind': 'file', 'address': '/report', 'device': 'local'}
    situation.observe(subject, 'version', {}, source='file_io', subject_revision='v1')
    decision['basis_refs'] = [supervisor.store.evidence(situation.snapshot())['id']]
    def changed():
        situation.observe(subject, 'version', {}, source='file_io', subject_revision='v2')
    if change_before_assessment:
        changed()
    assess(supervisor, {'incident_assessments': [decision]},
           digest(json.dumps(supervisor.framing, sort_keys=True, ensure_ascii=False)))
    if not change_before_assessment:
        assert not requires_attention(supervisor.recovery.view()[0])
        changed()
    assert requires_attention(supervisor.recovery.view()[0])


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
