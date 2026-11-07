"""최종 결과 비교는 한 번으로 끝나며 사용자 목표·공개·기억 계약을 보존한다."""
import json
from types import SimpleNamespace

import pytest
import boot_paths  # noqa: F401
import thread_context as tc
from consciousness_agent import system_ai_call as real_system_ai_call
from final_evaluator import execution_trace
from test_conscious_supervisor import supervisor, finish  # noqa: F401
from test_supervision_delivery import prepare as stage




def test_only_explicit_submissions_receive_submission_priority(supervisor, tmp_path):
    from final_evaluator import prepare
    report, source = tmp_path / 'report.md', tmp_path / 'source.json'
    report.write_text('최종 보고서')
    source.write_text('{"text":"수집 원문"}')
    supervisor.store.put_response(f'보고서: {report}')
    packet = prepare(supervisor, [{'name': 'Write', 'input': {'path': str(report)}, 'result': 'saved'},
                                  {'name': 'Read', 'input': {'path': str(source)}, 'result': source.read_text()}])
    roles = {r['subject']: r['role'] for r in packet['attachments']}
    assert roles[str(report)] == 'submission'
    assert str(source) not in roles


@pytest.mark.parametrize('feedback', [
    'UNKNOWN\nUNKNOWN_REASON: blocked\n현재 요청은 공개 전 승인을 기다리라는 내용입니다.',
    'UNKNOWN\nUNKNOWN_REASON: blocked\n별도 승인이 필요합니다.',
])
def test_authority_judgment_is_not_rewritten_by_keyword_or_receipt_format(supervisor, monkeypatch, feedback):
    from final_evaluator import prepare, invoke
    supervisor.store.put_response('현재 상태를 보고합니다.')
    prepare(supervisor, [])
    monkeypatch.setattr('final_evaluator.Evaluator._evaluate_achievement',
                        lambda *a, **kw: (None, feedback, 0))
    result = json.loads(invoke(supervisor))
    assert result['status'] == 'UNKNOWN' and result['reason'] == feedback
    assert not result['instruction']


def test_prior_user_limit_can_ground_authority_stop(supervisor, monkeypatch):
    from final_evaluator import prepare, invoke
    supervisor.message = '계속해'
    supervisor.history = [{'role': 'user', 'content': '업데이트하되 재기동 전에는 물어봐'}]
    supervisor.store.put_response('재기동에는 사용자 승인이 필요합니다.')
    prepare(supervisor, [])
    feedback = ('UNKNOWN\nUNKNOWN_REASON: blocked\nBLOCKER_KIND: authority\n'
                'AUTHORITY_EVIDENCE: {"id":"user_history:0","quote":"재기동 전에는 물어봐"}')
    monkeypatch.setattr('final_evaluator.Evaluator._evaluate_achievement', lambda *a, **kw: (None, feedback, None))
    result = json.loads(invoke(supervisor))
    assert result['status'] == 'UNKNOWN' and not result.get('recoverable')






def test_unicode_execution_source_is_not_final_result(supervisor, monkeypatch):
    source = "PDF 원문 앞\u2028가운데\u2029끝\u0085다음"
    supervisor.run_tool("read", {"query": source}, lambda: source)
    evaluated = []

    def evaluate(prompt, **kwargs):
        evaluated.append(prompt)
        assert source not in prompt
        return "ACHIEVED"

    monkeypatch.setattr("consciousness_agent.system_ai_call", evaluate)
    result = finish(supervisor, "원문을 확인했습니다.")
    assert len(evaluated) == 1
    decisions = [e for e in supervisor.store.read_events(limit=100000)["events"]
                 if e["kind"] == "decision"]
    assert decisions[-1]["decision"]["status"] == "APPROVED"
    assert result[-1]["content"] == "원문을 확인했습니다."


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
            assert "실제 실행된 액션 원장" not in kwargs["message"]
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




def test_staged_body_and_notice_are_supplied_before_publication(supervisor, tmp_path, monkeypatch):
    target, artifact, sent = stage(supervisor, tmp_path, monkeypatch)

    def evaluate(prompt, **kwargs):
        assert "new reviewed bytes" in prompt and "14 tips" in prompt
        assert target.read_text() == "old" and not sent
        return "ACHIEVED"

    monkeypatch.setattr("consciousness_agent.system_ai_call", evaluate)
    finish(supervisor, f"보고서: {target}")
    assert target.read_text() == "new reviewed bytes" and len(sent) == 1


