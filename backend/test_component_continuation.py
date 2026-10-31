"""일반 부품 수리의 재기동 인계: 같은 대화·예산·영수증, RED 권한 없음."""
import boot_paths  # noqa: F401
import json
import sqlite3
import time
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
import component_continuation as cc
import conversation_sessions as sessions
import execution_turn
import repair_continuation as journal
import api_repair_continuation as consumer
from conversation_handoff import Handoff
from providers.base import ProviderMetrics, turn_token_scope, read_turn_tokens, _turn_token_ledger


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, 'state_root', lambda: tmp_path / 'data/system_ai_state')
    monkeypatch.setattr('runtime_utils.get_base_path', lambda: tmp_path)
    monkeypatch.setattr('runtime_work.registry', lambda: NS(generation='old'))
    monkeypatch.setattr('principal.is_owner', lambda: True)
    monkeypatch.setattr('thread_context.get_task_origin', lambda: 'user')
    path = tmp_path / 'conversations.db'
    with sqlite3.connect(path) as conn:
        conn.execute('CREATE TABLE conversations(id INTEGER PRIMARY KEY, role TEXT, content TEXT, source TEXT)')
    store = sessions.SessionStore(path, 'conversations', 'system_ai')
    binding = store.begin(store.create()['id'])
    turn = execution_turn.Binding(NS(config={'_is_system_ai': True}), 'system_ai', 'original',
        context={}, conversation=binding, component_repair_allowed=True, component_session='component-first',
        request='원격 상태를 확인하고 보고서 저장', history=[{'role': 'user', 'content': '원래 제약'}])
    with sessions.scope(binding), turn_token_scope('system_ai', 'original', hard_token_limit=1000, deadline_s=600):
        yield tmp_path, store, turn


def armed(env):
    base, store, turn = env
    Handoff().record('started', {'message': turn.request})
    Handoff().observe({'type': 'tool_start', 'id': 'write', 'name': 'execute_ibl', 'input': {'code': 'remote write'}})
    Handoff().observe({'type': 'tool_result', 'id': 'write', 'result': {'success': True, 'receipt': 'existing-effect'}})
    Handoff().observe({'type': 'tool_start', 'id': 'unknown', 'name': 'execute_ibl', 'input': {'code': 'unknown effect'}})
    ProviderMetrics().record_request(1, 100, 10)
    cc.arm(turn)
    ProviderMetrics().record_request(1, 20, 2)
    return journal.read(turn.continuation_key)


def process(env, monkeypatch, execute):
    monkeypatch.setattr(sessions, '_PROCESS', 'replacement-process')
    monkeypatch.setattr(consumer, 'retry_deliveries', lambda *a: None)
    consumer.process_pending(env[0], 'new', execute=execute)


def test_resume_original_goal_receipts_budget_and_conversation_without_grant(env, monkeypatch):
    base, store, turn = env
    turn.allowed_set = {'execute_ibl', 'allowed-original'}
    row = armed(env)
    assert row['budget']['input'] + row['budget']['output'] == 132
    turn.followup_reason = 'observed_failure'
    cc.checkpoint(turn)
    calls = []

    def execute(row):
        b = sessions.current()
        assert b.session_id == turn.conversation.session_id and b.turn_id != turn.conversation.turn_id
        prompt = Handoff().recovery()
        assert 'existing-effect' in prompt and 'effect_unknown' in prompt
        assert row['goal'] == turn.request and row['component_key'] == 'component-first'
        monkeypatch.setattr('thread_context.get_current_task_id', lambda: row['resume_task_id'])
        monkeypatch.setattr('thread_context.get_current_agent_id', lambda: 'system_ai')
        resumed = execution_turn.Binding(turn.runner, turn.agent, row['resume_task_id'], conversation=b,
                                         request=row['goal'], context={}, allowed_set={'execute_ibl', 'new-tool'})
        with turn_token_scope(turn.agent, resumed.task, hard_token_limit=1500, deadline_s=900):
            cc.attach(resumed)
            assert read_turn_tokens() == 132
            assert _turn_token_ledger.get()['hard_token_limit'] == 1000
            assert _turn_token_ledger.get()['deadline'] - time.monotonic() < 600
            assert resumed.followup_reason == 'observed_failure'
            assert resumed.component_resume_key == 'component-first'
            assert resumed.allowed_set == {'execute_ibl'}
            assert cc.framing(row['goal']) is None
            with pytest.raises(ValueError, match='수리 권한'):
                journal.inherited_framing(row['goal'])
            ProviderMetrics().record_request(1, 10, 1)
            cc.finish(resumed, '보고서 저장 완료')
        calls.append(row['resume_task_id'])
        return {'response': '보고서 저장 완료'}

    process(env, monkeypatch, execute)
    process(env, monkeypatch, execute)
    final = journal.read(row['task_id'])
    assert calls and len(calls) == 1 and final['status'] == 'completed'
    assert final['budget']['input'] + final['budget']['output'] == 143
    assert journal.task_state('original') == 'completed'


