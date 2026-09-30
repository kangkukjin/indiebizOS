"""낭비 관문: 원문/의존성 보존, 판본별 귀속, 원장 및 수리 큐 재배달."""
import copy
import json

import boot_paths  # noqa: F401
import pytest

import ibl_distill_value as value
import unified_distill as ud
from ibl_distill_gates import recall_used
from test_unified_distill_2026_09_21 import env, arm, empty  # noqa: F401


def v2(code):
    return '#!ibl edition=2\n' + code


@pytest.mark.parametrize('wrapper', ['', 'return ', '$글 = '])
def test_url_change_across_editions_is_free(wrapper):
    old = '[sense:crawl]{url:"https://example.org/old"}'
    new = v2(wrapper + '[sense:crawl]{url:"https://example.org/new"}')
    assert value.redundant_reason([new], [{'id': 1, 'ibl_code': old}])
    assert value.redundant_reason([old], [{'id': 1, 'ibl_code': new}])
    assert not value.url_only_head(v2('return [sense:crawl]{url:"https://example.org/new",mode:"full"}'))


def test_v2_usage_matches_operations_and_explicit_edition():
    from associative_recall import _ibl_codes
    reference = '[self:blog]{op:"latest"} >> [self:read]{}'
    actual = _ibl_codes([{'tool_name': 'execute_ibl', 'input': {
        'edition': 2, 'code': '$글 = [self:blog]{op:"latest"}\nreturn $글 >> [self:read]{}'}}])
    assert recall_used(reference, actual)
    assert recall_used(v2('return ' + reference), actual)
    assert not recall_used('[self:blog]{op:"posts"}', actual)


@pytest.mark.parametrize('code', [
    '[def:숨음](){ return [self:blog]{op:"latest"} }',
    '[if:false]{ [self:blog]{op:"latest"} }',
    '[table:each]{} { [self:blog]{op:"latest"} }',
    'return "[self:blog]{op:latest}"',
    'return null\n[self:blog]{op:"latest"}',
    '[self:blog]{op:$동작}',
    '[self:read]{} ?? [self:blog]{op:"latest"}',
])
def test_unexecuted_or_unknown_code_gets_no_usage_credit(code):
    assert not recall_used('[self:blog]{op:"latest"}', [v2(code)])


@pytest.mark.parametrize('message', [
    'AI 팁보고서를 쓰는 관용구를 다시 만들어봐.', '그럼 가이드를 잘 읽고 갱신해봐.',
    'Indiebizos 홈페이지를 개선해봐.', '그럼 그렇게 고쳐봐.', '이 결과를 다시 확인해 보세요.',
    '전체 시스템을 살펴봐.', '색상을 바꿔봐.',
])
def test_simple_commands_never_search_or_call_a_memory_model(monkeypatch, message):
    import distill_memory_adapters as adapters
    monkeypatch.setattr(adapters, 'memory_modules', lambda: pytest.fail('unnecessary memory lookup'))
    assert adapters.prepare_deep({'user_message': message})['reason'] == 'no_user_fact_candidate'


def test_mixed_request_keeps_independent_fact():
    from memory_evidence import durable_source_units
    units = durable_source_units('나는 존댓말을 선호해. 홈페이지를 개선해봐.')
    assert [u['text'] for u in units if u['eligible']] == ['나는 존댓말을 선호해.']
    assert durable_source_units('나는 시스템을 고쳐봐야겠다고 생각한다.')[0]['eligible']


def execution(codes):
    return {'source_calls': codes, 'rows': [
        {'id': i, 'code': c, 'tool_call_index': i, 'statement_index': 1}
        for i, c in enumerate(codes, 1)], 'comparison_examples': [],
        'outcome': {'goal_evaluation': {'achieved': True}, 'call_results': [
            {'tool_call_index': i, 'excerpt': '확인'} for i in range(1, len(codes) + 1)]}}


def test_budget_selects_closed_component_without_truncating_code():
    codes = ['[self:read]{path:"' + 'x' * 30000 + '"}',
             '$자료 = [sense:search]{query:"공개 자료"}',
             '$자료 >> [table:select]{columns:["title"]}']
    original = execution(codes)
    prepared = ud.fit_input({'snapshot': {}, 'skip_reasons': {}, 'sections': {'execution': original}})
    section = prepared['sections']['execution']
    assert section['partial_selection'] is True
    assert section['source_calls'] == codes[1:]
    assert [r['original_id'] for r in section['rows']] == [2, 3]
    assert [r['id'] for r in section['rows']] == [1, 2]
    assert section['omitted_source_ids'] == [1]
    assert [r['tool_call_index'] for r in section['outcome']['call_results']] == [2, 3]
    assert original['source_calls'] == codes
    assert prepared['input_bytes'] <= ud.MAX_INPUT_BYTES


def test_budget_cannot_keep_consumer_when_producer_does_not_fit():
    codes = ['$자료 = [sense:search]{query:"' + 'x' * 30000 + '"}',
             '$자료 >> [table:select]{columns:["title"]}']
    prepared = ud.fit_input({'snapshot': {}, 'skip_reasons': {}, 'sections': {'execution': execution(codes)}})
    assert not prepared['sections']


