"""감독은 실제 경계를 막고, 승인한 본문은 재생성하지 않는다는 행동 계약."""
import json
import threading
import time
from types import SimpleNamespace

import pytest

import boot_paths  # noqa: F401
import thread_context as tc
from conscious_supervisor import Supervisor
from supervision_bus import current, wrap
from supervision_store import TurnStore, digest
from supervision_watch import JobWatch


@pytest.fixture
def supervisor(tmp_path, monkeypatch):
    monkeypatch.setattr("consciousness_agent.system_ai_call", lambda *a, **kw: pytest.fail("시험의 실제 모델 호출 금지"))
    previous = tc.snapshot()
    tc.set_current_agent_id("worker")
    tc.set_current_task_id("task-supervision-test")
    calls = []

    def execute(name, payload, **kwargs):
        calls.append((name, payload, kwargs))
        return {"success": True, "value": payload}

    ai = SimpleNamespace(agent_id="worker", project_path=str(tmp_path),
                         tools=[{"name": "inspect", "input_schema": {"type": "object"}}],
                         _custom_execute_tool=execute)
    controller = Supervisor(SimpleNamespace(ai=ai), "목표 원문", [], "worker", "task-supervision-test",
                            {"tick_s": 1000}, directory=tmp_path / "store")
    controller.configure({"task_framing": "문제", "achievement_criteria": "실제 증거 확인"})
    controller.calls = calls
    try:
        yield controller
    finally:
        controller.close()
        tc.restore(previous)


def verdict(controller, status="APPROVED", **extra):
    manifest = controller.store.manifest()
    return json.dumps({"status": status, "reason": "근거를 확인했다", "response_version": manifest["version"],
                       "response_hash": manifest["hash"], **extra})


def finish(controller, response):
    return list(controller.finalize(response, [], lambda ev: None))


def manager_tool(controller, payload):
    with tc.actor_context(agent_id=controller.supervisor_id):
        controller.call_deadline = time.monotonic() + 60
        return json.loads(controller.tool(payload))


def test_approval_delivers_exact_bytes_without_executor_call(supervisor, monkeypatch):
    monkeypatch.setattr("final_evaluator.invoke", lambda c, *a, **kw: verdict(c))
    original = "  시작\n\n```py\nx = 1\n```\n\n끝  \n"
    events = finish(supervisor, original)
    assert events[-1] == {"type": "final", "content": original}
    assert [e["content"] for e in events if e["type"] == "text"] == [original]
    assert not supervisor.calls
    assert tc.get_goal_eval_outcome()["achieved"] is True


@pytest.mark.parametrize("raw", ["", "{}", "```json\n{\"achieved\":true}\n```", "모델 오류", "[]",
                                  '{"status":"CONTINUE","reason":"더 진행"}'])
def test_empty_or_malformed_judgment_never_passes(supervisor, monkeypatch, raw):
    monkeypatch.setattr("final_evaluator.invoke", lambda *a, **kw: raw)
    events = finish(supervisor, "원래 결과")
    assert "검수 미승인" in events[-1]["content"]
    assert events[-1]["content"].startswith("원래 결과")
    assert tc.get_goal_eval_outcome()["achieved"] is False


def test_unread_tail_is_supplied_and_its_defect_can_fail_evaluation(supervisor, monkeypatch):
    def evaluate(prompt, **kwargs):
        assert "뒤쪽 중요한 오류" in prompt
        return "NOT_ACHIEVED\nSEVERITY: 2\n뒤쪽 중요한 오류를 고쳐라"
    monkeypatch.setattr("consciousness_agent.system_ai_call", evaluate)
    supervisor.config["max_repairs"] = 0
    events = finish(supervisor, "x" * 24000 + "뒤쪽 중요한 오류")
    assert "미승인" in events[-1]["content"]
    assert tc.get_goal_eval_outcome()["achieved"] is False


def test_long_response_is_evaluated_without_page_read_tools(supervisor, monkeypatch):
    def evaluate(prompt, **kwargs):
        assert "끝</block>" in prompt
        assert kwargs["role"] == "evaluate"
        return "ACHIEVED"
    monkeypatch.setattr("consciousness_agent.system_ai_call", evaluate)
    text = "원문" * 21000 + "끝"
    assert finish(supervisor, text)[-1]["content"] == text


