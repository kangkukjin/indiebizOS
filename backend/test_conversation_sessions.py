"""영속 세션: 원문 이전, 맥락/요약/실행 분리, 재접속·중단·다른 소유자 거절."""
import asyncio
import json
import sqlite3
from types import SimpleNamespace

import pytest
import conversation_sessions as sessions
from conversation_db import ConversationDB


@pytest.fixture
def project(tmp_path, monkeypatch):
    import conversation_db
    monkeypatch.setattr(conversation_db, '_ckpt_schedule', None)
    monkeypatch.setattr(conversation_db, '_ckpt_apply', None)
    db = ConversationDB(str(tmp_path / 'conversations.db'))
    user = db.get_or_create_agent('user', 'human')
    agent = db.get_or_create_agent('assistant')
    store = sessions.SessionStore(db.db_path, 'messages', sessions.pair_owner(user, agent))
    return db, user, agent, store


def test_sessions_alternate_and_resume_without_context_leak(project):
    db, user, agent, store = project
    old_id = db.save_message(user, agent, 'legacy original')
    a, b = store.create('A')['id'], store.create('B')['id']
    for sid, text in [(a, 'A1'), (b, 'B1'), (a, 'A2')]:
        binding = store.begin(sid)
        with sessions.scope(binding):
            assert all('legacy' not in m['content'] for m in db.get_history_for_ai(agent, user))
            db.save_message(user, agent, text)
            db.save_message(agent, user, text + ' answer')
        store.finish(binding)
    assert [m['content'] for m in store.history(a)['messages']] == ['A1','A1 answer','A2','A2 answer']
    assert [m['content'] for m in store.history(b)['messages']] == ['B1','B1 answer']
    assert db.get_history_for_ai(agent,user)[0]['content'].endswith('legacy original')
    with db.get_connection() as conn:
        assert conn.execute('SELECT content FROM messages WHERE id=?',(old_id,)).fetchone()[0] == 'legacy original'
    reopened = sessions.SessionStore(db.db_path, 'messages', store.owner)
    assert reopened.history(a) == store.history(a)


def test_title_uses_first_request_and_keeps_renames(project):
    db, user, agent, store = project
    sid = store.create()['id']
    with sessions.scope(sessions.Binding(store.path, sid, store.owner)):
        db.save_message(user, agent, '  이번 주\n회의 자료를 정리해줘  ')
        db.save_message(agent, user, '알겠습니다')
        db.save_message(user, agent, '지난주 자료도 포함해줘')
    assert next(s for s in store.list() if s['id'] == sid)['title'] == '이번 주 회의 자료를 정리해줘'
    store.update(sid, title='주간 회의')
    with sessions.scope(sessions.Binding(store.path, sid, store.owner)):
        db.save_message(user, agent, '추가 요청')
    assert next(s for s in store.list() if s['id'] == sid)['title'] == '주간 회의'


def test_one_turn_per_session_and_cross_session_cancellation(project):
    _, _, _, store = project
    a, b = store.create()['id'], store.create()['id']
    ba, bb = store.begin(a), store.begin(b)
    with pytest.raises(ValueError, match='이미 실행'):
        store.begin(a)
    import chat_session_service as service
    from threading import Event
    ra = SimpleNamespace(cancelled=Event()); rb = SimpleNamespace(cancelled=Event())
    service.attach(ra,ba); service.attach(rb,bb)
    try:
        assert service.cancel(store,a)
        assert ra.cancelled.is_set() and not rb.cancelled.is_set()
    finally:
        service.detach(ra); service.detach(rb)
    store.finish(ba,'cancelled'); store.finish(bb)
    assert store.begin(a)


def test_owner_validation_archive_and_pagination(project):
    db,user,agent,store = project
    sid = store.create()['id']
    other = sessions.SessionStore(db.db_path,'messages',sessions.pair_owner(user,db.get_or_create_agent('other')))
    with pytest.raises(ValueError): other.history(sid)
    with pytest.raises(ValueError): other.begin(sid)
    with sessions.scope(sessions.Binding(db.db_path,sid,store.owner)):
        for i in range(65): db.save_message(user,agent,str(i))
    latest = store.history(sid)
    assert latest['has_older'] and len(latest['messages']) == 50
    earlier = store.history(sid,int(latest['messages'][0]['id']))
    assert len(earlier['messages']) == 15 and not earlier['has_older']
    store.update(sid,archived=True)
    with pytest.raises(ValueError,match='보관'): store.begin(sid)
    store.update(sid,title='renamed',archived=False)
    assert store.begin(sid)