def test_internal_repair_criteria_do_not_replace_user_goal(supervisor, monkeypatch):
    supervisor._final_criteria_contract = {"criteria": [
        {"id": "C1", "text": "전체 보고서 세 편 완성", "source": "user"}]}

    def evaluate(prompt, **kwargs):
        assert supervisor.message in prompt
        assert "전체 보고서 세 편 완성" not in prompt
        return 'ACHIEVED\nGOAL_OUTCOME: {"status":"ACHIEVED","reason":"세 편의 원문 확인","evidence":["보고서 세 편"],"remaining":[]}'

    monkeypatch.setattr("consciousness_agent.system_ai_call", evaluate)
    finish(supervisor, "세 편의 결과")
    assert tc.get_goal_eval_outcome()["goal_status"] == "ACHIEVED"


def test_changed_code_file_cannot_be_approved_with_old_snapshot(supervisor, tmp_path, monkeypatch):
    path = tmp_path / "made.py"
    path.write_text("print('원래 코드')")
    supervisor.run_tool("Write", {"path": str(path)}, lambda: "saved")

    def evaluate(prompt, **kwargs):
        assert "print('원래 코드')" in prompt
        path.write_text("print('교체된 코드')")
        return "ACHIEVED"

    monkeypatch.setattr("consciousness_agent.system_ai_call", evaluate)
    result = finish(supervisor, str(path))[-1]["content"]
    assert result == str(path)
    assert "산출물이 변경" in tc.get_goal_eval_outcome()["reason"]
    assert tc.get_goal_eval_outcome()["status"] == "UNKNOWN"


def test_episode_summary_uses_delivered_verdict_not_earlier_success():
    from episode_logger import _final_evaluation_result
    assert _final_evaluation_result("[GoalEval] 평가 응답: ACHIEVED\n[GoalEval] 최종 판정: UNKNOWN") == "UNKNOWN"


def test_unknown_reason_mentioning_achieved_does_not_trigger_approval(supervisor, monkeypatch):
    monkeypatch.setattr("consciousness_agent.system_ai_call", lambda *a, **kw:
                        "UNKNOWN\n필수 출처가 없어 ACHIEVED라고 판단할 수 없습니다.")
    result = finish(supervisor, "출처 없는 답변")[-1]["content"]
    assert result == "출처 없는 답변" and tc.get_goal_eval_outcome()["status"] == "UNKNOWN"


def test_tool_capable_supervisor_rejects_final_phase(supervisor):
    from supervisor_runtime import invoke
    with pytest.raises(ValueError, match="도구 없는"):
        invoke(supervisor, "평가", phase="final")





