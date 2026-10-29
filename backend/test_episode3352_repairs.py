"""ep3352: 시스템 AI 감독 배선·MCP/병렬 비용·부분 중단·원문 의존성 회귀."""
import asyncio
import contextvars
import json
import threading
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest

import thread_context as tc
from providers.base import BaseProvider, ProviderMetrics, read_turn_tokens, turn_token_scope


@pytest.fixture(autouse=True)
def restore_actor():
    snapshot = tc.snapshot()
    tc.clear_all_context()
    try:
        yield
    finally:
        tc.restore(snapshot)


def test_partial_failure_marker_survives_without_full_results():
    from conscious_supervisor import _failed
    from ibl_honesty import completion_evidence
    result = {"success": True, "incomplete_steps": [{"at": "results[2]", "error_count": 3}]}
    assert _failed(result)
    for _ in range(4):
        result = {"success": True, "incomplete_steps": completion_evidence(result)}
        assert len(result["incomplete_steps"]) == 1
        assert _failed(result)


def test_system_ai_pipeline_binds_identity_and_closes_supervisor(tmp_path, monkeypatch):
    from agent_pipeline import CognitivePipelineMixin
    from conscious_supervisor import Supervisor
    from supervision_bus import current
    monkeypatch.setattr("agent_pipeline._reload_gate_notice", lambda: "")
    monkeypatch.setattr("execution_turn.enter", lambda *a, **k: None)
    monkeypatch.setattr("execution_turn.leave", lambda *a: None)
    opened = []

    def open_controller(runner, message, history, cancel):
        c = Supervisor(runner, message, history, tc.get_current_agent_id(),
                       tc.get_current_task_id(), {"tick_s": 1000}, directory=tmp_path)
        opened.append(c)
        return c
    monkeypatch.setattr("conscious_supervisor.open_supervisor", open_controller)

    class Runner(CognitivePipelineMixin):
        def _sync_execution_gear(self):
            pass

        def _cognitive_stream_body(self, *a, **k):
            assert tc.get_current_agent_id() == "system_ai"
            controller = current()
            assert controller is opened[0]
            controller.configure({"achievement_criteria": "fixture"})
            assert controller.phase == "execute"
            yield {"type": "final", "content": "done"}

    runner = Runner()
    runner.ai = SimpleNamespace(agent_id="system_ai", project_path=str(tmp_path),
                                tools=[], _custom_execute_tool=lambda *a, **k: {})
    tc.set_current_task_id("sysai-fixture")
    assert tc.get_current_agent_id() is None
    assert list(runner.cognitive_stream("fixture"))[-1]["content"] == "done"
    assert tc.get_current_agent_id() is None
    assert current("system_ai", "sysai-fixture") is None
    assert opened[0].stopped.is_set()


def test_mcp_tool_usage_rejoins_only_its_own_live_turn(monkeypatch):
    from api_ibl import IBLRequest, execute_ibl_code
    from providers.base import adopt_turn_token_ledger, read_turn_cache_read_tokens

    def execute(*a, **k):
        ProviderMetrics().record_usage(1, {"prompt_tokens": 101, "completion_tokens": 7,
                                        "prompt_cache_hit_tokens": 80})
        return {"success": True, "items": []}
    monkeypatch.setattr("system_tools._execute_ibl_unified", execute)

    with turn_token_scope("worker", "task-3352"):
        req = IBLRequest(code="[self:time]", agent_id="worker", task_id="task-3352")
        assert asyncio.run(execute_ibl_code(req))["success"]
        assert read_turn_tokens() == 108
        assert read_turn_cache_read_tokens() == 80
        with adopt_turn_token_ledger("other", "task-3352"):
            execute()
        assert read_turn_tokens() == 108
    with adopt_turn_token_ledger("worker", "task-3352"):
        assert read_turn_tokens() is None


def test_mcp_episode_usage_updates_parent_summary_and_restores_context(monkeypatch):
    import episode_logger as ep
    parent = ep._Episode("worker", "fixture", task_id="task-3352")
    parent.episode_id = 33520001
    parent.trajectory.episode_id = parent.episode_id
    monkeypatch.setitem(ep._live_episodes, parent.episode_id, parent)
    monkeypatch.setattr(ep, "record_trajectory_event", lambda *a, **k: None)

    def worker(task):
        assert ep.EpisodeLogger.current() is None
        with ep.trajectory_scope(task_id=task, episode_id=parent.episode_id):
            ep.notify_usage("fixture", "fixture", 1, {"input": 40, "output": 3})
        assert ep.EpisodeLogger.current() is None
    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(worker, "task-3352").result()
        pool.submit(worker, "other-task").result()
    assert len(parent.steps) == 1 and parent.steps[0]["input"] == 40








def test_oneshots_overlap_with_isolated_prompts_buffers_and_metrics(monkeypatch):
    import consciousness_agent as ca
    barrier = threading.Barrier(2)
    observations = []
    class Provider(BaseProvider):
        def init_client(self):
            return True
        def process_message(self, message, **kwargs):
            self._pending_map_tags.append(message)
            self.metrics.record_usage(1, {"prompt_tokens": 10, "completion_tokens": 2})
            barrier.wait(timeout=3)
            observations.append((self.system_prompt, list(self._pending_map_tags),
                                 self.metrics.total_input_tokens))
            return self.system_prompt
    provider = Provider("", "fixture", "original")
    monkeypatch.setattr(ca, "_resolve_oneshot_provider", lambda *a: provider)
    with turn_token_scope("worker", "oneshots-3352"):
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(contextvars.copy_context().run, ca.system_ai_call,
                                   message, system_prompt=message) for message in ("A", "B")]
            assert sorted(f.result() for f in futures) == ["A", "B"]
        assert read_turn_tokens() == 24
    assert sorted(observations) == [("A", ["A"], 10), ("B", ["B"], 10)]
    assert provider.system_prompt == "original"
    assert provider._pending_map_tags == [] and provider.metrics.total_input_tokens == 0








def test_project_sender_alias_joins_same_ledger():
    from providers.base import adopt_turn_token_ledger
    with turn_token_scope("project:worker", "task", aliases=("worker",)):
        with adopt_turn_token_ledger("worker", "task"):
            ProviderMetrics().record_usage(1, {"prompt_tokens": 10, "completion_tokens": 2})
        assert read_turn_tokens() == 12


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
