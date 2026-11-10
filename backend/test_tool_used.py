"""Public marketplace adapter contracts, including cursor and incomplete sources."""
import json

import boot_paths  # noqa: F401
import pytest
from test_shopping_sources import module

def product(pid=1, **fields):
    return {"type": "PRODUCT", "pid": pid, "name": f"RAM {pid}", "price": 10000,
            "status": "SELLING", "productImage": "https://example.com/image_w{res}.jpg",
            **fields}


def response(rows, cursor=None, total=20):
    return {"data": {"responses": {"mainGrid": {"searchResponse": {
        "data": rows, "cursor": cursor, "totalCount": total}},
        "recProductList": {"searchRecProductResponse": {"recProducts": [product(999)]}}}}}


def source(monkeypatch, pages):
    mod, calls = module("tool_used"), []
    pages = iter(pages)

    def get(url, params=None):
        calls.append((url, params.copy()))
        value = next(pages)
        if isinstance(value, Exception):
            raise value
        return json.dumps(value), 200

    monkeypatch.setattr(mod, "_get", get)
    return mod, calls


def test_current_search_contract_filters_ads_and_maps_product_fields(monkeypatch):
    mod, calls = source(monkeypatch, [response([
        {"type": "EXT_AD", "name": "unrelated"}, product(3, ad=True),
        product(1, status="SOLD_OUT", location="청주"), product(2, status="RESERVED"),
        product(4, status="UNKNOWN"),
    ])])
    result = mod.search_bunjang("RAM & 4GB", limit=10)
    assert calls == [("https://api.bunjang.co.kr/api/search/v8/web/search", {
        "q": "RAM & 4GB", "policyKey": "pw.product.keyword", "sort": "latest", "size": 40})]
    assert [r["title"] for r in result["items"]] == ["RAM 1", "RAM 2", "RAM 4"]
    first, reserved, unknown = result["items"]
    assert first["sold"] is True and first["location"] == "청주" and first["price"] == 10000
    assert first["url"] == "https://m.bunjang.co.kr/products/1"
    assert first["image"] == "https://example.com/image_w320.jpg"
    assert reserved["sold"] is False and "예약중" in reserved["meta"]
    assert unknown["sold"] is None and unknown["location"] is None


def test_cursor_not_page_length_or_count_controls_pagination(monkeypatch):
    mod, calls = source(monkeypatch, [response([product(1)], "opaque+cursor=", total=1),
                                    response([product(1), product(2)], None)])
    result = mod.search_bunjang("RAM", limit=2)
    assert len(calls) == 2 and calls[1][1]["cursor"] == "opaque+cursor="
    assert [r["title"] for r in result["items"]] == ["RAM 1", "RAM 2"]
    assert "truncations" not in result


def test_real_empty_does_not_use_recommendations(monkeypatch):
    mod, calls = source(monkeypatch, [response([], total=0)])
    result = mod.search_bunjang("nonexistent")
    assert result["items"] == [] and result["total_estimate"] == 0
    assert "truncations" not in result and len(calls) == 1


@pytest.mark.parametrize("bad", [{}, {"data": None}, response(None), response([None]),
                                 response([], cursor={}), response([product(name="")]),
                                 response([product(type="RENAMED")])])
def test_missing_or_invalid_main_grid_is_failure_not_zero(monkeypatch, bad):
    mod, _ = source(monkeypatch, [bad])
    result = mod.search_bunjang("RAM")
    assert result["success"] is False and "원천 구조 변경" in result["error"]


def test_later_http_failure_preserves_rows(monkeypatch):
    mod, _ = source(monkeypatch, [response([product()], "next"), RuntimeError("HTTP 503")])
    result = mod.search_bunjang("RAM")
    assert result["total"] == 1 and result["truncated"]
    assert result["truncations"][0]["reason"] == "fetch_error"


def test_repeated_cursor_is_partial_not_silent_success(monkeypatch):
    mod, calls = source(monkeypatch, [response([product()], "same"),
                                    response([product(2)], "same")])
    result = mod.search_bunjang("RAM")
    assert len(calls) == 2 and result["total"] == 2 and result["truncated"]
    assert "커서가 반복" in result["truncations"][0]["error"]


def test_region_missing_locations_is_observed_and_scan_is_bounded(monkeypatch):
    pages = [response([product(p * 60 + i + 1) for i in range(60)], str(p + 1)) for p in range(4)]
    mod, calls = source(monkeypatch, pages)
    result = mod.search_bunjang("RAM", region="청주")
    assert len(calls) == 4  # source can ignore size=40 and return 60 rows
    assert result["scanned"] == result["unlocated"] == 200 and result["items"] == []
    assert result["truncations"][0]["reason"] == "scan_limit"
    assert "지역 매물 부재를 단정할 수 없습니다" in result["note"]


def test_region_short_exhausted_source_preserves_unknown_locations(monkeypatch):
    mod, _ = source(monkeypatch, [response([product()], total=1)])
    result = mod.search_bunjang("RAM", region="청주")
    assert result["unlocated"] == 1 and result["items"] == []
    assert "판정 불가" in result["note"] and "truncations" not in result


def test_http_failure_is_not_empty(monkeypatch):
    mod = module("tool_used")
    monkeypatch.setattr(mod, "_get", lambda *a, **kw: ("Not Found", 404))
    result = mod.search_bunjang("RAM")
    assert result["success"] is False and "HTTP 404" in result["error"]
