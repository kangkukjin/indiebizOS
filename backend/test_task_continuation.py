"""실패 관측에서 다음 방법 실행, 정상/취소/예산/공유 재개 경계."""
from types import SimpleNamespace as NS

import boot_paths  # noqa: F401
import pytest
import execution_turn
import task_continuation as tc
from test_capability_guard import drain
from test_conscious_supervisor import supervisor  # noqa: F401


@pytest.fixture
def turn(monkeypatch):
    monkeypatch.setattr(tc, 'record_trajectory_event', lambda *a, **kw: None)
    monkeypatch.setattr(tc, 'turn_limit_reason', lambda: None)
    monkeypatch.setattr('repair_continuation.current', lambda: None)
    binding = execution_turn.Binding(NS(), 'owner', 'task', context={}, conversation=None)
    token = execution_turn._current.set(binding)
    yield binding
    execution_turn._current.reset(token)


def run(calls, *, cancel=None, events=None, enabled=True, supervisor=None, review_pending=False):
    invocations = []
    def stream(**kwargs):
        invocations.append(kwargs)
        yield from events or [{'type': 'tool_start', 'name': 'script'},
                              {'type': 'tool_result', 'result': {'items': ['recovered']}},
                              {'type': 'final', 'content': '결과 전달'}]
    collected = []
    runner = NS(ai=NS(process_message_stream=stream))
    emitted, result = drain(tc.continue_task(runner, '자료 찾아줘', '첫 시도 실패', calls, [],
                                             collect=collected.append, cancel_check=cancel,
                                             enabled=enabled, supervisor=supervisor,
                                             review_pending=review_pending))
    return result, invocations, collected, emitted


def test_failed_tool_runs_next_method_without_negative_word_judgment(turn):
    calls = [{'name': 'search', 'input': {'query': 'x'}, 'result': {'success': False, 'error': 'parser'}}]
    result, invocations, collected, emitted = run(calls)
    assert result == '결과 전달' and len(invocations) == 1
    assert '작은 Script' in invocations[0]['message_content']
    assert [e['type'] for e in collected] == ['tool_start', 'tool_result', 'final']
    assert all(e['type'] != 'final' for e in emitted)
    assert turn.followup_reason == 'observed_failure'
    assert run(calls)[1] == []


@pytest.mark.parametrize('calls', [[], [{'result': {'items': []}}]])
def test_success_and_resolved_failures_add_no_model_call(turn, calls):
    assert run(calls)[1] == []


def test_successful_guide_does_not_erase_failed_work(turn):
    calls = [{'name': 'play', 'result': {'success': False, 'error': 'timeout'}},
             {'name': 'guide', 'result': {'items': ['diagnostic instructions']}}]
    _, invocations, _, _ = run(calls)
    assert len(invocations) == 1
    packet = __import__('json').loads(invocations[0]['message_content'].split('\n', 1)[1])
    assert packet['recovery']['incidents'][0]['origin']['name'] == 'play'
    assert not run(calls)[1]


def test_scheduled_final_review_owns_semantic_recovery_without_erasing_failures(turn):
    supervisor = NS(enabled=True, evaluation_enabled=True)
    calls = [{'name': 'check', 'is_error': True, 'result': 'focus missing'},
             {'name': 'check', 'result': 'focus restored; 30 checks passed'}]
    before = tc.recovery_view(calls, supervisor, final=True)
    assert before and tc.needs_followup(calls, supervisor=supervisor)
    assert run(calls, supervisor=supervisor, review_pending=True)[1] == []
    assert not turn.followup_reason
    assert tc.recovery_view(calls, supervisor, final=True) == before
    # 검수가 없는 다음 경계에는 여전히 미해소 사실을 넘겨야 한다.
    supervisor.observe_native = lambda event: None
    assert len(run(calls, supervisor=supervisor)[1]) == 1


@pytest.mark.parametrize('mode', ['disabled', 'no_criteria', 'receipt_completion', 'not_scheduled'])
def test_absent_semantic_review_keeps_existing_recovery(turn, monkeypatch, mode):
    supervisor = NS(enabled=mode != 'disabled', evaluation_enabled=mode != 'no_criteria',
                    observe_native=lambda event: None)
    monkeypatch.setattr('repair_policy.receipt_completion', lambda c: mode == 'receipt_completion')
    assert len(run([{'is_error': True}], supervisor=supervisor,
                   review_pending=mode != 'not_scheduled')[1]) == 1