def test_eval_input_does_not_promote_planning_advice_to_requirements(supervisor, monkeypatch):
    supervisor.configure({"independent_review": True, "task_framing": "깊이 더 조사하라", "achievement_criteria": "입력 가격 두 개를 비교",
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
    supervisor.configure({'independent_review': True, 'task_framing': '무관한 과제 범위',
                          'achievement_criteria': '과제 범위 밖이므로 답하지 않는다'})
    def evaluate(prompt, **kwargs):
        assert supervisor.message in prompt
        assert '기준이 현재 사용자 요청과 명백히 충돌하면 UNKNOWN' in kwargs['system_prompt']
        return 'UNKNOWN\nC1은 원문 설명 요청을 무관한 과제 범위로 거부하게 만들어 충돌한다.'
    monkeypatch.setattr('consciousness_agent.system_ai_call', evaluate)
    supervisor.runner.ai.process_message_stream = lambda *a, **kw: pytest.fail('새 목표로 자동 재작업')
    finish(supervisor, '범위 밖이라 답하지 않았습니다')
    status = json.loads((supervisor.store.directory / 'review_status.json').read_text())
    assert status['status'] == 'UNKNOWN' and status['learning'] == 'components_only'


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
    assert tc.get_goal_eval_outcome()["review_status"] == "NOT_RUN"
    assert not (supervisor.store.directory / "review_status.json").exists()


def test_tool_metadata_cannot_supply_missing_consciousness_criteria():
    from cognitive_eval import CognitiveEvalMixin
    marker = "[ACHIEVEMENT_CRITERIA:self:write]내용 검수[/ACHIEVEMENT_CRITERIA]"
    assert CognitiveEvalMixin()._extract_achievement_criteria({}, marker) is None



@pytest.mark.parametrize('goal', ['ACHIEVED', 'NOT_ACHIEVED'])
def test_approved_response_preserves_independent_goal_to_final_store(supervisor, monkeypatch, goal):
    def evaluate(prompt, **kwargs):
        return 'ACHIEVED\nGOAL_OUTCOME: ' + json.dumps({'status': goal, 'reason': '실제 결과',
            'evidence': ['tool:1'], 'remaining': ['남은 작업'] if goal == 'NOT_ACHIEVED' else []})
    monkeypatch.setattr('consciousness_agent.system_ai_call', evaluate)
    assert finish(supervisor, '관측한 결과입니다')[-1]['content'] == '관측한 결과입니다'
    outcome = tc.get_goal_eval_outcome()
    assert outcome['review_status'] == 'APPROVED' and outcome['goal_status'] == goal
    stored = json.loads((supervisor.store.directory / 'review_status.json').read_text())
    assert stored['goal_status'] == goal and stored['goal_evidence'] == ['tool:1']


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))


def test_mcp_defaults_merge_without_collapsing_real_retries(supervisor):
    native = []
    for result in ('원천 실패', '저장 후 검증 성공'):
        payload = {'code': 'return $x', 'edition': 2, 'inputs': {'x': 3}}
        key = supervisor._start('execute_ibl', payload)
        supervisor._finish(key, result, error=result == '원천 실패')
        native.append({'name': 'mcp__indiebizos__execute_ibl',
                       'input': {'code': 'return $x', 'project_path': '.',
                                 'inputs': {'x': 3}, 'check': False, 'resume': None},
                       'result': '표시 사본'})
    calls = execution_trace(supervisor, native)
    assert len(calls) == 2
    assert [c['result'] for c in calls] == ['원천 실패', '저장 후 검증 성공']
    assert [c['is_error'] for c in calls] == [True, False]


@pytest.mark.parametrize('changed', [
    {'inputs': {'x': 4}}, {'edition': 1}, {'check': True},
    {'reuse': {'run_id': 'other'}}, {'budget': {'steps': 2000}},
])
def test_trace_merge_keeps_semantically_different_requests(supervisor, changed):
    payload = {'code': 'return $x', 'edition': 2, 'inputs': {'x': 3}}
    key = supervisor._start('execute_ibl', payload)
    supervisor._finish(key, 'stored result')
    calls = execution_trace(supervisor, [{'name': 'execute_ibl',
                                         'input': {**payload, **changed}, 'result': 'other result'}])
    assert len(calls) == 2


def test_other_mcp_server_is_not_the_same_tool(supervisor):
    key = supervisor._start('execute_ibl', {'code': 'return 1'})
    supervisor._finish(key, 'local')
    calls = execution_trace(supervisor, [{'name': 'mcp__other__execute_ibl',
                                         'input': {'code': 'return 1'}, 'result': 'remote'}])
    assert len(calls) == 2


def test_parallel_same_requests_match_result_references_not_completion_order(supervisor):
    payload = {'code': 'return 1', 'edition': 2}
    first = supervisor._start('execute_ibl', payload)
    second = supervisor._start('execute_ibl', payload)
    for key, ref in ((second, 'second'), (first, 'first')):
        supervisor._finish(key, json.dumps({'result_ref': {'id': ref}, 'full': ref}))
    native = [{'name': 'execute_ibl', 'input': {**payload, 'project_path': '.'},
               'result': json.dumps({'result_ref': {'id': ref}})} for ref in ('first', 'second')]
    calls = execution_trace(supervisor, native)
    assert len(calls) == 2
    assert [json.loads(c['result'])['full'] for c in calls] == ['first', 'second']


