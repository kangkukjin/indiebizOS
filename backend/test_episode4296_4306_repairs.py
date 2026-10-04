"""10/4 실사용의 의미 증거·출력 회수·적용 후 상태 경계 회귀."""
import boot_paths  # noqa: F401
import hashlib
import json
import subprocess
import sys
from types import SimpleNamespace

import pytest
import repair_policy as policy
from test_repair_receipt_flow import repair  # noqa: F401
from test_repair_workspace_completion import setup, module  # noqa: F401
from test_conscious_supervisor import supervisor  # noqa: F401
from test_repair_capability_parity import repair_handler  # noqa: F401


def observation(st, root, wt, session):
    stamp = st._candidate.digest(st._candidate.collect(str(root), session))
    return {'id': 'check-1', 'status': 'passed', 'candidate_hash': stamp,
            'before_hash': stamp, 'environment_hash': st._candidate.environment(wt),
            'output': 'rendered current candidate', 'evidence_ref': {'id': 'check-ref'}}


@pytest.mark.parametrize('anchor', ['check-1', 'check-ref'])
def test_semantic_mixed_check_and_visual_evidence_apply(repair, monkeypatch, anchor):
    root, wt, st, session, controller = repair
    (wt / 'a.txt').write_text('fixed')
    session['execution_checks'] = [observation(st, root, wt, session)]
    visual = controller.store.evidence({'observation': 'actual image comparison'})['id']
    monkeypatch.setattr(controller.store, 'tool_index', lambda **kw: [
        {'is_error': False, 'result': {'id': visual}}])
    monkeypatch.setattr(policy, 'semantic_review', lambda *a: {'status': 'APPROVED', 'reason': 'ACHIEVED',
        'workspace_coverage': [{'criterion_id': 'C1', 'status': 'passed', 'evidence_ids': [anchor, visual]}]})
    st._save_session(str(root), session)
    result = st.op_apply({'_repo_root': str(root), '_grant_key': session['key'],
                         'verification_plan': [{'criterion_id': 'C1', 'method': 'semantic'}]})
    assert result['complete'], result
    saved = st.read_session(str(root), session['key'])
    coverage = saved['readiness']['decision']['workspace_coverage'][0]
    assert coverage['evidence_ids'] == ['check-1']
    assert coverage['supporting_evidence_ids'] == [visual]
    assert policy.completion(saved, {}, root)[0]


@pytest.mark.parametrize('case', ['forged', 'stale', 'no_check'])
def test_semantic_invalid_evidence_never_looks_achieved(repair, monkeypatch, case):
    root, wt, st, session, controller = repair
    (wt / 'a.txt').write_text('fixed')
    record = observation(st, root, wt, session)
    if case == 'stale':
        record['candidate_hash'] = record['before_hash'] = 'old'
    session['execution_checks'] = [record]
    monkeypatch.setattr(policy, 'semantic_review', lambda *a: {'status': 'APPROVED', 'reason': 'ACHIEVED',
        'workspace_coverage': [{'criterion_id': 'C1', 'status': 'passed',
                               'evidence_ids': ['forged'] if case == 'no_check' else ['check-1', 'forged']}]})
    session['verification_plan'] = [{'criterion_id': 'C1', 'method': 'semantic'}]
    result = policy.prepare(controller, str(root), session, st.verify, st._candidate)
    assert not result['success'] and result['error'] != 'ACHIEVED'
    assert result['missing_criteria'] == ['C1'] and result['invalid_evidence']
    assert (root / 'a.txt').read_text() == 'before'


def test_new_supporting_evidence_invalidates_cached_semantic_failure(repair, monkeypatch):
    root, wt, st, session, controller = repair
    session['verification_plan'] = [{'criterion_id': 'C1', 'method': 'semantic'}]
    rows, calls = [], []
    monkeypatch.setattr(controller.store, 'tool_index', lambda **kw: rows)
    monkeypatch.setattr(policy, 'semantic_review', lambda *a: calls.append(1) or {'status': 'UNKNOWN'})
    for _ in range(2):
        policy.prepare(controller, str(root), session, st.verify, st._candidate)
    assert len(calls) == 1
    rows.append({'result': {'id': 'new-image'}})
    policy.prepare(controller, str(root), session, st.verify, st._candidate)
    assert len(calls) == 2


