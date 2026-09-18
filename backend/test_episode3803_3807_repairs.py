"""ep3803~3807: 실행 권한·계측·감독·가이드 브리지·빌드 계약의 외부 호출 없는 회귀."""
import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace as NS

import boot_paths  # noqa: F401
import associative_recall
import pytest

from test_conscious_supervisor import supervisor  # noqa: F401
from test_conscious_supervisor import verdict


@pytest.mark.parametrize("repair,tag,origin,expected", [
    (False, None, "user", False), (False, "REPAIR", "user", True),
    (True, None, "user", True), (None, None, "user", True),
    ("false", None, "user", True), (True, None, "scheduler", False),
])
def test_repair_candidate_can_return_to_normal_execution(supervisor, monkeypatch,
                                                        repair, tag, origin, expected):
    from agent_pipeline import CognitivePipelineMixin
    import thread_context as tc
    grants, switches, traces = [], [], []
    framing = {"task_framing": "사이트 정책 변경", "achievement_criteria": "4자 허용"}
    if repair is not None:
        framing["needs_repair"] = repair

    class Runner(CognitivePipelineMixin):
        config = {"name": "worker"}
        project_path = Path(supervisor.project_path)
        _associate = associative_recall.stub()
        _decide_request_type = lambda *a: ("REPAIR", None)
        _tag_override = lambda *a: tag
        _run_consciousness_or_reuse = lambda *a, **kw: framing
        _consciousness_clarification = lambda *a: None
        _extract_achievement_criteria = lambda *a: ""
        _build_system_prompt_split = lambda *a: ("stable", "")
        _apply_consciousness_to_history = lambda self, history, co: history
        _after_response_async = lambda *a, **kw: None

    runner = Runner()
    runner.ai = supervisor.runner.ai
    runner.ai._provider = None
    runner.ai.process_message_stream = lambda **kw: iter([{"type": "final", "content": "완료"}])
    supervisor.runner, supervisor.enabled = runner, False
    monkeypatch.setattr("pursuit_bind.prepare", lambda: ("", False))
    monkeypatch.setattr("pursuit_bind.refresh_memory", lambda mem: mem)
    monkeypatch.setattr("pursuit_bind.finish", lambda *a, **kw: None)
    monkeypatch.setattr("red_grant.issue_grant", lambda **kw: grants.append(kw))
    monkeypatch.setattr("system_ai_core._switch_to_role", lambda r, role: switches.append(role))
    monkeypatch.setattr("episode_logger.record_trajectory_event", lambda k, d: traces.append((k, d)))
    monkeypatch.setattr("final_evaluator.invoke", lambda c, *a, **kw: verdict(c))
    with tc.actor_context(origin=origin):
        events = list(runner._cognitive_stream_body("비밀번호를 4자로 바꿔", []))
    assert not [e for e in events if e["type"] == "error"], events
    assert bool(grants) is expected
    assert ("system_repair" in switches) is expected
    if repair is False and tag is None:
        assert [d for k, d in traces if k == "cognition.route"][-1]["request_type"] == "THINK"


def test_repair_rounds_include_unique_responses_but_not_supervision():
    from model_call_context import count_execution_rounds
    rows = [{"event": "round", "role": role, "call_id": role, "round_index": n}
            for role in ("system_repair", "execution", "system_ai", "consciousness", "oneshot:evaluate")
            for n in (1, 2)]
    assert count_execution_rounds(rows + rows) == 6


def test_distinct_missing_reads_do_not_wake_supervisor_but_repetition_does(supervisor):
    for path in ("/a.md", "/b.md", "/c.toml", "/d.json"):
        key = supervisor._start("execute_ibl", {"code": f'[self:read]{{path:"{path}"}}'})
        supervisor._finish(key, f"Error: [Errno 2] No such file or directory: '{path}'", True)
    assert supervisor.failures == 0 and supervisor.trigger == ""
    for _ in range(2):
        key = supervisor._start("execute_ibl", {"code": '[self:read]{path:"/d.json"}'})
        supervisor._finish(key, "Error: [Errno 2] No such file or directory: '/d.json'", True)
    assert supervisor.trigger == "unchanged_repeat"