def test_repair_sends_only_changed_block_and_keeps_rest(supervisor, monkeypatch):
    rounds = []
    original = "앞부분" * 900 + "수정할 뒷부분"

    def invoke(c, *args, **kwargs):
        c.store.read_response(0, 24000, mark=True)
        rounds.append(1)
        return verdict(c, "REWORK", instruction="마지막 블록의 오류만 고치세요") if len(rounds) == 1 else verdict(c)

    def stream(prompt, **kwargs):
        assert "변경된 부분만" in prompt
        assert original not in prompt
        blocks = supervisor.store.read_response()["blocks"]
        last = blocks[-1]
        result = supervisor.tool({"op": "patch", "version": 1,
                                  "patches": [{"id": last["id"], "hash": last["hash"], "text": "수정됨"}]})
        assert json.loads(result)["success"]
        # 재실행 중 도구가 있어도 감독 잠금에 교착하지 않는다.
        assert supervisor.run_tool("inspect", {}, lambda: "ok") == "ok"
        yield {"type": "final", "content": "PATCH_DONE"}

    supervisor.runner.ai.process_message_stream = stream
    monkeypatch.setattr("final_evaluator.invoke", invoke)
    events = finish(supervisor, original)
    assert events[-1]["content"] == original[:2000] + "수정됨"
    assert "PATCH_DONE" not in str(events)
    assert supervisor.store.version == 2


def test_patch_is_atomic_and_rejects_stale_hash_and_version(tmp_path):
    store = TurnStore(tmp_path)
    store.put_response("A" * 4000)
    b = store.blocks
    with pytest.raises(ValueError):
        store.patch(1, [{"id": "0", "hash": b[0]["hash"], "text": "yes"},
                        {"id": "1", "hash": "stale", "text": "no"}])
    assert store.text == "A" * 4000
    store.patch(1, [{"id": "0", "hash": b[0]["hash"], "text": "new"}])
    with pytest.raises(ValueError):
        store.patch(1, [{"id": "1", "hash": b[1]["hash"], "text": "stale"}])


def test_real_boundary_returns_instruction_before_side_effect(supervisor, monkeypatch):
    monkeypatch.setattr("supervisor_runtime.invoke", lambda c, *a, **kw:
                        verdict(c, "REWORK", instruction="같은 실패를 재시도하지 말고 원인을 확인하세요"))
    execute = wrap(supervisor._execute)
    for _ in range(3):
        execute("inspect", {"same": True})
    assert len(supervisor.calls) == 3
    supervisor.tick()  # 관찰은 watcher가 한다. 실행 경계는 모델을 기다리지 않는다.
    blocked = json.loads(execute("inspect", {"side_effect": True}))
    assert blocked["not_executed"] is True
    assert blocked["supervisor_instruction"]["instruction"]
    assert len(supervisor.calls) == 3
    execute("inspect", {"different": True})
    assert len(supervisor.calls) == 4
    assert supervisor.reviews == 1


def test_silent_active_tool_wakes_supervisor_without_new_log(supervisor, monkeypatch):
    calls = []
    monkeypatch.setattr("supervisor_runtime.invoke", lambda c, *a, **kw:
                        calls.append(kw["phase"]) or verdict(c, "CONTINUE"))
    supervisor._start("slow_voice_job", {})
    supervisor.tick(supervisor.last_progress + 181)
    assert calls == ["review"]
    supervisor.tick(supervisor.last_progress + 182)
    assert calls == ["review"]  # 짧은 재검토 간격에는 모델 호출 안 함


def test_manager_observation_does_not_trigger_recursive_review(supervisor):
    manager_tool(supervisor, {"op": "state"})
    manager_tool(supervisor, {"op": "state"})
    manager_tool(supervisor, {"op": "state"})
    assert supervisor.trigger == ""
    assert not supervisor.recent


def test_manager_tool_has_budget_and_exclusive_ownership(supervisor):
    key = supervisor._start("production", {})
    assert not manager_tool(supervisor, {"op": "execute", "name": "inspect", "input": {}})["success"]
    assert not supervisor.calls
    supervisor._finish(key, "done")
    supervisor.executor_paused = True
    assert manager_tool(supervisor, {"op": "execute", "name": "inspect", "input": {}})["success"]
    assert len(supervisor.calls) == 1
    supervisor.tools_used = supervisor.config["max_tools_total"] - supervisor.config["final_tool_reserve"]
    assert not manager_tool(supervisor, {"op": "state"})["success"]
    supervisor.finalizing = True
    assert manager_tool(supervisor, {"op": "state"})["success"]


