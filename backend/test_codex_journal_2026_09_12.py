"""3620 회귀: 병렬 도구 수와 응답 수 분리, resume 격리, 실제 주행 지표."""
import boot_paths  # noqa: F401
import json
import sqlite3
from datetime import datetime, timezone
from types import SimpleNamespace

from codex_rollout import CodexResponseLedger


def _row(kind, payload, second=1):
    return json.dumps({"type": kind, "timestamp": f"2026-09-12T12:00:{second:02d}Z",
                       "payload": payload}) + "\n"


def _response(rid, turn="new", total=100):
    return _row("token_usage_record", {"response_id": rid, "turn_id": turn,
        "turn_token_usage": {"input_tokens": total, "cached_input_tokens": 40,
                             "output_tokens": 9}})


def _file(tmp_path, content):
    folder = tmp_path / "sessions"
    folder.mkdir()
    path = folder / "rollout-test-thread.jsonl"
    path.write_text(content)
    return path


def test_response_ids_resume_duplicates_and_partial_lines(tmp_path):
    path = _file(tmp_path, _row("event_msg", {"type": "task_started", "turn_id": "old"}, 0)
                 + _response("old", "old")
                 + _row("event_msg", {"type": "task_started", "turn_id": "new"})
                 + _response("a") + _response("a") + _response("foreign", "other"))
    start = datetime(2026, 9, 12, 12, 0, 1, tzinfo=timezone.utc).timestamp()
    ledger = CodexResponseLedger(tmp_path, "thread", start)
    assert [r["response_id"] for r in ledger.poll()] == ["a"]
    assert ledger.poll() == []
    line = _response("b", total=200)
    with path.open("a") as stream:
        stream.write(line[:20])
    assert ledger.poll() == []
    with path.open("a") as stream:
        stream.write(line[20:])
    assert [r["response_id"] for r in ledger.poll()] == ["b"]
    assert ledger.turn_usage["input_tokens"] == 200


def test_provider_records_real_rounds_and_turn_cost(tmp_path, monkeypatch):
    import episode_logger as el
    from providers import get_provider
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    _file(tmp_path, _row("event_msg", {"type": "task_started", "turn_id": "new"})
          + _response("a") + _response("b", total=200))
    monkeypatch.setattr(el, "record_trajectory_event", lambda *a, **kw: None)
    ep = SimpleNamespace(steps=[])
    token = el._current_episode.set(ep)
    try:
        provider = get_provider("codex", api_key="", model="m", system_prompt="")
        provider._turn_base_total = 500  # 지난 턴을 빼면 새 CLI에서는 잘못된 0이 된다.
        provider._translate_stream_event({"type": "thread.started", "thread_id": "thread"}, "", 0)
        for _ in range(5):  # 하나의 응답에 포함된 여러 item은 왕복을 늘리지 않는다.
            provider._translate_stream_event({"type": "item.completed", "item": {
                "type": "agent_message", "text": "text"}}, "", 0)
        provider._translate_stream_event({"type": "turn.completed", "usage": {
            "input_tokens": 200, "output_tokens": 9}}, "", 0)
        rounds = [s for s in ep.steps if s["event"] == "round"]
        assert [s["round"] for s in rounds] == [1, 2]
        assert all(s["role"] == "execution" for s in rounds)
        assert provider.metrics.total_input_tokens == 200
        provider._reset_turn_state()
        assert provider._response_ledger is None
    finally:
        el._current_episode.reset(token)


def test_missing_rollout_does_not_turn_items_into_rounds(tmp_path, monkeypatch):
    from providers import get_provider
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    provider = get_provider("codex", api_key="", model="m", system_prompt="")
    rounds = []
    monkeypatch.setattr(provider, "_note_model_round", lambda: rounds.append(1))
    provider._translate_stream_event({"type": "thread.started", "thread_id": "missing"}, "", 0)
    provider._translate_stream_event({"type": "item.completed", "item": {
        "type": "agent_message", "text": "done"}}, "", 0)
    provider._translate_stream_event({"type": "turn.completed", "usage": {}}, "", 0)
    assert rounds == []


def test_final_answer_ledger_ignores_commentary_and_old_turn(tmp_path):
    def message(text, phase, second=1):
        return _row("response_item", {"type": "message", "role": "assistant",
            "phase": phase, "content": [{"type": "output_text", "text": text}]}, second)
    path = _file(tmp_path, message("old", "final_answer", 0)
                 + _row("event_msg", {"type": "task_started", "turn_id": "new"})
                 + message("checking", "commentary")
                 + message('{"status":"CONTINUE","reason":"recovered"}', "final_answer")
                 + message("late progress", "commentary"))
    ledger = CodexResponseLedger(tmp_path, "thread", 0)
    ledger.poll()
    assert json.loads(ledger.final_text)["status"] == "CONTINUE"
    with path.open("a") as stream:
        stream.write(_row("event_msg", {"type": "task_started", "turn_id": "next"}, 2))
    ledger.poll()
    assert ledger.final_text is None


