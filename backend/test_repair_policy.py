"""기준의 의미 검토 소유권과 검사 중 정본 충돌의 조기 중단."""
import pytest
import shlex
import subprocess
import sys
import boot_paths  # noqa: F401
from test_repair_receipt_flow import repair  # noqa: F401
from test_repair_workspace_completion import setup  # noqa: F401
from test_conscious_supervisor import supervisor  # noqa: F401
import repair_policy as policy
import api_repair_continuation as consumer
from supervisor_handoff import criteria_contract


@pytest.mark.parametrize('publication', ['program', 'component'])
def test_published_repair_uses_same_final_receipts_without_second_model_review(repair, monkeypatch, publication):
    from test_repair_receipt_flow import command
    from thread_context import get_goal_eval_outcome
    root, wt, st, session, controller = repair
    (wt / 'a.txt').write_text('fixed')
    probe = shlex.quote(sys.executable) + ' -c ' + shlex.quote(
        'from pathlib import Path; assert Path("a.txt").read_text() == "fixed"')
    applied = st.op_apply({'_repo_root': str(root), '_grant_key': session['key'],
                          'active_verify_cmd': probe,
                          'verification_plan': [{'criterion_id': 'C1', 'command': command(wt)}]})
    assert applied['complete'], applied
    saved = st.read_session(str(root), session['key'])
    saved[publication + '_activation'] = [{'activation': 'active'}]
    st._save_session(str(root), saved)
    monkeypatch.setattr('repair_readiness.' + publication + '_published', lambda *a: True)
    monkeypatch.setattr(st._candidate, 'active_generation_bytes', lambda *a: ('matched', 'publication verified'))
    events = list(controller.finalize('완료', [], lambda *a, **k: pytest.fail('second model review')))
    assert events[-1]['type'] == 'final'
    assert get_goal_eval_outcome()['goal_status'] == 'ACHIEVED'


def test_retry_keeps_activation_plan_and_applied_repair_accepts_missing_probe(repair):
    from test_repair_receipt_flow import command
    root, wt, st, session, controller = repair
    (wt / 'a.txt').write_text('fixed')
    probe = shlex.quote(sys.executable) + ' -c ' + shlex.quote(
        'from pathlib import Path; assert Path("a.txt").read_text() == "fixed"')
    session['activation_commands'] = {'verify_cmd': probe}
    st._save_session(str(root), session)
    args = {'_repo_root': str(root), '_grant_key': session['key']}
    applied = st.op_apply({**args, 'verification_plan': [{'criterion_id': 'C1', 'command': command(wt)}]})
    assert applied['applied'] and applied['commit']['success'], applied
    saved = st.read_session(str(root), session['key'])
    assert saved['activation_checks']['verify_cmd']['state'] == 'passed'
    assert not policy.completion(saved, {}, root)[0]  # Functional active probe still absent.
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root)
    completed = st.op_apply({**args, 'active_verify_cmd': probe})
    assert completed['complete'], completed
    saved = st.read_session(str(root), session['key'])
    assert saved['activation_checks']['active_verify_cmd']['state'] == 'passed'
    assert policy.completion(saved, {}, root)[0]
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root) == head
    assert not st.op_apply({**args, 'active_verify_cmd': ''})['success']
    assert st.op_apply(args)['complete']  # Omission retains the successful probe.


def test_supplementary_probe_failure_does_not_repeat_publication_or_claim_completion(repair):
    from test_repair_receipt_flow import command
    root, wt, st, session, controller = repair
    (wt / 'a.txt').write_text('fixed')
    args = {'_repo_root': str(root), '_grant_key': session['key']}
    applied = st.op_apply({**args, 'verification_plan': [{'criterion_id': 'C1', 'command': command(wt)}]})
    head = applied['commit']['commit']
    failed = st.op_apply({**args, 'active_verify_cmd': shlex.quote(sys.executable) + ' -c "raise SystemExit(1)"'})
    assert failed['applied'] and not failed['complete'] and failed['stage'] == 'activation'
    assert (root / 'a.txt').read_text() == 'fixed'
    assert failed['commit']['commit'] == head
    assert not policy.completion(st.read_session(str(root), session['key']), {}, root)[0]


