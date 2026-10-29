"""가격비교 원천의 범위·실패·표시 가격 계약. 네트워크 없이 수집 응답을 검증한다."""
import boot_paths  # noqa: F401
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

TOOLS = Path(__file__).resolve().parents[1] / "data/packages/installed/tools/shopping-assistant"


def module(name):
    spec = importlib.util.spec_from_file_location("shopping_test_" + name, TOOLS / (name + ".py"))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def card(code="123", price="12,345", name="밥솥", link="https://prod.danawa.com/info/?pcode=123"):
    price_html = f'<p class="price_sect"><a><strong>{price}</strong></a></p>' if price is not None else ""
    return (f'<li id="productItem{code}"><p class="prod_name"><a href="{link}">{name}</a></p>'
            f'<ul><li>{price_html}</li></ul><div class="spec_list">6인용 &amp; IH</div></li>')


def enuri_doc(rows, query="밥솥"):
    return '<script type="application/ld+json">' + json.dumps({
        "@type": "ItemList", "name": query + " 검색결과", "itemListElement": rows,
    }, ensure_ascii=False) + '</script>'


def product(price=150000):
    return {"@type": "ListItem", "item": {
        "@type": "Product", "name": "밥솥", "sku": "123",
        "url": "https://price.enuri.com/catalog/123",
        "offers": {"@type": "AggregateOffer", "lowPrice": price,
                   "priceCurrency": "KRW", "offerCount": 12},
    }}


def test_danawa_no_price_does_not_borrow_next_card_or_footer():
    mod = module("tool_danawa")
    html = card(price=None) + card("ABC_456", "1", "밥솥 렌탈") + '<p class="price_sect"><strong>999</strong></p>'
    result = mod.parse_danawa(html)
    assert len(result["items"]) == 2
    first, rental = result["items"]
    assert first["price"] is None and first["price_status"] == "unknown"
    assert rental["price"] == "1" and rental["rental_hint"] is True
    assert first["spec"] == "6인용 & IH"
    assert first["shipping_included"] is None


@pytest.mark.parametrize("price", [None, "0", "품절", "문의", "12개월"])
def test_danawa_unknown_price_is_not_zero(price):
    result = module("tool_danawa").parse_danawa(card(price=price))
    assert result["items"][0]["price"] is None


def test_danawa_params_keep_page_and_default_route(monkeypatch):
    mod = module("tool_danawa")
    seen = []
    monkeypatch.setattr(mod, "_fetch", lambda params: seen.append(params) or card())
    result = mod.search_danawa("밥솥 & 쌀", 1, 3)
    assert seen[0] == {"query": "밥솥 & 쌀", "page": 3}
    assert result["page"] == 3 and result["total"] == 1
    assert result["items"][0]["price"] == "12345"
    assert "%26" in result["source_url"] and result["observed_at"]


@pytest.mark.parametrize("kwargs", [{"limit": 0}, {"limit": 41}, {"page": True}, {"page": 101}, {"sort": "fake"}])
def test_danawa_invalid_options_do_not_fetch(monkeypatch, kwargs):
    mod = module("tool_danawa")
    monkeypatch.setattr(mod, "_fetch", lambda params: pytest.fail("invalid input fetched"))
    assert mod.search_danawa("밥솥", **kwargs)["success"] is False


def test_danawa_bad_card_is_partial_not_normal_empty():
    mod = module("tool_danawa")
    result = mod.parse_danawa(card() + card("456", name="", price="100"))
    assert len(result["items"]) == 1
    assert result["truncations"][0]["scope"] == "source"
    assert mod.parse_danawa('<html>captcha</html>')["success"] is False
    assert mod.parse_danawa('<div id="nosearchArea"></div>')["empty_reason"] == "no_results"