@pytest.mark.parametrize('reason', ['cancel', 'deadline', 'tokens', 'new_turn', 'finished', 'attempts'])
def test_no_replay_after_cancel_limit_new_request_or_finished_receipt(env, monkeypatch, reason):
    base, store, turn = env
    row = armed(env)
    if reason == 'cancel':
        journal.cancel_pending('', 'system_ai', base)
    elif reason == 'deadline':
        row['budget']['deadline_at'] = time.time() - 1
    elif reason == 'tokens':
        row['budget']['hard_token_limit'] = 132
    elif reason == 'new_turn':
        store.finish(turn.conversation)
        store.begin(turn.conversation.session_id)
    elif reason == 'finished':
        Handoff().finish(True, '이미 전달한 답변')
    elif reason == 'attempts':
        row['attempt'] = 3
    journal.save(row)
    process(env, monkeypatch, lambda row: pytest.fail('도구/모델을 재실행하면 안 됨'))
    final = journal.read(row['task_id'])
    assert final['status'] == ('cancelled' if reason == 'cancel' else 'completed' if reason == 'finished' else 'blocked')


def test_no_implicit_resume_for_unbound_external_or_delegated_task(env, monkeypatch):
    _, _, turn = env
    turn.conversation = None
    cc.arm(turn)
    assert not turn.continuation_key
    turn.conversation = sessions.current()
    monkeypatch.setattr('thread_context.get_task_origin', lambda: 'scheduler')
    cc.arm(turn)
    assert not turn.continuation_key
    monkeypatch.setattr('thread_context.get_task_origin', lambda: 'user')
    monkeypatch.setattr('task_tree_budget.current', lambda: NS())
    cc.arm(turn)
    assert not turn.continuation_key


def test_resume_framing_cannot_turn_into_red_grant(env, monkeypatch):
    row = armed(env)
    row.update(resume_task_id='resumed', framing={'criteria': '원래 목표', 'needs_repair': True,
                                                'imagined_ibl': 'old effect', '_repair_policy': 2})
    monkeypatch.setattr('thread_context.get_current_task_id', lambda: 'resumed')
    monkeypatch.setattr('thread_context.get_current_agent_id', lambda: 'system_ai')
    with journal.resuming(row):
        frame = cc.framing(row['goal'])
        assert frame == {'criteria': '원래 목표', '_framing_source': cc.KIND}
        assert '#repair 작업' not in journal.resume_context(row)
        with pytest.raises(ValueError):
            cc.framing('다른 목표')


def crash_body(base):
    """테스트 자식만 강제 종료. 정본 앱·제어자에는 접촉하지 않는다."""
    import runtime_utils, runtime_work, thread_context
    runtime_utils.get_base_path = lambda: base
    runtime_work.registry = lambda: NS(generation='before-crash')
    journal.state_root = lambda: base / 'data/system_ai_state'
    thread_context.set_task_origin('user')
    with sqlite3.connect(base / 'conversations.db') as conn:
        conn.execute('CREATE TABLE conversations(id INTEGER PRIMARY KEY, role TEXT, content TEXT, source TEXT)')
    store = sessions.SessionStore(base / 'conversations.db', 'conversations', 'system_ai')
    b = store.begin(store.create()['id'])
    turn = execution_turn.Binding(NS(config={'_is_system_ai': True}), 'system_ai', 'crashed',
        context={}, conversation=b, component_repair_allowed=True, component_session='component-candidate',
        request='기존 결과를 보존하고 보고서를 완성해줘')
    with sessions.scope(b), turn_token_scope('system_ai', 'crashed', hard_token_limit=1000):
        h = Handoff()
        h.record('started', {'message': turn.request})
        h.observe({'type': 'tool_start', 'id': 'write-once', 'name': 'write', 'input': {'path': 'effect.txt'}})
        (base / 'effect.txt').write_text('이미 수행한 효과')
        h.observe({'type': 'tool_result', 'id': 'write-once', 'result': {'success': True, 'receipt': 'effect.txt'}})
        ProviderMetrics().record_request(1, 100, 20)
        cc.arm(turn)
        os._exit(23)


@pytest.mark.system
def test_process_death_returns_to_original_goal_without_repeating_effect(tmp_path, monkeypatch):
    command = [sys.executable, '-c',
               'from pathlib import Path; import sys; sys.path.insert(0,sys.argv[1]); '
               'from test_component_continuation import crash_body; crash_body(Path(sys.argv[2]))',
               str(Path(__file__).parent), str(tmp_path)]
    child = subprocess.run(command, capture_output=True, timeout=30)
    assert child.returncode == 23, child.stderr
    original = (tmp_path / 'effect.txt').stat().st_mtime_ns
    executed = []

    def execute(row):
        assert row['budget']['input'] + row['budget']['output'] == 120
        assert 'effect.txt' in Handoff().recovery()
        (tmp_path / 'report.txt').write_text(row['goal'] + '\n' + (tmp_path / 'effect.txt').read_text())
        executed.append(row['goal'])
        return {'response': '보고서 저장 완료'}

    monkeypatch.setattr(consumer, 'retry_deliveries', lambda *a: None)
    consumer.process_pending(tmp_path, 'before-crash', execute=execute)
    consumer.process_pending(tmp_path, 'before-crash', execute=execute)
    assert len(executed) == 1 and (tmp_path / 'report.txt').is_file()
    assert (tmp_path / 'effect.txt').stat().st_mtime_ns == original