@pytest.mark.parametrize('entry', ['receipt', 'finalize'])
def test_unverified_symptom_cannot_close_applied_repair(repair, monkeypatch, entry):
    from test_repair_receipt_flow import command
    import repair_root
    from thread_context import get_goal_eval_outcome
    root, wt, st, session, controller = repair
    (wt / 'a.txt').write_text('fixed')
    cmd = command(wt)
    applied = st.op_apply({'_repo_root': str(root), '_grant_key': session['key'],
                           'verification_plan': [{'criterion_id': 'C1', 'command': cmd}]})
    assert applied['applied'] and applied['commit']['success']
    saved = st.read_session(str(root), session['key'])
    assert policy.symptom_recheck(saved, {}, root)[0] == 'unverified'
    assert not policy.completion(saved, {}, root)[0]
    if entry == 'receipt':
        monkeypatch.setattr(consumer, '_deliver', lambda *a, **k: pytest.fail('unverified completion notice'))
        answer = consumer._receipt_completion({'task_id': session['key'], 'repair_policy': 2,
                                               'phase': 'verify_remaining'}, root)
        assert answer['evaluation']['goal_status'] == 'UNKNOWN'
    else:
        from thread_context import actor_context
        from repair_continuation import read
        # Exercise user-requested continuation independently of prior tests.
        controller.runner.config = {'id': controller.owner}
        monkeypatch.setattr('principal.is_owner', lambda: True)
        with actor_context(origin='user'):
            policy.finalize(controller, '수정했습니다')
        assert get_goal_eval_outcome()['goal_status'] == 'UNKNOWN'
        projected = repair_root.projection(root, session['key'])
        assert projected['stage'] == 'incomplete' and projected['resume_condition']
        assert read(controller.task, root)['status'] == 'blocked'


def test_executor_cannot_downgrade_semantic_criterion(repair, monkeypatch):
    root, wt, st, session, controller = repair
    controller._final_criteria_contract = criteria_contract('전수 대조해줘', {'criteria': [
        {'text': '전수 대조와 미확인 목록', 'verification_method': 'semantic'}]})
    session['verification_plan'] = [{'criterion_id': 'C1', 'method': 'test', 'command': 'pytest test.py'}]
    monkeypatch.setattr('repair_check_runner.check', lambda *a: pytest.fail('test cannot prove semantic criterion'))
    result = policy.prepare(controller, str(root), session, st.verify, st._candidate)
    assert result['stage'] == 'plan' and result['missing_criteria'] == ['C1']


def test_live_change_stops_remaining_expensive_checks(repair, monkeypatch):
    root, wt, st, session, controller = repair
    controller._final_criteria_contract = criteria_contract('수리', {'criteria': [{'text': 'a'}, {'text': 'b'}]})
    session['verification_plan'] = [{'criterion_id': 'C1', 'command': 'pytest first.py'},
                                    {'criterion_id': 'C2', 'command': 'pytest expensive.py'}]
    calls = []
    def check(*args):
        calls.append(args[3])
        (root / 'b.txt').write_text('concurrent change')
        return {'status': 'passed', 'test_report': {'passed': True}, 'id': 'first'}
    monkeypatch.setattr('repair_check_runner.check', check)
    result = policy.prepare(controller, str(root), session, lambda *a: pytest.fail('late gate'), st._candidate)
    assert result['stage'] == 'conflict' and result['changed_files'] == ['b.txt']
    assert calls == ['pytest first.py']


def test_direct_apply_refreshes_untouched_dependencies_before_real_checks(repair):
    from test_repair_receipt_flow import command
    root, wt, st, session, controller = repair
    (wt / 'a.txt').write_text('fixed')
    (root / 'b.txt').write_text('new dependency')
    cmd = command(wt, 'assert __import__("pathlib").Path("b.txt").read_text() == "new dependency"')
    applied = st.op_apply({'_repo_root': str(root), '_grant_key': session['key'],
                          'verification_plan': [{'criterion_id': 'C1', 'command': cmd}]})
    assert applied['applied'] and applied['commit']['success'], applied
    assert (root / 'a.txt').read_text() == 'fixed'
    assert (wt / 'b.txt').read_text() == (root / 'b.txt').read_text() == 'new dependency'
    saved = st.read_session(str(root), session['key'])
    assert 'b.txt' not in saved['sealed']  # The other edit is never our delta.