def test_final_repair_marker_overrides_intermediate_semantic_verdict():
    from episode_logger import _final_evaluation_result
    assert _final_evaluation_result('[GoalEval] 최종 판정: ACHIEVED\n[RepairCheck] 최종 판정: UNKNOWN') == 'UNKNOWN'
    assert _final_evaluation_result('[RepairCheck] 최종 판정: ACHIEVED') == 'ACHIEVED'


def test_oversized_shell_output_recovers_without_protected_path(repair, monkeypatch):
    from ibl_result_transport import fit_tool_result
    from model_result_view import read_result
    from common import spill
    root, wt, st, session, controller = repair
    scope = module('repair_tool_scope')
    raw = {'success': False, 'output': 'original failure\n' * 10000, 'exit_code': 1}
    result = scope.shell_result(dict(raw), controller)
    monkeypatch.setattr(spill, 'spill_write', lambda *a, **kw: pytest.fail('unreadable spill path'))
    shown = json.loads(fit_tool_result(json.dumps(result), 4000))
    assert shown['success'] is False
    ref = shown['result_ref']
    pieces, query = [], ref['read_args']
    while query:
        page = read_result(query)
        pieces.append(page['text'])
        query = page['next_read']
    assert ''.join(pieces) == raw['output']
    assert 'path' not in shown['ref']


@pytest.mark.parametrize('state', ['applied', 'apply_scheduled'])
def test_candidate_read_does_not_reopen(repair_handler, setup, state):
    from thread_context import repair_workspace_scope
    root, wt, st, session = setup
    session['status'] = state
    st._save_session(str(root), session)
    with repair_workspace_scope(str(wt)):
        result = repair_handler.execute({'path': 'a.txt'},
            SimpleNamespace(tool_name='read_op', project_path=str(root), agent_id='owner'))
    assert 'before' in str(result)
    assert st.read_session(str(root), session['key'])['status'] == state
    if state == 'applied':
        with pytest.raises(RuntimeError):
            st.ensure_session(str(root), session['key'])


@pytest.mark.parametrize('state,version,drift,runs', [
    ('failed', 1, False, 1), ('failed', 2, False, 0),
    ('running', 1, False, 0), ('failed', 1, True, 0),
])
def test_activation_retry_requires_new_environment_and_unchanged_files(
        setup, monkeypatch, state, version, drift, runs):
    from repair_live_probe import ENVIRONMENT_VERSION
    root, wt, st, session = setup
    command = 'read-only probe'
    record = {'state': state, 'command_sha256': hashlib.sha256(command.encode()).hexdigest(),
              'receipt': {'exit_code': 1, 'environment_version': ENVIRONMENT_VERSION - (version == 1)}}
    session.update(activation_checks={'active_verify_cmd': record},
                   sealed={'a.txt': {'after': st._candidate.fingerprint(root / 'a.txt')}})
    if drift:
        (root / 'a.txt').write_text('concurrent edit')
    calls = []
    def probe(*args, **kwargs):
        calls.append(1)
        return {'exit_code': 0, 'environment_version': ENVIRONMENT_VERSION}
    monkeypatch.setattr('red_apply._run_post_verify', probe)
    result = st._candidate.activation(str(root), session, 'active_verify_cmd', command, st._save_session)
    assert len(calls) == runs
    if runs:
        assert result['state'] == 'passed'
        assert session['activation_history']['active_verify_cmd'] == [record]
    else:
        assert result['state'] == ('conflict' if drift else state)
    st._candidate.activation(str(root), session, 'active_verify_cmd', command, st._save_session)
    assert len(calls) == runs


