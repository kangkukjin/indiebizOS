"""음성 화면은 같은 대화의 턴만 제어하며 최근 다른 작업을 대신 읽거나 중단하지 않는다."""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import api_voice_chat as voice
import api_chat_sessions as chat_api
import chat_session_service as service
import conversation_sessions as sessions
from chat_runs import ChatRun


@pytest.fixture
def voice_client(tmp_path, monkeypatch):
    path = tmp_path / 'voice.db'
    with sessions.connection(path) as conn:
        conn.execute('CREATE TABLE conversations(id INTEGER PRIMARY KEY, role TEXT, '
                     'content TEXT, source TEXT, timestamp TEXT)')
    stores = {owner: sessions.SessionStore(path, 'conversations', owner)
              for owner in ('system_ai', 'appmaker')}
    def store_for(target, *_):
        return stores[target], {}
    monkeypatch.setattr(voice, 'get_store', store_for)
    monkeypatch.setattr(chat_api, 'get_store', store_for)
    monkeypatch.setattr(service, '_running', {})
    app = FastAPI()
    app.include_router(voice.router)
    app.include_router(chat_api.router)
    with TestClient(app) as client:
        yield stores['system_ai'], client


def test_turn_results_and_cancel_are_bound_to_the_requested_turn(voice_client):
    store, client = voice_client
    sid = store.create()['id']
    first = store.begin(sid)
    with sessions.scope(first):
        sessions.record_event({'type':'response', 'content':'재생 여부를 확인하지 못했습니다.'})
    store.finish(first)
    second = store.begin(sid)
    run = ChatRun('voice-fixture', target=('system_ai', None, second.turn_id))
    service.attach(run, second)
    try:
        root = '/chat-sessions/' + sid
        previous = client.get(root+'/voice-state', params={'turn_id':first.turn_id}).json()
        assert previous['state'] == 'completed' and previous['detail'] == '재생 여부를 확인하지 못했습니다.'
        assert client.get(root+'/voice-state').json()['turn_id'] == second.turn_id
        assert client.get(root+'/voice-state',params={'target':'appmaker'}).status_code == 404
        assert not client.post(root+'/cancel',json={'turn_id':first.turn_id}).json()['cancelled']
        assert not run.cancelled.is_set()
        assert client.post(root+'/cancel',json={'turn_id':second.turn_id}).json()['cancelled']
    finally:
        service.detach(run)


def test_missing_key_or_wrong_owner_never_opens_paid_session(voice_client, monkeypatch):
    store, client = voice_client
    sid = store.create()['id']
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    payload = {'sdp':'v=0 fixture offer'}
    url = '/chat-sessions/'+sid+'/voice'
    assert client.post(url,json={**payload,'target':'appmaker'}).status_code == 404
    assert client.post(url,json=payload).status_code == 503
