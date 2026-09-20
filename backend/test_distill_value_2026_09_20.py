"""증류가 0/1회 모델 호출로 끝나고 검증 가능한 새 경험만 저장하는지 검사."""
import json
import sys

import boot_paths  # noqa: F401
import pytest

import ibl_distill_value as value
from test_distill_source_recovery_2026_09_09 import _arm

SEARCH = '$자료 = [sense:search]{query:"공개 문서"}'
SELECT = '$자료 >> [table:select]{columns:["title","url"]}'
CRAWL = '[sense:crawl]{url:"https://example.test/old"}'


def call(code, **extra):
    return dict(tool_name='execute_ibl', input={'code': code}, success=True, **extra)


def known(code, ident=1):
    return {'id': ident, 'intent': '기존 용례', 'ibl_code': code}


@pytest.mark.parametrize('source,existing', [
    (SEARCH, SEARCH),
    ('$글 = [sense:crawl]{url:"https://example.test/new"}', CRAWL),
    (SEARCH + '\n' + SELECT, SEARCH + '\n' + SELECT),
])
def test_known_programs_cost_zero_model_calls(monkeypatch, tmp_path, source, existing):
    rag, saved, asked, runs = _arm(monkeypatch, tmp_path, [])
    monkeypatch.setattr(value, 'known_examples', lambda db: [known(existing)])
    assert not rag.distill_experience('반복 요청', [call(source)], 0)
    assert saved == asked == runs == []


def test_new_composition_and_options_are_not_erased():
    assert not value.redundant_reason([SEARCH, SELECT], [known(SEARCH), known(SELECT, 2)])
    assert not value.redundant_reason([CRAWL[:-1] + ',max_length:40000}'], [known(CRAWL)])
    assert not value.redundant_reason([CRAWL + ' >> [table:take]{n:2}'], [known(CRAWL)])
    assert not value.redundant_reason(['[table:ai]{instruction:"검증"}'],
                                      [known('[table:ai]{instruction:"요약"}')])


@pytest.mark.parametrize('reply', [
    {'decision': 'skip', 'source_ids': []},
    {'source_ids': [1], 'benefit': ''},
    {'source_ids': [1], 'applicability': ''},
    {'code': 'broken'},
    {'source_ids': [99]},
    {'source_ids': [True]},
])
def test_rejected_selection_never_retries_or_writes(monkeypatch, tmp_path, reply):
    rag, saved, asked, runs = _arm(monkeypatch, tmp_path, [{'intent': '검색', 'topic': '시험', **reply}])
    assert not rag.distill_experience('자료 찾기', [call(SEARCH), call(SELECT)], 0)
    assert len(asked) == 1 and saved == runs == []


def test_missing_success_is_not_positive_evidence(monkeypatch, tmp_path):
    rag, saved, asked, _ = _arm(monkeypatch, tmp_path, [])
    tc = call(SEARCH)
    del tc['success']
    assert not rag.distill_experience('검색', [tc], 0)
    assert saved == asked == []


@pytest.mark.parametrize('outcome', [{}, {'achieved': True, 'status': 'UNKNOWN'}])
def test_incomplete_goal_evidence_costs_no_call(monkeypatch, tmp_path, outcome):
    rag, saved, asked, _ = _arm(monkeypatch, tmp_path, [])
    import thread_context
    monkeypatch.setattr(thread_context, 'get_goal_eval_outcome', lambda: outcome)
    assert not rag.distill_experience('검색', [call(SEARCH)], 0)
    assert saved == asked == []


def test_evidence_excerpt_is_bounded_and_missing_is_explicit():
    result = {'items': [{'text': '긴 결과' * 1000}]}
    payload = json.loads(value.outcome_evidence([(3, call(SEARCH, result=result)),
                                                (5, call(SELECT))], None))
    assert payload['goal_evaluation'] is None
    first, missing = payload['call_results']
    assert first['tool_call_index'] == 3 and first['excerpt_truncated']
    assert len(first['excerpt']) == 400
    assert missing['tool_call_index'] == 5 and not missing['result_available']
    assert missing['excerpt'] == ''


def test_recall_shows_conditions_and_component_without_private_origin():
    import xml.etree.ElementTree as ET
    from ibl_usage_db import UsageExample
    from ibl_usage_rag import IBLUsageRAG
    entry = UsageExample(1, '자료 조회', SEARCH, 'sense', 'single', 1, .7,
                         'distilled_component', -1,
                         provenance=json.dumps({'task_id': 'private-task', 'applicability': '행에 "url" 필드가 있을 때'}))
    xml = IBLUsageRAG._format_references(None, [entry])
    ref = ET.fromstring(xml).find('ref')
    assert ref.attrib['scope'] == 'component'
    assert ref.attrib['applicability'] == '행에 "url" 필드가 있을 때'
    assert 'private-task' not in xml
    assert value.applicability_note('invalid') == ''


def test_input_budget_preserves_original_and_calls_no_model(monkeypatch, tmp_path):
    rag, saved, asked, _ = _arm(monkeypatch, tmp_path, [])
    tc = call(SEARCH)
    assert not rag.distill_experience('긴 요청' * value.MAX_INPUT_CHARS, [tc], 0)
    assert saved == asked == [] and tc['input']['code'] == SEARCH


