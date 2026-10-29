"""Danawa's public search entry point and result boundary regressions."""
import boot_paths  # noqa: F401
import importlib.util
import json
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


def state_entry(products, query='여성 캐시미어 가디건', page=1, total=None):
    return {'queryKey': ['search', 'productList', {'keyword': query, 'page': str(page)}],
            'state': {'status': 'success', 'data': {'kind': 'fetched', 'data': {
                'products': products, 'page': {'current': page, 'total': 2},
                'count': {'total': len(products) if total is None else total}}}}}


def flight(entries, split=False):
    # 실제 공개 페이지의 Flight 문자열 내부 queries 배열. 텍스트 레코드는 JSON 앞에 붙는다.
    stream = '2c:T4,text15:' + json.dumps(['$', {'state': {'queries': entries}}], ensure_ascii=False)
    chunks = [stream[:len(stream)//2], stream[len(stream)//2:]] if split else [stream]
    return ''.join('<script>self.__next_f.push(' + json.dumps([1, chunk]) + ')</script>' for chunk in chunks)


def state_product(name='여성 <b>캐시미어</b> 가디건', price=250710):
    return {'productSeq': '123569801', 'productName': name, 'minPrice': price,
            'memberPrice': 999, 'totalPrice': 300000,
            'linkUrl': 'https://prod.danawa.com/info/?pcode=123569801&keyword=cardigan',
            'imageUrl': 'https://img.danuri.io/catalog-image/cardigan.jpg',
            'summary': {'desc': ['<b>여성</b>의류', '니트 &amp; 가디건']}}


def test_flight_search_reads_requested_page_without_ads_or_retries(monkeypatch):
    tool = load_tool()
    ads = state_entry([state_product('광고', 1)])
    ads['queryKey'][1] = 'adLeader'
    html = flight([ads, state_entry([state_product('다른검색', 2)], query='다른검색'),
                   state_entry([state_product(), state_product('가격 미확인', None)], page=2)], split=True)
    calls = []
    monkeypatch.setattr(tool, '_fetch', lambda params: calls.append(params) or html)
    out = tool.search_danawa('여성 캐시미어 가디건', limit=2, page=2)
    assert len(calls) == 1 and out['page_items'] == 2 and out['page'] == 2
    a, b = out['items']
    assert a['name'] == '여성 캐시미어 가디건' and a['price'] == '250710'
    assert a['spec'] == '여성의류 / 니트 & 가디건'
    assert a['shipping_included'] is None and b['price'] is None
    assert b['price_status'] == 'unknown'


@pytest.mark.parametrize('entry', [state_entry([], total=49), state_entry([], query='다른검색'),
                                  state_entry([], page=2), {'queryKey': ['search', 'productList', None]}])
def test_flight_incomplete_or_wrong_scope_is_not_empty(entry):
    out = load_tool().parse_danawa(flight([entry]), query='여성 캐시미어 가디건')
    assert out['success'] is False and out['error_type'] == 'source_changed'


def test_flight_confirmed_empty_excludes_other_lists():
    out = load_tool().parse_danawa(flight([state_entry([]), state_entry([state_product()], query='추천')]),
                                   query='여성 캐시미어 가디건')
    assert out['empty_reason'] == 'no_results' and not out['items']


def test_flight_bad_product_preserves_partial_rows():
    out = load_tool().parse_danawa(flight([state_entry([state_product(), {'productName': 'bad'}])]),
                                   query='여성 캐시미어 가디건')
    assert len(out['items']) == 1
    assert out['truncations'] == [{'scope': 'source', 'reason': 'invalid_product', 'count': 1}]


@pytest.mark.parametrize('price', [0, False, None, '문의', '1.5', -1])
def test_flight_unknown_price_is_not_free_or_member_price(price):
    out = load_tool().parse_danawa(flight([state_entry([state_product(price=price)])]),
                                   query='여성 캐시미어 가디건')
    assert out['items'][0]['price'] is None


def test_flight_code_or_broken_json_is_never_evaluated():
    for text in ['self.__next_f.push((globalThis.touched=true))', 'self.__next_f.push([1,"broken])']:
        assert load_tool().parse_danawa('<script>' + text + '</script>')['success'] is False


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
