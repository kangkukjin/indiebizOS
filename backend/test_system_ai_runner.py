"""예약 위임의 최신 세션 선택·영속 소속·대기·실패 경계."""
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest
import conversation_sessions as sessions
import system_ai_memory as memory
import thread_context as tc
from system_ai_runner import SystemAIRunner


@pytest.fixture
def host(tmp_path, monkeypatch):
    monkeypatch.setattr(memory, 'MEMORY_DB_PATH', tmp_path / 'memory.db')
    monkeypatch.setattr(memory, '_ckpt_schedule', None)
    monkeypatch.setattr(memory, '_ckpt_apply', None)
    import onboarding_state
    monkeypatch.setattr(onboarding_state, '_marked_this_process', True)
    import episode_logger
    monkeypatch.setattr(episode_logger.EpisodeLogger, 'start_episode', lambda *a: None)
    monkeypatch.setattr(episode_logger.EpisodeLogger, 'end_episode', lambda: None)
    import delegation_tasks
    monkeypatch.setattr(delegation_tasks, 'recover_reports', lambda *a: [])
    monkeypatch.setattr(SystemAIRunner, 'internal_messages', [])
    monkeypatch.setattr(SystemAIRunner, 'held_reports', [])
    monkeypatch.setattr(sessions, '_task_bindings', {})
    monkeypatch.setattr(sessions, '_loaded_paths', set())
    memory.init_memory_db()
    store = sessions.SessionStore(memory.MEMORY_DB_PATH, 'conversations', 'system_ai')
    runner = object.__new__(SystemAIRunner)
    runner.ai = object()
    runner._sync_gear = lambda: None
    seen = []

    def answer(message, history, **kwargs):
        seen.append((sessions.current(), history))
        return '완성된 보고서'

    runner._process_via_cognition = answer
    previous = tc.snapshot()
    tc.clear_all_context()
    with sessions.scope(None):
        yield SimpleNamespace(store=store, runner=runner, seen=seen)
    tc.restore(previous)


def dispatch(host, task='task_report', origin='scheduler', content='오늘 보고서 작성'):
    if not memory.get_task(task):
        memory.create_task(task, '정기보고앱', 'delegate', content)
    SystemAIRunner.internal_messages.append({
        'task_id': task, 'origin': origin, 'from_agent': '정기보고앱', 'content': content})
    host.runner._check_internal_messages()


def test_schedule_uses_newest_created_session_and_its_history(host):
    old = host.store.create('이전 세션')['id']
    latest = host.store.create('최신 세션')['id']
    # 앱메이커는 더 최근에 생성됐어도 시스템 AI 세션이 아니다.
    sessions.SessionStore(host.store.path, 'conversations', 'appmaker').create()
    with sessions.scope(sessions.Binding(host.store.path, latest, 'system_ai')):
        memory.save_conversation('user', '이 세션의 보고서 지침')
    with sessions.scope(sessions.Binding(host.store.path, old, 'system_ai')):
        memory.save_conversation('user', '오래된 세션 지침')
    memory.save_conversation('user', '기존 대화가 가장 최근에 갱신됨')
    dispatch(host)
    binding, history = host.seen[0]
    assert binding.session_id == latest
    assert any('이 세션의 보고서 지침' in r['content'] for r in history)
    assert not any('오래된 세션' in r['content'] or '기존 대화' in r['content'] for r in history)
    assert host.store.history(latest)['messages'][-1]['content'] == '완성된 보고서'
    assert memory.get_task('task_report')['status'] == 'completed'
    assert sessions.current() is None
    with sessions.connection(host.store.path) as conn:
        assert conn.execute('SELECT state FROM conversation_turns WHERE id=?',
                            (binding.turn_id,)).fetchone()[0] == 'completed'


def test_pending_report_keeps_session_after_new_session_and_cache_loss(host):
    original = host.store.create()['id']
    message = {'task_id': 'task_pending', 'origin': 'scheduler'}
    memory.create_task('task_pending', 'app', 'delegate', '보고서')
    with host.runner._scheduled_conversation(message) as ready:
        assert ready and sessions.current().session_id == original
    host.store.create()
    sessions._task_bindings.clear()
    sessions._loaded_paths.clear()
    dispatch(host, 'task_pending', origin='agent', content='조사 결과를 이어서 보고')
    assert host.seen[0][0].session_id == original
    assert host.store.history(original)['messages'][-1]['content'] == '완성된 보고서'


def test_busy_session_defers_without_writing_and_keeps_target(host):
    latest = host.store.create()['id']
    active = host.store.begin(latest)
    dispatch(host)
    assert not host.seen and len(SystemAIRunner.held_reports) == 1
    assert host.store.history(latest)['messages'] == []
    host.store.create()
    host.store.finish(active)
    host.runner._check_internal_messages()
    assert len(host.seen) == 1 and host.seen[0][0].session_id == latest
    assert not SystemAIRunner.held_reports


def test_no_new_session_falls_back_to_existing_conversation(host):
    legacy = host.store.list()[0]['id']
    dispatch(host)
    assert host.seen[0][0].session_id == legacy


def test_failed_schedule_closes_session_as_failed(host):
    from system_ai_core import SystemAITurnFailed
    latest = host.store.create()['id']

    def fail(*a, **kw):
        raise SystemAITurnFailed('모델 실행 실패')

    host.runner._process_via_cognition = fail
    dispatch(host)
    assert memory.get_task('task_report')['status'] == 'failed'
    with sessions.connection(host.store.path) as conn:
        assert conn.execute('SELECT state FROM conversation_turns WHERE session_id=?',
                            (latest,)).fetchone()[0] == 'failed'


def test_non_schedule_without_binding_preserves_existing_routing(host):
    host.store.create()
    dispatch(host, origin='agent')
    assert host.seen[0][0] is None
    legacy = next(s['id'] for s in host.store.list() if s['legacy'])
    assert host.store.history(legacy)['messages'][-1]['content'] == '완성된 보고서'


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