@pytest.mark.parametrize('verified', [True, False])
def test_final_model_receives_terminal_verification_without_forced_approval(supervisor, monkeypatch, verified):
    for i in range(10):
        key = supervisor._start('execute_ibl', {'code': f'return {i}'})
        supervisor._finish(key, json.dumps({'success': True, 'value': {'large': 'x' * 4000}}))
    key = supervisor._start('execute_ibl', {'code': 'return $validation'})
    supervisor._finish(key, json.dumps({'success': True, 'value': {'verified': verified, 'rows': 320}}))
    prompts = []
    def evaluate(prompt, **kwargs):
        prompts.append(prompt)
        assert '"verified": ' + str(verified).lower() in prompt
        assert '"rows": 320' in prompt
        assert '총 11회' in prompt
        return 'UNKNOWN\n다른 필수 조건의 증거가 아직 없습니다.'
    monkeypatch.setattr('consciousness_agent.system_ai_call', evaluate)
    finish(supervisor, '검증 결과를 확인해 주세요')
    assert len(prompts) == 1
    assert tc.get_goal_eval_outcome()['status'] == 'UNKNOWN'


def test_rejected_malformed_native_input_does_not_break_evaluation(supervisor):
    calls = execution_trace(supervisor, [{'name': 'execute_ibl', 'input': {'code': 123},
                                         'result': 'invalid code type', 'is_error': True}])
    assert len(calls) == 1 and calls[0]['is_error']


@pytest.mark.parametrize('matched', [True, False])
def test_first_evaluation_receives_round17_checks_without_repair(supervisor, monkeypatch, matched):
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / 'docs/experiments/long_sentence_imagination/round_17/harness/evaluation_gap.json'
    receipt = json.loads(path.read_text())['before_evaluation_result']
    receipt['value']['verification']['exact_content_match'] = matched
    for i in range(9):
        key = supervisor._start('execute_ibl', {'code': f'return {i}'})
        supervisor._finish(key, json.dumps({'success': True, 'value': {'large': 'x' * 6000}}))
    key = supervisor._start('execute_ibl', {'code': 'return $receipt'})
    supervisor._finish(key, json.dumps(receipt))
    prompts = []
    def evaluate(prompt, **kwargs):
        prompts.append(prompt)
        assert '"saved_files_read_back": 3' in prompt
        assert '"exact_content_match": ' + str(matched).lower() in prompt
        assert '"W_overlaps_unchanged": true' in prompt
        return 'UNKNOWN\n다른 조건은 미검증입니다.'
    monkeypatch.setattr('consciousness_agent.system_ai_call', evaluate)
    finish(supervisor, '저장 검증을 확인해 주세요')
    assert len(prompts) == 1
    assert tc.get_goal_eval_outcome()['status'] == 'UNKNOWN'


def test_computed_written_artifacts_reach_first_evaluation(supervisor, tmp_path):
    from final_evaluator import prepare, snapshot_error
    report = tmp_path / '분석 보고.md'
    evidence = tmp_path / '근거.json'
    source = tmp_path / '원문.txt'
    report.write_text('첫 문단\n' + '중간 내용\n' * 1100 + '적용할 수 없는 부분: 원문에 명시', encoding='utf-8')
    evidence.write_text(json.dumps({'unconfirmed': '원문에서 확인 불가'}, ensure_ascii=False), encoding='utf-8')
    source.write_text('읽은 원문은 결과물로 첨부하지 않는다', encoding='utf-8')
    raw = supervisor.store.evidence(json.dumps({'evidence': [
        {'kind': 'invoke', 'action': 'self:write', 'targets': {'path': str(report)}},
        {'kind': 'invoke', 'action': 'self:write', 'targets': {'path': str(evidence)}},
        {'kind': 'invoke', 'action': 'self:read', 'targets': {'path': str(source)}}]}))
    key = supervisor._start('execute_ibl', {'code': '[self:write]{path:$out+"/근거.json",content:$data}'})
    supervisor._finish(key, json.dumps({'edition': 2, 'executed': True, 'result_ref': raw}))
    supervisor.store.put_response(f'[보고서](<{report}>) [근거표](<{evidence}>)')
    packet = prepare(supervisor)
    snapshot = supervisor._evaluation_snapshot
    assert report.read_text() in packet['files']
    assert evidence.read_text() in packet['files']
    assert source.read_text() not in packet['files']
    assert set(snapshot['files']) == {str(report), str(evidence)}
    assert packet['files'].count(report.read_text()) == 1
    evidence.write_text('{}')
    assert snapshot_error(supervisor)


