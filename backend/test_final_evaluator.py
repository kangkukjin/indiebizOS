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


@pytest.mark.parametrize("scope,has_artifact,active", [
    ("local", False, False), ("research", False, False),
    ("local", True, False), ("local", False, True),
])
def test_repair_targets_are_delivered_in_all_execution_paths(supervisor, scope, has_artifact, active):
    from supervisor_handoff import repair_execution
    provider = SimpleNamespace(system_prompt="기존 규칙", tools=[], _last_prompt_usage={})
    supervisor.runner.ai._provider = provider
    supervisor.store.put_response("첫 원문\n\n둘째 원문")
    expected = [dict(b) for b in supervisor.store.blocks]
    supervisor.content_artifacts = [{"path": "existing-artifact"}] if has_artifact else []
    if active:
        supervisor.active["running"] = {}
    decision = {"repair_scope": scope, "repair_block_ids": ["0", "missing", "1", "0", None]}
    with repair_execution(supervisor, decision, ["history"]) as (ai, history, packet):
        assert packet["target_blocks"] == {"version": packet["response"]["version"], "blocks": expected}
        assert not supervisor.store.coverage  # 입력을 구성한 일을 모델 열람으로 기록하지 않는다.
        assert (ai is supervisor.runner.ai) == (scope == "research" or has_artifact or active)


def test_handoff_target_snapshot_cannot_patch_a_newer_response(supervisor):
    from supervisor_handoff import handoff_state
    supervisor.store.put_response("옛 본문")
    packet = handoff_state(supervisor, {"repair_block_ids": ["0"]})
    block = packet["target_blocks"]["blocks"][0]
    supervisor.store.patch(1, [{"id": block["id"], "hash": block["hash"], "text": "새 본문"}])
    assert block["text"] == "옛 본문" and packet["target_blocks"]["version"] == 1
    with pytest.raises(ValueError, match="버전"):
        supervisor.store.patch(packet["target_blocks"]["version"], [
            {"id": block["id"], "hash": block["hash"], "text": "늦은 수정"}])
    assert supervisor.store.text == "새 본문"


def test_bounded_targets_preserve_whole_blocks_and_recover_omissions(supervisor):
    from supervisor_handoff import handoff_state, bounded_handoff
    supervisor.config["repair_context_chars"] = 5000
    supervisor.store.put_response("\n\n".join(f"단락 {i}: " + "원문" * 600 for i in range(8)))
    state = handoff_state(supervisor, {"repair_block_ids": [b["id"] for b in supervisor.store.blocks]})
    packet = bounded_handoff(supervisor, state)
    assert len(json.dumps(packet, ensure_ascii=False)) <= 5000
    page = packet["target_blocks"]
    assert 0 < len(page["blocks"]) < len(state["target_blocks"]["blocks"])
    assert page["blocks"] == state["target_blocks"]["blocks"][:len(page["blocks"])]
    assert page["version"] == state["response"]["version"]
    assert page["omitted_blocks"] == len(state["target_blocks"]["blocks"]) - len(page["blocks"])
    recovered = json.loads(supervisor.store.read_evidence(page["evidence"]["id"], 0, None)["text"])
    assert recovered == state["target_blocks"]
    assert not supervisor.store.coverage


def test_background_compaction_keeps_small_repair_targets_inline(supervisor):
    from supervisor_handoff import handoff_state, bounded_handoff
    supervisor.store.put_response("고칠 본문")
    state = handoff_state(supervisor, {"repair_block_ids": ["0"], "reason": "근거" * 20000})
    packet = bounded_handoff(supervisor, state)
    assert packet["target_blocks"] == state["target_blocks"]
    assert len(json.dumps(packet, ensure_ascii=False)) <= supervisor.config["repair_context_chars"]