def test_enuri_product_fields_and_limit():
    result = module("tool_enuri").parse_enuri(enuri_doc([product(), product(200000)]), "밥솥", 1)
    assert result["total"] == 1 and result["page_items"] == 2
    row = result["items"][0]
    assert row["price"] == "150000" and row["currency"] == "KRW"
    assert row["offer_count"] == 12 and row["price_basis"] == "aggregate_low"


def test_enuri_empty_search_does_not_pick_recommendations():
    mod = module("tool_enuri")
    html = enuri_doc([], "없는상품") + enuri_doc([product()], "인기상품")
    result = mod.parse_enuri(html, "없는상품")
    assert result["items"] == [] and result["empty_reason"] == "no_results"


@pytest.mark.parametrize("html", ['<html>blocked</html>', enuri_doc([product()], "다른검색"),
                                 '<script type="application/ld+json">{broken</script>'])
def test_enuri_missing_structure_is_failure(html):
    assert module("tool_enuri").parse_enuri(html, "밥솥")["error_type"] == "source_changed"


@pytest.mark.parametrize("price", [None, 0, False, "문의"])
def test_enuri_unknown_price(price):
    row = module("tool_enuri").parse_enuri(enuri_doc([product(price)]), "밥솥")["items"][0]
    assert row["price"] is None and row["price_status"] == "unknown"


def test_enuri_partial_preserves_valid_rows():
    bad = product()
    bad["item"]["url"] = "javascript:alert(1)"
    result = module("tool_enuri").parse_enuri(enuri_doc([product(), bad]), "밥솥")
    assert len(result["items"]) == 1 and result["truncations"][0]["count"] == 1


def test_enuri_current_detail_link_preserves_real_product_and_price():
    current = product(165700)
    current['item']['url'] = 'https://www.enuri.com/detail.jsp?modelno=137958691'
    result = module('tool_enuri').parse_enuri(enuri_doc([current]), '밥솥')
    assert result['total'] == 1 and 'truncations' not in result
    assert result['items'][0]['link'] == current['item']['url']
    assert result['items'][0]['price'] == '165700'


@pytest.mark.parametrize('url', ['https://www.enuri.com.evil.test/detail.jsp?modelno=123',
                               'https://www.enuri.com/detail.jsp',
                               'https://www.enuri.com/detail.jsp?modelno=abc',
                               'https://www.enuri.com/detail.jsp?modelno=1&modelno=2',
                               'https://user@www.enuri.com/detail.jsp?modelno=123',
                               'https://www.enuri.com/redirect?modelno=123'])
def test_enuri_detail_url_boundary_stays_closed(url):
    bad = product()
    bad['item']['url'] = url
    result = module('tool_enuri').parse_enuri(enuri_doc([bad]), '밥솥')
    assert result['items'] == [] and result['truncations'][0]['count'] == 1


@pytest.mark.parametrize("kwargs", [{"page": 2}, {"sort": "price_asc"}, {"limit": 41}])
def test_enuri_unsupported_options_do_not_fetch(monkeypatch, kwargs):
    mod = module("tool_enuri")
    monkeypatch.setattr(mod, "chrome_get", lambda *a, **k: pytest.fail("unsupported input fetched"))
    assert mod.search_enuri("밥솥", **kwargs)["success"] is False


def test_enuri_http_failure_is_not_empty(monkeypatch):
    mod = module("tool_enuri")
    monkeypatch.setattr(mod, "chrome_get", lambda *a, **k: SimpleNamespace(status_code=403))
    result = mod.search_enuri("밥솥")
    assert result["success"] is False and result["error_type"] == "http_error"


def test_handler_enuri_and_display_alias(monkeypatch):
    handler = module("handler")
    enuri = module("tool_enuri")
    monkeypatch.setattr(enuri, "chrome_get", lambda *a, **k: SimpleNamespace(
        status_code=200, text=enuri_doc([product(), product(200000)])))
    monkeypatch.setattr(handler, "_load_shopping_source", lambda name: enuri)
    result = json.loads(handler.execute({"query": "밥솥", "site": "enuri", "display": 1},
                                       SimpleNamespace(tool_name="search_shopping")))
    assert result["source"] == "enuri" and result["total"] == 1
    assert result["observed_at"] and result["price_note"]


