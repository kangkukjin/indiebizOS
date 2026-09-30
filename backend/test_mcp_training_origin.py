"""MCP training metadata reaches HTTP actor context without changing later calls."""
import asyncio
import json
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import boot_paths  # noqa: E402,F401
import mcp_server as M  # noqa: E402


@pytest.fixture(autouse=True)
def clean_identity(monkeypatch):
    for name in ("AGENT_ID", "TASK_ID", "TASK_ORIGIN", "EPISODE_ID", "PARENT_RUN_ID"):
        monkeypatch.setattr(M, "DEFAULT_" + name, "")
    monkeypatch.setattr(M, "_repeat_advisory", lambda *args: "")


def _ctx(origin):
    headers = {M._HDR_ORIGIN: origin, M._HDR_AGENT: "training-origin-agent",
               M._HDR_TASK: "training-origin-task", M._HDR_EPISODE: "4192",
               M._HDR_PARENT_RUN: "parent-run"}
    return SimpleNamespace(request_context=SimpleNamespace(
        request=SimpleNamespace(headers=headers)))


def test_published_schema_allows_only_training_override():
    tools = asyncio.run(M.mcp.list_tools())
    schema = next(t.inputSchema for t in tools if t.name == "execute_ibl")
    assert "origin" in schema["properties"]
    assert "origin" not in schema.get("required", [])
    from mcp.server.fastmcp.utilities.func_metadata import func_metadata
    model = func_metadata(M.execute_ibl, skip_names=["ctx"]).arg_model
    assert model.model_validate({"code": "", "origin": "training"}).origin == "training"
    assert model.model_validate({"code": ""}).origin is None
    for invalid in ("user", "test", "", "repair"):
        with pytest.raises(ValueError):
            model.model_validate({"code": "", "origin": invalid})


@pytest.mark.parametrize("invalid", ["user", "test", "", "repair"])
def test_invalid_origin_cannot_dispatch(monkeypatch, invalid):
    def forbidden(*args):
        pytest.fail("invalid origin reached backend")
    monkeypatch.setattr(M, "_post_backend", forbidden)
    with pytest.raises(ValueError, match="origin"):
        asyncio.run(M.execute_ibl("return 1", origin=invalid))


@pytest.mark.parametrize("transport,inherited", [
    ("http", "user"), ("http", "training"),
    ("stdio", "user"), ("stdio", "training"), ("stdio", ""),
])
def test_override_is_per_call_and_preserves_lineage(monkeypatch, transport, inherited):
    from api_ibl import IBLRequest
    ctx = _ctx(inherited) if transport == "http" else None
    monkeypatch.setattr(M, "DEFAULT_TASK_ORIGIN", inherited)
    requests = []

    def post(path, payload, timeout):
        assert path == "/ibl/execute"
        requests.append(IBLRequest(**payload))
        return json.dumps({"success": True, "value": 1})

    monkeypatch.setattr(M, "_post_backend", post)
    async def invoke():
        await M.execute_ibl("return 1", ctx=ctx, origin="training")
        await M.execute_ibl("return 2", ctx=ctx)
    asyncio.run(invoke())
    assert [req.origin for req in requests] == ["training", inherited or None]
    if ctx:
        assert all(req.agent_id == "training-origin-agent" and
                   req.task_id == "training-origin-task" and
                   req.episode_id == 4192 and req.parent_run_id == "parent-run"
                   for req in requests)
        assert ctx.request_context.request.headers[M._HDR_ORIGIN] == inherited
    assert M.DEFAULT_TASK_ORIGIN == inherited


def test_concurrent_calls_reach_http_health_context_without_leak(tmp_path, monkeypatch):
    import api_ibl
    import episode_logger
    import pulse_db
    import runtime_utils
    import system_tools
    import thread_context as tc
    from test_health_source_isolation import _tmp_pulse, _rows

    get = _tmp_pulse(tmp_path, monkeypatch)
    monkeypatch.setattr(runtime_utils, "in_test_process", lambda: False)
    barrier = threading.Barrier(2)
    observations = {}
    monkeypatch.setattr(api_ibl, "_attach_steer", lambda value, *args: value)

    def execute(tool_input, project_path, **kwargs):
        name = tool_input["code"]
        barrier.wait(timeout=10)
        observations[name] = tc.get_task_origin()
        pulse_db.record_action_health("self", name, True, 1)
        episode_logger.record_trajectory_event("ibl.origin_probe", {"name": name})
        return {"success": True, "value": name}

    monkeypatch.setattr(system_tools, "_execute_ibl_unified", execute)

    def post(path, payload, timeout):
        # Exercise the real HTTP request model and its worker/context restoration.
        # Ticket storage is irrelevant here; leave the live spill store untouched.
        request = api_ibl.IBLRequest(**{**payload, "ticket": None})
        return json.dumps(asyncio.run(api_ibl.execute_ibl_code(request)))

    monkeypatch.setattr(M, "_post_backend", post)
    async def invoke():
        await asyncio.gather(
            M.execute_ibl("training-probe", project_path=str(tmp_path),
                          ctx=_ctx("user"), origin="training"),
            M.execute_ibl("usage-probe", project_path=str(tmp_path), ctx=_ctx("user")))
    asyncio.run(invoke())
    assert observations == {"training-probe": "training", "usage-probe": "user"}
    assert {r["action"]: r["source"] for r in _rows(get)} == {
        "training-probe": "training", "usage-probe": "usage"}
    conn = episode_logger._get_db()
    try:
        rows = conn.execute(
            "SELECT source, episode_id, task_id, parent_run_id FROM trajectory_event "
            "WHERE kind='ibl.origin_probe'").fetchall()
    finally:
        conn.close()
    assert sorted(row["source"] for row in rows) == ["training", "usage"]
    assert all(row["episode_id"] == 4192 and row["task_id"] == "training-origin-task"
               and row["parent_run_id"] == "parent-run" for row in rows)


def test_recover_does_not_relabel_existing_execution(monkeypatch):
    seen = []
    def post(path, payload, timeout):
        seen.append((path, payload))
        return json.dumps({"success": True, "value": 1})
    monkeypatch.setattr(M, "_post_backend", post)
    asyncio.run(M.execute_ibl("", recover="abcdef123456", origin="training"))
    assert seen == [("/ibl/recover", {"ticket": "abcdef123456", "wait": 0.0})]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
