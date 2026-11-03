"""대화창 추가 지시: 실제 HTTP·원장·인박스·종료 경계의 접수 계약."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api_chat_sessions as api
import chat_session_service as service
import conversation_sessions as sessions
import steer_inbox as inbox
from chat_runs import ChatRun
from conversation_handoff import Handoff


@pytest.fixture
def chat(tmp_path, monkeypatch):
    path = tmp_path / 'conversation.db'
    with sessions.connection(path) as conn:
        conn.execute('CREATE TABLE conversations(id INTEGER PRIMARY KEY, role TEXT, '
                     'content TEXT, source TEXT, timestamp TEXT)')
    stores = {owner: sessions.SessionStore(path, 'conversations', owner)
              for owner in ('system_ai', 'appmaker')}
    monkeypatch.setattr(service, '_running', {})
    monkeypatch.setattr(api, 'get_store', lambda target, *args: (stores[target], {}))
    for name in ('_inbox', '_active', '_journals', '_delivered', '_held'):
        monkeypatch.setattr(inbox, name, {})
    monkeypatch.setattr(inbox, '_sealed', set())
    app = FastAPI()
    app.include_router(api.router)
    with TestClient(app) as client:
        yield stores['system_ai'], client


@contextmanager
def running(store):
    binding = store.begin(store.create()['id'])
    run = ChatRun('fixture', target=('system_ai', None, binding.turn_id))
    service.attach(run, binding)
    with sessions.scope(binding):
        handoff = Handoff()
    try:
        with inbox.task_scope(['system_ai'], binding.turn_id, handoff.record):
            yield run, handoff
    finally:
        service.detach(run)
        store.finish(binding, 'cancelled' if run.cancelled.is_set() else 'completed')


def send(client, run, message='제목만 변경', request_id='request-1', **overrides):
    binding = run.session_binding
    return client.post(f'/chat-sessions/{binding.session_id}/steer', json={
        'turn_id': binding.turn_id, 'request_id': request_id, 'message': message, **overrides})


def test_http_duplicate_delivery_and_durable_retry_after_completion(chat):
    store, client = chat
    with running(store) as (run, _):
        # 두 창의 동시 재전송도 한 번만 접수·소비한다.
        with ThreadPoolExecutor(max_workers=4) as pool:
            replies = list(pool.map(lambda _: send(client, run), range(8)))
        assert all(r.status_code == 200 and r.json()['accepted'] for r in replies)
        assert inbox.drain('system_ai', run.target[2]) == ['제목만 변경']
        assert inbox.drain('system_ai', run.target[2]) == []
        inbox.complete('system_ai', run.target[2])
        assert not send(client, run, message='다른 내용').json()['accepted']
    # 프로세스 메모리의 접수 상태가 없어도 저장된 영수증으로 같은 답을 한다.
    assert not inbox._active and not service._running
    assert send(client, run).json()['accepted']
    assert not send(client, run, request_id='new-request').json()['accepted']
    result = client.get(f'/chat-sessions/{run.session_binding.session_id}').json()
    assert [r['instruction'] for r in result['steering']] == ['제목만 변경']
    assert result['steering'][0]['turn_id'] == run.session_binding.turn_id
    assert result['turn']['state'] == 'completed'


def test_sessions_turns_and_owner_cannot_cross(chat):
    store, client = chat
    with running(store) as (a, _), running(store) as (b, _):
        assert send(client, a, target='appmaker').status_code == 404
        assert not send(client, a, turn_id=b.session_binding.turn_id).json()['accepted']
        assert send(client, b, message='B에만 전달').json()['accepted']
        assert inbox.drain('system_ai', a.target[2]) == []
        assert inbox.drain('system_ai', b.target[2]) == ['B에만 전달']
        a.cancelled.set()
        assert not send(client, a).json()['accepted']
        assert service.steering_history(store, a.session_binding.session_id) == []


def test_full_queue_sealed_turn_and_storage_failure_preserve_input(chat):
    store, client = chat
    with running(store) as (run, handoff):
        for n in range(5):
            assert send(client, run, message=f'지시 {n}', request_id=str(n)).json()['accepted']
        assert not send(client, run, request_id='full').json()['accepted']
        assert len(inbox.drain('system_ai', run.target[2])) == 5
        assert inbox.take_or_seal('system_ai', run.target[2]) == []
        assert not send(client, run, request_id='late').json()['accepted']
        # 접수된 요청은 종료 경계가 닫혀도 같은 영수증을 돌려준다.
        assert send(client, run, message='지시 0', request_id='0').json()['accepted']
    with running(store) as (run, handoff):
        def fail(*args):
            raise OSError('fixture storage unavailable')
        inbox._journals[('system_ai', run.target[2])] = fail
        assert not send(client, run).json()['accepted']
        assert inbox.drain('system_ai', run.target[2]) == []
        assert service.steering_history(store, run.session_binding.session_id) == []


@pytest.mark.parametrize('message', ['', '   ', 'x' * 2001])
def test_invalid_text_is_never_accepted(chat, message):
    store, client = chat
    with running(store) as (run, _):
        reply = send(client, run, message=message)
        assert reply.status_code == 422 or reply.json()['accepted'] is False
        assert inbox.drain('system_ai', run.target[2]) == []


def test_http_steering_at_final_boundary_continues_same_run(chat):
    from dialogue_continuation import stream
    store, client = chat
    prompts = []
    with running(store) as (run, handoff):
        def execute(message, history):
            prompts.append(message)
            yield {'type': 'final', 'content': '첫 답' if len(prompts) == 1 else '제목 수정 완료'}
            if len(prompts) == 1:
                assert send(client, run).json()['accepted']
        events = list(stream(execute, '보고서 작성', [], 'system_ai', run.target[2], handoff))
        assert len(prompts) == 2 and '제목만 변경' in prompts[1]
        assert [e['content'] for e in events if e['type'] == 'final'] == ['제목 수정 완료']
        result = service.snapshot(store, run.session_binding.session_id)
        assert sum(e['type'] == 'handoff.steer.completed' for e in result['events']) == 1


def test_parent_agent_steering_is_not_shown_as_user_input(chat):
    store, _ = chat
    with running(store) as (run, _):
        inbox.post('system_ai', '부모의 지시', run.target[2], require_active=True,
                   source='agent', sender='parent')
        assert service.steering_history(store, run.session_binding.session_id) == []


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
