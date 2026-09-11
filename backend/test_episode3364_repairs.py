"""ep3364: 감독 예산·실행 자원 신원·병렬 비용·검수 보류 회귀."""
import json
import time
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest
import thread_context as tc
from test_conscious_supervisor import supervisor, manager_tool, finish  # noqa: F401


def test_supervisor_executes_with_resource_owner_and_restores_manager(supervisor):
    from tool_context import ToolContext

    def inspect(*args, **kwargs):
        context = ToolContext.from_thread_context(supervisor.project_path, "inspect")
        assert context.agent_id == supervisor.owner
        assert context.project_path == supervisor.project_path
        return {"success": True, "memory_owner": context.agent_id}

    supervisor._execute = inspect
    supervisor.executor_paused = True
    with tc.actor_context(agent_id=supervisor.supervisor_id):
        supervisor.call_deadline = time.monotonic() + 60
        result = json.loads(supervisor.tool({"op": "execute", "name": "inspect", "input": {}}))
        assert result["success"] and result["result"]["memory_owner"] == supervisor.owner
        assert tc.get_current_agent_id() == supervisor.supervisor_id


def test_parallel_branches_share_episode_and_tokens_without_cross_turn_leak(monkeypatch):
    import episode_logger as ep
    from providers.base import ProviderMetrics, turn_token_scope, read_turn_tokens
    from workflow_parallel import _execute_parallel
    monkeypatch.setattr(ep, "record_trajectory_event", lambda *a, **kw: None)
    parent = ep._Episode("worker", "parallel", task_id="parallel-3364")
    token = ep._current_episode.set(parent)

    def action(step, path):
        ProviderMetrics().record_usage(1, {"prompt_tokens": 41, "completion_tokens": 3})
        return {"success": True}

    monkeypatch.setattr("ibl_engine.execute_ibl", action)
    previous_tokens = read_turn_tokens()
    try:
        with turn_token_scope("worker", "parallel-3364"):
            result = _execute_parallel([{"action": "a"}, {"action": "b"}], ".", "")
            assert all(r["success"] for r in result)
            assert read_turn_tokens() == 88
        assert len(parent.steps) == 2
        assert sum(s["input"] + s["output"] for s in parent.steps) == 88
    finally:
        ep._current_episode.reset(token)
    assert read_turn_tokens() == previous_tokens


def test_explicit_hard_budget_preserves_final_reserve(supervisor):
    supervisor.config["budget_mode"] = "hard"
    supervisor.call_deadline = time.monotonic() + 60
    supervisor.usage["input"] = 253964
    assert not supervisor.model_budget_available()
    assert supervisor.call_cancelled()
    assert supervisor.call_stop["kind"] == "budget"
    supervisor.finalizing = True
    supervisor.call_stop = None
    supervisor.call_deadline = time.monotonic() + 60
    supervisor.call_usage = {"input": 64020}
    assert supervisor.model_budget_available()
    assert not supervisor.call_cancelled()
    supervisor.final_usage["input"] = 64020
    supervisor.usage["input"] += 64020
    supervisor.call_usage = {"input": 20000}
    assert supervisor.call_cancelled() and supervisor.call_stop["kind"] == "budget"


def test_unknown_preserves_cause_and_defers_learning(supervisor, monkeypatch, capsys):
    def invoke(c, *a, **kw):
        c.call_stop = {"kind": "budget", "reason": "의식 호출 토큰 예산을 소진했습니다"}
        return ""
    monkeypatch.setattr("supervisor_runtime.invoke", invoke)
    result = finish(supervisor, "파일은 생성됨")[-1]["content"]
    assert "토큰 예산" in result and "JSON" not in result and "사용자 취소" not in result
    outcome = tc.get_goal_eval_outcome()
    assert outcome["status"] == "UNKNOWN" and outcome["severity"] == 0
    status = json.loads((supervisor.store.directory / "review_status.json").read_text())
    assert status["learning"] == "deferred" and status["stop_kind"] == "budget"
    from ibl_usage_rag import distill_experience
    assert not distill_experience("fixture", [], 0)
    assert "재검수까지 학습 보류" in capsys.readouterr().out


def test_large_supervisor_result_is_pageable_without_losing_error(supervisor):
    raw = {"success": False, "error": "실제 실패", "body": "원문" * 8000}
    supervisor._execute = lambda *a, **kw: raw
    supervisor.executor_paused = True
    result = manager_tool(supervisor, {"op": "execute", "name": "inspect", "input": {}})
    assert result["success"] is False
    page = result["result"]
    assert len(json.dumps(page, ensure_ascii=False)) < 13000
    assert len(page["page"]["text"]) == 12000
    ref = page["evidence"]["id"]
    restored = (supervisor.store.directory / (ref + ".txt")).read_text()
    assert json.loads(restored) == raw


def test_prompt_catalog_does_not_advertise_forbidden_control_tools(supervisor):
    from supervisor_runtime import tool_context
    supervisor.catalog["pursuit"] = {"name": "pursuit", "description": "control"}
    context = tool_context(supervisor)
    assert [t["name"] for t in context["tools"]] == ["inspect"]
    assert "tool_schemas" not in context
    assert "pursuit" not in supervisor.state()["tools"]


def test_distill_queue_preserves_unknown_reason_and_task():
    from distill_queue import DistillQueue, _Job
    original = tc.snapshot()
    seen = []
    runner = SimpleNamespace(_after_response=lambda *a, **kw:
                             seen.append((tc.get_goal_eval_outcome(), tc.get_current_task_id())))
    outcome = {"achieved": False, "severity": 0, "status": "UNKNOWN", "reason": "토큰 예산"}
    try:
        DistillQueue._execute(_Job(1, runner, {"response": "후보", "goal_eval": outcome,
                                             "task_id": "task_3364"}, {}))
        assert seen == [(outcome, "task_3364")]
        DistillQueue._execute(_Job(2, runner, {"response": "다른 턴"}, {}))
        assert seen[-1] == (None, None)
    finally:
        tc.restore(original)


