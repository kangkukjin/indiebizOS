"""추가 관용구 3개: AI 없는 본문, 결과·실패 보존, 상시 노출 계약."""
import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest
import boot_paths  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from idiom_experiment_worker import run_trial
from idiom_experiment_cases import decoded

CATALOG = json.loads((ROOT / 'data/idioms/curated.json').read_text())
NEW = {'미처리만고르기', '묶어순위내기', '주소마다읽기'}
# 이 선정집에서 실측한 비-AI 원시의 닫힌 집합. 동적 fn/script/AI 술어는 인증하지 않는다.
LEAVES = {'table:dedup', 'table:join', 'table:groupby', 'table:sort',
          'table:take', 'table:each', 'sense:crawl'}


def run(code):
    trial = run_trial(code, 'dedup')
    assert trial['result']['success'], trial['result'].get('error')
    assert trial['observed']['brief'] == 0
    assert set(trial['observed']['leaf_calls']) <= LEAVES | {'self:read', 'self:write'}
    return decoded(trial['result']['final_result']), trial['observed']


def test_new_bodies_are_closed_non_ai_procedures():
    from ibl_parser import parse_function_body
    for e in CATALOG['idioms']:
        if e['name'] not in NEW:
            continue
        assert e.get('always_on') is True
        parse_function_body(e['body'])
        actions = set(re.findall(r'\[([a-z_]+:[a-z_]+)', e['body']))
        assert actions and actions <= LEAVES
        assert not re.search(r'\b(criteria|instruction|prompt|do)\s*:', e['body'])
        assert '[goal' not in e['body'] and '[if' not in e['body']


def test_unprocessed_composite_keys_keep_first_candidate_and_original_columns():
    result, _ = run('$후보=[{id:1,kind:"a",값:"기존"},{id:1,kind:"b",값:"첫째"},'
                    '{id:1,kind:"b",값:"중복"},{id:2,kind:"a",값:"둘째"}]; '
                    '$완료=[{id:1,kind:"a"},{id:1,kind:"a"}]; '
                    '[fn:미처리만고르기]{후보:$후보,처리됨:$완료,키:["id","kind"]}')
    assert result['items'] == [{'id': 1, 'kind': 'b', '값': '첫째'}, {'id': 2, 'kind': 'a', '값': '둘째'}]


@pytest.mark.parametrize('candidates,done,expected', [
    ([], [{'id': 1}], []), ([{'id': 1}, {'id': 1}], [], [{'id': 1}]),
    ([{'id': 1}], [{'id': 1}], []), ([], [], []),
])
def test_unprocessed_empty_and_all_processed(candidates, done, expected):
    result, _ = run('$후보=' + json.dumps(candidates) + '; $완료=' + json.dumps(done) + '; '
                    '[fn:미처리만고르기]{후보:$후보,처리됨:$완료,키:"id"}')
    assert result['items'] == expected


def test_grouped_ranking_composite_keys_and_counts():
    result, _ = run('$목록=[{부서:"가",항목:"교통",금액:10},{부서:"가",항목:"교통",금액:30},'
                    '{부서:"가",항목:"식비",금액:50},{부서:"나",항목:"교통",금액:5}]; '
                    '[fn:묶어순위내기]{목록:$목록,묶음:["부서","항목"],값열:"금액",개수:2}')
    assert result['items'] == [{'부서': '가', '항목': '식비', '합계': 50, '건수': 1},
                               {'부서': '가', '항목': '교통', '합계': 40, '건수': 2}]


def test_grouped_ranking_does_not_invent_numbers_for_missing_values():
    result, _ = run('$목록=[{종류:"가",값:10},{종류:"가",값:null},{종류:"가",값:"미상"},'
                    '{종류:"나",값:null}]; '
                    '[fn:묶어순위내기]{목록:$목록,묶음:"종류",값열:"값",개수:10}')
    rows = {r['종류']: r for r in result['items']}
    assert rows['가']['합계'] == 10 and rows['가']['건수'] == 3
    assert rows['나']['합계'] is None


@pytest.mark.parametrize('code', [
    '$목록=[]; [fn:묶어순위내기]{목록:$목록,묶음:"종류",값열:"값",개수:5}',
    '$목록=[{종류:"가",값:1}]; [fn:묶어순위내기]{목록:$목록,묶음:"종류",값열:"값",개수:0}',
    '$목록=[]; [fn:주소마다읽기]{목록:$목록,개수:5}',
    '$목록=[self:read]{path:"input.json"}; [fn:주소마다읽기]{목록:$목록,개수:0}',
])
def test_empty_results_do_not_expand_into_full_read(code):
    result, observed = run(code)
    assert result['items'] == [] and observed['crawl'] == []


