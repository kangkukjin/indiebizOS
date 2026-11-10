"""HTTP agent commands retain conversation ownership for task delegation."""
import asyncio
import boot_paths  # noqa: F401
from types import SimpleNamespace

import pytest
import conversation_sessions as sessions
import task_worker_store as store
import task_workers
from conversation_db import ConversationDB


def prepare(tmp_path, monkeypatch):
    import api_agents
    import delegation_tasks
    from episode_logger import EpisodeLogger
    path = tmp_path / "conversations.db"
    monkeypatch.setattr(api_agents, "project_manager", SimpleNamespace(get_project_path=lambda _: tmp_path))
    monkeypatch.setattr(delegation_tasks, "_owner_db_path", lambda owner: path if owner == "p" else tmp_path / "system.db")
    monkeypatch.setattr(task_workers, "dispatch", lambda *args: None)
    monkeypatch.setattr(EpisodeLogger, "start_episode", lambda *a, **kw: None)
    monkeypatch.setattr(EpisodeLogger, "end_episode", lambda: None)
    return api_agents, path


@pytest.mark.parametrize("origin", [None, "training"])
def test_command_task_worker_followup_has_same_owned_session(tmp_path, monkeypatch, origin):
    api, path = prepare(tmp_path, monkeypatch)
    seen, receipts = [], []

    def cognitive(command, history, **kwargs):
        binding = sessions.current()
        assert binding is not None
        seen.append(binding)
        args = {"request_id": "one", "message": command}
        if receipts:
            args["worker_ref"] = receipts[0]["worker_ref"]
        receipt = task_workers.delegate(args, str(tmp_path))
        receipts.append(receipt)
        store.finish(path, receipt["task_ref"]["task_id"], "completed", "child result")
        yield {"type": "final", "content": "finished"}

    runner = SimpleNamespace(config={"id": "a", "name": "agent"}, cognitive_stream=cognitive)
    for command in ("initial", "followup"):
        assert api._run_agent_command("p", "a", runner, command, origin) == "finished"
    assert seen[0].session_id == seen[1].session_id
    assert seen[0].turn_id != seen[1].turn_id
    assert receipts[0]["worker_ref"] == receipts[1]["worker_ref"]
    assert receipts[0]["task_ref"] != receipts[1]["task_ref"]
    with sessions.connection(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM conversation_task_links").fetchone()[0] == 4
        assert conn.execute("SELECT COUNT(*) FROM conversation_turns WHERE state='running'").fetchone()[0] == 0


@pytest.mark.parametrize("origin", [None, "training"])
def test_command_waits_for_owned_children_after_model_returns(tmp_path, monkeypatch, origin):
    api, path = prepare(tmp_path, monkeypatch)
    receipts = []

    def cognitive(command, history, **kwargs):
        receipts.append(task_workers.delegate({"request_id": "one", "message": "child"}, str(tmp_path)))
        yield {"type": "final", "content": "waiting for child"}

    runner = SimpleNamespace(config={"id": "a", "name": "agent"}, cognitive_stream=cognitive)
    api._run_agent_command("p", "a", runner, "request", origin, task_id="parent")
    db = ConversationDB(str(path))
    assert db.get_task("parent")["status"] == "waiting_children"
    store.finish(path, receipts[0]["task_ref"]["task_id"], "completed", "child result")
    parent = db.get_task("parent")
    assert parent["status"] == "completed" and parent["pending_delegations"] == 0
    assert parent["result"] == "waiting for child"


def test_command_training_preserves_separate_history_and_worker_ownership(tmp_path, monkeypatch):
    api, path = prepare(tmp_path, monkeypatch)
    seen, receipts = [], []

    def cognitive(command, history, **kwargs):
        seen.append((command, sessions.current().session_id, history))
        if command == "training":
            receipt = task_workers.delegate({"request_id": "one", "message": "child"}, str(tmp_path))
            receipts.append(receipt)
            store.finish(path, receipt["task_ref"]["task_id"], "completed", "child result")
        if command == "normal followup":
            with pytest.raises(ValueError):
                task_workers.delegate({"request_id": "two", "message": "child",
                                       "worker_ref": receipts[0]["worker_ref"]}, str(tmp_path))
        yield {"type": "final", "content": command + " response"}

    runner = SimpleNamespace(config={"id": "a", "name": "agent"}, cognitive_stream=cognitive)
    for command, origin in (("normal", None), ("training", "training"),
                            ("normal followup", None), ("training followup", "training")):
        api._run_agent_command("p", "a", runner, command, origin)
    assert seen[0][1] == seen[2][1] != seen[1][1] == seen[3][1]
    assert "training response" not in str(seen[2][2])
    assert "normal response" not in str(seen[3][2])
    assert "training response" in str(seen[3][2])
    with sessions.connection(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM messages WHERE contact_type='rehearsal' AND session_id IS NOT NULL").fetchone()[0] == 0




def test_role_note_http_and_lifecycle_share_storage(tmp_path, monkeypatch):
    import api_agents as api
    import agent_lifecycle as lifecycle
    import yaml
    monkeypatch.setattr(api, 'project_manager', SimpleNamespace(get_project_path=lambda _: tmp_path))
    monkeypatch.setattr(lifecycle, '_project_path', lambda _: tmp_path)
    (tmp_path / 'agents.yaml').write_text(yaml.safe_dump({'agents': [{'id': 'a', 'name': 'one'}]}))
    assert asyncio.run(api.get_agent_role('p', 'a')) == {'role': '', 'agent_name': 'one'}
    assert asyncio.run(api.update_agent_role('p', 'a', api.AgentRole(role='role'))) == {'status': 'saved', 'agent_name': 'one'}
    assert lifecycle.read_text('p', 'a', 'role') == 'role'
    lifecycle.write_text('p', 'a', 'note', 'memo')
    assert asyncio.run(api.get_agent_note('p', 'a')) == {'note': 'memo'}
    assert asyncio.run(api.save_agent_note('p', 'a', api.AgentNote(note=''))) == {'status': 'saved'}
    assert lifecycle.read_text('p', 'a', 'note') == ''


@pytest.mark.parametrize('state', ['missing', 'empty', 'no_id', 'broken', 'duplicate', 'nameless', 'legacy_none'])
def test_text_endpoint_absence_and_error_contract(tmp_path, monkeypatch, state):
    import api_agents as api
    from fastapi import HTTPException
    import yaml
    monkeypatch.setattr(api, 'project_manager', SimpleNamespace(get_project_path=lambda _: tmp_path))
    data = {'agents': [{'id': 'a', 'name': 'one'}]}
    if state == 'no_id':
        data['agents'] = []
    elif state == 'duplicate':
        data['agents'] *= 2
    elif state in ('nameless', 'legacy_none'):
        data['agents'] = [{'id': 'a'}]
        if state == 'legacy_none':
            (tmp_path / 'agent_None_role.txt').write_text('orphan')
    if state != 'missing':
        (tmp_path / 'agents.yaml').write_text('' if state == 'empty' else '[' if state == 'broken' else yaml.safe_dump(data))
    if state in ('missing', 'empty', 'no_id'):
        assert asyncio.run(api.get_agent_note('p', 'a')) == {'note': ''}
        expected = 404
    elif state == 'nameless':
        assert asyncio.run(api.update_agent_role('p', 'a', api.AgentRole(role='x'))) == {'status': 'saved', 'agent_name': 'a'}
        assert (tmp_path / 'agent_a_role.txt').read_text() == 'x'
        return
    else:
        expected = 500 if state == 'broken' else 409
    with pytest.raises(HTTPException) as raised:
        asyncio.run(api.get_agent_role('p', 'a'))
    assert raised.value.status_code == expected


def test_update_conflict_is_http_409(tmp_path, monkeypatch):
    import api_agents as api
    import agent_lifecycle as lifecycle
    import yaml
    from fastapi import HTTPException
    monkeypatch.setattr(lifecycle, '_project_path', lambda _: tmp_path)
    (tmp_path / 'agents.yaml').write_text(yaml.safe_dump({'agents': [{'id': 'a', 'name': 'one'}, {'id': 'b', 'name': 'two'}]}))
    with pytest.raises(HTTPException) as raised:
        asyncio.run(api.update_agent('p', 'a', api.AgentUpdate(name='two')))
    assert raised.value.status_code == 409


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))