def test_direct_apply_preserves_real_collision_without_running_checks(repair, monkeypatch):
    root, wt, st, session, controller = repair
    (wt / 'a.txt').write_text('our repair')
    (root / 'a.txt').write_text('other repair')
    session['verification_plan'] = [{'criterion_id': 'C1', 'command': 'pytest expensive.py'}]
    monkeypatch.setattr('repair_check_runner.check', lambda *a: pytest.fail('unresolved collision'))
    result = policy.prepare(controller, str(root), session, st.verify, st._candidate)
    assert result['stage'] == 'conflict' and 'a.txt' in result['error']
    assert (root / 'a.txt').read_text() == 'other repair'
    assert (wt / 'a.txt').read_text() == 'our repair'


@pytest.mark.parametrize('change', ['none', 'uncollected', 'applied', 'broken'])
def test_code_receipts_follow_actual_candidate_not_repair_turn(setup, monkeypatch, change):
    from types import SimpleNamespace
    from repair_readiness import requires_code_receipts, completion_error
    root, wt, st, session = setup
    monkeypatch.setattr('runtime_utils.get_base_path', lambda: root)
    controller = SimpleNamespace(task=session['key'], repair_granted=True)
    if change == 'uncollected':
        (wt / 'a.txt').write_text('code fix')
        assert not session['files']
    elif change == 'applied':
        session['status'] = 'applied'
        st._save_session(str(root), session)
    elif change == 'broken':
        (wt / 'a.txt').unlink()
        # Without a baseline the candidate cannot be declared empty.
        session.pop('baseline')
        st._save_session(str(root), session)
    assert requires_code_receipts(controller) is (change != 'none')
    assert bool(completion_error(controller)) is (change != 'none')


def test_unreadable_code_session_cannot_skip_receipts(supervisor, tmp_path, monkeypatch):
    from repair_readiness import requires_code_receipts
    from repair_continuation import key
    monkeypatch.setattr('runtime_utils.get_base_path', lambda: tmp_path)
    path = tmp_path / 'data/system_ai_state/repair_sessions' / (key(supervisor.task) + '.json')
    path.parent.mkdir(parents=True)
    path.write_text('{broken')
    assert requires_code_receipts(supervisor)
    from thread_context import get_goal_eval_outcome
    policy.finalize(supervisor, '수리 결과')
    assert get_goal_eval_outcome()['goal_status'] == 'UNKNOWN'


def test_resume_still_requires_code_receipts_without_session(supervisor):
    from repair_readiness import requires_code_receipts
    from repair_continuation import resuming
    with resuming({'task_id': 'missing-code-session', 'job_path': 'reserved.apply.json'}):
        assert requires_code_receipts(supervisor)


def test_review_continuation_alone_is_not_code_repair(supervisor):
    from repair_readiness import requires_code_receipts
    from repair_continuation import resuming
    with resuming({'task_id': supervisor.task, 'staging_task_id': supervisor.task, 'phase': 'review'}):
        assert not requires_code_receipts(supervisor)


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))


@pytest.mark.parametrize("transferred", [False, True])
def test_receipt_policy_continues_unapplied_workspace_without_another_request(repair, monkeypatch, transferred):
    import repair_continuation as journal
    import repair_root
    # This test owns queue production; the scheduler has separate integration tests.
    monkeypatch.setattr(consumer, 'kick', lambda: None)
    from thread_context import actor_context, get_goal_eval_outcome
    root, wt, st, session, controller = repair
    (wt / 'a.txt').write_text('partial implementation')
    st._candidate.collect(str(root), session)
    st._save_session(str(root), session)
    if transferred:
        old = session['key']
        st._save_session(str(root), {**session, 'reused_by': 'latest'})
        session = {**session, 'key': 'latest', 'resumed_from': old}
        st._save_session(str(root), session)
    controller.runner.config = {'id': controller.owner}
    monkeypatch.setattr('principal.is_owner', lambda: True)
    monkeypatch.setattr('final_evaluator.invoke', lambda *a, **kw: pytest.fail('extra completion model'))
    with actor_context(origin='user'):
        response = policy.finalize(controller, '검사 접수 중단으로 미실행')
    row = journal.read(controller.task, root)
    assert row['status'] == 'waiting_execution'
    assert row['staging_task_id'] == session['key']
    assert row['worktree'] == session['worktree']
    assert row['criteria_contract']['criteria']
    assert get_goal_eval_outcome()['status'] == 'PENDING_EXECUTION'
    assert get_goal_eval_outcome()['goal_status'] == 'UNKNOWN'
    assert not repair_root.projection(root, session['root_task_id'])['terminal']
    assert '[작업 계속]' in response
