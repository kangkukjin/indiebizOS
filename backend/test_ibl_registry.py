"""공개 사전의 단일 소스와 API 등록부 통합의 기능 보존 계약."""
import copy
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

import boot_paths  # noqa: F401
import ibl_registry as registry

ROOT = Path(__file__).resolve().parents[1]
PACKAGES = ROOT / 'data/packages/installed/tools'
RETIRED = {
    'search_legal', 'detail', 'laws', 'law_detail', 'precedents', 'precedent_detail',
    'search_kosis', 'data', 'info', 'integrated', 'indicators', 'restaurants_combined',
    'kstartup', 'mss', 'us_quote', 'us_search', 'us_metrics', 'us_income', 'us_balance',
    'us_cashflow', 'finnhub_profile', 'price_target', 'recommendations', 'market_news',
    'semantic_scholar', 'openalex', 'pubmed', 'guardian_news', 'books', 'naver_local',
    'house_trade', 'house_rent',
}


def handler(package):
    path = PACKAGES / package / 'handler.py'
    spec = importlib.util.spec_from_file_location('registry_test_' + package.replace('-', '_'), path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_installed_and_catalog_cannot_resurrect_api_actions(tmp_path, monkeypatch):
    """새 연결 정의가 낡은 node를 가져도 실행·UI·회상 소유에 침투하지 않는다."""
    import asyncio
    import api_ibl
    import runtime_utils
    import vocabulary_state
    source = {'nodes': {'sense': {'actions': {'paper': {
        'router': 'handler', 'tool': 'paper_op', 'group': 'research',
    }}}}}
    path = tmp_path / 'ibl_nodes.yaml'
    path.write_text(yaml.safe_dump(source))
    monkeypatch.setattr(registry, '_nodes_path', path)
    monkeypatch.setattr(registry, '_nodes', None)
    monkeypatch.setattr(registry, '_nodes_revision', None)
    monkeypatch.setattr(registry, '_registry', {'tools': {'hidden': {
        'node': 'sense', 'action_name': 'ghost', 'description': 'must remain private',
    }}})
    monkeypatch.setattr(runtime_utils, 'get_base_path', lambda: tmp_path)
    monkeypatch.setattr(runtime_utils, 'detect_body', lambda: {'profile': 'pc'})
    monkeypatch.setattr(vocabulary_state, 'revision', lambda: 1)
    monkeypatch.setattr(vocabulary_state, 'action_reason', lambda *args: None)
    assert registry.load_nodes_installed() == source
    catalog = asyncio.run(api_ibl.get_actions_catalog())
    assert set(catalog['nodes']['sense']['actions']) == {'paper'}
    assert not registry.code_is_own('[sense:ghost]{}')
    assert not registry.code_is_owned('[sense:ghost]{}')
    assert registry.get_tool_config('hidden')['action_name'] == 'ghost'
    # 같은 소유·활성 관문을 통과해야 하며 API 이름으로 재등장할 수 없다.
    monkeypatch.setattr(vocabulary_state, 'action_reason', lambda *args: '잠들어 있음')
    registry.invalidate_nodes()
    assert registry.load_nodes_installed()['nodes']['sense']['actions'] == {}


def test_all_32_extra_actions_are_absent_from_sources_and_registry():
    source = yaml.safe_load((ROOT / 'data/ibl_nodes.yaml').read_text())['nodes']['sense']['actions']
    assert len(RETIRED) == 32
    assert not RETIRED.intersection(source)
    connections = yaml.safe_load((ROOT / 'data/api_registry.yaml').read_text())['tools']
    assert all('node' not in cfg and 'action_name' not in cfg for cfg in connections.values())
    assert {'paper', 'realty', 'stock', 'company', 'kosis', 'legal', 'place', 'book',
            'search', 'startup', 'restaurant', 'world_bank', 'reverse_geocode', 'crypto'} <= source.keys()
    assert {'price_target', 'recommendations', 'market_news'} <= source['stock']['ops']['values'].keys()
    assert 'metrics' in source['company']['ops']['values']
    assert 'list' in source['kosis']['ops']['values']


def test_build_rejects_implicit_api_bindings(tmp_path):
    sys.path.insert(0, str(ROOT / 'scripts'))
    from iblbuild_guards import check_api_registry_bindings
    (tmp_path / 'data').mkdir()
    path = tmp_path / 'data/api_registry.yaml'
    path.write_text('tools: {hidden: {node: sense, action_name: ghost}}')
    assert len(check_api_registry_bindings(tmp_path)) == 1
    path.write_text('tools: {hidden: {service: example, endpoint: /query}}')
    assert check_api_registry_bindings(tmp_path) == []


@pytest.mark.parametrize('tool,params,expected,forwarded', [
    ('stock_op', {'op': 'price_target', 'ticker': 'AAPL'}, 'finnhub_price_target', {'symbol': 'AAPL'}),
    ('stock_op', {'op': 'recommendations', 'ticker': 'AAPL'}, 'finnhub_recommendations', {'symbol': 'AAPL'}),
    ('stock_op', {'op': 'market_news', 'category': 'forex'}, 'finnhub_market_news', {'category': 'forex'}),
    ('company_op', {'op': 'profile', 'source': 'finnhub', 'ticker': 'AAPL'}, 'finnhub_company_profile', {'symbol': 'AAPL'}),
    ('company_op', {'op': 'metrics', 'ticker': 'AAPL', 'period': 'quarter', 'limit': 2}, 'us_key_metrics', {'symbol': 'AAPL', 'period': 'quarter', 'limit': 2}),
])
def test_investment_preserves_internal_endpoints_and_rows(monkeypatch, tool, params, expected, forwarded):
    import api_engine
    h = handler('investment')
    calls = []
    rows = [{'symbol': 'AAPL', 'observed': 42}, {'symbol': 'AAPL', 'observed': 43}]
    def execute(name, inputs, path):
        calls.append((name, inputs))
        return {'success': True, 'data': copy.deepcopy(rows), 'source': 'fixture'}
    monkeypatch.setattr(api_engine, 'execute_tool', execute)
    result = h.execute(dict(params), SimpleNamespace(tool_name=tool))
    assert calls == [(expected, forwarded)]
    assert result['items'] == result['data'] == rows
    assert result['source'] == 'fixture'


@pytest.mark.parametrize('reply', [
    {'success': False, 'error': 'permission denied'}, {'error': 'network'},
    {'success': True, 'data': []}, {'success': True, 'data': {'target_mean': 123}},
])
def test_registry_currency_keeps_failure_empty_and_single_row(monkeypatch, reply):
    import api_engine
    h = handler('investment')
    monkeypatch.setattr(api_engine, 'execute_tool', lambda *args: copy.deepcopy(reply))
    result = h._registry_items('finnhub_price_target', {})
    if 'error' in reply:
        assert result == reply
    else:
        assert result['items'] == ([] if reply['data'] == [] else [reply['data']])
        assert result['data'] == reply['data']


@pytest.mark.parametrize('tool,params', [
    ('stock_op', {'op': 'price_target'}), ('stock_op', {'op': 'recommendations'}),
    ('stock_op', {'op': 'market_news', 'category': 'unknown'}),
    ('company_op', {'op': 'metrics', 'ticker': '005930'}),
    ('company_op', {'op': 'profile', 'source': 'unknown', 'ticker': 'AAPL'}),
])
def test_invalid_preserved_branches_do_not_call_api(monkeypatch, tool, params):
    h = handler('investment')
    monkeypatch.setattr(h, '_registry_items', lambda *args: pytest.fail('unexpected API call'))
    assert h.execute(params, SimpleNamespace(tool_name=tool)).get('error')


def test_kosis_list_and_existing_lookup_branches(monkeypatch):
    h = handler('kosis')
    calls = []
    def fn(name):
        def run(**kwargs):
            calls.append((name, kwargs))
            return {'items': [{'called': name}]}
        return run
    api = SimpleNamespace(**{name: fn(name) for name in (
        'search_statistics', 'integrated_search', 'get_statistics_data',
        'get_statistics_info', 'get_indicators')})
    monkeypatch.setattr(h, 'load_module', lambda name: api)
    ctx = SimpleNamespace(tool_name='kosis_lookup')
    result = h.execute({'op': 'list', 'query': '인구', 'vw_cd': 'MT_ZTITLE', 'parent_list_id': 'A'}, ctx)
    assert calls[-1] == ('search_statistics', {'keyword': '인구', 'vw_cd': 'MT_ZTITLE', 'parent_list_id': 'A'})
    assert result['items'] == [{'called': 'search_statistics'}]
    for args, name in [({'query': '인구'}, 'integrated_search'),
                       ({'org_id': '101', 'tbl_id': 'T'}, 'get_statistics_data'),
                       ({'org_id': '101', 'tbl_id': 'T', 'info': True}, 'get_statistics_info'),
                       ({'indicator': ''}, 'get_indicators')]:
        assert h.execute(args, ctx)['items'][0]['called'] == name
    assert h.execute({'op': 'unknown', 'query': '인구'}, ctx).get('error')


def test_place_naver_preserves_rows_and_rejects_unsupported_filters(monkeypatch):
    h = handler('location-services')
    calls = []
    def search(query, display, sort):
        calls.append((query, display, sort))
        return {'restaurants': [{'name': '도서관', 'lat': 37.5, 'lng': 127}], 'total': 1}
    monkeypatch.setattr(h, 'search_naver_local', search)
    ctx = SimpleNamespace(tool_name='search_place')
    result = json.loads(h.execute({'source': 'naver', 'query': '도서관', 'limit': 3, 'sort': 'comment'}, ctx))
    assert calls == [('도서관', 3, 'comment')]
    assert result['items'] == result['restaurants']
    for extra in ({'radius': 1000}, {'sort': 'distance'}, {'op': 'detail'}):
        assert json.loads(h.execute({'source': 'naver', 'query': '도서관', **extra}, ctx)).get('error')
    assert len(calls) == 1
    monkeypatch.setattr(h, '_load_place', lambda: SimpleNamespace(place_search=lambda p: {'items': [{'source': 'kakao'}]}))
    assert json.loads(h.execute({'query': '도서관'}, ctx))['items'] == [{'source': 'kakao'}]


def test_kosis_empty_list_is_empty_currency(monkeypatch):
    h = handler('kosis')
    api = SimpleNamespace(search_statistics=lambda **kwargs: {'success': True, 'data': []})
    monkeypatch.setattr(h, 'load_module', lambda name: api)
    assert h.execute({'op': 'list'}, SimpleNamespace(tool_name='kosis_lookup'))['items'] == []


@pytest.mark.parametrize('action,params', [
    ('stock', {'op': 'price_target'}), ('stock', {'op': 'recommendations'}),
    ('stock', {'op': 'market_news'}), ('company', {'op': 'profile', 'source': 'finnhub'}),
    ('kosis', {'op': 'list'}), ('place', {'source': 'naver'}),
])
def test_new_branches_do_not_borrow_baseline_columns(monkeypatch, action, params):
    import ibl_typecheck
    import ibl_access
    config = yaml.safe_load((ROOT / 'data/ibl_nodes.yaml').read_text())['nodes']['sense']['actions'][action]
    monkeypatch.setattr(ibl_typecheck, '_action_def', lambda *args: config)
    monkeypatch.setattr(ibl_access, '_return_shapes', lambda: {
        'sense:' + action: {'kind': 'items', 'keys': ['baseline_only'], 'source': 'fixture'},
    })
    assert ibl_typecheck.catalog_entry('sense', action, params) is None


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