@pytest.mark.parametrize("code,error", [
    ('[self:write]{path:"/a",content:"x"}', "Error: [Errno 2] No such file or directory: '/a'"),
    ('[self:read]{path:"/a"}', "Error: [Errno 13] Permission denied: '/a'"),
    ('[self:read]{path:"/a"} >> [self:write]{path:"/b"}', "Error: [Errno 2] No such file or directory: '/a'"),
])
def test_action_and_permission_failures_still_wake_supervisor(supervisor, code, error):
    for _ in range(2):
        key = supervisor._start("execute_ibl", {"code": code})
        supervisor._finish(key, error, True)
    assert supervisor.trigger == "repeated_failure"


@pytest.mark.parametrize("headers", [False, True])
def test_mcp_guide_read_carries_identity_and_restores_http_context(monkeypatch, headers):
    import mcp_server
    import thread_context as tc
    import selfbuild_gate
    from api_ibl import GuideRequest, read_guide_bridge
    agent, task = ("header-guide", "header-task") if headers else ("stdio-guide", "stdio-task")
    monkeypatch.setattr(mcp_server, "DEFAULT_AGENT_ID", "stdio-guide")
    monkeypatch.setattr(mcp_server, "DEFAULT_TASK_ID", "stdio-task")
    context = NS(request_context=NS(request=NS(headers={
        "x-indiebiz-agent-id": agent, "x-indiebiz-task-id": task}))) if headers else None
    payloads = []
    monkeypatch.setattr(mcp_server, "_post_backend", lambda path, data, timeout: payloads.append(data) or "{}")
    asyncio.run(mcp_server.read_guide("world_tools.md", ctx=context))
    assert payloads[0]["agent_id"] == agent and payloads[0]["task_id"] == task
    selfbuild_gate.reset(agent)
    try:
        with tc.actor_context(agent_id="unrelated", task_id="unrelated-task"):
            result = asyncio.run(read_guide_bridge(GuideRequest(**payloads[0])))
            assert tc.get_current_agent_id() == "unrelated"
            assert tc.get_current_task_id() == "unrelated-task"
        assert result["content"] and selfbuild_gate.state(agent)["consulted"]
    finally:
        selfbuild_gate.reset(agent)


def test_guide_listing_or_failed_read_does_not_clear_gate(monkeypatch):
    import ibl_routing
    import thread_context as tc
    import selfbuild_gate
    selfbuild_gate.reset("guide-negative")
    try:
        with tc.actor_context(agent_id="guide-negative"):
            ibl_routing.search_guide("world_tools.md", {"read": False})
            assert not selfbuild_gate.state("guide-negative")["consulted"]
            monkeypatch.setattr(ibl_routing, "_search_guide", lambda *a: {"error": "missing"})
            ibl_routing.search_guide("world_tools.md", {"read": True})
            assert not selfbuild_gate.state("guide-negative")["consulted"]
    finally:
        selfbuild_gate.reset("guide-negative")


@pytest.fixture
def builder():
    path = Path(__file__).resolve().parents[1] / "data/packages/installed/tools/web-builder/tools/build_site.py"
    spec = importlib.util.spec_from_file_location("episode_web_build", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("output", ["dist", ".next", "custom-output"])
def test_build_reports_observed_output_and_skips_nonexistent_lint(builder, tmp_path, monkeypatch, output):
    (tmp_path / "package.json").write_text(json.dumps({"scripts": {"build": "node build.mjs"}}))
    # 과거 .next가 남아 있어도 새 정적 빌드의 경로라고 보고하지 않는다.
    (tmp_path / ".next").mkdir()
    (tmp_path / ".next/old.js").write_text("old")
    calls = []

    def command(cmd, **kw):
        calls.append((cmd, kw))
        folder = tmp_path / output
        folder.mkdir(exist_ok=True)
        (folder / "index.html").write_text("built")
        return {"success": True, "stdout": "ok"}

    monkeypatch.setattr(builder, "run_command", command)
    result = builder.run(str(tmp_path), analyze=True)
    assert result["success"] and len(calls) == 1
    assert calls[0][1]["env"]["ANALYZE"] == "true"
    assert result["output_dir"] == (None if output == "custom-output" else str(tmp_path / output))
    assert "Vercel" not in str(result) and "린트 경고" not in str(result)


def test_failed_build_never_reports_old_output_as_success(builder, tmp_path, monkeypatch):
    (tmp_path / "package.json").write_text('{"scripts":{"build":"exit 1"}}')
    monkeypatch.setattr(builder, "run_command", lambda *a, **kw: {"success": False, "stderr": "failed"})
    assert builder.run(str(tmp_path))["success"] is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