def test_handler_default_danawa_and_naver_retirement(monkeypatch):
    handler = module("handler")
    seen = []

    async def fake(query, display, page, sort):
        seen.append((query, display, page, sort))
        return {"items": [], "total": 0, "empty_reason": "no_results"}

    monkeypatch.setattr(handler, "search_danawa_shopping_async", fake)
    context = SimpleNamespace(tool_name="search_shopping")
    assert json.loads(handler.execute({"query": "밥솥"}, context))["source"] == "danawa"
    assert seen == [("밥솥", 5, 1, "default")]
    assert json.loads(handler.execute({"query": "밥솥", "site": "naver"}, context))["success"] is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))


@pytest.mark.parametrize('modern', [False, True])
def test_browser_fallback_preserves_page_and_closes(monkeypatch, modern):
    import asyncio
    import sys
    handler = module("handler")
    danawa = module("tool_danawa")
    monkeypatch.setattr(danawa, "_fetch", lambda _: '<html>incomplete shell</html>')
    monkeypatch.setattr(handler, "_load_shopping_source", lambda _: danawa)
    seen = {}

    class Tab:
        async def goto(self, url, **kwargs):
            seen["url"] = url
            return SimpleNamespace(status=200)

        async def wait_for_selector(self, selector, **kwargs):
            pytest.fail('ready search data must not wait for an obsolete selector')

        async def content(self):
            if modern:
                entry = {'queryKey': ['search', 'productList', {'keyword': '밥솥', 'page': '2'}],
                         'state': {'status': 'success', 'data': {'kind': 'fetched', 'data': {
                             'products': [{'productName': '밥솥', 'linkUrl': 'https://prod.danawa.com/info/?pcode=1'}],
                             'page': {'current': 2}}}}}
                return '<script>self.__next_f.push(' + json.dumps([1, json.dumps({'queries': [entry]})]) + ')</script>'
            return card(price=None)

    class Browser:
        async def new_page(self):
            return Tab()

        async def close(self):
            seen["closed"] = True

    class Chromium:
        async def launch(self, **kwargs):
            return Browser()

    class Playwright:
        async def __aenter__(self):
            return SimpleNamespace(chromium=Chromium())

        async def __aexit__(self, *args):
            pass

    monkeypatch.setitem(sys.modules, "playwright.async_api", SimpleNamespace(async_playwright=Playwright))
    result = asyncio.run(handler.search_danawa_shopping_async("밥솥", 1, 2))
    assert result["transport"] == "browser" and result["page"] == 2
    assert "page=2" in seen["url"] and "sort=" not in seen["url"] and seen["closed"]
    assert result["items"][0]["price"] is None
    assert result["http_failure"]["error_type"] == "source_changed"


def test_partial_rows_propagate_through_ibl_adapter():
    from ibl_v2_adapters import decode_envelope
    from ibl_v2_ir import Fault
    raw = module("tool_danawa").parse_danawa(card() + card("bad", name=""))
    with pytest.raises(Fault) as caught:
        decode_envelope(raw, {"value_path": "items"})
    assert caught.value.code == "PARTIAL_SOURCE"
    assert len(caught.value.partial) == 1


def test_danawa_shell_retries_same_first_page(monkeypatch):
    mod = module("tool_danawa")
    requests = []
    def fetch(params):
        requests.append(params)
        return card() if params.get("page") == 1 else "<html>shell</html>"
    monkeypatch.setattr(mod, "_fetch", fetch)
    result = mod.search_danawa("밥솥", 1)
    assert requests == [{"query": "밥솥"}, {"query": "밥솥", "page": 1}]
    assert result["total"] == 1 and "page=1" in result["source_url"]
