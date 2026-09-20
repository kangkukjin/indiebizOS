"""ep3315: 잘못된 과제 JSON을 재요청하고 실패를 완료로 기록하지 않는다."""
import boot_paths  # noqa: F401
import asyncio
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import pytest

import consciousness_agent as ca
import pursuit_bind as pb
from pursuit_ledger import PursuitLedger


SUMMARY = {"progress": "디지털 노마드 원고 작성", "next": "내용 검토"}

def model_answers(monkeypatch, answers):
    calls = []
    replies = iter(answers)

    def call(prompt, **kwargs):
        calls.append((prompt, kwargs))
        return next(replies)

    monkeypatch.setattr(ca, "oneshot_ai_call", call)
    return calls


@pytest.mark.parametrize("raw", [
    '{progress:"원고 작성"}', '{"progress":"원고 작성",}', '{"progress":null}',
    '{"progress":[]}', '{"status":"done"}', '[]', '', None,
])
def test_invalid_summary_retries_once_with_original_request(monkeypatch, raw):
    calls = model_answers(monkeypatch, [raw, json.dumps(SUMMARY)])
    assert pb.ask_json("사용자의 정정을 반영하라", kind="summary") == SUMMARY
    assert len(calls) == 2 and calls[1][0].startswith(calls[0][0])
    assert "previous_response" in calls[1][0]
    assert all(k["role"] == "background" for _, k in calls)


@pytest.mark.parametrize("fenced", [False, True])
def test_valid_json_needs_only_one_call(monkeypatch, fenced):
    raw = json.dumps(SUMMARY, ensure_ascii=False)
    if fenced:
        raw = "```json\n" + raw + "\n```"
    calls = model_answers(monkeypatch, [raw])
    assert pb.ask_json("요약", kind="summary") == SUMMARY
    assert len(calls) == 1


@pytest.mark.parametrize("bad,good", [
    ({"status": "done"}, {"progress": "확인된 결과"}),
    ({"artifacts": [{"path": "draft.md"}]}, {"artifacts": ["draft.md"]}),
    ({"next": "x" * 601}, {"next": "실제 산출물 확인"}),
])
def test_summary_validates_before_accepting(monkeypatch, bad, good):
    model_answers(monkeypatch, [json.dumps(bad), json.dumps(good)])
    assert pb.ask_json("판단", kind="summary") == good


def test_exhausted_retry_retains_cause_and_masks_diagnostic(monkeypatch, capsys):
    secret = "sk-" + "a" * 32
    raw = '{progress:"원고", api_key:"' + secret + '"}'
    calls = model_answers(monkeypatch, [raw, raw])
    with pytest.raises(ValueError, match="2회 실패") as caught:
        pb.ask_json("요약", kind="summary")
    assert isinstance(caught.value.__cause__, json.JSONDecodeError)
    assert len(calls) == 2
    log = capsys.readouterr().out
    assert "summary 2/2" in log and "응답 미리보기=" in log and secret not in log


def test_prepare_never_calls_model_and_binding_preserves_episode(tmp_path, monkeypatch):
    import episode_logger as el
    ledger = PursuitLedger(tmp_path / "pursuit.db", "agent")
    row = ledger.create("미래의 문화", "원고 완성", "origin", framing="기존 규정")
    binding = pb.Binding(None, ledger, "agent", "turn", "디지털 노마드 글 작성", [])
    token = pb._current.set(binding)
    monkeypatch.setattr(el.EpisodeLogger, "current", lambda: SimpleNamespace(episode_id=3315))
    monkeypatch.setattr(ca, "oneshot_ai_call", lambda *a, **k: pytest.fail("전경 과제 판단 금지"))
    try:
        assert row["id"] in pb.prepare() and binding.row is None
        assert not ledger.turns(row["id"])
        pb.connect(binding, row["id"], "현재 원고는 이 과제의 후속 집필")
        assert ledger.get(row["id"])["framing"] == "기존 규정"
        assert ledger.turns(row["id"])[0]["episode_id"] == "3315"
    finally:
        pb.leave(token)
    assert ledger.turns(row["id"])[0]["state"] == "interrupted"


@pytest.fixture
def ws_env(tmp_path, monkeypatch):
    import chat_streams as ws
    import episode_logger as el
    import xray_stream
    from conversation_db import ConversationDB
    (tmp_path / "agents.yaml").write_text('agents:\n- id: agent\n  name: 컨텐츠\n')
    db = ConversationDB(str(tmp_path / "conversations.db"))
    messages, xray = [], []
    ended = []

    async def send(client, payload):
        messages.append(payload)

    monkeypatch.setattr(ws, "project_manager", SimpleNamespace(get_project_path=lambda _: tmp_path))
    monkeypatch.setattr(ws.manager, "send_message", send)
    monkeypatch.setattr(el.EpisodeLogger, "start_episode", lambda *a, **k: None)
    monkeypatch.setattr(el.EpisodeLogger, "end_episode", lambda: ended.append(True))
    monkeypatch.setattr(el, "record_trajectory_event", lambda *a, **k: None)
    monkeypatch.setattr(xray_stream, "push_xray_event", lambda name, data: xray.append((name, data)))
    with ThreadPoolExecutor(max_workers=1) as pool:
        monkeypatch.setattr(ws, "executor", pool)
        yield SimpleNamespace(ws=ws, db=db, messages=messages, xray=xray, ended=ended)