@pytest.mark.parametrize("scope", ["local", "research"])
def test_executor_can_apply_the_prompt_batch_example_without_response_reads(supervisor, monkeypatch, scope):
    from supervision_store import digest
    supervisor.runner.ai._provider = SimpleNamespace(system_prompt="실행 규칙", tools=[], _last_prompt_usage={})
    evaluations, packets = [], []

    def evaluate(prompt, **kwargs):
        evaluations.append(prompt)
        if len(evaluations) == 1:
            return ('NOT_ACHIEVED\nSEVERITY: 1\nREPAIR_SCOPE: ' + scope
                    + '\nREPAIR_BLOCK_IDS: ["0", "1"]\nDEFECTS: [{"criterion_id":"C1","evidence":"시간과 영업 확정이 확보한 근거와 다름","repair":"두 문단을 수정하라"}]')
        assert "체류 80분" in prompt and "영업 여부 미확인" in prompt and "수정 문구" in prompt
        return "ACHIEVED"

    def repair(prompt, **kwargs):
        packet = json.loads(prompt.split("작업 인계=", 1)[1])
        packets.append(packet)
        page = packet["target_blocks"]
        batch = json.loads(next(line for line in prompt.splitlines() if line.startswith('{"op": "patch"')))
        batch["version"] = page["version"]
        assert len(batch["patches"]) == len(page["blocks"]) == 2
        for patch, block in zip(batch["patches"], page["blocks"]):
            assert block["hash"] == digest(block["text"])
            patch.update(id=block["id"], hash=block["hash"])
        result = json.loads(supervisor.tool(batch))
        assert result["success"], result
        assert result["result"]["version"] == page["version"] + 1
        yield {"type": "final", "content": "PATCH_DONE"}

    supervisor.runner.ai.process_message_stream = repair
    monkeypatch.setattr("consciousness_agent.system_ai_call", evaluate)
    result = finish(supervisor, "체류 100분, 영업 확정\n\n기존 문구")[-1]["content"]
    assert result == "체류 80분, 영업 여부 미확인\n\n수정 문구"
    assert len(evaluations) == 2 and len(packets) == 1
    events = [json.loads(line) for line in (supervisor.store.directory / "events.jsonl").read_text().splitlines()]
    assert [e["operation"] for e in events if e["kind"] == "response.operation"] == ["patch"]


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
        return 'NOT_ACHIEVED\nSEVERITY: 1\nREPAIR_SCOPE: local\nREPAIR_BLOCK_IDS: ["0"]\nDEFECTS: [{"criterion_id":"C1","evidence":"핵심 근거 미반영","repair":"근거를 반영하라"}]'

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
    supervisor.original_pursuit = {"id": "goal", "goal_criteria": "정정 전 목표"}
    binding = SimpleNamespace(row={"id": "goal", "version": 3, "goal_criteria": "전체 보고서 세 편 완성"},
                              write=lambda *a, **kw: writes.append((a, kw)))
    supervisor.request_done(binding, "모두 완성")
    monkeypatch.setattr("pursuit_bind.resolve_session", lambda *a: binding)

    def evaluate(prompt, **kwargs):
        assert "전체 보고서 세 편 완성" in prompt and not writes
        contract = json.loads(prompt.split("## 달성 기준\n", 1)[1].split("\n\n", 1)[0])
        assert any(row["text"] == "전체 보고서 세 편 완성" for row in contract["criteria"])
        assert all(row["text"] != "정정 전 목표" for row in contract["criteria"])
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



@pytest.mark.parametrize("feedback", [
    'NOT_ACHIEVED\nSEVERITY: 2\n더 깊게 조사하라',
    'NOT_ACHIEVED\nDEFECTS: [{"criterion_id":"C99","evidence":"더 할 수 있다","repair":"추가 조사"}]',
    'NOT_ACHIEVED\nDEFECTS: [{"criterion_id":"C1","evidence":"","repair":"추가 조사"}]',
    'NOT_ACHIEVED\nDEFECTS: []',
])
def test_unlinked_feedback_never_launches_repair(supervisor, monkeypatch, feedback):
    calls = []
    monkeypatch.setattr("consciousness_agent.system_ai_call", lambda *a, **kw: calls.append(1) or feedback)
    supervisor.runner.ai.process_message_stream = lambda *a, **kw: pytest.fail("기준 없는 재작업")
    result = finish(supervisor, "기존 응답")[-1]["content"]
    assert result.startswith("기존 응답") and len(calls) == 1
    assert tc.get_goal_eval_outcome()["status"] == "UNKNOWN"


def test_eval_input_does_not_promote_planning_advice_to_requirements(supervisor, monkeypatch):
    supervisor.configure({"task_framing": "깊이 더 조사하라", "achievement_criteria": "입력 가격 두 개를 비교",
                          "capability_focus": {"highlight_actions": ["추천도구"], "hint": "일곱 곳 검색"}})
    def evaluate(prompt, **kwargs):
        assert "입력 가격 두 개를 비교" in prompt and '"id": "C1"' in prompt
        assert "깊이 더 조사하라" not in prompt and "추천도구" not in prompt and "일곱 곳 검색" not in prompt
        assert "<system_structure>" not in kwargs["system_prompt"]
        return "ACHIEVED"
    monkeypatch.setattr("consciousness_agent.system_ai_call", evaluate)
    assert finish(supervisor, "첫 가격이 두 번째보다 낮습니다")[-1]["content"] == "첫 가격이 두 번째보다 낮습니다"