def test_budget_keeps_v2_program_as_one_source():
    program = v2('$자료 = [sense:search]{query:"자료"}\nreturn $자료')
    prepared = ud.fit_input({'snapshot': {}, 'skip_reasons': {}, 'sections': {'execution': execution([
        '[self:read]{path:"' + 'x' * 30000 + '"}', program])}})
    assert prepared['sections']['execution']['source_calls'] == [program]


def test_unrelated_invalid_source_does_not_block_closed_component():
    from ibl_distill_gates import _close_source_dependencies
    codes = ['$자료 = [sense:search]{query:"자료"}', 'unparseable', '[self:time]']
    assert _close_source_dependencies([3], codes) == ([3], None)
    # 알 수 없는 문장이 변수를 바꿨을 수 있으므로 그 너머의 생산자를 추측하지 않는다.
    codes.append('$자료 >> [table:select]{columns:["title"]}')
    ids, error = _close_source_dependencies([4], codes)
    assert ids is None and error


def test_compaction_preserves_decision_receipts_and_replay(env):
    import distill_ledger as ledger
    section = execution(['[sense:crawl]{url:"https://example.org/a"}'])
    section.pop('comparison_examples')
    section['known'] = [{'id': i, 'intent': '기존', 'ibl_code': '[self:read]{path:"' + 'x' * 1000 + '"}'}
                        for i in range(30)]
    section['prompt'] = 'unused prompt' * 500
    asked = arm(env, sections={'execution': section})
    before = ud.run(env.job)
    ledger.create({**env.job, 'job_key': 'pending'})
    ledger.update('pending', prepared=copy.deepcopy(before['prepared']))
    compacted = ledger.compact_finished(value.full_comparisons)
    assert compacted['compacted'] == 1 and compacted['bytes_saved'] > 30000
    after = ud.run(env.job)
    assert len(asked) == 1 and after['decision'] == before['decision']
    assert after['receipts'] == before['receipts'] and after['payload'] == before['payload']
    assert 'known' in ledger.read('pending')['prepared']['sections']['execution']
    assert ledger.compact_finished(value.full_comparisons)['compacted'] == 0


def test_unified_preparation_does_not_persist_whole_corpus(monkeypatch, tmp_path):
    from test_distill_source_recovery_2026_09_09 import _arm
    rag, _, _, _ = _arm(monkeypatch, tmp_path, [])
    monkeypatch.setattr(value, 'known_examples', lambda db: [
        {'id': i, 'intent': '다른 용례', 'ibl_code': '[self:time]'} for i in range(100)])
    section = rag.prepare_experience('공개 자료 검색', [{'tool_name': 'execute_ibl',
        'input': {'code': '[sense:search]{query:"자료"}'}, 'success': True,
        'result': {'items': [{'title': '자료'}]}}], 0, unified=True)
    assert section and 'known' not in section and 'prompt' not in section
    assert section['user_message'] == '공개 자료 검색'


def repair_env(monkeypatch):
    import repair_verdict_distill as rv
    import forage_memory as fm
    meta, asked = {rv._META_KEY: 'anchor'}, []
    commits = ['old', 'middle', 'recent', 'newest']
    monkeypatch.setattr(fm, 'get_meta', lambda key: meta.get(key))
    monkeypatch.setattr(fm, 'set_meta', lambda key, val: meta.__setitem__(key, val))
    monkeypatch.setattr(rv, '_repo_root', lambda: '/fixture/repo')
    monkeypatch.setattr(rv, '_pending_commits', lambda root, last: commits[commits.index(last)+1:] if last in commits else commits)
    monkeypatch.setattr(rv, '_commit_detail', lambda *a: ('fix problem', ['backend/file.py']))
    monkeypatch.setattr(rv, '_known_map_text', lambda *a: '')
    monkeypatch.setattr(rv, '_distill_commit', lambda body, repo, h, *a: asked.append(h) or 0)
    return rv, meta, asked


def test_repair_recent_first_preserves_backlog_and_completed_holes(monkeypatch):
    rv, meta, asked = repair_env(monkeypatch)
    first = rv.run_repair_verdict_distill(limit=2)
    assert asked == ['newest', 'old'] and first['remaining'] == 2
    assert meta[rv._META_KEY] == 'old'
    assert json.loads(meta[rv._DONE_KEY]) == ['newest']
    second = rv.run_repair_verdict_distill(limit=2)
    assert asked == ['newest', 'old', 'recent', 'middle']
    assert second['remaining'] == 0 and meta[rv._META_KEY] == 'newest'
    assert rv.run_repair_verdict_distill(limit=2)['scanned'] == 0


def test_repair_failure_is_not_completion_and_no_cues_do_not_consume_model_budget(monkeypatch):
    rv, meta, asked = repair_env(monkeypatch)
    monkeypatch.setattr(rv, '_distill_commit', lambda *a: None)
    assert rv.run_repair_verdict_distill(limit=2)['remaining'] == 4
    assert meta[rv._META_KEY] == 'anchor'
    monkeypatch.setattr(rv, '_commit_detail', lambda *a: ('docs: text', []))
    assert rv.run_repair_verdict_distill(limit=1)['remaining'] == 0
    assert asked == [] and meta[rv._META_KEY] == 'newest'


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
