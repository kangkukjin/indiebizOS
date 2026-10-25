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
# 스크립트는 일반 인증하지 않는다. 예외는 판정관용구의 모델 없는 두 op 뿐(3ded991b):
# urls(주소 문자열 그대로 중복 제거)·finish(실패·잘림 합산). 판정 op(prepare·select)는 불허.
SCRIPT_CALL = re.compile(r'\[self:script\]\{op:"run",id:"([^"]+)",args:\{op:"([a-z_]+)"')
PURE_SCRIPT_OPS = {('판정관용구', 'urls'), ('판정관용구', 'finish')}


def run(code):
    trial = run_trial(code, 'dedup')
    assert trial['result']['success'], trial['result'].get('error')
    assert trial['observed']['brief'] == 0
    assert set(trial['observed']['leaf_calls']) <= LEAVES | {'self:read', 'self:write', 'self:script'}
    return decoded(trial['result']['final_result']), trial['observed']


def test_new_bodies_are_closed_non_ai_procedures():
    from ibl_parser import parse_function_body
    for e in CATALOG['idioms']:
        if e['name'] not in NEW:
            continue
        # 본문 계약은 상시 노출 선정과 독립적이다. 내려간 관용구도 호출 가능하다.
        parse_function_body(e['body'])
        actions = set(re.findall(r'\[([a-z_]+:[a-z_]+)', e['body']))
        scripts = set(SCRIPT_CALL.findall(e['body']))
        assert scripts <= PURE_SCRIPT_OPS
        assert e['body'].count('[self:script]') == len(SCRIPT_CALL.findall(e['body']))
        actions.discard('self:script')
        assert actions and actions <= LEAVES
        assert not re.search(r'\b(criteria|instruction|prompt|do)\s*:', e['body'])
        assert '[goal' not in e['body'] and '[if' not in e['body']
















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


@pytest.mark.parametrize('compact', [False, True])
def test_selected_idioms_exposed_in_map_and_leaf_actions_with_scope_filter(tmp_path, monkeypatch, compact):
    import ibl_v2_adapters
    current_registry=ibl_v2_adapters.load_registry()
    monkeypatch.setattr(ibl_v2_adapters,'load_registry',lambda *a,**k:current_registry)
    import ibl_access
    import runtime_utils
    from ibl_usage_db import _signature_of
    from ibl_typecheck import return_type_of
    from test_function_support import current_source
    import copy
    catalog=copy.deepcopy(CATALOG)
    for entry in catalog['idioms']:
        if entry.get('always_on',True):
            entry['body']=current_source(entry['name'])
    (tmp_path / 'data/idioms').mkdir(parents=True)
    (tmp_path / 'data/idioms/curated.json').write_text(json.dumps(catalog, ensure_ascii=False))
    entries = [e for e in catalog['idioms'] if e.get('always_on', True)]
    with sqlite3.connect(tmp_path / 'data/ibl_usage.db') as con:
        con.execute('CREATE TABLE ibl_examples (intent,ibl_code,success_count,fail_count,topic,alias,returns,signature,always_on,created_at)')
        for e in entries:
            con.execute('INSERT INTO ibl_examples VALUES (?,?,?,?,?,?,?,?,?,?)',
                        (e['when'], e['body'], 0, 0, e['topic'], e['name'], return_type_of(e['body']),
                         _signature_of(e['body']), 1, '2026-09-09'))
    monkeypatch.setattr(runtime_utils, 'get_base_path', lambda: tmp_path)
    monkeypatch.setattr(ibl_access, '_get_nodes_path', lambda: ROOT / 'data/ibl_nodes.yaml')
    monkeypatch.setattr(ibl_access, '_idioms_cache', {'text': None, 't': 0, 'key': None, 'anchors': {}})
    from test_function_support import import_memory
    with sqlite3.connect(tmp_path / 'data/ibl_usage.db') as fixture_db:
        import_memory(fixture_db)
    env = ibl_access.build_environment(compact=compact)
    assert env.count('↳ 관용구') == len(entries)
    for e in entries:
        assert f"[fn:{e['name']}]" in ibl_access.idioms_map(None)
    for name in ('원장에누적', '위치마다읽기', '최신범위읽기', '묶어순위내기',
                 '고치고확인하기', '미처리만고르기'):
        assert f'[fn:{name}]' not in env
    assert '[fn:좁혀서읽기]' in env
    core = ibl_access.build_environment(allowed_nodes=['self', 'others', 'table'])
    assert '[fn:주소마다읽기]' not in core and '[fn:열추려보기]' in core
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