def test_same_agent_two_tasks_and_closed_alias_do_not_collide(supervisor, tmp_path):
    other = Supervisor(supervisor.runner, "다른 목표", [], "worker", "other-task",
                       {"tick_s": 1000}, directory=tmp_path / "other")
    try:
        assert current("worker", supervisor.task) is supervisor
        assert current("worker", "other-task") is other
        other.close()
        assert current("worker", "other-task") is None
        assert current("worker", supervisor.task) is supervisor
    finally:
        other.close()


def test_job_watch_liveness_is_not_progress_and_reads_incrementally(tmp_path):
    path = tmp_path / "job.log"
    path.write_text('PROGRESS {"phase":"generate","completed":2,"total":8}\n')
    job = JobWatch(path, now=0)
    assert job.poll(1)["changed"]
    with path.open("a") as stream:
        stream.write("heartbeat alive\n")
    observed = job.poll(90)
    assert observed["stalled_s"] == 89 and observed["silent_s"] == 0
    assert not observed["changed"]
    with path.open("a") as stream:
        stream.write('PROGRESS {"phase":"generate","completed":3,"total":8}\n')
    assert job.poll(91)["units"] == [3, 8]
    assert job.poll(92)["stalled_s"] == 1


def test_mcp_bridge_restores_scope_and_supervisor_cannot_bypass_workbench(supervisor):
    from api_supervision import dispatch
    original = tc.get_current_agent_id()
    supervisor.call_deadline = time.monotonic() + 60
    result = dispatch(supervisor.supervisor_id, supervisor.task, {"op": "state"})
    assert result["success"]
    assert tc.get_current_agent_id() == original
    with tc.actor_context(agent_id=supervisor.supervisor_id):
        blocked = json.loads(supervisor.run_tool("execute_ibl", {}, lambda: pytest.fail("bypass")))
    assert blocked["not_executed"]


def test_pursuit_done_is_request_until_final_overall_approval(supervisor, monkeypatch):
    writes = []
    binding = SimpleNamespace(row={"id": "p1", "version": 7, "goal_criteria": "전체 영상 배포"},
                              write=lambda *a, **kw: writes.append((a, kw)))
    result = supervisor.request_done(binding, "영상 완성")
    assert result["status"] == "completion_requested" and not writes
    monkeypatch.setattr("pursuit_bind.resolve_session", lambda *a: binding)
    monkeypatch.setattr("final_evaluator.invoke", lambda c, *a, **kw: verdict(c, pursuit_status="APPROVED"))
    finish(supervisor, "완성한 영상")
    assert writes[0][0][0] == {"status": "done"}


def test_turn_approval_alone_cannot_close_whole_pursuit(supervisor, monkeypatch):
    binding = SimpleNamespace(row={"id": "p", "version": 1, "goal_criteria": "전체 목표"})
    supervisor.request_done(binding, "이번 단계 완료")
    monkeypatch.setattr("final_evaluator.invoke", lambda c, *a, **kw: verdict(c))
    assert "전체 과제의 목표 달성" in finish(supervisor, "응답")[-1]["content"]
    assert tc.get_goal_eval_outcome()["achieved"] is False


def test_stale_response_approval_is_unknown(supervisor, monkeypatch):
    def invoke(c, *args, **kwargs):
        old = verdict(c)
        block = c.store.blocks[0]
        c.store.patch(1, [{"id": "0", "hash": block["hash"], "text": "changed"}])
        c.store.read_response(mark=True)
        return old
    monkeypatch.setattr("final_evaluator.invoke", invoke)
    assert "검수 미승인" in finish(supervisor, "original")[-1]["content"]


