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


def test_receipts_frozen_masked_and_checkpoint_has_only_references(tmp_path):
    from evaluation_evidence import freeze_receipts, receipt_sections
    from supervision_store import TurnStore
    store = TurnStore(tmp_path / 'evidence')
    secret = 'sk-' + 'Ab3' * 12
    citation = {'valid': [{'citation': '[자료:v:p]', 'version_ref': 'v', 'locator': 'p',
                          'receipts': [{'access_id': 2, 'extraction_revision': 1,
                                        'quote': '앞 조건\n' + secret + '\n반례: 효과 미확인'}]}]}
    freeze_receipts(citation, store)
    restored = json.loads(json.dumps(citation))
    assert secret not in json.dumps(restored)
    rows = receipt_sections(restored, store)
    assert secret not in rows[0]['text'] and '반례: 효과 미확인' in rows[0]['text']
    assert rows[0]['receipt']['access_id'] == 2
    path = store.directory / (rows[0]['source_ref'] + '.txt')
    path.write_text('changed')
    with pytest.raises(ValueError):
        receipt_sections(restored, store)


def test_claim_context_elision_requires_exact_delivered_document_span():
    from evaluation_input import context_sections
    from research_review import claims
    text = '조건부 반례: 효과 미확인 [자료:v:p] 끝'
    _, sections = context_sections(json.dumps({'research_claims': claims(text, path='report', digest='v1')}))
    from evaluation_evidence import structure_display
    artifact = record(text, subject='report', role='submission')
    assert 'claim_context' not in structure_display(sections[0], [artifact])['claims'][0]
    assert 'claim_context' in structure_display(sections[0], [{**artifact, 'text': text[:5]}])['claims'][0]
    assert 'claim_context' in structure_display(sections[0], [{**artifact, 'text': text.replace('미확인', '확인됨')}])['claims'][0]


def test_structured_display_uses_masked_store_copy(tmp_path, monkeypatch):
    from final_evaluator import Evaluator
    from supervision_store import TurnStore
    evaluator = Evaluator()
    evaluator.evaluation_store = TurnStore(tmp_path / 'masked-evaluation')
    secret = 'sk-' + 'Ab3' * 12
    captured = []
    def evaluate(prompt, **kwargs):
        captured.append(prompt)
        return 'ACHIEVED'
    monkeypatch.setattr('consciousness_agent.system_ai_call', evaluate)
    evaluator._evaluate_achievement('inspect', '{"criteria":[{"id":"C1","text":"check"}]}', 'done', '',
        evaluation_context=json.dumps({'evidence_index': [{'warning': secret + ' 부분 실패'}]}))
    assert captured and secret not in captured[0] and '부분 실패' not in captured[0]


def test_structured_evidence_is_whole_or_omitted_and_citation_roles_remain_distinct():
    from evaluation_input import context_sections
    _, records = context_sections(json.dumps({'evidence_index': [{'x': 'a' * 50000}]}))
    prompt = EvaluationPrompt('C1', records + [record('조건 말미의 반례', subject='p', role='citation')])
    shown = prompt.prepare_request(provider(request_limits={'chars': 16000}))
    assert '조건 말미의 반례' in shown
    assert prompt.metrics['sections'][0]['shown_chars'] == 0
    rows = [record('same', subject='p', role='citation', source_ref='x') for _ in range(2)]
    rows[0]['receipt'] = {'access_id': 1, 'extraction_revision': 1}
    rows[1]['receipt'] = {'access_id': 2, 'extraction_revision': 2}
    distinct = EvaluationPrompt('C1', rows)
    distinct.prepare_request(provider())
    assert len(distinct.metrics['sections']) == 2


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
    assert '"revision":"v1"' in shown and '"revision":"v2"' in shown
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
    assert evidence_requests('EVIDENCE_REQUESTS: ' + json.dumps([request]), packet)['requests'] == [request]
    rows = recover(supervisor, [request])
    assert rows[0]['text'] == '중간 반례' and rows[0]['start'] == 2
    for changed in ({'revision': 'other'}, {'evidence_id': 'f' * 64}, {'end': 999}, {'start': -1}):
        assert evidence_requests('EVIDENCE_REQUESTS: ' + json.dumps([{**request, **changed}]), packet)['status'] == 'invalid'
    (supervisor.store.directory / (ref['id'] + '.txt')).write_text('다른 판본')
    with pytest.raises(ValueError, match='판본'):
        recover(supervisor, [request])






