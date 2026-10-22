"""The CLI bridge preserves turn ownership, sessions and todo errors."""
import boot_paths  # noqa: F401
import json
from types import SimpleNamespace
from concurrent.futures import ThreadPoolExecutor

import pytest
import pursuit_bind as pb
import conversation_sessions as sessions
import thread_context as tc
from todo_bridge import execute


@pytest.fixture
def active(tmp_path):
    runner = SimpleNamespace(project_path=tmp_path, config={'id': 'owner'}, ai=None)
    with tc.actor_context(agent_id='owner', task_id='todo-turn', origin='training'):
        token = pb.enter(runner, '계획을 세워 실행해 줘', [])
        binding = pb.current()
        binding.aliases.add('provider-alias')
        session = sessions.Binding(str(tmp_path / 'db.sqlite'), 'conversation', 'owner')
        binding.conversation = session
        with sessions._task_lock:
            sessions._task_bindings['todo-turn'] = session
        try:
            yield binding, session
        finally:
            pb.leave(token)
            with sessions._task_lock:
                sessions._task_bindings.pop('todo-turn', None)


def test_http_worker_uses_bound_session_and_restores_context(active):
    b, session = active
    todos = [{'content': '검수', 'activeForm': '검수 중', 'status': 'in_progress'}]
    def worker():
        before = tc.snapshot()
        foreign = sessions.Binding(session.db_path, 'foreign', 'other')
        with sessions.scope(foreign):
            result = execute(todos, 'provider-alias', b.task)
            assert sessions.current() == foreign
        assert not sessions.state_directory(foreign).exists()
        assert tc.snapshot() == before
        return result
    with ThreadPoolExecutor(1) as pool:
        assert pool.submit(worker).result()['success']
    saved = sessions.state_directory(session) / 'todo_state.json'
    assert json.loads(saved.read_text())['todos'] == todos
    assert not (b.runner.project_path / 'agent_owner_todo_state.json').exists()
    with ThreadPoolExecutor(1) as pool:
        assert pool.submit(execute, [{'status': 'invalid'}], b.agent, b.task).result()['success'] is False
    assert json.loads(saved.read_text())['todos'] == todos


def test_supervisor_observes_actual_tool_with_original_identity(active, monkeypatch):
    b, _ = active
    calls = []
    def run_tool(name, payload, call):
        calls.append((name, tc.get_current_task_id(), tc.get_current_agent_id(), tc.get_task_origin()))
        return call()
    supervisor = SimpleNamespace(context=b.context, run_tool=run_tool, cancelled=lambda: False)
    monkeypatch.setattr('supervision_bus.current', lambda *a, **kw: supervisor)
    with ThreadPoolExecutor(1) as pool:
        assert pool.submit(execute, [], 'provider-alias', b.task).result()['success']
    assert calls == [('todo_write', b.task, b.agent, 'training')]


@pytest.mark.parametrize('agent,task', [('', ''), ('other', 'todo-turn'), ('owner', 'wrong'), ('owner', '')])
def test_missing_or_foreign_turn_cannot_write(active, agent, task):
    _, session = active
    with ThreadPoolExecutor(1) as pool:
        assert pool.submit(execute, [], agent, task).result()['success'] is False
    assert not (sessions.state_directory(session) / 'todo_state.json').exists()


def test_finished_turn_cannot_write():
    assert execute([], 'owner', 'todo-turn')['success'] is False


@pytest.mark.parametrize('name', ['todo_write', 'mcp__indiebizos__todo_write'])
@pytest.mark.parametrize('error', [False, True])
def test_surface_shows_successful_clear_but_not_rejected_plan(name, error):
    from chat_streams import tool_event_payload
    event = {'type': 'tool_result', 'name': name, 'input': {'todos': []},
             'result': json.dumps({'success': not error}), 'is_error': error}
    result = tool_event_payload(event, 'owner')
    assert ('todos' in result) == (not error)
    if not error:
        assert result['todos'] == []


def test_json_failure_does_not_publish_todo_input():
    from chat_streams import tool_event_payload
    result = tool_event_payload({'type': 'tool_result', 'name': 'todo_write',
        'input': {'todos': []}, 'result': '{"success":false}', 'is_error': False}, 'owner')
    assert 'todos' not in result


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
