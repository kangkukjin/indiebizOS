"""A malformed replacement must never destroy the last usable todo list."""
import json
import boot_paths  # noqa: F401
import pytest
from system_tools import execute_tool
from thread_context import actor_context


def item(status='pending'):
    return {'content': '검수', 'activeForm': '검수 중', 'status': status}


@pytest.mark.parametrize('payload', [
    {}, {'todos': None}, {'todos': {}}, {'todos': [None]},
    {'todos': [{'content': 'missing fields'}]},
    {'todos': [item('blocked')]},
    {'todos': [item('in_progress'), item('in_progress')]},
])
def test_invalid_replacement_preserves_previous_state(tmp_path, payload):
    with actor_context(agent_id='todo-test', task_id='todo-test', origin='training'):
        execute_tool('todo_write', {'todos': [item()]}, str(tmp_path), 'todo-test')
        path = tmp_path / 'agent_todo-test_todo_state.json'
        before = path.read_bytes()
        result = execute_tool('todo_write', payload, str(tmp_path), 'todo-test')
    assert path.read_bytes() == before
    assert json.loads(result)['success'] is False


def test_empty_list_explicitly_clears_state(tmp_path):
    with actor_context(agent_id='todo-test', task_id='todo-test', origin='training'):
        execute_tool('todo_write', {'todos': [item()]}, str(tmp_path), 'todo-test')
        result = execute_tool('todo_write', {'todos': []}, str(tmp_path), 'todo-test')
    assert 'Todo list updated' in result
    assert json.loads((tmp_path / 'agent_todo-test_todo_state.json').read_text())['todos'] == []


def test_failed_atomic_replace_keeps_previous_plan(tmp_path, monkeypatch):
    from tool_loader import load_tool_handler
    handler = load_tool_handler('todo_write')
    with actor_context(agent_id='todo-test', task_id='todo-test', origin='training'):
        execute_tool('todo_write', {'todos': [item()]}, str(tmp_path), 'todo-test')
        path = tmp_path / 'agent_todo-test_todo_state.json'
        before = path.read_bytes()
        def fail(*args):
            raise OSError('simulated replace failure')
        monkeypatch.setattr(handler._file_io.os, 'replace', fail)
        result = execute_tool('todo_write', {'todos': [item('completed')]}, str(tmp_path), 'todo-test')
    assert json.loads(result)['success'] is False
    assert path.read_bytes() == before
    assert not list(tmp_path.glob('.*.tmp'))


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