def test_real_aiagent_role_uses_same_tools_but_separate_identity(supervisor, monkeypatch):
    from providers.base import ProviderMetrics
    from supervisor_runtime import invoke
    providers = []

    class Provider:
        is_ready = True

        def __init__(self, **kwargs):
            self.metrics = ProviderMetrics()
            self._client = None
            self.kwargs = kwargs
            providers.append(self)

        def init_client(self):
            pass

        def process_message_stream(self, message, history, images, execute_tool, cancel_check):
            assert tc.get_current_agent_id() == supervisor.supervisor_id
            assert self.agent_role == "consciousness"
            assert self.kwargs["tools"][0]["name"] == "supervision"
            result = execute_tool("supervision", {"op": "execute", "name": "inspect", "input": {"probe": 1}},
                                  supervisor.project_path, supervisor.supervisor_id)
            assert json.loads(result)["success"]
            yield {"type": "tool_result", "name": "supervision", "result": result}
            yield {"type": "final", "content": '{"task_framing":"확인한 사실로 계획"}'}

    monkeypatch.setattr("providers.get_provider", lambda name, **kw: Provider(**kw))
    monkeypatch.setattr("model_resolver.resolve", lambda role: {"provider": "openai", "model": "fake", "api_key": ""})
    supervisor.executor_paused = True
    answer = invoke(supervisor, "기존 inspect 도구로 확인", phase="plan")
    assert json.loads(answer)["task_framing"] == "확인한 사실로 계획"
    assert supervisor.calls[0][2]["agent_id"] == supervisor.owner
    assert providers[0].disable_session_persistence is True
    assert tc.get_current_agent_id() == supervisor.owner


@pytest.mark.parametrize("lane", ["THINK", "EXECUTE", "REFLEX", "NO_FRAMING", "NO_CRITERIA", "CONTEXT_UPDATE"])
@pytest.mark.parametrize("signal", ["read", "write", "failed", "unknown"])
@pytest.mark.parametrize("supervised", [False, True])
def test_real_pipeline_suppresses_draft_and_fast_lane_has_no_supervisor_call(supervisor, monkeypatch, lane, signal, supervised):
    from agent_pipeline import CognitivePipelineMixin
    from pathlib import Path
    calls = []
    trace = []
    monkeypatch.setattr("episode_logger.record_trajectory_event", lambda kind, data: trace.append((kind, data)))

    class Runner(CognitivePipelineMixin):
        config = {"name": "worker"}
        project_path = Path(supervisor.project_path)
        _build_execution_memory = lambda *a, **kw: ("", 0, "")
        _decide_request_type = lambda *a: ("EXECUTE" if lane == "REFLEX" else "THINK" if lane in {"NO_FRAMING", "NO_CRITERIA"} else lane,
                                          "[self:time]" if lane == "REFLEX" else None)
        _run_consciousness_or_reuse = lambda *a: None if lane == "NO_FRAMING" else {"task_framing": "문제", "achievement_criteria": "" if lane == "NO_CRITERIA" else "기준"}
        _consciousness_needs_repair = lambda *a: False
        _consciousness_clarification = lambda *a: None
        _extract_achievement_criteria = lambda *a: "" if lane == "NO_CRITERIA" else "기준"
        _run_goal_evaluation_stream = lambda self, **kw: calls.append(1) or iter(())
        _build_system_prompt_split = lambda *a: ("stable", "")
        _apply_consciousness_to_history = lambda self, history, co: history
        _after_response_async = lambda *a, **kw: None

    def stream(**kwargs):
        code = '[self:write]{path:"fixture.txt",content:"fixture"}' if signal == "write" else '[self:time]'
        name = "native_fixture" if signal == "unknown" else "mcp__indiebizos__execute_ibl"
        result = json.dumps({"success": signal != "failed", **({"error": "fixture failure"} if signal == "failed" else {})})
        for i in range(3):
            yield {"type": "tool_start", "id": str(i), "name": name, "input": {"code": code}}
            if signal != "unknown":
                supervisor.run_tool(name, {"code": code}, lambda: result)
            yield {"type": "tool_result", "id": str(i), "name": name, "result": result, "is_error": signal == "failed"}
        yield {"type": "text", "content": "사용자 응답"}
        yield {"type": "final", "content": "사용자 응답"}

    runner = Runner()
    runner.ai = supervisor.runner.ai
    runner.ai._provider = None
    runner.ai.process_message_stream = stream
    supervisor.runner = runner
    monkeypatch.setattr("pursuit_bind.prepare", lambda mem: (mem, False))
    monkeypatch.setattr("pursuit_bind.refresh_memory", lambda mem: mem)
    monkeypatch.setattr("pursuit_bind.finish", lambda *a, **kw: None)
    monkeypatch.setattr("system_ai_core._switch_to_midtier", lambda *a: None)
    if not supervised:
        monkeypatch.setattr("supervision_bus.current", lambda *a, **kw: None)
    monkeypatch.setattr("final_evaluator.invoke", lambda c, *a, **kw: calls.append(1) or verdict(c))
    supervisor.enabled = False
    events = list(runner._cognitive_stream_body("질문", []))
    assert not [e for e in events if e["type"] == "error"], events
    assert [e["content"] for e in events if e["type"] == "text"] == ["사용자 응답"]
    assert len(calls) == (1 if lane == "THINK" else 0)
    expected = {"path": "goal_eval", **({"supervised": True} if supervised else {})} if lane == "THINK" else {"path": "none"}
    assert ("cognition.evaluation", expected) in trace


