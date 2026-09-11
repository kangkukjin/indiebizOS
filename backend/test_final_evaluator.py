"""최종 평가는 증거 기반 원샷이며 중간관리 도구와 공개·기억 계약을 보존한다."""
import json
from types import SimpleNamespace

import pytest
import boot_paths  # noqa: F401
import thread_context as tc
from consciousness_agent import system_ai_call as real_system_ai_call
from final_evaluator import execution_trace
from test_conscious_supervisor import supervisor, finish  # noqa: F401
from test_supervision_delivery import prepare as stage


def test_real_oneshot_cannot_call_tools_or_resume_executor(supervisor, monkeypatch):
    calls = []

    class Provider:
        tools = ["execution tool"]
        no_tools = False
        disable_session_persistence = False

        def process_message(self, **kwargs):
            assert self.tools == [] and self.no_tools
            assert self.disable_session_persistence and self.agent_role == "oneshot:evaluate"
            assert kwargs["execute_tool"] is None and kwargs["history"] == []
            assert "실제 실행된 액션 원장" in kwargs["message"]
            assert "조회한 근거" in kwargs["message"]
            calls.append(kwargs)
            return "ACHIEVED"

    provider = Provider()
    monkeypatch.setattr("consciousness_agent._resolve_oneshot_provider", lambda role: provider)
    monkeypatch.setattr("consciousness_agent.system_ai_call", real_system_ai_call)
    monkeypatch.setattr("supervisor_runtime.invoke", lambda *a, **kw: pytest.fail("최종평가가 의식 호출"))
    key = supervisor._start("execute_ibl", {"code": '[sense:search]{query:"사실"}'})
    supervisor._finish(key, "조회한 근거")
    assert finish(supervisor, "조회한 근거에 따른 답변")[-1]["content"] == "조회한 근거에 따른 답변"
    assert len(calls) == 1 and supervisor.tools_used == 0
    assert provider.tools == ["execution tool"] and not provider.no_tools
    cost = supervisor.store.cost_summary(1)
    assert cost["evaluation_calls"] == 1 and cost["evaluation_model_s"] >= 0


def test_repeated_calls_and_changed_results_survive_trace_merge(supervisor):
    payload = {"code": '[sense:search]{query:"같은 조회"}'}
    for result in ("실패", "복구된 원문"):
        key = supervisor._start("execute_ibl", payload)
        supervisor._finish(key, result)
    calls = execution_trace(supervisor, [{"name": "mcp__indiebizos__execute_ibl", "input": payload,
                                         "result": "축약"}])
    assert len(calls) == 2
    assert [c["result"] for c in calls] == ["실패", "복구된 원문"]


def test_rework_uses_updated_evidence_and_stops_after_one_repair(supervisor, monkeypatch):
    supervisor.config["max_repairs"] = 9  # 옛 설정도 무한 보완을 되살리지 않는다.
    evaluations, repairs = [], []

    def evaluate(prompt, **kwargs):
        evaluations.append(prompt)
        if len(evaluations) == 2:
            assert "보완으로 확보한 출처" in prompt and "수정한 답변" in prompt
        return 'NOT_ACHIEVED\nSEVERITY: 1\nREPAIR_SCOPE: local\nREPAIR_BLOCK_IDS: ["0"]\n핵심 근거를 반영하라'

    def repair(prompt, **kwargs):
        repairs.append(prompt)
        key = supervisor._start("execute_ibl", {"code": '[sense:search]{query:"새 근거"}'})
        supervisor._finish(key, "보완으로 확보한 출처")
        block = supervisor.store.blocks[0]
        supervisor.store.patch(supervisor.store.version, [{"id": block["id"], "hash": block["hash"],
                                                           "text": "수정한 답변"}])
        yield {"type": "final", "content": "PATCH_DONE"}

    supervisor.runner.ai.process_message_stream = repair
    monkeypatch.setattr("consciousness_agent.system_ai_call", evaluate)
    result = finish(supervisor, "기존 답변")[-1]["content"]
    assert len(evaluations) == 2 and len(repairs) == 1
    assert result.startswith("수정한 답변") and "미승인" in result
    assert tc.get_goal_eval_outcome()["status"] == "NOT_ACHIEVED"


def test_staged_body_and_notice_are_supplied_before_publication(supervisor, tmp_path, monkeypatch):
    target, artifact, sent = stage(supervisor, tmp_path, monkeypatch)

    def evaluate(prompt, **kwargs):
        assert "new reviewed bytes" in prompt and "14 tips" in prompt
        assert target.read_text() == "old" and not sent
        return "ACHIEVED"

    monkeypatch.setattr("consciousness_agent.system_ai_call", evaluate)
    finish(supervisor, f"보고서: {target}")
    assert target.read_text() == "new reviewed bytes" and len(sent) == 1


def test_whole_pursuit_criteria_are_included_before_done(supervisor, monkeypatch):
    writes = []
    binding = SimpleNamespace(row={"id": "goal", "version": 3, "goal_criteria": "전체 보고서 세 편 완성"},
                              write=lambda *a, **kw: writes.append((a, kw)))
    supervisor.request_done(binding, "모두 완성")
    monkeypatch.setattr("pursuit_bind.resolve_session", lambda *a: binding)

    def evaluate(prompt, **kwargs):
        assert "전체 보고서 세 편 완성" in prompt and not writes
        return "ACHIEVED"

    monkeypatch.setattr("consciousness_agent.system_ai_call", evaluate)
    finish(supervisor, "세 편의 결과")
    assert writes[0][0][0] == {"status": "done"}


def test_changed_code_file_cannot_be_approved_with_old_snapshot(supervisor, tmp_path, monkeypatch):
    path = tmp_path / "made.py"
    path.write_text("print('원래 코드')")

    def evaluate(prompt, **kwargs):
        assert "print('원래 코드')" in prompt
        path.write_text("print('교체된 코드')")
        return "ACHIEVED"

    monkeypatch.setattr("consciousness_agent.system_ai_call", evaluate)
    result = finish(supervisor, str(path))[-1]["content"]
    assert "산출물이 변경" in result
    assert tc.get_goal_eval_outcome()["status"] == "UNKNOWN"


def test_episode_summary_uses_delivered_verdict_not_earlier_success():
    from episode_logger import _final_evaluation_result
    assert _final_evaluation_result("[GoalEval] 평가 응답: ACHIEVED\n[GoalEval] 최종 판정: UNKNOWN") == "UNKNOWN"


def test_unknown_reason_mentioning_achieved_does_not_trigger_approval(supervisor, monkeypatch):
    monkeypatch.setattr("consciousness_agent.system_ai_call", lambda *a, **kw:
                        "UNKNOWN\n필수 출처가 없어 ACHIEVED라고 판단할 수 없습니다.")
    result = finish(supervisor, "출처 없는 답변")[-1]["content"]
    assert "미승인" in result and tc.get_goal_eval_outcome()["status"] == "UNKNOWN"


def test_tool_capable_supervisor_rejects_final_phase(supervisor):
    from supervisor_runtime import invoke
    with pytest.raises(ValueError, match="도구 없는"):
        invoke(supervisor, "평가", phase="final")


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