@pytest.mark.parametrize("outcome,status", [
    ("exception", "failed"), ("error_event", "failed"), ("final_then_error", "failed"),
    ("empty", "failed"), ("empty_final", "failed"), ("cancelled", "cancelled"),
    ("cancel_flag", "cancelled"), ("success", "completed"),
])
def test_real_ws_handler_records_terminal_outcome(ws_env, monkeypatch, outcome, status):
    env = ws_env
    tool = {"name": "execute_ibl", "result": "원문 보존"}
    cleaned = []

    def stream(*args, **kwargs):
        try:
            if outcome == "exception":
                json.loads('{action:"keep"}')
            elif outcome == "cancel_flag":
                env.ws.set_cancel("test-client", True)
                yield {"type": "text", "content": "취소 뒤 전달되면 안 됨"}
            elif outcome == "cancelled":
                yield {"type": "cancelled", "content": "사용자 중단"}
            elif outcome in {"success", "final_then_error"}:
                yield {"type": "final", "content": "작성 완료"}
            elif outcome == "empty_final":
                yield {"type": "final", "content": "  "}
            if outcome in {"error_event", "final_then_error"}:
                yield {"type": "error", "content": "검증 실패"}
            yield {"type": "_turn_meta", "tool_calls": [tool]}
        finally:
            cleaned.append(True)

    runner = SimpleNamespace(ai=SimpleNamespace(get_last_tool_images=lambda: []), cognitive_stream=stream)
    monkeypatch.setattr(env.ws, "_ensure_agent_runner", lambda *a: {"runner": runner})
    asyncio.run(env.ws.handle_chat_message_stream("test-client", {
        "project_id": "test", "agent_name": "컨텐츠", "message": "원고 작성",
    }))
    with env.db.get_connection() as c:
        row = dict(c.execute("SELECT * FROM tasks").fetchone())
    assert row["status"] == status
    assert row["completed_at"] and row["result"].strip()
    assert cleaned and env.ended
    assert env.messages[-1]["type"] == "end"
    assert any(m["type"] == "response" for m in env.messages) == (status == "completed")
    if outcome not in {"exception", "cancel_flag"}:
        assert json.loads(row["tool_history"]) == [tool]
    terminal = env.xray[-1]
    assert terminal[0] == {"failed": "task_failed", "cancelled": "task_cancelled", "completed": "task_complete"}[status]
    assert terminal[1]["status"] == status
    assert not env.ws.is_cancelled("test-client")


@pytest.mark.parametrize("fail", [False, True])
def test_timeout_leaves_task_open_until_worker_finishes(ws_env, monkeypatch, fail):
    env = ws_env
    started, release, ended = threading.Event(), threading.Event(), threading.Event()
    import episode_logger as el
    monkeypatch.setattr(el.EpisodeLogger, "end_episode", ended.set)

    def stream(*args, **kwargs):
        started.set()
        assert release.wait(5)
        if fail:
            raise ValueError("늦게 발생한 검증 오류")
        yield {"type": "final", "content": "늦게 완성된 원고"}

    async def timeout(awaitable, timeout):
        assert await asyncio.to_thread(started.wait, 5)
        awaitable.close()
        raise asyncio.TimeoutError

    runner = SimpleNamespace(ai=SimpleNamespace(get_last_tool_images=lambda: []), cognitive_stream=stream)
    monkeypatch.setattr(env.ws, "_ensure_agent_runner", lambda *a: {"runner": runner})
    monkeypatch.setattr(env.ws.asyncio, "wait_for", timeout)

    async def run():
        try:
            await env.ws.handle_chat_message_stream("test-client", {
                "project_id": "test", "agent_name": "컨텐츠", "message": "원고 작성",
            })
            with env.db.get_connection() as c:
                row = c.execute("SELECT status, completed_at FROM tasks").fetchone()
            assert tuple(row) == ("pending", None)
            assert not env.xray
        finally:
            release.set()
        assert await asyncio.to_thread(ended.wait, 5)

    asyncio.run(run())
    with env.db.get_connection() as c:
        row = dict(c.execute("SELECT * FROM tasks").fetchone())
    assert row["status"] == ("failed" if fail else "completed")
    assert row["result"] == ("늦게 발생한 검증 오류" if fail else "늦게 완성된 원고")
    assert env.xray[-1][0] == ("task_failed" if fail else "task_complete")


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