def test_living_process_is_not_restarted_by_generation_change(env, monkeypatch):
    row = armed(env)
    monkeypatch.setattr(consumer, 'retry_deliveries', lambda *a: None)
    consumer.process_pending(env[0], 'another-generation', execute=lambda row: pytest.fail('아직 실행 중'))
    assert journal.read(row['task_id'])['attempt'] == 0


def test_project_executor_preserves_owned_conversation_and_images(tmp_path, monkeypatch):
    import api_agents
    import thread_context as tc
    from conversation_db import ConversationDB
    previous = tc.snapshot()
    monkeypatch.setenv('INDIEBIZ_BASE_PATH', str(tmp_path))
    monkeypatch.setattr(api_agents, 'project_manager', NS(get_project_path=lambda p: tmp_path))
    monkeypatch.setattr('episode_logger.EpisodeLogger.start_episode', lambda *a, **kw: None)
    monkeypatch.setattr('episode_logger.EpisodeLogger.end_episode', lambda *a, **kw: None)
    db = ConversationDB(str(tmp_path / 'conversations.db'))
    owner = sessions.pair_owner(db.get_or_create_agent('user', 'human'),
                                db.get_or_create_agent('데이터', 'ai_agent'))
    store = sessions.SessionStore(db.db_path, 'messages', owner)
    bound = store.begin(store.create()['id'])
    row = {'kind': cc.KIND, 'task_id': 'component-parent-proj', 'root_task_id': 'component-parent-proj',
           'resume_task_id': 'component-resume-proj', 'agent_id': 'agent', 'project_id': 'project',
           'system_ai': False, 'goal': '원래 업무', 'images': [{'path': 'original.png'}]}
    calls = []

    def stream(message, history, **kwargs):
        assert sessions.current() == bound
        assert tc.get_current_task_id() == row['resume_task_id']
        assert tc.get_task_origin() == 'user' and not kwargs['extra_role']
        assert kwargs['images'] == row['images']
        calls.append(message)
        yield {'type': 'final', 'content': '남은 업무 완료'}

    monkeypatch.setattr(consumer, '_project_runner', lambda row: NS(config={'name': '데이터'}, cognitive_stream=stream))
    try:
        with sessions.scope(bound), journal.resuming(row):
            result = consumer._execute(row)
        assert result['response'] == '남은 업무 완료' and calls == [row['goal']]
        with db.get_connection() as conn:
            assert conn.execute('SELECT COUNT(*) FROM conversation_turns').fetchone()[0] == 1
            assert [r[0] for r in conn.execute('SELECT content FROM messages')] == ['남은 업무 완료']
    finally:
        store.finish(bound)
        tc.restore(previous)


def test_real_pipeline_resumes_as_execute_without_classifier_or_red_grant(env, monkeypatch):
    from agent_pipeline import CognitivePipelineMixin
    from cognitive_consciousness import CognitiveConsciousnessMixin
    from test_reflex_execution import AI

    class Runner(CognitivePipelineMixin, CognitiveConsciousnessMixin):
        pass

    row = armed(env)
    row['resume_task_id'] = 'resumed'
    monkeypatch.setattr('thread_context.get_current_task_id', lambda: 'resumed')
    monkeypatch.setattr('thread_context.get_current_agent_id', lambda: 'system_ai')
    r = Runner()
    r.config = {'name': 'system_ai', '_is_system_ai': True}
    r.ai = AI([[{'type': 'final', 'content': '남은 보고서 저장 완료'}]])
    r._associate = r._decide_request_type = r._run_consciousness_or_reuse = lambda *a, **kw: pytest.fail('재분류·재의식 금지')
    r._load_role = lambda: 'role'
    r._build_system_ai_prompt_split = lambda role, c, mem, **kw: ('System structure + IBL + rules', mem)
    r._after_response_async = lambda *a, **kw: None
    monkeypatch.setattr('red_grant.issue_grant', lambda **kw: pytest.fail('RED 권한 발급 금지'))
    monkeypatch.setattr('supervision_bus.current', lambda: None)
    monkeypatch.setattr('unified_distill.capture_model', lambda r: None)
    monkeypatch.setattr('framing_inheritance.remember', lambda *a, **kw: None)
    with journal.resuming(row), r.turn_ai_scope():
        events = list(r._cognitive_stream_body(row['goal'], row['history'], extra_role=cc.context(row)))
    assert not [e for e in events if e['type'] == 'error'], events
    assert [e['content'] for e in events if e['type'] == 'final'] == ['남은 보고서 저장 완료']
    assert len(r.ai.calls) == 1 and '기존 실행 영수증' in r.ai.calls[0][1]['message_content']


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