@pytest.mark.parametrize("enabled,task,agent,reason", [
    (False, "t", "a", "disabled"), (True, "", "a", "no_task"),
    (True, "t", "", "no_agent"), (True, "t", "a", "available"),
])
def test_supervisor_selection_reports_reason_without_creating_fallback_identity(monkeypatch, enabled, task, agent, reason):
    import conscious_supervisor as module
    events = []
    monkeypatch.setattr("world_pulse._load_config", lambda: {"conscious_supervisor": {"enabled": enabled}})
    monkeypatch.setattr(tc, "get_current_agent_id", lambda: agent)
    monkeypatch.setattr(tc, "get_current_task_id", lambda: task)
    monkeypatch.setattr(module, "Supervisor", lambda *a: "controller")
    monkeypatch.setattr("episode_logger.record_trajectory_event", lambda kind, data: events.append((kind, data)))
    result = module.open_supervisor(SimpleNamespace(ai=SimpleNamespace(agent_id=agent)), "private", [])
    assert result == ("controller" if reason == "available" else None)
    assert events == [("cognition.supervisor_selected", {"reason": reason, "enabled": reason == "available"})]


def test_same_poll_with_elapsed_numbers_is_not_progress(supervisor):
    initial = supervisor.last_progress
    for i in range(3):
        key = supervisor._start("status", {})
        supervisor._finish(key, {"items": [{"job_id": "j", "status": "running", "duration_ms": i * 1000}]})
    assert supervisor.last_progress == initial
    assert supervisor.trigger == "unchanged_repeat"


def test_verdict_from_before_real_progress_is_not_delivered(supervisor, monkeypatch):
    active = supervisor._start("inspect", {"target": "stalled"})
    def invoke(c, *args, **kwargs):
        c._finish(active, "recovered")
        return verdict(c, "REWORK", instruction="예전 작업을 다시 시작하라")
    monkeypatch.setattr("supervisor_runtime.invoke", invoke)
    supervisor.review("tool_stalled")
    assert supervisor.pending is None
    assert "decision.stale" in (supervisor.store.directory / "events.jsonl").read_text()


def test_job_completion_comes_from_runner_row(tmp_path):
    path = tmp_path / "job.log"
    path.write_text("프로그램의 평범한 출력\n")
    (tmp_path / "jobs").mkdir()
    (tmp_path / "jobs/job.json").write_text('{"status":"done","runner_pid":123}')
    state = JobWatch(path, now=0).poll(2)
    assert state["phase"] == "complete" and state["job_status"] == "done"


def test_known_long_job_does_not_spend_periodic_review_budget(supervisor, monkeypatch, tmp_path):
    path = tmp_path / "voice.log"
    path.write_text('PROGRESS {"phase":"model-load","stall_after_s":1200}\n')
    job = JobWatch(path, now=supervisor.started)
    job.poll(supervisor.started)
    supervisor.jobs[str(path)] = job
    supervisor.progress({"phase": "model-load"})
    monkeypatch.setattr("supervisor_runtime.invoke", lambda *a, **kw: pytest.fail("정상적인 적재 대기 중 의식 낭비"))
    supervisor.tick(supervisor.started + 800)
    assert supervisor.reviews == 0


def test_cli_profiles_limit_manager_and_install_execution_boundary():
    from providers.claude_code import ClaudeCodeProvider
    from providers.codex import CodexProvider
    claude = ClaudeCodeProvider(api_key="", model="test", system_prompt="supervision")
    claude._binary_path = "claude"
    claude.agent_role = "consciousness"
    cmd = claude._build_command(mcp_config_path="/tmp/mcp.json")
    assert cmd[cmd.index("--tools") + 1] == "Read"
    assert "mcp__indiebizos__supervision" in cmd[cmd.index("--allowed-tools") + 1]
    hooks = claude.shadow_hook_settings()["hooks"]["PreToolUse"]
    assert any("supervision_hook.py" in h["hooks"][0]["command"] for h in hooks)
    codex = CodexProvider(api_key="", model="test", system_prompt="supervision")
    codex._binary_path = "codex"
    codex.agent_role = "consciousness"
    cmd = codex._build_command()
    assert "--dangerously-bypass-approvals-and-sandbox" not in cmd
    assert cmd[cmd.index("--sandbox") + 1] == "read-only"