def test_pipeline_reviews_recovered_task_without_second_execution(turn, supervisor, monkeypatch):
    from agent_pipeline import CognitivePipelineMixin
    from cognitive_consciousness import CognitiveConsciousnessMixin
    from cognitive_eval import CognitiveEvalMixin
    from test_reflex_execution import AI
    from thread_context import get_goal_eval_outcome

    class Runner(CognitivePipelineMixin, CognitiveConsciousnessMixin, CognitiveEvalMixin):
        pass

    runner = Runner()
    runner.config = {'name': 'worker'}
    runner.ai = AI([[{'type': 'tool_start', 'id': 'check1', 'name': 'check', 'input': {}},
                     {'type': 'tool_result', 'id': 'check1', 'result': 'focus missing', 'is_error': True},
                     {'type': 'tool_start', 'id': 'check2', 'name': 'check', 'input': {}},
                     {'type': 'tool_result', 'id': 'check2', 'result': 'focus restored; 30 checks passed'},
                     {'type': 'final', 'content': '초점 복구와 검사 완료'}]])
    runner._associate = lambda *a, **kw: None
    runner._decide_request_type = lambda *a, **kw: ('THINK', None)
    runner._run_consciousness_or_reuse = lambda *a, **kw: {
        'task_framing': '초점 복구', 'achievement_criteria': '초점 복구와 실제 검사', 'independent_review': True}
    runner._apply_consciousness_to_history = lambda history, co: history
    runner._refresh_execution_prompt = lambda message, *a, **kw: message
    runner._after_response_async = lambda *a, **kw: None
    supervisor.runner = runner
    monkeypatch.setattr('supervision_bus.current', lambda: supervisor)
    monkeypatch.setattr('unified_distill.capture_model', lambda *a: None)
    monkeypatch.setattr('framing_inheritance.remember', lambda *a, **kw: None)
    evaluations = []

    def evaluate(prompt, **kw):
        evaluations.append(prompt)
        assert 'recovery_incidents' in prompt and 'focus missing' in prompt
        assert 'focus restored; 30 checks passed' in prompt
        return 'ACHIEVED'

    monkeypatch.setattr('consciousness_agent.system_ai_call', evaluate)
    events = list(runner._cognitive_stream_body('초점을 복구하고 검사해줘', []))
    assert len(runner.ai.calls) == len(evaluations) == 1
    assert get_goal_eval_outcome()['status'] == 'ACHIEVED'
    assert [e['content'] for e in events if e['type'] == 'final'] == ['초점 복구와 검사 완료']
    assert supervisor.recovery.view() and not turn.followup_reason


def test_missing_return_is_not_a_mid_call_failure_but_final_boundary_preserves_it(turn):
    calls = [{'id': 'lost', 'name': 'write', 'input': {}, '_result_received': False}]
    assert not tc.needs_followup(calls)
    assert len(run(calls)[1]) == 1


def test_no_supervisor_native_followup_records_actual_recovery_calls(turn):
    from execution_situation import Situation, fingerprint
    from recovery_observation import configure
    turn.situation = Situation('owner', 'task', lambda *a, **k: None, lambda v: {'id': fingerprint(v)})
    configure(turn.situation)
    turn.situation.tool_started('a', 'play', {})
    turn.situation.tool_finished('a', 'timeout', error=True)
    events = [{'type': 'tool_start', 'id': 'diagnose', 'name': 'shell', 'input': {}},
              {'type': 'tool_result', 'id': 'diagnose', 'result': 'remote denied', 'is_error': True},
              {'type': 'final', 'content': '확인된 차단과 부분 결과'}]
    _, invocations, _, emitted = run([], events=events)
    assert len(invocations) == 1 and not any(e['type'] == 'final' for e in emitted)
    assert {r['origin']['call_id'] for r in turn.situation.recovery.view()} == {'a', 'diagnose'}


def test_cancel_budget_and_existing_handoff_stop_additional_execution(turn, monkeypatch):
    calls = [{'result': 'Error: parse failed'}]
    assert run(calls, cancel=lambda: True)[1] == []
    monkeypatch.setattr(tc, 'turn_limit_reason', lambda: 'budget')
    assert run(calls)[1] == []
    monkeypatch.setattr(tc, 'turn_limit_reason', lambda: None)
    monkeypatch.setattr('repair_continuation.current', lambda: {'phase': 'activation'})
    assert run(calls)[1] == []
    assert not turn.followup_reason


def test_capability_and_context_handoff_share_limit(turn):
    assert execution_turn.claim_followup('reflex_context')
    assert not execution_turn.claim_followup('capability_claim')
    assert run([{'is_error': True}])[1] == []


def test_evidence_retains_successful_effect_and_unknown_receipt(turn):
    calls = [{'name': 'write', 'result': {'task_ref': 'remote-1', 'success': True}},
             {'name': 'query', 'result': None, 'is_error': True}]
    _, invocations, _, _ = run(calls)
    prompt = invocations[0]['message_content']
    assert 'remote-1' in prompt and '효과가 불명확하면' in prompt


