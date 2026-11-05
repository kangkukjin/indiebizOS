"""10/4 실사용의 의미 증거·출력 회수·적용 후 상태 경계 회귀."""
import boot_paths  # noqa: F401
import hashlib
import json
import shlex
import subprocess
import sys
from types import SimpleNamespace

import pytest
import repair_policy as policy
from test_repair_receipt_flow import repair  # noqa: F401
from test_repair_workspace_completion import setup, module  # noqa: F401
from test_conscious_supervisor import supervisor  # noqa: F401
from test_repair_capability_parity import repair_handler  # noqa: F401


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
    ('failed', 1, False, 1), ('failed', 2, False, 1),
    ('running', 1, False, 0), ('failed', 1, True, 1),
])
def test_explicit_probe_retry_does_not_require_environment_version_change(
        setup, monkeypatch, state, version, drift, runs):
    from repair_live_probe import ENVIRONMENT_VERSION
    root, wt, st, session = setup
    command = 'read-only probe'
    record = {'state': state, 'command_sha256': hashlib.sha256(command.encode()).hexdigest(),
              'receipt': {'exit_code': 1, 'environment_version': ENVIRONMENT_VERSION - (version == 1)}}
    session.update(activation_commands={'active_verify_cmd': command},
                   activation_checks={'active_verify_cmd': record},
                   sealed={'a.txt': {'after': st._candidate.fingerprint(root / 'a.txt')}})
    if drift:
        (root / 'a.txt').write_text('concurrent edit')
    calls = []
    def probe(*args, **kwargs):
        calls.append(1)
        return {'exit_code': 0, 'environment_version': ENVIRONMENT_VERSION}
    monkeypatch.setattr('red_apply._run_post_verify', probe)
    st._candidate.activation_plan(session, {})  # Only explicit apply requests a fresh attempt.
    result = st._candidate.activation(str(root), session, 'active_verify_cmd', command, st._save_session)
    assert len(calls) == runs
    if runs:
        assert result['state'] == 'passed'
        assert session['activation_history']['active_verify_cmd'] == [record]
    else:
        assert result['state'] == state
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
    failure = session['activation_checks']['active_verify_cmd']
    def activation(repo, current, field, command, save):
        current.setdefault('activation_checks', {})[field] = failure
        return failure
    monkeypatch.setattr(st._candidate, 'activation', activation)
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
def test_completed_probe_is_not_automatically_retried(setup, monkeypatch, receipt):
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
    monkeypatch.setattr(st._candidate, 'commit', lambda *a: {'success': False, 'error': 'index busy'})
    failed = st.op_apply({'_repo_root': str(root), '_grant_key': session['key']})
    assert failed['stage'] == 'commit' and failed['recovery']['action'] == 'retry_apply'
    monkeypatch.setattr(st._candidate, 'commit', lambda *a: {'success': True, 'commit': 'abc1234'})
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