def test_observation_does_not_hold_native_or_api_boundary(supervisor, monkeypatch):
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()

    def review(c, *args, **kwargs):
        entered.set()
        assert release.wait(3)
        return verdict(c, "CONTINUE", instruction="불필요한 지시")

    monkeypatch.setattr("supervisor_runtime.invoke", review)
    thread = threading.Thread(target=lambda: supervisor.review("tool_stalled"))
    thread.start()
    assert entered.wait(2)
    result = []

    def execute():
        assert supervisor.boundary() is None
        result.append(supervisor.run_tool("inspect", {}, lambda: "completed"))
        finished.set()

    worker = threading.Thread(target=execute)
    worker.start()
    try:
        assert finished.wait(1), "관찰 모델을 기다리느라 실제 도구가 멈췄다"
        assert result == ["completed"]
    finally:
        release.set()
        thread.join(3)
        worker.join(3)
    journal = (supervisor.store.directory / "events.jsonl").read_text()
    assert "decision.stale" not in journal  # CONTINUE는 진척 후에도 폐기할 개입이 없다.
    assert supervisor.pending is None


def test_start_announcement_cannot_invalidate_intervention(supervisor, monkeypatch):
    def review(c, *args, **kwargs):
        c.observe_native({"type": "tool_start", "id": "next", "name": "Bash", "input": {}})
        return verdict(c, "REWORK", instruction="정체 원인을 확인")

    monkeypatch.setattr("supervisor_runtime.invoke", review)
    supervisor.review("tool_stalled")
    assert supervisor.boundary()["instruction"] == "정체 원인을 확인"
    assert "decision.stale" not in (supervisor.store.directory / "events.jsonl").read_text()


def test_progress_after_review_before_delivery_retires_old_instruction(supervisor, monkeypatch):
    monkeypatch.setattr("supervisor_runtime.invoke", lambda c, *a, **kw: verdict(c, "REWORK", instruction="재시도"))
    key = supervisor._start("inspect", {})
    supervisor.review("tool_stalled")
    supervisor._finish(key, "recovered")
    assert supervisor.boundary() is None
    assert supervisor.pending is None


def test_long_progressing_work_gets_bounded_cost_review(supervisor, monkeypatch):
    seen = []
    monkeypatch.setattr("supervisor_runtime.invoke", lambda *a, **kw: (seen.append(kw) or '{"status":"CONTINUE","reason":"독립 처리 병렬 실행 중"}'))
    key = supervisor._start("inspect", {})
    supervisor._finish(key, "progress")
    now = supervisor.started + 500
    supervisor.last_progress = now - 10
    supervisor.tick(now)
    assert supervisor.reviews == 1
    supervisor.tick(now + 1)
    assert len(seen) == 1


def test_manager_state_is_delta_and_cannot_consume_job_progress(supervisor, tmp_path):
    path = tmp_path / "job.log"
    path.write_text('PROGRESS {"phase":"generate","completed":1,"total":4}\n')
    job = JobWatch(path)
    supervisor.jobs[str(path)] = job
    full = supervisor.state()
    assert "original_goal" in full
    delta = manager_tool(supervisor, {"op": "state"})["result"]
    assert not delta["changed"] and "original_goal" not in delta
    assert job.offset == 0  # 상태 조회는 로그를 소비하지 않는다.
    supervisor.tick()
    delta = manager_tool(supervisor, {"op": "state"})["result"]
    assert delta["changed"] and delta["jobs"][0]["units"] == [1, 4]


