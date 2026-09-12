"""검수 전 저장 우회·중단 턴·최종 본문과 근거/가치 선별의 회귀."""
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

import boot_paths  # noqa: F401
from test_conscious_supervisor import supervisor  # noqa: F401
from test_supervisor_episode_repairs import memory_harness  # noqa: F401


@pytest.fixture
def handler():
    path = Path(__file__).resolve().parents[1] / "data/packages/installed/tools/memory/handler.py"
    spec = importlib.util.spec_from_file_location("_memory_retention_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("content", [
    "시세가 지난번보다 떨어졌으므로 지금 구매를 권한다.",
    "목표 원문",  # 사용자 문장과 같아도 즉시 저장/저장 보장은 금지.
])
def test_save_never_writes_or_queues_draft(handler, supervisor, content):
    class NoWrites:
        def save(self, **kw):
            pytest.fail("검수 전 기억 저장")

    result = json.loads(handler._memory_save(NoWrites(), {"content": content}, "/unused", "worker"))
    assert result["success"] and not result["saved"]
    assert result["status"] == "automatic_selection" and "memory_id" not in result
    assert content not in json.dumps(result, ensure_ascii=False)


def test_save_alone_does_not_trigger_final_evaluator():
    from cognitive_trace import should_self_reflect
    calls = [{"name": "execute_ibl", "input": {"code": code},
              "result": '{"success": true, "saved": false}', "is_error": False}
             for code in ('[self:time]{}', '[self:memory]{op:"recall"}',
                          '[self:memory]{op:"save",content:"조사 결과"}')]
    assert should_self_reflect(calls)[0] is False


@pytest.mark.parametrize("ending", ["complete", "close", "error"])
def test_pipeline_queues_only_after_final_delivery(supervisor, monkeypatch, ending):
    from agent_pipeline import CognitivePipelineMixin
    queued = []

    class Runner(CognitivePipelineMixin):
        config = {"name": "worker"}
        project_path = Path(supervisor.project_path)
        _build_execution_memory = lambda *a, **kw: ("", 0, "")
        _decide_request_type = lambda *a: ("THINK", None)
        _run_consciousness_or_reuse = lambda *a: {"task_framing": "문제", "achievement_criteria": "기준"}
        _consciousness_needs_repair = lambda *a: False
        _consciousness_clarification = lambda *a: None
        _extract_achievement_criteria = lambda *a: "기준"
        _build_system_prompt_split = lambda *a: ("stable", "")
        _apply_consciousness_to_history = lambda self, history, co: history
        _after_response_async = lambda self, user, response, **kw: queued.append((user, response))

    def execute(**kw):
        yield {"type": "final", "content": "수정 전 초안"}

    def finalize(response, *a, **kw):
        assert response == "수정 전 초안" and not queued
        yield {"type": "test_checkpoint"}
        if ending == "error":
            raise RuntimeError("검수 도중 실패")
        yield {"type": "final", "content": "검수로 수정한 최종 보고"}
        return "검수로 수정한 최종 보고"

    runner = Runner()
    runner.ai = supervisor.runner.ai
    runner.ai._provider = None
    runner.ai.process_message_stream = execute
    supervisor.runner = runner
    monkeypatch.setattr(supervisor, "finalize", finalize)
    monkeypatch.setattr("pursuit_bind.prepare", lambda mem: (mem, False))
    monkeypatch.setattr("pursuit_bind.refresh_memory", lambda mem: mem)
    monkeypatch.setattr("pursuit_bind.finish", lambda *a, **kw: None)
    stream = runner._cognitive_stream_body("사용자 원문", [])
    events = []
    for event in stream:
        events.append(event)
        if event["type"] in {"test_checkpoint", "final"}:
            assert not queued
        if event["type"] == "test_checkpoint" and ending == "close":
            stream.close()
            break
    assert any(e["type"] == "test_checkpoint" for e in events), events
    assert queued == ([("사용자 원문", "검수로 수정한 최종 보고")] if ending == "complete" else [])


@pytest.mark.parametrize("evaluation,retained", [
    (None, True), ({"status": "ACHIEVED", "achieved": True}, True),
    ({"status": "UNKNOWN"}, False), ({"status": "NOT_ACHIEVED"}, False),
    ({"achieved": False}, False),
])
def test_unapproved_turn_cannot_distill(memory_harness, monkeypatch, evaluation, retained):
    seen = []
    monkeypatch.setattr("thread_context.get_goal_eval_outcome", lambda: evaluation)
    monkeypatch.setattr(memory_harness.runner, "_distill_deep_memory", lambda *a: seen.append(a))
    memory_harness.runner._after_response("user", "final", write_experience=False, write_forage=False)
    assert bool(seen) == retained


def test_retention_requires_value_and_stores_source_not_model_analysis(memory_harness, monkeypatch):
    h = memory_harness
    user = "나는 앞으로도 중고 제품은 사지 않을 거야."
    final = "신품 중에서 비교하겠습니다."
    candidates = [
        {"source_ids": [1], "retention": "user_preference"},  # 가치 판단 없음
        {"source_ids": [99], "retention": "user_fact", "future_use": "미래 계획"},
        {"source_ids": [1], "retention": "assistant_analysis", "future_use": "미래 계획"},
        {"source_ids": [1], "retention": "user_preference", "future_use": "향후 구매 후보에서 중고 제외",
         "content": "사용자는 비싼 고급 제품을 선호하며 가격이 떨어졌다."},
    ]

    def model(prompt, **kw):
        assert "0건인 것이 정상" in prompt and "future_use" in prompt
        assert final not in prompt  # AI 보고는 사실 근거로 제공하지 않는다.
        return json.dumps(candidates, ensure_ascii=False)

    monkeypatch.setattr("consciousness_agent.oneshot_ai_call", model)
    monkeypatch.setattr(sys.modules["memory_db"], "search", lambda **kw: [])
    h.runner._distill_deep_memory(user, final)
    assert len(h.saved) == 1 and h.saved[0]["content"] == user
    source = json.loads(h.saved[0]["source_ref"])
    assert source["retention"] == "user_preference"
    assert source["evidence"][0]["text"] == user
    assert source["final_response_sha256"] == hashlib.sha256(final.encode()).hexdigest()
    assert "고급 제품" not in h.saved[0]["content"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
