"""HTTP agent commands retain conversation ownership for task delegation."""
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


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