def test_cli_partial_usage_updates_budget_without_double_counting(supervisor, monkeypatch):
    from providers.claude_code import ClaudeCodeProvider
    from providers.base import ProviderMetrics
    from supervisor_runtime import UsageSnapshots
    provider = object.__new__(ClaudeCodeProvider)
    provider.model = "test"
    provider._note_model_round = lambda *a: None
    snapshots = UsageSnapshots(supervisor)
    provider.usage_snapshot_callback = snapshots.observe
    supervisor.call_metrics = ProviderMetrics()
    supervisor.config.update(max_input_tokens=1000, final_input_reserve=200)
    first = {"id": "msg-1", "usage": {"input_tokens": 100, "output_tokens": 5,
                                        "cache_read_input_tokens": 500, "cache_creation_input_tokens": 100}}
    provider._observe_response(first)
    provider._observe_response(first)  # 같은 응답의 다른 content block
    assert supervisor.call_usage["input"] == 700
    assert supervisor.model_budget_available()
    provider._observe_response({"id": "msg-2", "usage": {"input_tokens": 110, "output_tokens": 3}})
    assert not supervisor.model_budget_available()  # CLI 마지막 result 이전에 중단 조건 도달
    snapshots.reconcile(supervisor.call_metrics, 10)
    snapshots.reconcile(supervisor.call_metrics, 10)
    assert supervisor.call_metrics.total_input_tokens == 810
    assert supervisor.call_metrics.total_output_tokens == 8
    assert supervisor.call_metrics.total_requests == 1
    assert supervisor.call_metrics.total_cache_read_tokens == 500


def test_executor_state_read_does_not_advance_managers_cursor(supervisor):
    baseline = supervisor.state()["cursor"]
    key = supervisor._start("inspect", {})
    supervisor._finish(key, "new evidence")
    # 지금 actor는 실행자. 감독 모델이 아직 못 본 변경을 읽음으로 표시하면 안 된다.
    result = json.loads(supervisor.tool({"op": "state"}))
    assert result["success"] and supervisor.state_cursor == baseline
    delta = manager_tool(supervisor, {"op": "state"})["result"]
    assert any(e["kind"] == "tool.finished" for e in delta["events"])


def test_cli_final_totals_are_not_added_again_to_snapshots(supervisor):
    from providers.base import ProviderMetrics
    from supervisor_runtime import UsageSnapshots
    snapshots = UsageSnapshots(supervisor)
    snapshots.observe("m", {"input": 500, "output": 5})
    metrics = ProviderMetrics()
    metrics.record_usage(20, {"input_tokens": 520, "output_tokens": 8})
    snapshots.reconcile(metrics, 20)
    assert metrics.total_input_tokens == 520 and metrics.total_requests == 1


def test_supervisor_mcp_results_are_not_logged_as_native_reads(supervisor, monkeypatch):
    from providers.base import ProviderMetrics
    from supervisor_runtime import invoke

    class Agent:
        def __init__(self, *args, **kwargs):
            self._provider = SimpleNamespace(metrics=ProviderMetrics())
            self.model, self.provider_name = "test", "test"

        def process_message_stream(self, *args, **kwargs):
            yield {"type": "tool_start", "id": "mcp-1", "name": "mcp__indiebizos__supervision"}
            yield {"type": "tool_result", "id": "mcp-1", "name": "", "result": "already logged"}
            yield {"type": "tool_start", "id": "read-1", "name": "Read"}
            yield {"type": "tool_result", "id": "read-1", "name": "", "result": "actual native evidence"}
            yield {"type": "final", "content": "{}"}

    monkeypatch.setattr("ai_agent.AIAgent", Agent)
    monkeypatch.setattr("model_resolver.resolve", lambda *a: {})
    invoke(supervisor, "test")
    events = [json.loads(line) for line in (supervisor.store.directory / "events.jsonl").read_text().splitlines()]
    native = [e for e in events if e["kind"] == "model.native_tool"]
    assert len(native) == 2 and all(e["name"] == "Read" for e in native)


def test_manager_errors_are_typed_and_counted_in_whole_turn_cost(supervisor):
    supervisor.executor_paused = True
    supervisor._execute = lambda *a, **kw: json.dumps({"requires_approval": True, "command": "probe"})
    result = manager_tool(supervisor, {"op": "execute", "name": "inspect", "input": {}})
    assert result["success"] is False
    assert isinstance(result["result"], dict)
    key = supervisor._start("Bash", {})
    supervisor._finish(key, "denied", error=True)
    summary = supervisor.store.cost_summary(10)
    assert summary["supervisor_tool_failures"] == 1
    assert summary["execution_calls"] == 1 and summary["execution_failures"] == 1
    assert summary["wall_s"] == 10


def test_supervisor_action_contract_comes_from_registry():
    from supervisor_runtime import action_schema
    schema = action_schema("self:list")
    assert schema["action"] == "self:list"
    assert "path" in json.dumps(schema["definition"])
    assert schema["definition"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