# ── 대화 턴을 열지 못한 명령은 실행하지 않는다(무소유 실행 없음, 2026-11-11) ──

@pytest.mark.parametrize("background", [False, True])
def test_concurrent_command_is_409_and_leaves_nothing_in_the_running_conversation(tmp_path, monkeypatch, background):
    from fastapi import HTTPException
    api, path = prepare(tmp_path, monkeypatch)
    calls = []

    def cognitive(command, history, **kwargs):
        calls.append(sessions.current())
        yield {"type": "final", "content": "done"}

    runner = SimpleNamespace(config={"id": "a", "name": "agent"}, cognitive_stream=cognitive, ai=object())
    monkeypatch.setattr(api, "agent_runners", {"p": {"a": {"runner": runner}}})
    monkeypatch.setattr(api.threading, "Thread", lambda target, **kw: SimpleNamespace(start=target))
    db = ConversationDB(str(path))
    owner = sessions.pair_owner(db.get_or_create_agent("user", "human"), db.get_or_create_agent("agent", "ai_agent"))
    store = sessions.SessionStore(path, "messages", owner)
    with sessions.connection(path) as conn:
        sid = sessions.resolve(conn, str(path), owner, "messages")
    running = store.begin(sid)
    try:
        with pytest.raises(HTTPException) as refused:
            api.send_agent_command("p", "a", api.AgentCommand(command="동시에 하나 더", background=background))
    finally:
        store.finish(running)
    assert refused.value.status_code == 409 and calls == []
    with sessions.connection(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0   # 사용자 메시지도 남기지 않는다
        assert conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0
    # 앞선 턴이 끝난 뒤의 명령은 같은 대화의 새 턴으로 실행된다.
    api.send_agent_command("p", "a", api.AgentCommand(command="이어서", background=background))
    assert calls[0].session_id == running.session_id and calls[0].turn_id != running.turn_id
    with sessions.connection(path) as conn:
        assert conn.execute("SELECT COUNT(*) FROM conversation_turns WHERE state='running'").fetchone()[0] == 0


def test_direct_caller_without_a_turn_gets_an_explicit_error_not_an_unowned_run(tmp_path, monkeypatch):
    api, path = prepare(tmp_path, monkeypatch)
    calls = []
    runner = SimpleNamespace(config={"id": "a", "name": "agent"},
                             cognitive_stream=lambda *a, **k: calls.append(1) or iter(()))
    db = ConversationDB(str(path))
    owner = sessions.pair_owner(db.get_or_create_agent("user", "human"), db.get_or_create_agent("agent", "ai_agent"))
    store = sessions.SessionStore(path, "messages", owner)
    with sessions.connection(path) as conn:
        sid = sessions.resolve(conn, str(path), owner, "messages")
    running = store.begin(sid)
    try:
        with pytest.raises(sessions.TurnUnavailable):
            api._run_agent_command("p", "a", runner, "겹친 요청", task_id="refused")
    finally:
        store.finish(running)
    assert calls == []
    with sessions.connection(path) as conn:
        assert conn.execute("SELECT status FROM tasks WHERE task_id='refused'").fetchone()[0] == "failed"
        assert conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0