def test_request_criteria_conflict_is_deferred_not_learned_as_success(supervisor, monkeypatch):
    supervisor.message = '제주 유입 정책이 지속되는 이유를 설명해줘'
    supervisor.configure({'task_framing': '무관한 과제 범위',
                          'achievement_criteria': '과제 범위 밖이므로 답하지 않는다'})
    def evaluate(prompt, **kwargs):
        assert supervisor.message in prompt
        assert '기준이 현재 사용자 요청과 명백히 충돌하면 UNKNOWN' in kwargs['system_prompt']
        return 'UNKNOWN\nC1은 원문 설명 요청을 무관한 과제 범위로 거부하게 만들어 충돌한다.'
    monkeypatch.setattr('consciousness_agent.system_ai_call', evaluate)
    supervisor.runner.ai.process_message_stream = lambda *a, **kw: pytest.fail('새 목표로 자동 재작업')
    finish(supervisor, '범위 밖이라 답하지 않았습니다')
    status = json.loads((supervisor.store.directory / 'review_status.json').read_text())
    assert status['status'] == 'UNKNOWN' and status['learning'] == 'deferred'


def test_criteria_are_fixed_across_repair_and_handoff(supervisor):
    from final_evaluator import prepare
    from supervisor_handoff import handoff_state
    supervisor.store.put_response("초안")
    original = prepare(supervisor)["criteria"]
    supervisor.framing["achievement_criteria"] = "나중에 추가한 목표"
    block = supervisor.store.blocks[0]
    supervisor.store.patch(supervisor.store.version, [{"id": block["id"], "hash": block["hash"], "text": "수정본"}])
    assert prepare(supervisor)["criteria"] == original
    assert json.dumps(handoff_state(supervisor, {})["criteria"], ensure_ascii=False) == original


def test_arithmetic_observation_does_not_override_criterion_approval(supervisor, monkeypatch):
    import quantity_checks
    calls = []
    monkeypatch.setattr(quantity_checks, "arithmetic_issues", lambda _: [{"issue": "별도 시간 합산"}])
    monkeypatch.setattr("consciousness_agent.system_ai_call", lambda *a, **kw: calls.append(1) or "ACHIEVED")
    supervisor.runner.ai.process_message_stream = lambda *a, **kw: pytest.fail("기준 외 자동 재작업")
    assert finish(supervisor, "기준을 충족한 응답")[-1]["content"] == "기준을 충족한 응답"
    assert len(calls) == 1


def test_empty_criteria_have_no_evaluation_or_pending_delivery(supervisor, tmp_path, monkeypatch):
    target, artifact, sent = stage(supervisor, tmp_path, monkeypatch)
    # 실행 중 의식이 최종 평가 기준을 거둬도 앞서 등록된 전달을 방치하지 않는다.
    supervisor.framing = {"task_framing": "단순 확인", "achievement_criteria": ""}
    tc.clear_goal_eval_outcome()
    monkeypatch.setattr("final_evaluator.invoke", lambda *a, **kw: pytest.fail("기준 없는 평가"))
    assert finish(supervisor, "확인 완료")[-1]["content"] == "확인 완료"
    assert target.read_text() == "new reviewed bytes" and len(sent) == 1
    assert tc.get_goal_eval_outcome() is None
    assert not (supervisor.store.directory / "review_status.json").exists()


def test_tool_metadata_cannot_supply_missing_consciousness_criteria():
    from cognitive_eval import CognitiveEvalMixin
    marker = "[ACHIEVEMENT_CRITERIA:self:write]내용 검수[/ACHIEVEMENT_CRITERIA]"
    assert CognitiveEvalMixin()._extract_achievement_criteria({}, marker) is None


def test_unlinked_free_prose_is_not_passed_as_repair_instructions(supervisor, monkeypatch):
    from final_evaluator import invoke, prepare
    supervisor.store.put_response("보고서")
    prepare(supervisor)
    feedback = ('NOT_ACHIEVED\nSEVERITY: 2\nREPAIR_SCOPE: local\n'
                'DEFECTS: [{"criterion_id":"C1","evidence":"원문 수치와 다름","repair":"원문 수치로 수정"}]'
                '\n추가로 미래 전망도 조사하라')
    monkeypatch.setattr("consciousness_agent.system_ai_call", lambda *a, **kw: feedback)
    decision = json.loads(invoke(supervisor))
    assert decision["status"] == "REWORK"
    assert "원문 수치로 수정" in decision["instruction"] and "미래 전망" not in decision["instruction"]

if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