def test_masked_secret_in_artifact_is_not_a_change_during_evaluation(supervisor, tmp_path):
    """증거 마스킹(****)은 디스크 원문을 바꾸지 않는다. 지문이 가려진 본문 기준이면 마스킹이 닿은
    산출물은 평가 뒤 늘 '변경'으로 오판돼 판정이 비워진다(ep5045·5518 AI 동향 보고서 URL)."""
    from final_evaluator import prepare, snapshot_error
    report = tmp_path / '보고.md'
    secret = 'sk-' + 'aB3xY7zQ1wK9m2Lt4Rn8' * 2
    report.write_text('## 출처\n- 키 노출 사례: ' + secret + '\n', encoding='utf-8')
    raw = supervisor.store.evidence(json.dumps({'evidence': [
        {'kind': 'invoke', 'action': 'self:write', 'targets': {'path': str(report)}}]}))
    key = supervisor._start('execute_ibl', {'code': '[self:write]{path:$out+"/보고.md",content:$data}'})
    supervisor._finish(key, json.dumps({'edition': 2, 'executed': True, 'result_ref': raw}))
    supervisor.store.put_response(f'[보고서]({report})')
    packet = prepare(supervisor)
    assert secret not in packet['files'] and '****' in packet['files']
    assert snapshot_error(supervisor) is None
    report.write_text('바뀜', encoding='utf-8')
    assert snapshot_error(supervisor)


def test_final_evaluation_uses_goal_policy(supervisor, monkeypatch):
    from final_evaluator import invoke, prepare, FINAL_POLICY
    prepare(supervisor)
    assert supervisor._evaluation_packet['response'] == ''
    contract = supervisor._evaluation_packet['criteria']
    calls = []

    def evaluate(prompt, **kwargs):
        calls.append((prompt, kwargs))
        assert contract not in prompt and supervisor.message in prompt
        policy = kwargs['system_prompt']
        assert FINAL_POLICY in policy
        return 'ACHIEVED\nWORKSPACE_COVERAGE: [{"criterion_id":"C1","status":"passed","evidence_ids":["test-1"]}]'

    monkeypatch.setattr('consciousness_agent.system_ai_call', evaluate)
    decision = json.loads(invoke(supervisor))
    assert decision['status'] == 'APPROVED'
    assert len(calls) == 1  # 단계 구분에 새 감독/평가 호출이 필요하지 않다.
    assert supervisor._evaluation_packet['criteria'] == contract


def test_final_evaluation_rejects_missing_documentation(supervisor, monkeypatch):
    from final_evaluator import invoke, prepare
    prepare(supervisor)
    feedback = ('NOT_ACHIEVED\nSEVERITY: 2\nREPAIR_SCOPE: local\n'
                'DEFECTS: [{"criterion_id":"C1","evidence":"사본 문서에 필수 설치 안내 누락",'
                '"repair":"설치 안내를 문서에 추가"}]')
    monkeypatch.setattr('consciousness_agent.system_ai_call', lambda *a, **kw: feedback)
    decision = json.loads(invoke(supervisor))
    assert decision['status'] == 'REWORK'
    assert '필수 설치 안내 누락' in decision['reason'] and not decision['instruction']


def test_saved_completion_review_cannot_take_receipt_shortcut(supervisor, monkeypatch):
    from repair_continuation import resuming
    row = {"completion_review_required": True,
           "criteria_contract": {"criteria": [{"id": "C1", "text": "보존된 전체 기준"}]}}
    with resuming(row):
        supervisor.configure({"task_framing": "재개", "achievement_criteria": "보존된 전체 기준",
                              "_framing_source": "repair_continuation"}, repair=True)
    assert supervisor.completion_review_required
    monkeypatch.setattr("repair_policy.enabled", lambda _: True)
    monkeypatch.setattr("repair_policy.finalize", lambda *a: pytest.fail("전체 검수 생략"))
    monkeypatch.setattr("repair_readiness.completion_error", lambda _: None)
    seen = []
    def evaluate(prompt, **kwargs):
        seen.append(prompt)
        return "ACHIEVED"
    monkeypatch.setattr("consciousness_agent.system_ai_call", evaluate)
    finish(supervisor, "검증한 결과")
    assert len(seen) == 1 and "보존된 전체 기준" not in seen[0] and supervisor.message in seen[0]


