"""새 사용자 후속 요청도 원래 기준·사본을 유지하는 수리 재개."""
from datetime import datetime
from types import SimpleNamespace

import pytest
import boot_paths  # noqa: F401
import repair_resume as resume
import repair_continuation as journal
import framing_inheritance as framing
from test_repair_workspace_completion import setup  # noqa: F401


@pytest.fixture
def unfinished(setup, monkeypatch):
    root, wt, st, sess = setup
    monkeypatch.setattr(journal, 'state_root', lambda: root / 'data/system_ai_state')
    monkeypatch.setattr('principal.is_owner', lambda: True)
    monkeypatch.setattr('thread_context.get_task_origin', lambda: 'user')
    monkeypatch.setattr('thread_context.get_current_agent_id', lambda: 'owner')
    monkeypatch.setattr('thread_context.get_current_task_id', lambda: 'next')
    controller = SimpleNamespace(task=sess['key'], owner='owner', message='build and deliver',
        runner=SimpleNamespace(config={'id': 'owner', '_project_id': 'p'}),
        framing={'_repair_policy': 2, 'task_framing': 'build and deliver', 'criteria': [
            {'text': 'build'}, {'text': 'deliver without changing key'}]},
        cancelled=lambda: False, store=SimpleNamespace(directory=root / 'store'),
        verifications=SimpleNamespace(records=[]), original_pursuit=None, done_request=None, episode_id=1)
    (wt / 'a.txt').write_text('completed partial work')
    resume.preserve_unfinished(controller, sess, 'not delivered', 'C2 unmet')
    framing._save('owner', {'last': {'task_id': sess['key'], 'at': datetime.now().isoformat()}, 'repeat': {}})
    monkeypatch.setattr(framing, '_judge_relation', lambda *a, **kw: 'CONTINUE')
    return root, wt, st, sess, controller


@pytest.mark.parametrize("message", ["#repair 수리를 마쳐줘", "수리를 완료해줘"])
def test_user_followup_keeps_all_criteria_and_reuses_same_workspace(unfinished, message):
    root, wt, st, sess, controller = unfinished
    with resume.user_resume(controller.runner, message, [{'role': 'user', 'content': controller.message}]):
        row = journal.current()
        inherited = journal.inherited_framing(message)
        assert len(inherited['criteria']) == 2
        assert row['criteria_contract']['criteria'][1]['text'] == 'deliver without changing key'
        continued = st.load_session(str(root), 'next')
        assert continued['worktree'] == sess['worktree']
        assert (wt / 'a.txt').read_text() == 'completed partial work'
        assert st.read_session(str(root), sess['key'])['reused_by'] == 'next'
    assert journal.current() is None


@pytest.mark.parametrize('applied', [False, True, None])
def test_rejected_apply_reuses_workspace_only_with_confirmed_no_write(unfinished, applied):
    root, wt, st, sess, controller = unfinished
    row = {**journal.read(controller.task), 'resume_task_id': 'next', 'phase': 'repair_apply',
           'result': {'controller': 'apply_rejected', 'outcome': 'deferred_verify_failed',
                      'apply': {'applied': applied}}}
    with journal.resuming(row):
        continued = st.load_session(str(root), 'next')
    if applied is False:
        assert continued['worktree'] == sess['worktree']
        assert continued['root_task_id'] == sess['root_task_id']
        assert (wt / 'a.txt').read_text() == 'completed partial work'
    else:
        assert continued is None


@pytest.mark.parametrize('change', ['new', 'foreign_agent', 'foreign_project', 'no_history', 'not_user'])
def test_unrelated_or_unauthorized_request_cannot_inherit(unfinished, monkeypatch, change):
    root, wt, st, sess, controller = unfinished
    history = ['previous']
    if change == 'new':
        monkeypatch.setattr(framing, '_judge_relation', lambda *a, **kw: 'NEW')
    elif change == 'foreign_agent':
        monkeypatch.setattr('thread_context.get_current_agent_id', lambda: 'other')
    elif change == 'foreign_project':
        controller.runner.config['_project_id'] = 'other'
    elif change == 'no_history':
        history = []
    elif change == 'not_user':
        monkeypatch.setattr('thread_context.get_task_origin', lambda: 'scheduler')
    with resume.user_resume(controller.runner, '#repair another task', history):
        assert journal.current() is None
    assert not st.read_session(str(root), sess['key']).get('reused_by')


def test_relation_failure_does_not_silently_replace_original_criteria(unfinished, monkeypatch):
    *_, controller = unfinished
    monkeypatch.setattr(framing, '_judge_relation', lambda *a, **kw: (_ for _ in ()).throw(RuntimeError('offline')))
    with pytest.raises(ValueError, match='기존 기준'):
        with resume.user_resume(controller.runner, '#repair 계속', ['previous']):
            pytest.fail('new execution')
    assert len(journal.read(controller.task)['criteria_contract']['criteria']) == 2


def test_strict_relation_rejects_empty_model_output(monkeypatch):
    monkeypatch.setattr(framing, '_prompt', lambda *a: 'relation')
    monkeypatch.setattr(framing, '_oneshot', lambda *a: '')
    with pytest.raises(ValueError, match='응답'):
        framing._judge_relation({'message': 'prior'}, '#repair continue', strict=True)