def test_migrate_original_rows_idempotently(project):
    db,user,agent,store = project
    with db.get_connection() as conn:
        conn.execute('INSERT INTO messages(from_agent_id,to_agent_id,content) VALUES (?,?,?)',(user,agent,'original'))
        conn.commit()
    for _ in range(2): sessions.SessionStore(db.db_path,'messages',store.owner)
    with db.get_connection() as conn:
        rows = conn.execute('SELECT content,session_id FROM messages').fetchall()
        assert len(rows) == 1 and rows[0]['content'] == 'original' and rows[0]['session_id'].startswith('legacy-')
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute('INSERT INTO messages(content,session_id) VALUES (?,?)',('bad','unknown'))
        conn.rollback()


@pytest.mark.parametrize('table', ['messages', 'conversations'])
def test_migrate_legacy_turn_schema_preserves_rows_and_events(tmp_path, table):
    path = tmp_path / 'legacy.db'
    with sessions.connection(path) as conn:
        conn.execute(f'CREATE TABLE {table} (id INTEGER PRIMARY KEY, content TEXT)')
        conn.execute('''CREATE TABLE conversation_turns (
            id TEXT PRIMARY KEY, session_id TEXT NOT NULL, state TEXT NOT NULL,
            process TEXT NOT NULL, started_at TEXT NOT NULL, finished_at TEXT, error TEXT)''')
        original = ('old-turn', 'old-session', 'failed', 'old-process', 'start', 'end', 'old error')
        conn.execute('INSERT INTO conversation_turns VALUES (?,?,?,?,?,?,?)', original)
        sessions.ensure_schema(conn, table)
        conn.execute('INSERT INTO conversation_sessions(id,owner,title,created_at,updated_at) '
                     'VALUES (?,?,?,?,?)', ('old-session', 'owner', 'original', 'start', 'end'))
        conn.execute('INSERT INTO conversation_events(session_id,turn_id,created_at,payload) '
                     'VALUES (?,?,?,?)', ('old-session', 'old-turn', 'start', '{"type":"start"}'))
        sessions.ensure_schema(conn, table)
        row = conn.execute('SELECT * FROM conversation_turns').fetchone()
        assert tuple(row) == (*original, '')
    with sessions.scope(sessions.Binding(str(path), 'old-session', 'owner', 'old-turn')):
        sessions.record_event({'type': 'stream_chunk', 'content': 'resumed draft'})
        with sessions.connection(path) as conn:
            sessions.ensure_schema(conn, table)
            assert conn.execute('SELECT stream_content FROM conversation_turns').fetchone()[0] == 'resumed draft'
        sessions.record_event({'type': 'response', 'content': 'final answer'})
    with sessions.connection(path) as conn:
        assert conn.execute('SELECT stream_content FROM conversation_turns').fetchone()[0] == ''
        events = [json.loads(r[0]) for r in conn.execute('SELECT payload FROM conversation_events ORDER BY id')]
        assert events == [{'type': 'start'}, {'type': 'response', 'content': 'final answer'}]


