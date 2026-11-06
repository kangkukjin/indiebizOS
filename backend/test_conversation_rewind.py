"""Real SQLite and filesystem rewind, conflict and crash recovery contracts."""
import pytest
import conversation_sessions as sessions
from conversation_db import ConversationDB
from coding_store import CodingStore
from file_workspace import FileWorkspace
import conversation_rewind as rewind


@pytest.fixture
def setup(tmp_path, monkeypatch):
    import conversation_db
    monkeypatch.setattr(conversation_db, '_ckpt_schedule', None)
    monkeypatch.setattr(conversation_db, '_ckpt_apply', None)
    db = ConversationDB(str(tmp_path / 'chat.db'))
    user = db.get_or_create_agent('user', 'human'); agent = db.get_or_create_agent('agent')
    store = sessions.SessionStore(db.db_path, 'messages', sessions.pair_owner(user, agent))
    sid = store.create()['id']
    journal = CodingStore(tmp_path / 'changes')
    work = tmp_path / 'work'; work.mkdir(); (work / 'a').write_text('before\n')
    app = FileWorkspace(journal); row = app.open(work)
    return db, user, agent, store, sid, journal, work, app, row


def change(setup):
    db, user, agent, store, sid, journal, work, app, row = setup
    binding = store.begin(sid)
    with sessions.scope(binding):
        db.save_message(user, agent, 'change the file')
        p = app.patch(row, '*** Begin Patch\n*** Update File: a\n@@\n-before\n+after\n*** Add File: b\n+created\n*** End Patch')
        app.apply(row, p['proposal'])
        db.save_message(agent, user, 'done')
    store.finish(binding)
    return rewind.list_checkpoints(store, sid)['items'][0]['id']


def test_both_rewind_preserves_archive_and_new_turn(setup):
    db, user, agent, store, sid, journal, work, app, row = setup
    checkpoint = change(setup)
    plan = rewind.preview(store, sid, checkpoint, db=journal)
    assert not plan['conflicts'] and len(plan['files']) == 2
    done = rewind.execute(store, sid, plan['id'], db=journal)
    assert done['state'] == 'completed'
    assert (work / 'a').read_text() == 'before\n' and not (work / 'b').exists()
    assert store.history(sid)['messages'] == []
    with db.get_connection() as conn:
        assert conn.execute('SELECT count(*) FROM messages WHERE session_id=?', (sid,)).fetchone()[0] == 2
    binding = store.begin(sid)
    with sessions.scope(binding):
        assert db.get_history_for_ai(agent, user) == []
        db.save_message(user, agent, 'a different direction')
        history = db.get_history_for_ai(agent, user)
        assert len(history) == 1 and 'different direction' in history[0]['content']
        assert sessions.revision_suffix(binding) == '@revision:1'
    store.finish(binding)
    assert rewind.execute(store, sid, plan['id'], db=journal)['state'] == 'completed'


def test_conflict_and_files_only(setup):
    _, _, _, store, sid, journal, work, _, _ = setup
    checkpoint = change(setup)
    (work / 'a').write_text('human edit\n')
    plan = rewind.preview(store, sid, checkpoint, 'files', db=journal)
    assert plan['conflicts']
    with pytest.raises(Exception): rewind.execute(store, sid, plan['id'], db=journal)
    assert (work / 'b').exists()
    (work / 'a').write_text('after\n')
    plan = rewind.preview(store, sid, checkpoint, 'files', db=journal)
    rewind.execute(store, sid, plan['id'], db=journal)
    assert len(store.history(sid)['messages']) == 2