def test_long_receipts_keep_full_inputs_and_effects_in_existing_store(turn, monkeypatch):
    saved = []
    def save(value):
        saved.append(value)
        return {'id': 'full-receipts', 'chars': 100000}
    monkeypatch.setattr('capability_guard.evidence_ref', save)
    calls = [{'name': 'write', 'input': {'content': 'a' * 10000},
              'result': {'receipt': i, 'content': 'b' * 10000}} for i in range(20)]
    calls[-1]['is_error'] = True
    _, invocations, _, _ = run(calls)
    prompt = invocations[0]['message_content']
    assert saved == [calls] and saved[0][0]['result']['receipt'] == 0
    assert 'full-receipts' in prompt and len(prompt) < 28000


@pytest.mark.parametrize('phase', ['execution', 'repair_apply', 'repair_active', 'verify_remaining'])
def test_repair_execution_keeps_failure_recovery(turn, monkeypatch, phase):
    monkeypatch.setattr('repair_continuation.current', lambda: {'phase': phase})
    result, calls, _, _ = run([{'result': {'success': False, 'error': 'parse'}}])
    assert result == '결과 전달' and len(calls) == 1


@pytest.mark.parametrize('phase', ['apply', 'activation', 'active_verify', 'review', 'unknown'])
def test_owned_handoff_does_not_start_another_executor(turn, monkeypatch, phase):
    monkeypatch.setattr('repair_continuation.current', lambda: {'phase': phase})
    assert run([{'is_error': True}])[1] == []
    assert not turn.followup_reason


def test_new_apply_reservation_stops_recovery_before_continuation_is_saved(turn):
    assert run([{'is_error': True}], supervisor=NS(apply_scheduled={'key': 'repair'}))[1] == []
    assert not turn.followup_reason


def test_repair_pipeline_retries_failed_tool_and_keeps_grant_and_owner_lock(tmp_path, monkeypatch):
    from agent_pipeline import CognitivePipelineMixin
    from cognitive_consciousness import CognitiveConsciousnessMixin
    from cognitive_eval import CognitiveEvalMixin
    from test_reflex_execution import AI
    from thread_context import actor_context
    from repair_context import active
    from repair_continuation import key
    from restart_protocol import OwnerLock
    monkeypatch.setenv('INDIEBIZ_BASE_PATH', str(tmp_path))
    monkeypatch.setattr('supervision_bus.current', lambda: None)
    monkeypatch.setattr('system_ai_core._switch_to_role', lambda *a: None)
    monkeypatch.setattr('unified_distill.capture_model', lambda *a: None)
    monkeypatch.setattr('framing_inheritance.remember', lambda *a, **kw: None)
    def adopt(guard, runner, message, response, *args, **kwargs):
        yield from ()
        return response
    monkeypatch.setattr('capability_guard.adopt_response', adopt)
    class Runner(CognitivePipelineMixin, CognitiveConsciousnessMixin, CognitiveEvalMixin):
        pass
    class RepairAI(AI):
        def process_message_stream(self, **kwargs):
            assert active(), '후속 실행이 원래 수리 권한을 잃었다'
            lock = OwnerLock(tmp_path / 'data/system_ai_state/repair_sessions' / ('owner-' + key('recovery') + '.lock'))
            assert not lock.acquire(), '같은 사본의 실행자 잠금이 없다'
            yield from super().process_message_stream(**kwargs)
    r = Runner(); r.config = {'name': 'system_ai', '_is_system_ai': True}
    r.ai = RepairAI([
        [{'type': 'tool_start', 'name': 'search', 'input': {'query': 'x'}},
         {'type': 'tool_result', 'result': {'success': False, 'error': 'parser'}},
         {'type': 'text', 'content': '첫 시도 실패'}, {'type': 'final', 'content': '첫 시도 실패'}],
        [{'type': 'tool_start', 'name': 'alternative'},
         {'type': 'tool_result', 'result': {'items': ['recovered']}},
         {'type': 'final', 'content': '요청 결과 확인'}]])
    r._associate = lambda *a, **kw: None
    r._decide_request_type = lambda *a, **kw: ('REPAIR', None)
    r._run_consciousness_or_reuse = lambda *a, **kw: {'needs_repair': True, 'task_framing': '결함 해결'}
    r._load_role = lambda: 'role'
    r._build_system_ai_prompt_split = lambda *a, **kw: ('System structure + IBL + rules', '')
    r._apply_consciousness_to_history = lambda history, co: history
    r._after_response_async = lambda *a, **kw: None
    with actor_context(agent_id='system_ai', task_id='recovery', origin='user'), r.turn_ai_scope():
        events = list(r._cognitive_stream_body('문제를 고치고 결과를 내줘', []))
        assert len(r.ai.calls) == 2
    assert [e['content'] for e in events if e['type'] == 'final'] == ['요청 결과 확인']
    assert not any(e.get('content') == '첫 시도 실패' for e in events)
    assert not active()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