def test_dedup_keeps_subjects_and_every_explicit_criterion_relation():
    rows = [record('same', subject='first', source_ref='r', criterion_ids=['C1']),
            record('same', subject='second', source_ref='r', criterion_ids=['C2'])]
    prompt = EvaluationPrompt('criteria', rows)
    prompt.prepare_request(provider())
    section, = prompt.metrics['sections']
    assert section['subjects'] == ['first', 'second']
    assert section['criterion_ids'] == ['C1', 'C2']


def request_packet(supervisor):
    from final_evaluator import prepare
    supervisor.run_tool('read', {}, lambda: '앞🙂\n정답 7\n끝')
    supervisor.store.put_response('응답')
    packet = prepare(supervisor)
    packet['context']['evidence_index'] = supervisor.store.tool_index()
    ref = packet['context']['evidence_index'][0]['result']
    return packet, {'criterion_id': packet['context']['criteria_contract']['criteria'][0]['id'],
                    'evidence_id': ref['id'], 'start': 3, 'end': 7}


def test_missing_immutable_revision_is_normalized_but_conflicts_are_not(supervisor):
    from evaluation_input import evidence_references
    packet, request = request_packet(supervisor)
    result = evidence_requests('EVIDENCE_REQUESTS: ' + json.dumps([request]), packet)
    assert result['status'] == 'normalized'
    assert result['requests'][0]['revision'] == request['evidence_id']
    assert result['normalizations'][0]['reason'] == 'immutable_turn_evidence'
    assert recover(supervisor, result['requests'])[0]['text'] == '정답 7'
    packet['attachments'].append(record('other', subject='conflict', source_ref=request['evidence_id'], revision='different'))
    refs = {r['evidence_id']: r for r in evidence_references(packet)}
    assert refs[request['evidence_id']]['ambiguous']
    result = evidence_requests('EVIDENCE_REQUESTS: ' + json.dumps([request]), packet)
    assert result['status'] == 'invalid' and result['errors'][0]['code'] == 'reference_conflict'


@pytest.mark.parametrize('value', ['{', '{}', '[]', '[1]', '[null]', '["x"]', '[[]]', 'null', 'true'])
def test_malformed_request_is_a_protocol_result(supervisor, value):
    packet, _ = request_packet(supervisor)
    result = evidence_requests('EVIDENCE_REQUESTS: ' + value, packet)
    assert result['status'] == 'invalid' and result['errors'] and not result['requests']
    assert evidence_requests('UNKNOWN_REASON: evidence', packet)['status'] == 'absent'


@pytest.mark.parametrize('change,code', [({'revision': None}, 'revision'), ({'revision': 'wrong'}, 'revision'),
    ({'start': True}, 'range'), ({'end': '7'}, 'range'), ({'end': 9999}, 'range'),
    ({'criterion_id': []}, 'criterion'), ({'evidence_id': []}, 'reference'),
    ({'evidence_id': 'a' * 64}, 'reference')])
def test_invalid_items_do_not_silently_recover_the_valid_subset(supervisor, change, code):
    packet, request = request_packet(supervisor)
    result = evidence_requests('EVIDENCE_REQUESTS: ' + json.dumps([request, {**request, **change}]), packet)
    assert result['status'] == 'invalid' and result['errors'] == [{'index': 1, 'code': code}]
    assert len(result['requests']) == 1  # retained for diagnosis, not automatic dispatch






def test_recovered_segment_is_never_silently_retruncated():
    prompt = EvaluationPrompt('기준', [record('원문' * 12000, subject='r', role='recovered')])
    with pytest.raises(InputTooLarge, match='회수 요청 구간'):
        prompt.prepare_request(provider(request_limits={'chars': 15000}))
    prompt = EvaluationPrompt('기준', [record('짧은 반례', subject='r', role='recovered'),
                                       record('잡음' * 10000, subject='s')])
    assert '짧은 반례' in prompt.prepare_request(provider(request_limits={'chars': 15000}))


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))