def test_deep_memory_receives_unknown_before_experience_consumes_outcome(monkeypatch):
    import ibl_usage_rag
    from cognitive_distill import CognitiveDistillMixin
    original = tc.snapshot()
    seen = []
    monkeypatch.setattr(ibl_usage_rag, "distill_experience", lambda *a, **kw: tc.clear_goal_eval_outcome())
    monkeypatch.setattr(ibl_usage_rag, "record_recall_outcome", lambda *a, **kw: None)
    runner = CognitiveDistillMixin()
    runner._distill_deep_memory = lambda u, r: seen.append(r)
    try:
        tc.set_goal_eval_outcome(False, 0, status="UNKNOWN", reason="예산 중단")
        runner._after_response("영상", "완성했습니다", tool_calls=[{}], write_forage=False, guides_used=[])
        assert seen == ["검수 미완료(성공 판정으로 저장하지 말 것): 예산 중단\n완성했습니다"]
    finally:
        tc.restore(original)


def test_deep_memory_keeps_full_utterance_and_supplement_source(monkeypatch, tmp_path):
    import sys
    import cognitive_distill as mod
    import consciousness_agent
    utterance = "이 작업의 요청 " * 60 + "마지막 조건도 보존"
    fact = {"source_ids": [2], "content": "이번 영상은 오분", "keywords": "영상", "category": "작업기록", "node": "영상"}
    replies = iter([json.dumps([fact], ensure_ascii=False),
                    json.dumps({"verdicts": [{"action": "UPDATE", "content": fact["content"]}]})])
    monkeypatch.setattr(consciousness_agent, "oneshot_ai_call", lambda **kw: next(replies))
    old = {"id": 123, "content": "이전 작업", "keywords": "영상", "source_ref": "이전 출처"}
    saved = []
    fake = SimpleNamespace(_get_db_path=lambda *a: "fixture", search=lambda **kw: [old],
                           read=lambda *a: old, update=lambda *a, **kw: saved.append(kw),
                           body_noun_leak=lambda *a: None)
    monkeypatch.setitem(sys.modules, "memory_db", fake)
    monkeypatch.setitem(sys.modules, "memory_tree", SimpleNamespace(map_text=lambda *a: "영상", norm_node=lambda x: x))
    runner = mod.CognitiveDistillMixin()
    runner.project_path, runner.agent_id = tmp_path, "worker"
    with tc.actor_context(agent_id="worker", task_id="task_3364"):
        runner._distill_deep_memory(utterance, "이번 영상 완성")
    assert len(saved) == 1
    assert saved[0]["content"] == "이전 작업\n[보충] 이번 영상 완성"
    provenance = json.loads(saved[0]["source_ref"])
    assert provenance["previous"] == "이전 출처"
    assert provenance["supplement"]["utterance"] == utterance
    assert provenance["supplement"]["task"] == "task_3364"


def test_source_notes_material_and_length_share_one_input(tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("narration_prepare_test",
        Path(__file__).resolve().parents[1] / "data/scripts/나레이션원고추출.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    monkeypatch.setattr(mod, "ROOT", tmp_path)
    lec = tmp_path / "outputs/lectures/demo"
    lec.mkdir(parents=True)
    deck_path = lec / "deck.json"
    deck_path.write_text(json.dumps({"slide_order": ["s001"], "slides": {"s001": {"speaker_note": "old"}}}))
    src = tmp_path / "script.md"
    src.write_text(f"## s001 — 표지\n{mod.INTRO} 새 본문. {mod.OUTRO}\n")
    args = {"lecture_id": "demo", "source": str(src)}
    assert mod.prepare({**args, "inspect": True})["mismatched_notes"] == ["s001"]
    assert not (lec / "narration_texts.json").exists()
    with pytest.raises(ValueError, match="불일치"):
        mod.prepare(args)
    result = mod.prepare({**args, "apply_notes": True})
    assert json.loads((lec / "narration_texts.json").read_text()) == {"s001": "새 본문."}
    assert (lec / "materials/script.md").read_text() == src.read_text()
    assert result["chars"] == 5 and result["estimated_seconds"] > 8.7
    src.write_text("## s002 — 잘못된 장\n본문")
    original = deck_path.read_bytes()
    with pytest.raises(ValueError, match="ID"):
        mod.prepare({"lecture_id": "demo", "apply_notes": True})
    assert deck_path.read_bytes() == original


def test_final_audio_gain_remeasures_encoding_peak_before_publish(tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("video_gain_test",
        Path(__file__).resolve().parents[1] / "data/scripts/영상음량정렬.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    readings = iter([{"lufs": -27.9, "true_peak": -6.6, "seconds": 317, "bytes": 1},
                     {"lufs": -22.3, "true_peak": -0.8, "seconds": 317, "bytes": 2},
                     {"lufs": -22.6, "true_peak": -1.1, "seconds": 317, "bytes": 3}])
    monkeypatch.setattr(mod, "measure", lambda path: next(readings))
    def encode(command, **kwargs):
        assert command[command.index("-c:v") + 1] == "copy"
        Path(command[-1]).write_bytes(b"encoded")
    monkeypatch.setattr(mod.subprocess, "run", encode)
    dst = tmp_path / "final.mp4"
    result = mod.align({"src": str(tmp_path / "raw.mp4"), "dst": str(dst)})
    assert result["gain_db"] == 5.3 and result["items"][0]["true_peak"] == -1.1
    assert dst.read_bytes() == b"encoded"
    assert dst.with_suffix(".audio.json").exists()


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