@pytest.mark.parametrize('outcome', ['ACHIEVED', 'UNKNOWN'])
@pytest.mark.parametrize('independent_review', [False, True])
def test_definition_only_repair_leaves_review_to_ai_choice(supervisor, monkeypatch, outcome, independent_review):
    from function_library import register
    from thread_context import repair_workspace_scope
    supervisor.configure({'_repair_policy': 2, 'task_framing': '관용구 개정',
                          'independent_review': independent_review,
                          'achievement_criteria': '등록된 함수가 새 결과를 반환한다'}, repair=True)
    monkeypatch.setattr('repair_policy.finalize', lambda *a: pytest.fail('코드 없는 변경에 적용 영수증 요구'))
    with repair_workspace_scope(str(supervisor.store.directory / 'unused-code-workspace')):
        register('revised', '#!ibl edition=2\n[def:revised](){return 2}')
    seen = []
    def evaluate(prompt, **kwargs):
        seen.append(prompt)
        return outcome + "\nGOAL_OUTCOME: " + json.dumps({
            "status": outcome, "reason": "실제 결과 검증", "evidence": ["함수 개정"], "remaining": []})
    monkeypatch.setattr('consciousness_agent.system_ai_call', evaluate)
    finish(supervisor, '개정 결과')
    assert len(seen) == int(independent_review)
    if independent_review:
        assert '등록된 함수가 새 결과를 반환한다' not in seen[0] and supervisor.message in seen[0]
        assert tc.get_goal_eval_outcome()['goal_status'] == outcome
    else:
        assert tc.get_goal_eval_outcome()['review_status'] == 'NOT_RUN'




def test_explicit_final_paths_submit_existing_files_without_creation_receipt(supervisor, tmp_path):
    from final_evaluator import prepare
    plan, report = tmp_path / 'plan.md', tmp_path / 'report.md'
    plan.write_text('기존 계획의 인용 [자료:old:p70]')
    report.write_text('다시 제출하는 기존 보고서')
    supervisor.store.put_response(f'참고 계획: {plan}\n보고서: {report}')
    packet = prepare(supervisor, [{'name': 'artifact', 'result': {'path': str(report), 'role': 'submission'}}])
    assert plan.read_text() in packet['files']
    assert report.read_text() in packet['files']
    assert str(plan) in supervisor._evaluation_snapshot['files']




def test_unused_question_and_read_additions_do_not_invalidate_selected_inputs(supervisor, tmp_path):
    import research_capture
    from research_context import scope, review_state
    from research_store import ResearchStore
    from research_questions import ResearchQuestions
    from research_library import ResearchLibrary
    store = ResearchStore(tmp_path, 'input-dependencies')
    tid = store.create_thread('연구')['id']
    ctx = {'project_uid': store.uid, 'thread_id': tid, 'run_id': 'r', 'epoch': store.epoch, 'path': str(tmp_path)}
    with scope(ctx):
        questions = ResearchQuestions(store, tid)
        rows = questions.apply([{'expected_revision': 0, 'text': f'질문 {i}', 'scope': '문맥' * 100}
                                for i in range(20)])['items']
        result = research_capture.review(ctx, '', query=rows[0]['question_id'], full_receipts=True)
        deps = result['dependencies']
        unused = next(q for q in rows if q['question_id'] not in deps['questions'])
        questions.apply([{'question_id': unused['question_id'], 'expected_revision': 1, 'scope': '무관한 수정'}])
        lib = ResearchLibrary(store, tid)
        ref = lib.capture('새 읽기 행', title='추가 근거')
        lib.read(ref['version_ref'])
        assert review_state(deps) == result['state_revision']
        used = next(q for q in rows if q['question_id'] in deps['questions'])
        questions.apply([{'question_id': used['question_id'], 'expected_revision': 1, 'scope': '관련 수정'}])
        assert review_state(deps) != result['state_revision']




