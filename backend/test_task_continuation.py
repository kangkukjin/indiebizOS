"""실패 관측에서 다음 방법 실행, 정상/취소/예산/공유 재개 경계."""
from types import SimpleNamespace as NS

import boot_paths  # noqa: F401
import pytest
import execution_turn
import task_continuation as tc
from test_capability_guard import drain


@pytest.fixture
def turn(monkeypatch):
    monkeypatch.setattr(tc, 'record_trajectory_event', lambda *a, **kw: None)
    monkeypatch.setattr(tc, 'turn_limit_reason', lambda: None)
    monkeypatch.setattr('repair_continuation.current', lambda: None)
    binding = execution_turn.Binding(NS(), 'owner', 'task', context={}, conversation=None)
    token = execution_turn._current.set(binding)
    yield binding
    execution_turn._current.reset(token)


def run(calls, *, cancel=None, events=None, enabled=True):
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
                                             enabled=enabled))
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


@pytest.mark.parametrize('calls', [[], [{'result': {'items': []}}],
    [{'result': {'error': 'old'}}, {'result': {'items': ['alternative']}}]])
def test_success_and_resolved_failures_add_no_model_call(turn, calls):
    assert run(calls)[1] == []


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


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
