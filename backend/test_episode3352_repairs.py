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
    monkeypatch.setattr("pursuit_bind.enter", lambda *a, **k: None)
    monkeypatch.setattr("pursuit_bind.leave", lambda *a: None)
    monkeypatch.setattr("pursuit_bind.observe", lambda *a: None)
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


def test_each_parallel_workers_inherit_cost_context(monkeypatch):
    from ibl_exec_each import _execute_table_each as execute_each
    import workflow_engine

    def child(*a, **k):
        ProviderMetrics().record_usage(1, {"prompt_tokens": 10, "completion_tokens": 2})
        return {"success": True, "final_result": {"items": [{"ok": True}]}}
    monkeypatch.setattr(workflow_engine, "execute_pipeline", child)
    with turn_token_scope("worker", "parallel-3352"):
        result = execute_each({"items": [{"x": 1}, {"x": 2}], "parallel": 2,
                               "do": "[self:time]"}, ".")
        assert result["ok_count"] == 2
        assert read_turn_tokens() == 24


def test_each_budget_cut_reports_true_processed_count_and_keeps_results(monkeypatch):
    import ibl_exec_each as each
    import workflow_engine
    monkeypatch.setattr(each, "_EACH_MAX_SUBSTEPS", 2)
    done = []
    def child(*a, **k):
        done.append(1)
        return {"success": True, "final_result": {"items": [{"ok": True}]}}
    monkeypatch.setattr(workflow_engine, "execute_pipeline", child)
    result = each._execute_table_each({"items": [{"x": i} for i in range(5)],
                                "do": "[self:time]", "limit": 5}, ".")
    assert not result["success"] and result["error_type"] == "budget"
    assert len(done) == result["rows_processed"] == result["ok_count"] == 2
    assert result["rows_requested"] == 5 and result["rows_unprocessed"] == 3
    assert result["skipped"] == 3 and len(result["items"]) == 2


@pytest.mark.parametrize("verbose", [False, True])
def test_intermediate_partial_failure_survives_projection_and_alerts_supervisor(verbose):
    from ibl_envelope import diet_envelope
    from ibl_honesty import completion_evidence
    from conscious_supervisor import _failed
    inner = {"success": True, "items": [{"ok": True}], "rows_requested": 5,
             "rows_processed": 4, "ok_count": 3, "error_count": 1, "rows_unprocessed": 1}
    envelope = {"success": True, "results": [{"step": 1, "result": json.dumps(inner)}],
                "final_result": {"success": True, "items": [{"done": True}]}}
    compact = diet_envelope(envelope, verbose=verbose)
    evidence = completion_evidence(compact)
    assert evidence[0]["error_count"] == 1
    assert evidence[0]["rows_unprocessed"] == 1
    if not verbose:
        assert compact["incomplete_steps"]
    assert _failed(json.dumps(compact))
    assert not _failed({"success": True, "items": [{"error_count": 10, "error": "user data"}]})


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


def test_selection_closes_transitive_dependencies_without_another_model_call():
    from ibl_distill_gates import _recover_distill_selection
    calls = ['$a = [self:time]', '$b = $a >> [table:select]{columns:["date"]}',
             '$b >> [table:take]{n:1}']
    seen = []
    def ask(**kwargs):
        seen.append(kwargs)
        return '{"call_ids":[3]}'
    code, note = _recover_distill_selection("날짜", "broken", "missing", calls, ask)
    assert code == "\n".join(calls) and note == "호출 1, 2, 3"
    assert len(seen) == 1


def test_dependency_uses_latest_prior_definition_and_rejects_future_producer():
    from ibl_distill_gates import _close_source_dependencies
    calls = ['$x = [self:time]', '$x = [self:time]', '$x >> [table:take]{n:1}']
    assert _close_source_dependencies([3], calls) == ([2, 3], None)
    ids, reason = _close_source_dependencies([1], [calls[2], calls[0]])
    assert ids is None and "앞선 생산자" in reason


def test_recovered_dependencies_reach_corpus_without_allowing_fabricated_pipes(monkeypatch, tmp_path):
    from test_distill_source_recovery_2026_09_09 import _arm
    from ibl_distill_gates import _composition_grounded
    sources = ['$x = [sense:search]{query:"fixture"} >> [table:take]{n:2}',
               '$x >> [table:select]{columns:["title"]}']
    rag, stored, asked, _ = _arm(monkeypatch, tmp_path, [
        {"intent": "검색 제목 확인", "source_ids": [2]},
    ])
    calls = [{"tool_name": "execute_ibl", "input": {"code": c}, "success": True} for c in sources]
    assert rag.distill_experience("검색 제목 확인", calls, 0)
    assert stored[0]["ibl_code"] == "\n".join(sources) and len(asked) == 1
    assert not _composition_grounded('[sense:search]{query:"fixture"} >> [self:read]{path:"x"}',
                                     [sources[0], '[self:read]{path:"x"}'])


def test_project_sender_alias_joins_same_ledger():
    from providers.base import adopt_turn_token_ledger
    with turn_token_scope("project:worker", "task", aliases=("worker",)):
        with adopt_turn_token_ledger("worker", "task"):
            ProviderMetrics().record_usage(1, {"prompt_tokens": 10, "completion_tokens": 2})
        assert read_turn_tokens() == 12


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