def test_workspace_check_reference_is_recoverable_without_conflating_check_id():
    from evaluation_input import evidence_references
    original = 'a' * 64
    packet = {'context': {'workspace_evidence': [{'id': 'check-1',
        'evidence_ref': {'id': original, 'chars': 90000}, 'criterion_ids': ['C1']}]}}
    refs = evidence_references(packet)
    assert len(refs) == 1
    assert refs[0]['evidence_id'] == refs[0]['revision'] == original
    assert refs[0]['recoverable'] and refs[0]['total'] == 90000
    assert refs[0]['criterion_ids'] == ['C1']


def test_submission_is_complete_before_large_collected_sources():
    report = '보고서 앞\n' + '최종 결론과 근거\n' * 1000 + '보고서 끝'
    prompt = EvaluationPrompt('기준', [
        *[record('수집 원문\n' * 10000, subject=f'source-{i}', source_ref=str(i)) for i in range(14)],
        record(report, subject='report', role='submission')])
    prompt.prepare_request(provider(request_limits={'chars': 40000}))
    report_meta = next(r for r in prompt.metrics['sections'] if r['subject'] == 'report')
    assert report_meta['completeness'] == 'complete'
    assert prompt.metrics['omitted'] == 14


def test_new_evidence_ranges_exclude_overlap_and_preserve_revision():
    from evaluation_input import new_evidence_requests
    rows = [record('abcd', subject='x', role='recovered', source_ref='x', revision='v1', start=2),
            record('xx', subject='x', role='recovered', source_ref='x', revision='v1', start=8),
            record('all text', subject='y', source_ref='y', revision='v1')]
    request = {'criterion_id': 'C1', 'evidence_id': 'x', 'revision': 'v1', 'start': 0, 'end': 12}
    result = new_evidence_requests([request, request], rows)
    assert [(r['start'], r['end']) for r in result] == [(0, 2), (6, 8), (10, 12)]
    changed = {**request, 'revision': 'v2'}
    assert new_evidence_requests([changed], rows) == [changed]
    other = {**request, 'evidence_id': 'y'}
    assert new_evidence_requests([other], rows) == [other]








def test_review_restore_preserves_evaluation_budget(supervisor, monkeypatch, tmp_path):
    from final_evaluator import prepare, invoke
    from repair_continuation import review_checkpoint
    from repair_resume import restore_review
    root = tmp_path / 'body'
    directory = root / 'data/spill/supervision/review'
    directory.mkdir(parents=True)
    supervisor.store.directory = directory
    supervisor.store.put_response('동일 응답')
    prepare(supervisor)
    from model_call_context import record_captured_usage

    def evaluate(*args, **kw):
        record_captured_usage({'input': 1000, 'output': 20}, 1)
        return 'UNKNOWN\nUNKNOWN_REASON: evidence'

    monkeypatch.setattr('consciousness_agent.system_ai_call', evaluate)
    invoke(supervisor)
    supervisor._final_repair_counts = [0, 2]
    review_checkpoint(supervisor, supervisor._evaluation_packet, supervisor._evaluation_snapshot)
    supervisor.usage = supervisor.final_usage = {'input': 0, 'output': 0}
    supervisor.phase_usage = {}
    monkeypatch.setattr('runtime_utils.get_base_path', lambda: root)
    restore_review(supervisor, {'review_path': str(directory / 'repair_review.json')})
    assert supervisor.usage == supervisor.final_usage == {'input': 1000, 'output': 20}
    assert supervisor.phase_usage['final']['last_input'] == 1000
    assert supervisor._final_repair_counts == [0, 2]


def test_first_review_supplies_stored_result_body_and_linked_revision(supervisor):
    from evaluation_evidence import result_sections
    body = '사용자 관점과 연구 질문: ' + '기존 논의 ' * 600 + '정정된 목적을 저장했다.'
    source = supervisor.store.evidence(body)
    envelope = supervisor.store.evidence({'result_ref': {'id': source['id']}, 'status': 'complete'})
    rows = result_sections([{'seq': 7, 'name': 'execute_ibl', 'result': envelope}], supervisor.store,
                            {'criteria': [{'id': 'C4', 'text': '사용자 관점과 연구 질문을 보존한다'}]})
    match = next(r for r in rows if r['source_ref'] == source['id'])
    assert match['criterion_ids'] == ['C4'] and match['text'] == body
    assert match['receipt']['tool_seq'] == 7
    prompt = EvaluationPrompt('기준 C4', rows)
    shown = prompt.prepare_request(provider())
    assert body in shown and source['id'] in shown
    assert prompt.metrics['criterion_coverage']['C4'][0]['completeness'] == 'complete'


