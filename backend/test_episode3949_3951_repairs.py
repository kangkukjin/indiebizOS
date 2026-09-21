"""실제 주행에서 드러난 증류 누락·오귀속·오진 로그의 회귀."""
import copy
import json
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest

import associative_recall as recall
import capability_guard as guard
import unified_distill as distill
from ibl_distill_gates import recall_used
from memory_evidence import durable_source_units


def test_punctuation_cannot_trigger_memory_search(monkeypatch):
    import distill_memory_adapters as adapters
    monkeypatch.setattr(adapters, 'memory_modules', lambda: pytest.fail('no memory lookup for punctuation'))
    message = '. 우체국에 k 패키지라는게 있다는데 그걸 어떻게 쓰는지 저사해줘'
    units = durable_source_units(message)
    assert units[0]['text'] == '.' and units[0]['basis'] == 'punctuation_only'
    assert not any(u['eligible'] for u in units)
    assert adapters.prepare_deep({'user_message': message})['reason'] == 'no_user_fact_candidate'
    assert durable_source_units('나는 존댓말을 선호해.')[0]['eligible']


def test_budget_preserves_execution_before_smaller_spatial_section(monkeypatch):
    rows = [{'id': 1, 'code': '[sense:search]{query:"우체국"}'}]
    prepared = {'snapshot': {}, 'skip_reasons': {}, 'sections': {
        'execution': {'rows': rows, 'outcome': {'evidence': '가' * 1500}},
        'forage': {'observations': [{'id': 2, 'result': '나' * 1000}]}}}
    execution = copy.deepcopy(prepared['sections']['execution'])
    base = len((distill.SYSTEM_PROMPT + json.dumps(distill.model_input(
        {**prepared, 'sections': {'execution': execution}}), ensure_ascii=False)).encode())
    monkeypatch.setattr(distill, 'MAX_INPUT_BYTES', base + 500)
    fitted = distill.fit_input(prepared)
    assert fitted['sections']['execution'] == execution
    assert fitted['skip_reasons']['forage'] == 'complete_section_exceeds_input_budget'
    assert fitted['input_bytes'] <= distill.MAX_INPUT_BYTES


def test_budget_drops_directory_before_source_or_comparison():
    code = '[self:blog]{op:"check_new"}'
    prepared = {'snapshot': {}, 'skip_reasons': {}, 'sections': {'execution': {
        'rows': [{'id': 1, 'code': code}], 'source_calls': [code],
        'known': [{'id': 7, 'intent': '비교', 'ibl_code': code}],
        'outcome': {'goal_evaluation': None}, 'topic_map': '목차' * 15000}}}
    fitted = distill.fit_input(prepared)
    view = distill.model_input(fitted)
    assert view['sections']['execution']['source_rows'] == [{'id': 1, 'code': code}]
    assert view['sections']['execution']['comparison_examples'][0]['ibl_code'] == code
    assert 'topic_map' not in view['sections']['execution']
    assert 'execution.topic_map' in view['omitted_context']
    assert fitted['input_bytes'] <= distill.MAX_INPUT_BYTES


def test_blog_usage_counts_only_matching_operations_and_complete_sequence():
    examples = [
        '[self:blog]{op:"check_new"}', '[self:blog]{op:"posts"}',
        '[self:blog]{op:"latest"} >> [self:read]{} >> [table:document]{format:"html"}',
        '[self:blog]{op:"latest"}', '[self:blog]{op:"posts",category:"일상"}']
    calls = ['[self:blog]{op:"check_new"}', '$최신글=[self:blog]{op:"latest"}; $최신글 >> [self:read]{}']
    join = {'items': [{'id': i, 'code': code} for i, code in enumerate(examples)]}
    result = recall._used_hippocampus(list(range(5)), join, {'ibl_codes': calls})
    assert result['used'] == [0, 3]
    import ibl_usage_rag
    assert not ibl_usage_rag._recall_was_used(examples[1], calls)


@pytest.mark.parametrize('calls', [
    ['[self:read]{}', '[self:blog]{op:"latest"}'],
    ['[self:blog]{op:"latest"}'],
    ['[self:read]{path:"[self:blog]{op:latest}"}'],
    ['# [self:blog]{op:"latest"}\n[self:read]{}'],
    ['[table:each]{do:\'[self:blog]{op:"latest"} >> [self:read]{}\'}'],
])
def test_partial_reversed_quoted_or_deferred_code_is_not_complete_usage(calls):
    assert not recall_used('[self:blog]{op:"latest"} >> [self:read]{}', calls)


def test_alias_in_string_is_not_a_call():
    result = recall._used_hippocampus([1], {'items': [
        {'id': 1, 'alias': '한글함수', 'code': '[sense:search]{}'}]},
        {'ibl_codes': ['[self:read]{path:"[fn:한글함수]{}"}']})
    assert result['used'] == []
    assert recall_used('[fn:한글함수]{}', ['[fn:한글함수]{}'])
    assert not recall_used('[잘못된 코드', ['[self:read]{}'])


def test_feedback_only_does_not_claim_owner_was_rejected(monkeypatch):
    import cognitive_distill
    logs = []
    monkeypatch.setattr(cognitive_distill, '_principal_owner', lambda: True)
    runner = SimpleNamespace(_log=logs.append)
    cognitive_distill.CognitiveDistillMixin._after_response(
        runner, '나는 경쟁 때문에 성장이 계속된다고 생각해.', '응답',
        write_experience=False, write_deep=False, write_forage=False,
        guides_used=[], deep_confirmed=[])
    assert not any('주인이 직접' in message or '검수 미완료' in message for message in logs)


def test_retrospective_critique_needs_no_capability_judge():
    text = '제가 문맥을 충분히 반영하지 못했습니다.'
    assert not guard.candidate_matches(text)
    refusal = '저는 눈이 없어서 이미지를 볼 수 없습니다.'
    assert guard.candidate_matches(text + ' ' + refusal)
    assert guard.candidate_matches('현재 파일을 읽지 못했습니다.')
    assert guard.candidate_matches('이미지를 볼 수는 없습니다.')
    assert guard.candidate_matches('이 파일을 열 수가 없습니다.')
    assert not guard.CANDIDATE.search('수업을 마치면 문제가 없습니다.')


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