def test_url_gather_preserves_raw_text_sources_and_failures_without_summary():
    result, observed = run('$목록=[self:read]{path:"input.json"}; [fn:주소마다읽기]{목록:$목록,개수:3}')
    assert sorted(observed['crawl']) == ['https://fixture.test/a', 'https://fixture.test/bad', 'https://fixture.test/c']
    assert [(r['title'], r['url']) for r in result['items']] == [
        ('first', 'https://fixture.test/a'), ('broken', 'https://fixture.test/bad'), ('third', 'https://fixture.test/c')]
    assert result['items'][0]['text'] == 'SOURCE:https://fixture.test/a'
    assert result['items'][1]['_error'] and result['error_count'] == 1


def test_unprocessed_then_raw_read_composes_by_named_results():
    result, observed = run('$후보=[self:read]{path:"input.json"}; $완료=[{url:"https://fixture.test/a"}]; '
                          '$새것=[fn:미처리만고르기]{후보:$후보,처리됨:$완료,키:"url"}; '
                          '[fn:주소마다읽기]{목록:$새것,개수:2}')
    assert observed['fn_calls'] == ['미처리만고르기', '주소마다읽기']
    assert observed['crawl'] == ['https://fixture.test/bad', 'https://fixture.test/c']
    assert len(result['items']) == 2


def test_crawl_handler_converts_raw_paragraphs_without_model_call(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from idiom_experiment_worker import load
    from tool_context import ToolContext
    import consciousness_agent
    import oneshot_facade
    def forbidden(*args, **kwargs):
        pytest.fail('원문 수집 경로가 모델을 호출했다')
    monkeypatch.setattr(consciousness_agent, 'oneshot_ai_call', forbidden)
    monkeypatch.setattr(oneshot_facade, 'execution_oneshot', forbidden)
    handler = load('_idiom_raw_web', ROOT / 'data/packages/installed/tools/web/handler.py')
    original_loader = handler.load_module
    crawler = SimpleNamespace(crawl_website=lambda url, max_length, **kwargs:
                              {'success': True, 'title': '제목', 'text': '첫 문단\n\n둘째 문단'})
    monkeypatch.setattr(handler, 'load_module', lambda name:
                        crawler if name == 'tool_webcrawl' else original_loader(name))
    result = decoded(handler.execute({'url': 'https://fixture.test/a'}, ToolContext(str(tmp_path), 'crawl_website')))
    assert result['items'] == [{'type': 'heading', 'level': 1, 'text': '제목'},
                               {'type': 'paragraph', 'text': '첫 문단'}, {'type': 'paragraph', 'text': '둘째 문단'}]


def test_all_six_exposed_in_map_and_leaf_actions_with_scope_filter(tmp_path, monkeypatch):
    import ibl_access
    import runtime_utils
    from ibl_usage_db import _signature_of
    from ibl_typecheck import return_type_of
    (tmp_path / 'data/idioms').mkdir(parents=True)
    (tmp_path / 'data/idioms/curated.json').write_text(json.dumps(CATALOG, ensure_ascii=False))
    entries = [e for e in CATALOG['idioms'] if e.get('always_on', True)]
    with sqlite3.connect(tmp_path / 'data/ibl_usage.db') as con:
        con.execute('CREATE TABLE ibl_examples (intent,ibl_code,success_count,fail_count,topic,alias,returns,signature,always_on,created_at)')
        for e in entries:
            con.execute('INSERT INTO ibl_examples VALUES (?,?,?,?,?,?,?,?,?,?)',
                        (e['when'], e['body'], 0, 0, e['topic'], e['name'], return_type_of(e['body']),
                         _signature_of(e['body']), 1, '2026-09-09'))
    monkeypatch.setattr(runtime_utils, 'get_base_path', lambda: tmp_path)
    monkeypatch.setattr(ibl_access, '_get_nodes_path', lambda: ROOT / 'data/ibl_nodes.yaml')
    monkeypatch.setattr(ibl_access, '_idioms_cache', {'text': None, 't': 0, 'key': None, 'anchors': {}})
    env = ibl_access.build_environment()
    assert env.count('↳ 관용구') == 6
    for e in entries:
        assert f"[fn:{e['name']}]" in ibl_access.idioms_map(None)
    core = ibl_access.build_environment(allowed_nodes=['self', 'others', 'table'])
    assert '[fn:주소마다읽기]' not in core and '[fn:묶어순위내기]' in core
    hidden = ibl_access.build_environment(expose_idioms=False)
    assert '↳ 관용구' not in hidden and '<ibl_idioms' not in hidden


def test_explicit_reload_invalidates_idiom_map_and_leaf_lines(monkeypatch):
    import ibl_access
    import node_registry
    monkeypatch.setattr(node_registry, 'invalidate_node_cache', lambda: None)
    monkeypatch.setattr(ibl_access, '_idioms_cache',
                        {'text': '옛 지도', 't': 9999999999, 'key': None, 'anchors': {'self:read': ['옛 이름']}})
    ibl_access.invalidate_nodes_cache()
    assert ibl_access._idioms_cache['text'] is None
    assert ibl_access._idioms_cache['anchors'] == {}


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
