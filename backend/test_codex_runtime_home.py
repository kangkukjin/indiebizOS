"""수리·코딩의 격리 실행 기록이 완료 전 주행기록까지 전달되는지 확인한다."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import boot_paths  # noqa: F401
import episode_logger as el
from providers.codex import CodexProvider
from test_codex_journal_2026_09_12 import _file, _journal_db, _response, _row


@pytest.mark.parametrize("profile", ["normal", "coding", "repair"])
def test_actual_launch_home_feeds_live_rounds(tmp_path, monkeypatch, profile):
    parent = tmp_path / "parent"
    parent.mkdir()
    (parent / "auth.json").write_text("{}")
    monkeypatch.setenv("CODEX_HOME", str(parent))
    monkeypatch.setattr("repair_context.active", lambda: profile == "repair")
    monkeypatch.setattr("repair_context.activation_only", lambda: False)
    monkeypatch.setattr("repair_continuation.current", lambda: {"root_task_id": "repair-root"})
    st = SimpleNamespace(task_key=lambda key: key,
                         ensure_session=lambda *args: {"worktree": "workspace"})
    handler = SimpleNamespace(_REPO_ROOT=tmp_path, _staging_mod=lambda: st,
                              _staging_key=lambda: "repair-root")
    monkeypatch.setattr("tool_loader.load_tool_handler", lambda _: handler)
    provider = CodexProvider(api_key="", model="test", system_prompt="")
    provider._completion_channel = "test"
    provider._reset_turn_state()
    if profile == "coding":
        provider.execution_profile = "coding"
        provider.coding_environment = {"CODEX_HOME": str(tmp_path / "coding")}
    env, _ = provider._prepare_launch_context(None)
    home = Path(env["CODEX_HOME"])
    home.mkdir(parents=True, exist_ok=True)
    assert home == provider._runtime_home
    assert (home == parent) == (profile == "normal")
    # A valid but unrelated parent record must never supply isolated metrics.
    if home != parent:
        _file(parent, _row("event_msg", {"type": "task_started", "turn_id": "new"})
              + _response("wrong-parent"))
    path = _file(home, _row("event_msg", {"type": "task_started", "turn_id": "new"})
                 + _response("a") + _response("b"))
    with path.open("a") as stream:
        stream.write(json.dumps({"type": "event_msg", "payload": {
            "type": "token_count", "info": {
                "total_token_usage": {"input_tokens": 900},
                "last_token_usage": {"input_tokens": 321}, "model_context_window": 1000,
            }}}) + "\n")
    assert provider._measure_context_size("thread") == 321
    db = _journal_db(tmp_path, monkeypatch)
    with db() as conn:
        conn.execute("INSERT INTO episode_log(id,started_at,source) VALUES(1,'now','usage')")
    seq = 0

    def record(kind, data):
        nonlocal seq
        seq += 1
        with db() as conn:
            conn.execute("INSERT INTO trajectory_event(run_id,event_seq,episode_id,ts,kind,data,source) "
                         "VALUES('run',?,1,'now',?,?,'usage')", (seq, kind, json.dumps(data)))

    monkeypatch.setattr(el, "record_trajectory_event", record)
    monkeypatch.setattr("model_call_context.fields", lambda **kw: {})
    token = el._current_episode.set(SimpleNamespace(steps=[]))
    role = el._current_role.set("system_repair")
    try:
        provider._translate_stream_event({"type": "thread.started", "thread_id": "thread"}, "", 0)
        assert el.get_episode_journal()[0]["execution_rounds"] == 2
        with path.open("a") as stream:
            stream.write(_response("c"))
        for _ in range(2):
            provider._translate_stream_event({"type": "item.updated"}, "", 0)
        row = el.get_episode_journal()[0]
        assert row["is_running"] and row["execution_rounds"] == 3
        assert provider._response_ledger.path == path
    finally:
        el._current_episode.reset(token)
        el._current_role.reset(role)
    # A subsequent ordinary turn must not keep the preceding isolated home.
    provider._reset_turn_state()
    provider.execution_profile = ""
    monkeypatch.setattr("repair_context.active", lambda: False)
    provider._prepare_launch_context(None)
    assert provider._runtime_home == parent


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