def test_explicit_prior_task_uses_existing_conversation_record(unfinished):
    root, wt, st, sess, controller = unfinished
    old = framing._load('owner')['last']
    old['at'] = '2020-01-01T00:00:00'
    framing._save('owner', {'last': {'task_id': 'unrelated'}, 'repeat': {'old': old}})
    with resume.user_resume(controller.runner, sess['key'] + ' 수리를 완료해줘', ['previous']):
        assert journal.current()['staging_task_id'] == sess['key']
        assert st.load_session(str(root), 'next')['worktree'] == sess['worktree']


def test_resume_relation_requires_execution_intent_and_keeps_history(monkeypatch):
    seen = []
    monkeypatch.setattr(framing, '_prompt', lambda name: 'relation')
    def model(body, prompt, role):
        seen.append((body, prompt))
        return 'NEW'
    monkeypatch.setattr(framing, '_oneshot', model)
    assert framing._judge_relation({'message': 'repair'}, '지금 상태는?', strict=True,
        history=[{'role': 'user', 'content': 'original work'}], execution_only=True) == 'NEW'
    assert '상태 조회' in seen[0][1]
    assert 'original work' in seen[0][0]


def test_applied_backend_can_resume_commit_without_reapplying(setup, monkeypatch):
    from test_repair_workspace_completion import ready
    root, wt, st, sess = setup
    (wt / 'a.txt').write_text('fixed')
    ready(root, st, sess)
    assert st._perform_apply(str(root), sess, [], None, None)['applied']
    monkeypatch.setattr(st, '_reload_triggering', lambda s: True)
    monkeypatch.setattr(st, '_perform_apply', lambda *a: pytest.fail('duplicate apply'))
    with journal.resuming({'result': {'outcome': 'healthy'}}):
        result = st.op_apply({'_repo_root': str(root), '_grant_key': sess['key']})
    assert result['complete'], result
    assert result['commit']['success']


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))


def test_plain_followup_follows_completed_execution_handoff_to_current_candidate(unfinished):
    root, wt, st, sess, controller = unfinished
    prior = journal.read(controller.task)
    child = {**prior, 'task_id': 'latest', 'staging_task_id': 'latest'}
    journal.save(child)
    journal.save({**prior, 'status': 'continued', 'child_task_id': 'latest'})
    st._save_session(str(root), {**sess, 'reused_by': 'latest'})
    st._save_session(str(root), {**sess, 'key': 'latest'})
    with resume.user_resume(controller.runner, '수리를 완료해줘', ['previous']):
        assert journal.current()['staging_task_id'] == 'latest'
        assert st.load_session(str(root), 'next')['worktree'] == sess['worktree']


def test_stale_continuation_follows_owned_workspace_transfer(unfinished):
    root, wt, st, sess, controller = unfinished
    st._save_session(str(root), {**sess, 'reused_by': 'latest'})
    st._save_session(str(root), {**sess, 'key': 'latest', 'resumed_from': sess['key']})
    with resume.user_resume(controller.runner, '수리를 완료해줘', ['previous']):
        assert journal.current()['staging_task_id'] == 'latest'
        assert st.load_session(str(root), 'next')['worktree'] == sess['worktree']


@pytest.mark.parametrize('field', ['owner', 'root_task_id', 'worktree', 'resumed_from'])
def test_workspace_transfer_rejects_changed_ownership(unfinished, field):
    root, wt, st, sess, controller = unfinished
    st._save_session(str(root), {**sess, 'reused_by': 'latest'})
    st._save_session(str(root), {**sess, 'key': 'latest', 'resumed_from': sess['key'], field: 'foreign'})
    with pytest.raises(ValueError, match='소유권'):
        journal.staging_session(sess['key'])


def test_applied_resume_follows_existing_task_binding_across_http_thread(unfinished, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    import thread_context as tc
    import supervision_bus
    from repair_context import activation_only
    from test_repair_staging import _load_handler
    root, wt, st, sess, controller = unfinished
    sess['status'] = 'applied'
    st._save_session(str(root), sess)
    resume.preserve_unfinished(controller, sess, 'commit rejected', 'hook failed')
    handler = _load_handler()
    handler._REPO_ROOT = root
    monkeypatch.setattr(handler, '_red_grant_active', lambda: {'task_id': 'next'})
    def invoke(task):
        with tc.actor_context(agent_id='owner', task_id=task):
            return journal.current(), activation_only(), handler._staging_key()
    with resume.user_resume(controller.runner, '수리를 완료해줘', ['previous']):
        binding = SimpleNamespace(task='next', repair_continuation=journal.current())
        monkeypatch.setattr(tc, 'get_current_task_id', lambda: getattr(tc._thread_local, 'task_id', None))
        supervision_bus.register(binding, ['owner'])
        try:
            with ThreadPoolExecutor(max_workers=1) as pool:
                row, activation, key = pool.submit(invoke, 'next').result()
                assert row['staging_task_id'] == sess['key'] and activation
                assert key == sess['key']
                assert st.read_session(str(root), 'next') is None
                row, activation, key = pool.submit(invoke, 'unrelated').result()
                assert row is None and not activation and key == 'next'
        finally:
            supervision_bus.unregister(binding)