def test_system_ai_sessions_and_checkpoint_isolation(tmp_path, monkeypatch):
    import system_ai_memory as memory
    import history_checkpoint as hc
    monkeypatch.setattr(memory,'MEMORY_DB_PATH',tmp_path/'system.db')
    monkeypatch.setattr(memory,'_ckpt_schedule',None)
    monkeypatch.setattr(memory,'_ckpt_apply',hc._apply_system)
    memory.init_memory_db()
    store = sessions.SessionStore(memory.MEMORY_DB_PATH,'conversations','system_ai')
    a,b = store.create()['id'],store.create()['id']
    for sid in (a,b):
        with sessions.scope(sessions.Binding(store.path,sid,store.owner)):
            for i in range(12): memory.save_conversation('user',f'{sid}:{i}')
            def summary(prev, rows):
                assert all(sid in content for _,content in rows)
                return f'only {sid}'
            monkeypatch.setattr(hc,'_summarize',summary)
            assert hc._update(store.path,'session:'+sid,7,hc._fetch_system('system_ai',sid)) == 'updated'
            history = memory.get_history_for_ai()
            assert all((b if sid == a else a) not in row['content'] for row in history)
            assert f'only {sid}' in history[0]['content']
    assert memory.get_history_for_ai() == []
    with sessions.connection(store.path) as conn:
        assert conn.execute('SELECT COUNT(*) FROM history_checkpoint_versions').fetchone()[0] == 2


def test_events_survive_without_a_connected_window(project):
    _,_,_,store=project
    binding=store.begin(store.create()['id'])
    from websocket_manager import WebSocketManager
    manager=WebSocketManager()
    async def emit():
        with sessions.scope(binding):
            await manager.send_message('no-window',{'type':'stream_chunk','content':'working'})
            await manager.send_message('no-window',{'type':'tool_start','id':'call1','name':'read'})
            await manager.send_message('no-window',{'type':'tool_result','id':'call1','name':'read','result':'ok'})
    asyncio.run(emit())
    from chat_session_service import snapshot
    result=snapshot(store,binding.session_id)
    assert [e['type'] for e in result['events']] == ['tool_start','tool_result']
    assert result['turn']['stream_content'] == ''


def test_cli_keys_separate_sessions_and_return_to_original(project):
    from providers.cli_provider import CliSubprocessProvider
    provider=object.__new__(CliSubprocessProvider)
    provider.agent_id='agent';provider.agent_name='Agent'
    _,_,_,store=project
    keys=[]
    a,b=store.create()['id'],store.create()['id']
    for sid in (a,b,a):
        with sessions.scope(sessions.Binding(store.path,sid,store.owner)):
            keys.append(provider._get_session_key())
    assert keys[0] == keys[2] and keys[0] != keys[1]


def test_http_turn_runs_after_response_and_keeps_origin(project,monkeypatch):
    _,_,_,store=project
    import api_chat_sessions as api
    import chat_session_service as service
    import chat_streams
    from chat_runs import registry
    from websocket_manager import manager
    monkeypatch.setattr(api,'get_store',lambda *args:(store,{}))
    monkeypatch.setattr(service,'from_data',lambda data:store)
    gate=asyncio.Event()
    async def fake(client_id,data):
        await gate.wait()
        await manager.send_message(client_id,{'type':'response','content':'finished'})
    monkeypatch.setattr(chat_streams,'handle_system_ai_chat_stream',fake)
    sid=store.create()['id']
    async def run():
        reply=await api.send(sid,api.Message(message='go'))
        assert reply['session_id'] == sid
        await asyncio.sleep(0)
        assert store.list()[0]['running'] or any(s['running'] for s in store.list())
        with pytest.raises(Exception) as exc: await api.send(sid,api.Message(message='duplicate'))
        assert exc.value.status_code == 409
        gate.set()
        await asyncio.gather(*list(registry.background))
        assert service.snapshot(store,sid)['turn']['state'] == 'completed'
    asyncio.run(run())


def test_research_messages_are_not_migrated_into_general_sessions(project):
    db,user,agent,store=project
    mid=db.save_message(user,agent,'research source',contact_type='research')
    db.save_message(user,agent,'ordinary source')
    sessions.SessionStore(db.db_path,'messages',store.owner)
    with db.get_connection() as conn:
        row=conn.execute('SELECT content,contact_type,session_id FROM messages WHERE id=?',(mid,)).fetchone()
        assert tuple(row) == ('research source','research',None)
    assert all('research source' != m['content'] for s in store.list() for m in store.history(s['id'])['messages'])


