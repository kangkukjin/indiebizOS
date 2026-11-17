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


class _Runner:
    """의식 호출만 가짜인 실행 주체. 나머지(_run_consciousness_or_reuse·rethink·인계 원장)는 실제 경로다."""
    def __init__(self, config, answer):
        from cognitive_consciousness import CognitiveConsciousnessMixin
        self.config, self.answer, self.calls = config, answer, []
        self.reuse = CognitiveConsciousnessMixin._run_consciousness_or_reuse.__get__(self)

    def _run_consciousness(self, message, history, memory="", repair=False, revision=None, resume=None):
        self.calls.append({"message": message, "repair": repair, "resume": resume})
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def test_user_resumed_repair_is_reframed_from_its_present_state_with_criteria_fixed(unfinished, monkeypatch):
    """사용자의 말로 이은 수리는 의식이 지금 상태에서 남은 일을 새로 규정한다. 완료 기준과 권한은 못 바꾼다.
    (그 전에는 수리를 시작하기 전에 쓴 규정을 다시 틀었다 — 11-03: 같은 수리에 "완료해줘" 15번.)"""
    root, wt, st, sess, controller = unfinished
    events = []
    monkeypatch.setattr('episode_logger.record_trajectory_event', lambda kind, data=None: events.append((kind, data)))
    runner = _Runner(controller.runner.config, {
        'task_framing': '남은 것은 전달이다. 사본의 a.txt 를 확인하고 전달 단계만 마친다.',
        'criteria': [{'text': '기준을 느슨하게 바꿔 본다'}], 'needs_repair': False, '_repair_policy': 99,
        'independent_review': False, 'deep_execution': 3, 'first_step': '처음부터 다시 조사',
        'assumptions': ['사본이 그대로 있다']})
    message = '수리를 완료해줘'
    with resume.user_resume(runner, message, [{'role': 'user', 'content': controller.message}]):
        assert resume.user_resumed()
        out = runner.reuse(message, [], '', repair=True)
    call = runner.calls[0]
    assert call['repair'] is True
    facts = call['resume']
    assert facts['stopped_because'] == 'C2 unmet' and facts['last_report'] == 'not delivered'
    assert facts['applied_to_canonical'] is False and facts['copy']['path'] == sess['worktree']
    assert [c['text'] for c in facts['criteria']] == ['build', 'deliver without changing key']
    # 남은 일의 규정은 의식의 것, 완료 기준·권한·검토 여부는 보존된 것
    assert out['task_framing'].startswith('남은 것은 전달이다')
    assert [c['text'] for c in out['criteria']] == ['build', 'deliver without changing key']
    assert out['_repair_policy'] == 2 and out['_framing_source'] == 'repair_continuation'
    assert out['independent_review'] is True and 'needs_repair' not in out
    assert 'deep_execution' not in out and 'first_step' not in out
    assert out['assumptions'] == ['사본이 그대로 있다']
    assert ('repair.resume_rethink', {'used': True, 'needs_clarification': False,
                                      'task_framing_chars': len(out['task_framing'])}) in events
    assert not resume.user_resumed()            # 표식은 그 턴 밖으로 나가지 않는다


@pytest.mark.parametrize('answer', [None, {'task_framing': '  '}, RuntimeError('의식 모델 오프라인')])
def test_resume_falls_back_to_the_preserved_framing_when_consciousness_cannot_answer(unfinished, monkeypatch, answer):
    root, wt, st, sess, controller = unfinished
    events = []
    monkeypatch.setattr('episode_logger.record_trajectory_event', lambda kind, data=None: events.append((kind, data)))
    runner = _Runner(controller.runner.config, answer)
    message = '수리를 완료해줘'
    with resume.user_resume(runner, message, [{'role': 'user', 'content': controller.message}]):
        out = runner.reuse(message, [], '', repair=True)
    assert out['task_framing'].startswith('build and deliver') and '사용자 후속 요청: ' + message in out['task_framing']
    assert len(out['criteria']) == 2
    assert [data['used'] for kind, data in events if kind == 'repair.resume_rethink'] == [False]


def test_automatic_continuation_keeps_the_preserved_framing_without_waking_consciousness(unfinished):
    """하네스가 자동으로 잇는 턴(재기동 뒤·검수 지점 복원)은 같은 턴이 이어지는 것이다 — 의식을 부르지 않는다."""
    root, wt, st, sess, controller = unfinished
    runner = _Runner(controller.runner.config, {'task_framing': '불리면 안 된다'})
    row = {**journal.read(controller.task), 'resume_task_id': 'next', 'resume_message': 'build and deliver'}
    with journal.resuming(row):
        assert not resume.user_resumed()
        out = runner.reuse('build and deliver', [], '', repair=True)
    assert runner.calls == [] and out['task_framing'] == 'build and deliver'


def test_state_facts_carry_why_it_stopped_and_every_earlier_stop(unfinished):
    root, wt, st, sess, controller = unfinished
    first = journal.read(controller.task)
    journal.save({**first, 'status': 'continued', 'child_task_id': 'second'})
    second = journal.save({**first, 'task_id': 'second', 'parent_task_id': first['task_id'], 'status': 'blocked',
                           'reason': '적용할 수리 델타가 없습니다', 'response': '두 번째 보고', 'execution_round': 2,
                           'criteria_state': [{'id': 'C1', 'text': 'build', 'status': 'met'},
                                              {'id': 'C2', 'text': 'deliver without changing key', 'status': 'unmet'}]})
    facts = journal.state_facts(second)
    assert facts['stopped_because'] == '적용할 수리 델타가 없습니다' and facts['rounds_so_far'] == 2
    assert facts['earlier_stops'] == [{'task': first['task_id'], 'phase': first['phase'], 'reason': 'C2 unmet'}]
    assert [(c['id'], c['status']) for c in facts['criteria']] == [('C1', 'met'), ('C2', 'unmet')]
    assert facts['applied_to_canonical'] is False and '반영되기 전' in facts['tool_facts'][0]
    assert '반영된 뒤' in journal.state_facts({**second, 'applied': True, 'staging_task_id': 'none'})['tool_facts'][0]
    text = journal.state_text(second)
    assert '적용할 수리 델타가 없습니다' in text and '지시가 아니다' in text