def test_first_review_preserves_required_body_before_long_submission():
    rows = [record('제출물' * 30000, subject='report', role='submission'),
            record('사용자 정정 저장 본문', subject='result', role='criterion', criterion_ids=['C4'])]
    prompt = EvaluationPrompt('C4', rows)
    shown = prompt.prepare_request(provider(request_limits={'chars': 16000}))
    assert '사용자 정정 저장 본문' in shown
    assert prompt.metrics['sections'][1]['completeness'] == 'complete'
    assert prompt.metrics['sections'][0]['completeness'] != 'complete'


def test_first_review_does_not_import_foreign_or_changed_evidence(supervisor):
    from evaluation_evidence import result_sections
    ref = supervisor.store.evidence('기준 원문')
    (supervisor.store.directory / (ref['id'] + '.txt')).write_text('다른 원문')
    rows = result_sections([{'result': ref}, {'result': {'id': 'a' * 64}}],
                            supervisor.store, {'criteria': [{'id': 'C1', 'text': '기준 원문'}]})
    assert rows == []


def test_identical_tool_body_preserves_each_call_receipt(supervisor):
    from evaluation_evidence import result_sections
    ref = supervisor.store.evidence('동일한 결과 원문')
    rows = result_sections([{'seq': n, 'result': ref} for n in (1, 2)],
                           supervisor.store, {'criteria': []})
    assert [r['receipt']['tool_seq'] for r in rows] == [1, 2]
    prompt = EvaluationPrompt('검수', rows)
    prompt.prepare_request(provider())
    assert len(prompt.metrics['sections']) == 2


def test_large_lexical_candidates_do_not_displace_submissions_or_fill_context():
    from evaluation_input import SUPPORT_PREVIEW_CHARS
    report = '비교 보고서\n' * 4000 + '최종 판단'
    ledger = '근거 원장\n' * 1000 + '남은 확인'
    rows = [record('기준과 겹치는 수집 결과\n' * 20000, subject=f'candidate-{i}',
                   role='criterion', criterion_ids=['C1'], source_ref=str(i)) for i in range(20)]
    rows += [record(report, subject='report', role='submission'),
             record(ledger, subject='ledger', role='submission')]
    prompt = EvaluationPrompt('C1 비교', rows)
    shown = prompt.prepare_request(provider(request_limits={'chars': 250000}))
    assert report in shown and ledger in shown
    assert sum(r['shown_chars'] for r in prompt.metrics['sections'] if r['role'] == 'criterion') <= SUPPORT_PREVIEW_CHARS
    assert len(shown) < 150000
    assert len(prompt.metrics['criterion_coverage']['C1']) == 20


def test_preview_limit_does_not_limit_explicit_recovery(supervisor):
    from evaluation_input import SUPPORT_PREVIEW_CHARS, evidence_references
    text = '원문 앞\n' + '내용\n' * SUPPORT_PREVIEW_CHARS + '원문 끝'
    ref = supervisor.store.evidence(text)
    source = record(text, subject='source', source_ref=ref['id'], revision=ref['id'],
                    role='criterion', criterion_ids=['C1'])
    initial = EvaluationPrompt('C1', [source])
    initial.prepare_request(provider())
    assert initial.metrics['sections'][0]['completeness'] == 'partial'
    packet = {'attachments': [source], 'context': {'criteria_contract': {'criteria': [{'id': 'C1'}]}}}
    assert evidence_references(packet)[0]['recoverable']
    requests = evidence_requests('EVIDENCE_REQUESTS: ' + json.dumps([
        {'criterion_id': 'C1', 'evidence_id': ref['id'], 'start': 0, 'end': len(text)}]), packet)
    recovered = recover(supervisor, requests['requests'])
    p = provider()
    p.context_window_tokens = 1000000
    review = EvaluationPrompt('C1', recovered)
    assert text in review.prepare_request(p)
    assert review.metrics['sections'][0]['completeness'] == 'complete'
