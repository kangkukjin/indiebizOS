"""Danawa's public search entry point and result boundary regressions."""
import boot_paths  # noqa: F401
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_tool():
    path = ROOT / 'data/packages/installed/tools/shopping-assistant/tool_danawa.py'
    spec = importlib.util.spec_from_file_location('danawa_regression', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def card(number, title):
    return f'''<li id="productItem{number}" class="prod_item"><div class="prod_main_info">
    <p class="prod_name"><a href="https://prod.danawa.com/info/?pcode={number}">{title}</a></p>
    <p class="price_sect"><a><strong>49,800</strong></a></p>
    <div class="spec_list">분리형 / 다이얼식</div></div></li>'''


@pytest.mark.parametrize('query', ['전기쿠커 타이머', '무선 키보드'])
def test_search_uses_public_query_route_not_legacy_ui_route(monkeypatch, query):
    module = load_tool()
    requests = []

    def fetch(params):
        requests.append(params.copy())
        # 2026-10-20: any of sort=saveDESC, list=list, tab=main selects
        # a shell without SSR product cards; bare query returns the cards.
        if any(key in params for key in ('sort', 'list', 'tab')):
            return '<html><title>검색</title><div id="productListArea"></div></html>'
        assert params['query'] == query
        return '<ul class="product_list">' + card(11, '시험 상품') + card(12, '다른 상품') + '</ul>'

    monkeypatch.setattr(module, '_fetch', fetch)
    result = module.search_danawa(query, limit=1)
    assert len(result['items']) == 1
    assert result['items'][0]['name'] == '시험 상품'
    assert result['items'][0]['link'].endswith('pcode=11')
    assert result['items'][0]['price'] == '49800'
    assert len(requests) == 1  # no browser/duplicate network retry required


def test_empty_response_and_unrecognized_markup_remain_distinct(monkeypatch):
    module = load_tool()
    monkeypatch.setattr(module, '_fetch', lambda _: '<div id="nosearchArea"></div>')
    assert module.search_danawa('없는 상품')['empty_reason'] == 'no_results'
    monkeypatch.setattr(module, '_fetch', lambda _: '<html>unknown layout</html>')
    result = module.search_danawa('상품')
    assert result['success'] is False
    assert result['error_type'] == 'source_changed'


def test_network_failure_is_not_reported_as_empty(monkeypatch):
    module = load_tool()
    def failed(_):
        raise RuntimeError('HTTP 503')
    monkeypatch.setattr(module, '_fetch', failed)
    with pytest.raises(RuntimeError, match='503'):
        module.search_danawa('상품')


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
