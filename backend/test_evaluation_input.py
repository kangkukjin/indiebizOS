"""Whole-request limits, exact evidence pages, and provider failure separation."""
import boot_paths  # noqa: F401
import json
from types import SimpleNamespace

import pytest
from evaluation_input import EvaluationPrompt, record, recover, evidence_requests
from model_request_budget import InputTooLarge, check, serialized
from consciousness_agent import system_ai_call as real_system_ai_call
from test_conscious_supervisor import supervisor, finish  # noqa: F401


def provider(**overrides):
    return SimpleNamespace(model='test', CONTEXT_PROVIDER='test', context_window_tokens=100000,
                           system_prompt='정책', tools=[], **overrides)


def test_many_files_share_one_budget_and_keep_small_failure():
    p = provider(request_limits={'chars': 100000, 'source': 'fixture'})
    rows = [record(('자료 한글\\\"\n' * 9000), subject=f'file-{i}', source_ref=str(i)) for i in range(20)]
    rows.append(record('작은 검사 실패: 수치는 틀렸음', subject='failure'))
    required = '사용자 정정: C1 기준을 유지\n'
    prompt = EvaluationPrompt(required, rows, '수치')
    shown = prompt.prepare_request(p)
    check(p, serialized(p, shown), reserve=8192)
    assert required in shown and '작은 검사 실패: 수치는 틀렸음' in shown
    assert prompt.metrics['omitted'] and len(prompt.metrics['sections']) == 21
    assert sum(r['shown_chars'] for r in prompt.metrics['sections']) < 100000
    assert 'text' not in json.dumps(prompt.metrics['sections'])


def test_middle_counterexample_and_different_revisions_are_not_merged():
    p = provider(request_limits={'chars': 16000, 'source': 'fixture'})
    body = ('앞\n' * 4000) + '반례 매출 감소 99\n' + ('뒤\n' * 4000)
    rows = [record(body, subject='same', source_ref='a', revision='v1'),
            record(body, subject='same', source_ref='a', revision='v2')]
    prompt = EvaluationPrompt('C1 매출 감소 반례', rows, '매출 감소 반례')
    shown = prompt.prepare_request(p)
    assert '반례 매출 감소 99' in shown
    assert len(prompt.metrics['sections']) == 2
    assert all(r['range']['start'] > 0 for r in prompt.metrics['sections'])


def test_required_only_overflow_never_calls_model(monkeypatch):
    from consciousness_agent import call_oneshot_provider, oneshot_failure_details
    p = provider(request_limits={'bytes': 14000, 'source': 'fixture'})
    p.process_message = lambda **kw: pytest.fail('must stop before model call')
    result = call_oneshot_provider(p, EvaluationPrompt('정정' * 5000, []), system_prompt='정책', role='evaluate')
    assert result is None
    assert oneshot_failure_details()['kind'] == 'input_too_large'
    assert 'bytes' in oneshot_failure_details()['details']['exceeded']


def test_actual_codex_wrapper_and_image_reserve():
    from providers.codex import CodexProvider
    p = CodexProvider(api_key='', model='gpt-5.6', system_prompt='정책' * 1000, tools=[])
    p.context_window_tokens = 100000
    p.no_tools = True
    p.request_limits = {'chars': 20000, 'source': 'fixture'}
    prompt = EvaluationPrompt('기준', [record('원문' * 20000, subject='file')])
    text = prompt.prepare_request(p, [{'base64': 'abc', 'media_type': 'image/png'}])
    assert p.system_prompt in serialized(p, text)
    assert len(serialized(p, text)) + 8192 <= 20000
    assert prompt.metrics['estimated_tokens'] >= 8192


@pytest.mark.parametrize('failure', ['input_too_large', 'deadline', 'authentication', 'transport'])
def test_error_containing_verdict_never_becomes_approval(supervisor, monkeypatch, failure):
    import consciousness_agent as ca
    from final_evaluator import prepare, invoke
    class Provider:
        model = 'fake'
        context_window_tokens = 100000
        CONTEXT_PROVIDER = 'test'
        def process_message(self, **kwargs):
            self.last_failure_kind = failure
            return 'ACHIEVED\nUNKNOWN_REASON: evidence\nREPAIR_SCOPE: research'
    p = Provider()
    monkeypatch.setattr(ca, '_resolve_oneshot_provider', lambda role: p)
    monkeypatch.setattr(ca, 'system_ai_call', real_system_ai_call)
    supervisor.store.put_response('응답')
    prepare(supervisor)
    out = json.loads(invoke(supervisor))
    assert out['status'] == 'UNKNOWN' and out['failure']['kind'] == failure
    assert not out.get('recoverable') and not out.get('retryable')


def test_structured_recovery_validates_revision_range_and_masking(supervisor):
    from final_evaluator import prepare
    ref = supervisor.store.evidence('앞\n중간 반례\n끝')
    supervisor.store.put_response('응답')
    packet = prepare(supervisor)
    packet['attachments'] = [record('앞\n중간 반례\n끝', subject='file', source_ref=ref['id'], revision=ref['id'])]
    cid = packet['context']['criteria_contract']['criteria'][0]['id']
    request = {'criterion_id': cid, 'evidence_id': ref['id'], 'revision': ref['id'], 'start': 2, 'end': 7}
    assert evidence_requests('EVIDENCE_REQUESTS: ' + json.dumps([request]), packet) == [request]
    rows = recover(supervisor, [request])
    assert rows[0]['text'] == '중간 반례' and rows[0]['start'] == 2
    for changed in ({'revision': 'other'}, {'evidence_id': 'f' * 64}, {'end': 999}, {'start': -1}):
        assert evidence_requests('EVIDENCE_REQUESTS: ' + json.dumps([{**request, **changed}]), packet) == []
    (supervisor.store.directory / (ref['id'] + '.txt')).write_text('다른 판본')
    with pytest.raises(ValueError, match='판본'):
        recover(supervisor, [request])


def test_controller_reads_existing_evidence_once_without_executor(supervisor, monkeypatch):
    from final_evaluator import prepare
    ref = supervisor.store.evidence('정확한 원문')
    from supervisor_handoff import criteria_contract
    cid = criteria_contract(supervisor.message, supervisor.framing)['criteria'][0]['id']
    calls = []
    def evaluate(prompt, **kwargs):
        calls.append(prompt)
        if len(calls) == 1:
            # Use the original tool index's reference, already in this turn.
            return 'UNKNOWN\nUNKNOWN_REASON: evidence\nEVIDENCE_REQUESTS: ' + json.dumps([
                {'criterion_id': cid, 'evidence_id': ref['id'], 'revision': ref['id'], 'start': 0, 'end': 6}])
        assert '정확한 원문' in prompt
        return 'ACHIEVED'
    supervisor.run_tool('read', {}, lambda: '정확한 원문')
    monkeypatch.setattr('consciousness_agent.system_ai_call', evaluate)
    supervisor.runner.ai.process_message_stream = lambda *a, **kw: pytest.fail('automatic and executor recovery duplicated')
    finish(supervisor, '응답')
    assert len(calls) == 2


def test_dedup_keeps_subjects_and_every_explicit_criterion_relation():
    rows = [record('same', subject='first', source_ref='r', criterion_ids=['C1']),
            record('same', subject='second', source_ref='r', criterion_ids=['C2'])]
    prompt = EvaluationPrompt('criteria', rows)
    prompt.prepare_request(provider())
    section, = prompt.metrics['sections']
    assert section['subjects'] == ['first', 'second']
    assert section['criterion_ids'] == ['C1', 'C2']


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))