def test_activation_failure_keeps_cause_through_ibl_and_status(repair, monkeypatch):
    from ibl_v2_adapters import decode_envelope
    from ibl_v2_ir import Fault
    root, wt, st, session, controller = repair
    session.update(status='applied', verified=True, readiness={'decision': {'status': 'APPROVED'},
        'activation_commands': {'active_verify_cmd': 'probe'}}, activation_checks={
        'active_verify_cmd': {'state': 'failed', 'receipt': {'exit_code': 1, 'output': '403 != 200'}}})
    st._save_session(str(root), session)
    monkeypatch.setattr(st._candidate, 'activation', lambda *a: session['activation_checks']['active_verify_cmd'])
    result = st._complete_immediate(str(root), session, {'success': True, 'applied': True}, {})
    assert not result['success'] and result['applied'] and result['stage'] == 'activation'
    assert '403 != 200' in result['error']
    assert result['activation']['state'] == 'failed'
    assert result['activation_checks']['active_verify_cmd'] == result['activation']
    with pytest.raises(Fault) as exc:
        decode_envelope(result, {})
    assert exc.value.details['applied'] and exc.value.details['activation']
    status = st.op_status({'_repo_root': str(root), '_grant_key': session['key'], 'key': session['key']})
    rows, _ = decode_envelope(status, {'value_path': '/items'})
    assert len(rows) == 1 and rows[0]['stage'] == 'activation'
    assert '403 != 200' in rows[0]['last_error']


@pytest.mark.parametrize('receipt', [
    {'exit_code': None}, {'exit_code': 1, 'effect_unknown': True},
    {'exit_code': 1, 'timed_out': True},
])
def test_activation_unknown_outcome_is_never_retried(setup, monkeypatch, receipt):
    root, wt, st, session = setup
    command = 'probe'
    record = {'state': 'failed', 'command_sha256': hashlib.sha256(command.encode()).hexdigest(),
              'receipt': {**receipt, 'environment_version': 1}}
    session.update(activation_checks={'active_verify_cmd': record},
                   sealed={'a.txt': {'after': st._candidate.fingerprint(root / 'a.txt')}})
    monkeypatch.setattr('red_apply._run_post_verify', lambda *a, **kw: pytest.fail('unknown result replay'))
    assert st._candidate.activation(str(root), session, 'active_verify_cmd', command, st._save_session) == record


def test_commit_retry_does_not_reapply_files(repair, monkeypatch):
    root, wt, st, session, controller = repair
    session.update(status='applied', verified=True, readiness={'decision': {'status': 'APPROVED'}},
                   commit={'success': False, 'error': 'index busy'})
    st._save_session(str(root), session)
    monkeypatch.setattr(st, '_perform_apply', lambda *a: pytest.fail('duplicate write'))
    monkeypatch.setattr(st, 'commit_applied', lambda *a: {'success': False, 'error': 'index busy'})
    failed = st.op_apply({'_repo_root': str(root), '_grant_key': session['key']})
    assert failed['stage'] == 'commit' and failed['recovery']['action'] == 'retry_apply'
    monkeypatch.setattr(st, 'commit_applied', lambda *a: {'success': True, 'commit': 'abc1234'})
    assert st.op_apply({'_repo_root': str(root), '_grant_key': session['key']})['complete']


def test_preparation_fetch_is_host_owned_once(setup, tmp_path):
    root, wt, st, session = setup
    remote = tmp_path / 'remote.git'
    subprocess.run(['git', 'init', '--bare', '-q', str(remote)], check=True)
    subprocess.run(['git', 'remote', 'add', 'origin', str(remote)], cwd=root, check=True)
    subprocess.run(['git', 'push', '-q', 'origin', 'HEAD:main'], cwd=root, check=True)
    first = st.ensure_session(str(root), 'fresh')
    evidence = first['repository_baseline']
    assert evidence['fetch_status'] == 'ok' and evidence['behind_origin_main'] == 0
    assert evidence['live_head'] == evidence['origin_main']
    assert st.ensure_session(str(root), 'fresh')['repository_baseline'] == evidence


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