def test_provider_streams_progress_but_delivers_only_final(tmp_path, monkeypatch):
    from providers import get_provider
    from supervisor_runtime import parse_decision
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    provider = get_provider("codex", api_key="", model="m", system_prompt="")
    accumulated = ""
    decision = '{"status":"CONTINUE","reason":"recovered"}'
    streamed = []
    for text in ["실패 기록을 확인하겠습니다.", decision]:
        for event, updated in provider._translate_stream_event({"type": "item.completed",
                "item": {"type": "agent_message", "text": text}}, accumulated, 0):
            streamed.append(event)
            if updated is not None:
                accumulated = updated
    assert "확인하겠습니다" in accumulated
    result = provider._translate_stream_event({"type": "turn.completed", "usage": {}}, accumulated, 0)
    final = next(event["content"] for event, _ in result if event["type"] == "final")
    assert final == decision
    assert parse_decision(final)["status"] == "CONTINUE"
    assert len(streamed) == 2
    provider._reset_turn_state()
    assert provider._last_agent_message is None


def _journal_db(tmp_path, monkeypatch):
    import episode_logger as el
    path = tmp_path / "episodes.db"
    def db():
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        return conn
    monkeypatch.setattr(el, "_get_db", db)
    el._ensure_episode_tables()
    return db


def test_journal_counts_rejected_ibl_attempt_without_double_count(tmp_path, monkeypatch):
    import episode_logger as el
    db = _journal_db(tmp_path, monkeypatch)
    with db() as conn:
        for eid in (1, 2):
            conn.execute("INSERT INTO episode_log (id, started_at, source) VALUES (?, 'now', 'usage')", (eid,))
        events = [("supervision.tool.started", {"name": "execute_ibl"}),
                  ("ibl.started", {"nested": False}),
                  ("supervision.tool.started", {"name": "execute_ibl"}),
                  ("ibl.started", {"nested": True})]
        for seq, (kind, data) in enumerate(events):
            conn.execute("INSERT INTO trajectory_event (run_id,event_seq,episode_id,ts,kind,data,source) "
                         "VALUES ('run',?,1,'now',?,?,'usage')", (seq, kind, json.dumps(data)))
    rows = {r["id"]: r for r in el.get_episode_journal()}
    assert rows[1]["ibl_calls"] == 2
    assert rows[1]["execution_rounds"] is None
    assert rows[2]["ibl_calls"] is None


def test_live_journal_counts_system_ai_before_summary_and_after_finish(tmp_path, monkeypatch):
    import episode_logger as el
    from datetime import datetime
    db = _journal_db(tmp_path, monkeypatch)
    with db() as conn:
        conn.execute("INSERT INTO episode_log (id,started_at,agent,source) "
                     "VALUES (1,'2026-09-12T21:44:54','system_ai','usage')")
        steps = [{"event": "round", "role": role, "call_id": call, "round_index": n, "round": n}
                 for role, call, n in [("system_ai", "main", 1), ("system_ai", "main", 2),
                                       ("system_ai", "main", 2), ("oneshot:evaluate", "eval", 1)]]
        for seq, step in enumerate(steps):
            conn.execute("INSERT INTO trajectory_event (run_id,event_seq,episode_id,ts,kind,data,source) "
                         "VALUES ('run',?,1,'now','model.round',?,'usage')", (seq, json.dumps(step)))
    row = el.get_episode_journal()[0]
    assert row["is_running"] and row["execution_rounds"] == 2
    # 실제 종료 요약 생산자도 같은 역할을 세야 한다.
    el._extract_and_save_summary(1, datetime.now(), "system_ai", "request", "", 100, steps=steps)
    with db() as conn:
        assert conn.execute("SELECT execution_rounds FROM episode_summary").fetchone()[0] == 2
        conn.execute("UPDATE episode_log SET ended_at='2026-09-12T21:50:00' WHERE id=1")
        conn.execute("UPDATE episode_summary SET execution_rounds=0")  # 구버전의 잘못된 요약
    row = el.get_episode_journal()[0]
    assert not row["is_running"] and row["execution_rounds"] == 2


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