def test_consciousness_input_carries_the_resume_state():
    from consciousness_agent import ConsciousnessAgent
    agent = ConsciousnessAgent.__new__(ConsciousnessAgent)
    text = agent._build_input('수리를 완료해줘', [], '', '', '', '', resume={'stopped_because': '커밋 관문 거부', 'phase': 'verify_remaining'})
    assert '<repair_resume' in text and '커밋 관문 거부' in text and '원래 기준이 쓰인다' in text
    assert '<repair_resume' not in agent._build_input('수리를 완료해줘', [], '', '', '', '')


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
    # The fixture's literal task ID is "task"; this request must not name it.
    with resume.user_resume(controller.runner, '#repair another goal', history):
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


@pytest.mark.parametrize('history', [['previous'], []])
@pytest.mark.parametrize('suffix', [' 수리를 완료해줘', '에서 이어오던 수리를 완료해줘'])
def test_explicit_prior_task_uses_existing_conversation_record(unfinished, history, suffix):
    root, wt, st, sess, controller = unfinished
    old = framing._load('owner')['last']
    old['at'] = '2020-01-01T00:00:00'
    framing._save('owner', {'last': {'task_id': 'unrelated'}, 'repeat': {'old': old}})
    with resume.user_resume(controller.runner, sess['key'] + suffix, history):
        assert journal.current()['staging_task_id'] == sess['key']
        assert st.load_session(str(root), 'next')['worktree'] == sess['worktree']


def test_user_review_resume_authenticates_followup_but_preserves_original_goal(unfinished, monkeypatch):
    from unittest.mock import create_autospec
    from agent_pipeline import CognitivePipelineMixin
    root, wt, st, sess, controller = unfinished
    sess['status'] = 'applied'
    st._save_session(str(root), sess)
    row = journal.read(controller.task)
    journal.save({**row, 'phase': 'review', 'applied': True})
    controller.store.text = 'previous reviewed response'
    controller.configure = lambda frame, **kw: setattr(controller, 'framing', frame)
    controller.runner._refresh_execution_prompt = create_autospec(
        CognitivePipelineMixin._refresh_execution_prompt.__get__(controller.runner))
    controller.finalize = lambda response, *a, **kw: iter([{'type': 'final', 'content': response}])
    monkeypatch.setattr(resume, 'restore_review', lambda *a: None)
    monkeypatch.setattr('system_ai_core._switch_to_role', lambda *a: None)
    monkeypatch.setattr('system_ai_core._restore_provider', lambda *a: None)
    monkeypatch.setattr('red_grant.issue_grant', lambda **kw: None)
    monkeypatch.setattr('red_grant.revoke_grant', lambda **kw: None)
    monkeypatch.setattr('reframe.turn_key_for', lambda *a: 'fixture')
    monkeypatch.setattr('reframe.open_turn', lambda *a, **kw: None)
    message = sess['key'] + '에서 이어오던 수리를 완료해줘'
    with resume.user_resume(controller.runner, message, []):
        current = journal.current()
        assert current['goal'] == controller.message != current['resume_message']
        events = list(resume.review_stream(controller.runner, controller, current))
    assert events == [{'type': 'final', 'content': 'previous reviewed response'}]
    assert controller.framing['criteria'] == row['framing']['criteria']


def test_resume_relation_requires_execution_intent_and_keeps_history(monkeypatch):
    """수리 재개 판정은 의식 축의 모델이 답한다 — CONTINUE 한 단어가 옛 기준과 수리 권한을 되살리기 때문이다
    (2026-11-17 사용자 판정. 그 전에는 분류 축의 경량 모델이 답했다)."""
    seen = []
    def model(body, prompt, role):
        seen.append((body, prompt, role))
        return 'NEW'
    monkeypatch.setattr(framing, '_oneshot', model)
    assert framing._judge_relation({'message': 'repair'}, '지금 상태는?', strict=True,
        history=[{'role': 'user', 'content': 'original work'}]) == 'NEW'
    body, prompt, role = seen[0]
    assert role == 'consciousness'
    assert '상태 조회' in prompt and '애매하면 NEW' in prompt      # 수리 재개만을 위한 지문
    assert 'original work' in body


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


def test_confirmed_recovery_reopens_same_candidate_in_current_execution(unfinished, monkeypatch):
    from repair_context import activation_only
    root, wt, st, sess, controller = unfinished
    row = {**journal.read(controller.task), 'resume_task_id': 'next',
           'staging_task_id': sess['key'], 'phase': 'verify_remaining', 'applied': True,
           'result': {'outcome': 'healthy'}}
    sess['status'] = 'applied'
    st._save_session(str(root), sess)
    with journal.resuming(row):
        assert activation_only()
        # The application service owns this transition after confirmed recovery.
        sess.update(status='staging', verified=False)
        st._save_session(str(root), sess)
        assert not activation_only()
        continued = st.load_session(str(root), 'next')
        assert continued['worktree'] == sess['worktree']
        assert continued['resumed_from'] == sess['key']
        assert (wt / 'a.txt').read_text() == 'completed partial work'