@pytest.mark.parametrize('target',['system_ai','agent'])
@pytest.mark.parametrize('legacy_schema', [False, True])
def test_real_stream_adapter_preserves_session_history(tmp_path,monkeypatch,target,legacy_schema):
    import system_ai_memory as memory
    import system_ai_core as core
    import chat_session_service as service
    import chat_streams
    import api_chat_sessions as api
    from chat_runs import registry
    monkeypatch.setattr(memory,'MEMORY_DB_PATH',tmp_path/'system.db')
    monkeypatch.setattr(memory,'_ckpt_schedule',None)
    monkeypatch.setattr(memory,'_ckpt_apply',None)
    memory.init_memory_db()
    (tmp_path/'agents.yaml').write_text('agents:\n  - id: writer\n    name: Writer\n')
    pm=SimpleNamespace(get_project_path=lambda _id:tmp_path)
    monkeypatch.setattr(service,'project_manager',pm)
    monkeypatch.setattr(chat_streams,'project_manager',pm)
    histories=[]
    class Runner:
        ai=SimpleNamespace(get_last_tool_images=lambda:[])
        def cognitive_stream(self,message,history,**kwargs):
            histories.append((sessions.current().session_id,history))
            yield {'type':'stream_chunk','content':'draft'}
            yield {'type':'final','content':'answer '+message}
    monkeypatch.setattr(core,'_resolve_system_ai_config',lambda:{'provider':'ollama','api_key':''})
    monkeypatch.setattr(core,'get_system_ai_runner',lambda:Runner())
    monkeypatch.setattr(chat_streams,'_ensure_agent_runner',lambda *args:{'runner':Runner()})
    params={'target':target,'project_id':'p' if target=='agent' else '', 'agent_id':'writer' if target=='agent' else ''}
    store,_=service.store_for(**params)
    a,b=store.create('A')['id'],store.create('B')['id']
    if legacy_schema:
        with sessions.connection(store.path) as conn:
            conn.execute('ALTER TABLE conversation_turns DROP COLUMN stream_content')
    async def run():
        for sid,text in [(a,'A1'),(b,'B1'),(a,'A2')]:
            await api.send(sid,api.Message(**params,message=text))
            await asyncio.gather(*list(registry.background))
            result=service.snapshot(store,sid)
            assert result['turn']['state']=='completed',result
    asyncio.run(run())
    assert histories[0][1] == [] and histories[1][1] == []
    assert 'A1' in str(histories[2][1]) and 'B1' not in str(histories[2][1])
    assert [m['content'] for m in store.history(a)['messages']] == ['A1','answer A1','A2','answer A2']
    assert [m['content'] for m in store.history(b)['messages']] == ['B1','answer B1']


def test_session_panels_and_late_task_callbacks_keep_their_owner(project, monkeypatch):
    import sys
    from pathlib import Path
    from thread_context import set_current_task_id
    from chat_session_service import respond_panel
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / 'data/packages/installed/tools/system_essentials'))
    from essentials_state_paths import get_state_paths
    _, _, _, store = project
    a, b = store.create()['id'], store.create()['id']
    binding = sessions.Binding(store.path, a, store.owner, 'panel-turn')
    with sessions.scope(binding):
        sessions.bind_task('fixture-panel-task')
        paths = get_state_paths(str(Path(store.path).parent), 'agent')
        paths['question'].write_text(json.dumps({'status':'pending','questions':[{'question':'continue?'}]}))
    with sessions.scope(sessions.Binding(store.path, b, store.owner)):
        assert not get_state_paths(str(Path(store.path).parent), 'agent')['question'].exists()
    respond_panel(binding, 'answer', 'yes')
    assert json.loads(paths['question'].read_text())['status'] == 'answered'
    set_current_task_id('fixture-panel-task')
    try:
        assert sessions.current() == binding
        assert get_state_paths(str(Path(store.path).parent), 'agent') == paths
        with sessions.scope(None):
            default = get_state_paths(str(Path(store.path).parent), 'agent')
            assert default['question'].parent == Path(store.path).parent
            assert default['question'].name == 'agent_agent_question_state.json'
    finally:
        set_current_task_id(None)


def test_history_invalid_page_size_is_explicit(project):
    store = project[3]
    sid = store.create()['id']
    for limit in (0, 101):
        with pytest.raises(ValueError, match='1~100'):
            store.history(sid, limit=limit)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