def test_selected_dependencies_and_origin_are_preserved(monkeypatch, tmp_path):
    import thread_context
    monkeypatch.setattr(thread_context, 'get_current_task_id', lambda: 'task-fixture')
    rag, saved, asked, runs = _arm(monkeypatch, tmp_path, [
        {'intent': '검색 결과 열 추리기', 'source_ids': [2], 'scope': 'component', 'topic': '시험'}])
    assert rag.distill_experience('자료 찾기', [call(SEARCH), call(SELECT), call('[self:time]')], 0)
    assert len(asked) == len(saved) == 1
    entry = saved[0]
    assert entry['ibl_code'] == SEARCH + '\n' + SELECT
    assert runs[0][2] == [SEARCH, SELECT]
    evidence = entry['provenance']
    assert evidence['task_id'] == 'task-fixture'
    assert [r['tool_call_index'] for r in evidence['sources']] == [1, 2]
    assert all(len(r['sha256']) == 64 for r in evidence['sources'])
    exported = json.loads((tmp_path / 'data/training/ibl_distilled.json').read_text())
    assert exported[0]['provenance'] == evidence


def test_duplicate_selected_after_model_does_not_write(monkeypatch, tmp_path):
    rag, saved, asked, runs = _arm(monkeypatch, tmp_path, [{'intent': '시간', 'source_ids': [2]}])
    monkeypatch.setattr(value, 'known_examples', lambda db: [known('[self:time]')])
    assert not rag.distill_experience('검색과 시간', [call(SEARCH), call('[self:time]')], 0)
    assert len(asked) == 1 and saved == runs == []


def test_unavailable_comparison_or_validation_fails_closed(monkeypatch, tmp_path):
    rag, saved, asked, runs = _arm(monkeypatch, tmp_path, [{'intent': '검색', 'source_ids': [1]}])
    import ibl_param_vocab
    def broken(*args):
        raise RuntimeError('unavailable')
    monkeypatch.setattr(ibl_param_vocab, 'check_code_params', broken)
    assert not rag.distill_experience('검색', [call(SEARCH)], 0)
    assert len(asked) == 1 and saved == runs == []
    monkeypatch.setattr(value, 'known_examples', broken)
    assert not rag.distill_experience('검색', [call(SEARCH)], 0)
    assert len(asked) == 1


def test_db_migration_provenance_and_component_retention(monkeypatch, tmp_path):
    import ibl_usage_db as mod
    from test_hippo_tree import _mk_db
    path = str(tmp_path / 'usage.db')
    _mk_db(path)  # 기존 provenance 없는 스키마에서 시작
    monkeypatch.setattr(mod, 'DB_PATH', path)
    monkeypatch.setattr(mod.IBLUsageDB, '_instance', None)
    monkeypatch.setattr(mod, '_tree_refresh', lambda *args: None)
    monkeypatch.setattr(mod.IBLUsageDB, '_index_single', lambda *args: None)
    monkeypatch.setattr(mod.IBLUsageDB, 'is_semantic_available', lambda self: False)
    db = mod.IBLUsageDB()
    seed = db.add_example('기존 씨앗', '[self:time]', source='manual_seed')
    first = db.add_example('부분 절차', SEARCH, source='distilled_component', provenance={'task_id': 'fixture'})
    second = db.add_example('부분 절차 2', CRAWL, source='distilled_component')
    with db._get_connection() as conn:
        assert json.loads(conn.execute('SELECT provenance FROM ibl_examples WHERE id=?', (first,)).fetchone()[0]) == {'task_id': 'fixture'}
    stats = db.consolidate_distilled(cap=1)
    assert stats['distilled'] == 2 and stats['pruned_cap'] == 1
    assert {r['id'] for r in value.known_examples(db)} == {seed, second}


def test_release_copy_keeps_private_provenance_local(monkeypatch, tmp_path):
    import importlib.util
    import sqlite3
    import zipfile
    from pathlib import Path
    spec = importlib.util.spec_from_file_location('distill_test_publish',
        Path(__file__).resolve().parents[1] / 'scripts/publish_hippocampus.py')
    publisher = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(publisher)
    monkeypatch.setattr(publisher, 'DATA', tmp_path)
    monkeypatch.setattr(publisher, '_iter_model_files', lambda: [])
    with sqlite3.connect(tmp_path / 'ibl_usage.db') as conn:
        conn.execute('CREATE TABLE ibl_examples (ibl_code TEXT, provenance TEXT)')
        conn.execute('INSERT INTO ibl_examples VALUES (?, ?)', (SEARCH, '{"task_id":"private-task"}'))
    (tmp_path / 'training').mkdir()
    original = json.dumps([{'ibl_code': SEARCH, 'provenance': {'task_id': 'private-task'}}])
    (tmp_path / 'training/ibl_distilled.json').write_text(original)
    archive = tmp_path / 'public.zip'
    assert publisher.build_zip(archive) == 2
    with zipfile.ZipFile(archive) as bundle:
        assert b'private-task' not in bundle.read('ibl_usage.db')
        assert 'provenance' not in json.loads(bundle.read('training/ibl_distilled.json'))[0]
    with sqlite3.connect(tmp_path / 'ibl_usage.db') as conn:
        assert 'private-task' in conn.execute('SELECT provenance FROM ibl_examples').fetchone()[0]
    assert (tmp_path / 'training/ibl_distilled.json').read_text() == original


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