@pytest.mark.parametrize('status', ['ACHIEVED', 'NOT_ACHIEVED', 'UNKNOWN'])
def test_final_comparison_never_reopens_execution_or_evidence(supervisor, monkeypatch, status):
    calls = []
    def evaluate(prompt, **kwargs):
        calls.append(prompt)
        assert supervisor.message in prompt and '최종 결과' in prompt
        return status + '\nUNKNOWN_REASON: evidence\nREPAIR_SCOPE: research\nEVIDENCE_REQUESTS: [{"start":0,"end":24000}]'
    monkeypatch.setattr('consciousness_agent.system_ai_call', evaluate)
    monkeypatch.setattr('evaluation_input.recover', lambda *a: pytest.fail('final comparison read evidence'))
    supervisor.runner.ai.process_message_stream = lambda *a, **k: pytest.fail('final comparison restarted work')
    supervisor.config['max_repairs'] = 10
    result = finish(supervisor, '최종 결과')
    assert result[-1]['content'] == '최종 결과'
    assert tc.get_goal_eval_outcome()['status'] == status
    assert len(calls) == 1


def test_final_comparison_uses_user_goal_and_corrections_not_internal_plan(supervisor, monkeypatch):
    from final_evaluator import prepare, invoke
    supervisor.message = '보고서에서 성과와 한계를 설명해'
    supervisor.history = [{'role': 'user', 'content': '확인 안 된 것은 미확인이라고 써'},
                          {'role': 'assistant', 'content': '추가로 100개 과제를 새로 실행하겠다'}]
    supervisor.framing['achievement_criteria'] = '출처 100개를 다시 조회하라'
    supervisor.store.put_response('일반 성과 개선은 미확인이다.')
    prepare(supervisor)
    def model(prompt, **kwargs):
        assert '보고서에서 성과와 한계를 설명해' in prompt
        assert '확인 안 된 것은 미확인이라고 써' in prompt
        assert '100개' not in prompt
        assert '일반 성과 개선은 미확인이다.' in prompt
        return 'ACHIEVED'
    monkeypatch.setattr('consciousness_agent.system_ai_call', model)
    assert json.loads(invoke(supervisor))['status'] == 'APPROVED'


def test_complete_final_result_overflow_stops_before_model_without_truncation(supervisor, tmp_path, monkeypatch):
    import consciousness_agent as ca
    from final_evaluator import prepare, invoke
    from test_evaluation_input import provider
    report = tmp_path / 'report.md'
    report.write_text('최종 본문' * 20000 + '마지막 한계')
    supervisor.store.put_response(f'[최종 보고서]({report})')
    p = provider(request_limits={'chars': 20000})
    p.process_message = lambda **kw: pytest.fail('overflow called model')
    monkeypatch.setattr(ca, '_resolve_oneshot_provider', lambda role: p)
    monkeypatch.setattr(ca, 'system_ai_call', real_system_ai_call)
    packet = prepare(supervisor)
    assert report.read_text() in packet['files']
    result = json.loads(invoke(supervisor))
    assert result['status'] == 'UNKNOWN' and result['failure']['kind'] == 'input_too_large'
    assert not result.get('recoverable')


@pytest.mark.parametrize('change', ['request', 'user_history'])
def test_user_goal_change_invalidates_comparison(supervisor, monkeypatch, change):
    def model(prompt, **kwargs):
        if change == 'request':
            supervisor.message += ' 수정된 요청'
        else:
            supervisor.history.append({'role': 'user', 'content': '추가한 명시 조건'})
        return 'ACHIEVED'
    monkeypatch.setattr('consciousness_agent.system_ai_call', model)
    finish(supervisor, '최종 결과')
    assert tc.get_goal_eval_outcome()['status'] == 'UNKNOWN'
    assert '사용자 목표·정정' in tc.get_goal_eval_outcome()['reason']


def test_requested_comparison_does_not_require_generated_criteria(supervisor, monkeypatch):
    supervisor.configure({'task_framing': '요청 처리', 'independent_review': True})
    seen = []
    monkeypatch.setattr('consciousness_agent.system_ai_call', lambda prompt, **kw: seen.append(prompt) or 'ACHIEVED')
    finish(supervisor, '최종 결과')
    assert len(seen) == 1 and supervisor.message in seen[0]
