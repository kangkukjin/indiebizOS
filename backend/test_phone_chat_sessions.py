"""폰 자체 실행자의 세션 저장·재개·동시 실행·취소를 임시 DB에서 검증."""
import importlib.util
from pathlib import Path
import threading
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest


@pytest.mark.parametrize('version', ['pydantic', 'pydantic.v1'])
def test_phone_request_import_and_image_limit(version, monkeypatch):
    """맥 테스트 환경과 Android의 Pydantic 1.x 모두 부팅·개수 제한을 지킨다."""
    import importlib
    import sys
    pydantic = importlib.import_module(version)
    monkeypatch.setitem(sys.modules, 'pydantic', pydantic)
    path = Path(__file__).resolve().parents[1] / 'phone-companion/app/src/main/python/phone_chat_sessions.py'
    spec = importlib.util.spec_from_file_location('phone_request_compat', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.SessionRequest().images == []
    assert len(module.SessionRequest(images=['image'] * 20).images) == 20
    with pytest.raises(pydantic.ValidationError):
        module.SessionRequest(images=['image'] * 21)


@pytest.fixture
def phone(tmp_path, monkeypatch):
    import system_ai_memory as memory
    import chat_session_service as service
    import conversation_db
    monkeypatch.setattr(memory, 'MEMORY_DB_PATH', tmp_path / 'system.db')
    monkeypatch.setattr(conversation_db, '_ckpt_schedule', None)
    monkeypatch.setattr(conversation_db, '_ckpt_apply', None)
    monkeypatch.setattr(service, 'project_manager', None)
    memory.init_memory_db()
    (tmp_path / 'agents.yaml').write_text('agents:\n- id: a\n  name: phone agent\n')
    spec = importlib.util.spec_from_file_location('phone_chat_sessions', Path(__file__).resolve().parents[1] / 'phone-companion/app/src/main/python/phone_chat_sessions.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    seen, started, release = [], threading.Event(), threading.Event()

    def system(message, images, cancel_check):
        seen.append((message, memory.get_history_for_ai(limit=7)))
        memory.save_conversation('user', message, source='phone')
        if message == 'wait':
            started.set()
            while not release.wait(.01) and not cancel_check():
                pass
        if not cancel_check():
            memory.save_conversation('assistant', 'reply ' + message, source='phone-self')
        return {'response': 'reply ' + message}

    def agent(project, aid, message, history, images, cancel_check):
        seen.append((message, history))
        return {'response': 'reply ' + message}

    class PM:
        def get_project_path(self, pid):
            return tmp_path if pid == 'p' else None
    app = FastAPI()
    app.include_router(module.create_router(PM, system, agent))
    with TestClient(app) as client:
        yield client, seen, started, release
    release.set()


def finished(client, sid, target):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        response = client.get('/chat-sessions/' + sid, params=target)
        assert response.status_code == 200
        data = response.json()
        if data.get('turn') and data['turn']['state'] != 'running':
            return data
        time.sleep(.01)
    pytest.fail('phone turn did not finish')


@pytest.mark.parametrize('target', [{'target': 'system_ai'}, {'target': 'agent', 'project_id': 'p', 'agent_id': 'a'}])
def test_phone_sessions_are_resumable_and_context_isolated(phone, target):
    client, seen, _, _ = phone
    a = client.post('/chat-sessions', json=target).json()['id']
    assert client.post('/chat-sessions', json=target).json()['id'] == a
    assert client.post(f'/chat-sessions/{a}/messages', json={**target, 'message': 'first'}).status_code == 202
    assert finished(client, a, target)['turn']['state'] == 'completed'
    b = client.post('/chat-sessions', json=target).json()['id']
    assert b != a
    for sid, message in [(b, 'separate'), (a, 'resume')]:
        assert client.post(f'/chat-sessions/{sid}/messages', json={**target, 'message': message}).status_code == 202
        assert finished(client, sid, target)['turn']['state'] == 'completed'
    assert seen[0][1] == seen[1][1] == []
    assert any('first' in row['content'] for row in seen[2][1])
    assert all('separate' not in row['content'] for row in seen[2][1])
    rows = client.get('/chat-sessions/' + a, params=target).json()['messages']
    assert [r['content'] for r in rows] == ['first', 'reply first', 'resume', 'reply resume']
    assert client.get('/chat-sessions/' + a, params={'target': 'appmaker'}).status_code == 404


def test_phone_cancel_does_not_cancel_other_session(phone):
    client, _, started, _ = phone
    a = client.post('/chat-sessions', json={}).json()['id']
    assert client.post(f'/chat-sessions/{a}/messages', json={'message': 'wait'}).status_code == 202
    assert started.wait(3)
    b = client.post('/chat-sessions', json={}).json()['id']
    assert b != a
    assert client.post(f'/chat-sessions/{a}/messages', json={'message': 'duplicate'}).status_code == 409
    assert client.post(f'/chat-sessions/{b}/messages', json={'message': 'other'}).status_code == 202
    assert client.post(f'/chat-sessions/{a}/cancel', json={}).json()['cancelled']
    assert finished(client, a, {})['turn']['state'] == 'cancelled'
    assert finished(client, b, {})['turn']['state'] == 'completed'


def test_phone_agent_adapter_uses_isolated_stream_runner(tmp_path, monkeypatch):
    """실제 폰 함수의 인자 계약과 우편함 중복 기동 방지를 확인한다."""
    import ast
    import sys
    from types import SimpleNamespace
    from conversation_sessions import Binding, scope
    path = Path(__file__).resolve().parents[1] / 'phone-companion/app/src/main/python/phone_api.py'
    tree = ast.parse(path.read_text())
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == '_run_phone_agent')
    observed = {}

    class Runner:
        def __init__(self, config, common):
            observed['config'] = config
            self.ai = SimpleNamespace(process_message_stream=self.stream)
        def _init_ai(self):
            observed['initialized'] = True
        def stream(self, **kwargs):
            observed['request'] = kwargs
            yield {'type': 'final', 'content': '응답'}
        def stop(self):
            observed['stopped'] = True
    monkeypatch.setitem(sys.modules, 'agent_runner', SimpleNamespace(AgentRunner=Runner))
    monkeypatch.setitem(sys.modules, 'episode_logger', SimpleNamespace(EpisodeLogger=SimpleNamespace(start_episode=lambda *a: None, end_episode=lambda: None)))
    (tmp_path/'agents.yaml').write_text('agents:\n- id: a\n  name: 폰 에이전트\n')
    env = {'os': __import__('os'), '_phone_agent_runners': {}, '_phone_pm': lambda: SimpleNamespace(get_project_path=lambda _: tmp_path)}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(path), 'exec'), env)
    cancel = lambda: False
    with scope(Binding(str(tmp_path/'test.db'), 's', 'pair:1:2')):
        result = env['_run_phone_agent']('p', 'a', '질문', history=[{'role': 'user', 'content': '앞 대화'}], images=[], cancel_check=cancel)
    assert result == {'response': '응답'}
    assert observed['config']['_conversation_session'] == 's'
    assert observed['request']['history'][0]['content'] == '앞 대화'
    assert observed['request']['cancel_check'] is cancel
    assert observed['initialized'] and observed['stopped']
    assert env['_phone_agent_runners'] == {}


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))