def test_rewind_resume_after_second_file_failure(setup, monkeypatch):
    _, _, _, store, sid, journal, work, _, _ = setup
    checkpoint = change(setup)
    plan = rewind.preview(store, sid, checkpoint, db=journal)
    import file_changes
    original = file_changes._replace
    n = [0]
    def fail(path, value):
        n[0] += 1
        if n[0] == 2: raise OSError('injected power loss')
        original(path, value)
    monkeypatch.setattr(file_changes, '_replace', fail)
    with pytest.raises(OSError): rewind.execute(store, sid, plan['id'], db=journal)
    assert len(store.history(sid)['messages']) == 2
    assert rewind.get(store, sid, plan['id'])['state'] == 'applying_files'
    monkeypatch.setattr(file_changes, '_replace', original)
    rewind.execute(store, sid, plan['id'], db=journal)
    assert store.history(sid)['messages'] == []
    assert (work / 'a').read_text() == 'before\n'


def test_tracked_copy_move_delete_restore_executable(setup, monkeypatch):
    db, user, agent, store, sid, _, work, _, _ = setup
    monkeypatch.setenv('INDIEBIZ_RUNTIME_STATE_DIR', str(work.parent/'runtime'))
    journal = CodingStore()
    import file_changes
    (work/'a').chmod(0o755)
    binding = store.begin(sid)
    with sessions.scope(binding):
        db.save_message(user, agent, 'copy move delete')
        file_changes.transfer_file(work/'a', work/'b')
        file_changes.transfer_file(work/'b', work/'c', move=True)
        file_changes.delete_file(work/'a')
    store.finish(binding)
    assert not (work/'a').exists() and (work/'c').exists()
    point = rewind.list_checkpoints(store, sid)['items'][0]['id']
    plan = rewind.preview(store, sid, point, db=journal)
    assert not plan['conflicts']
    rewind.execute(store, sid, plan['id'], db=journal)
    assert (work/'a').read_text() == 'before\n'
    assert (work/'a').stat().st_mode & 0o777 == 0o755
    assert not (work/'b').exists() and not (work/'c').exists()


def test_detached_worker_finishes_restore(setup):
    import time
    _, _, _, store, sid, journal, work, _, _ = setup
    checkpoint = change(setup)
    plan = rewind.preview(store, sid, checkpoint, db=journal)
    receipt = rewind.submit(store, sid, plan['id'], db=journal)
    assert receipt['task_ref']['kind'] == 'rewind'
    deadline = time.time()+15
    while time.time()<deadline:
        state = rewind.get(store, sid, plan['id'])
        if state['state']=='completed' or state.get('error'): break
        time.sleep(.05)
    assert state['state']=='completed', state
    assert (work/'a').read_text() == 'before\n'
    assert store.history(sid)['messages']==[]


def test_old_turn_cannot_append_after_rewind(setup):
    db, user, agent, store, sid, journal, work, app, row = setup
    old = store.begin(sid)
    with sessions.scope(old):
        db.save_message(user, agent, 'old request')
    store.finish(old)
    point = rewind.list_checkpoints(store, sid)['items'][0]['id']
    plan = rewind.preview(store, sid, point, mode='conversation', db=journal)
    rewind.execute(store, sid, plan['id'], db=journal)
    with sessions.scope(old), pytest.raises(ValueError, match='판본'):
        db.save_message(agent, user, 'late old response')
    assert store.history(sid)['messages'] == []


def test_child_effect_is_owned_by_original_turn(setup):
    db, user, agent, store, sid, journal, work, app, row = setup
    parent = store.begin(sid)
    child_sid = store.create()['id']
    child = store.begin(child_sid)
    with sessions.scope(child), sessions.effect_scope(parent):
        p = app.patch(row, '*** Begin Patch\n*** Update File: a\n@@\n-before\n+child\n*** End Patch')
        app.apply(row, p['proposal'])
    store.finish(child)
    store.finish(parent)
    checkpoint = rewind.list_checkpoints(store, sid)['items'][0]['id']
    plan = rewind.preview(store, sid, checkpoint, db=journal)
    assert len(plan['files']) == 1
    rewind.execute(store, sid, plan['id'], db=journal)
    assert (work/'a').read_text()=='before\n'
    with sessions.scope(child), sessions.effect_scope(parent):
        with pytest.raises(Exception, match='판본'):
            app.patch(row, '*** Begin Patch\n*** Update File: a\n@@\n-before\n+stale\n*** End Patch')
