"""상상훈련 78·79회차 잔여 — 위치·문화·쇼핑 묶음 회귀 (원천 응답은 전부 fixture·모킹, 네트워크 없음).

B79-3 당근 로더 JSON 복구·구조 미발견 관문 · B79-4 번개장터 region 표본 신고 · B79-5 블로그 지역어 ·
B79-7 show_map 좌표 별칭·좌표 칸 계약 · B79-2 코드표 거절 문구 · F79-1 title_key · F79-2 공모전 안내 ·
침묵 클램프(기간·반경·이름 붙은 상한) · 길찾기 대안 경로.
"""
import boot_paths  # noqa: F401
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / "data/packages/installed/tools"
sys.path.insert(0, str(ROOT / "scripts"))


def module(package, name="handler"):
    spec = importlib.util.spec_from_file_location(
        "r7879_" + package.replace("-", "_") + "_" + name, TOOLS / package / (name + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def decode(value):
    from ibl_v2_adapters import decode_envelope
    return decode_envelope(value, {"protocol": "legacy-envelope"})[0]


# ── B79-3 당근 ─────────────────────────────────────────────────────────────

def _article(i, region="동A", status="Ongoing", price="170000"):
    return {"id": f"/kr/buy-sell/item-{i}/", "href": f"/kr/buy-sell/item-{i}/", "title": f"자전거 {i}",
            "content": "설명", "price": price, "thumbnail": "https://img.example/x.webp", "status": status,
            "createdAt": "2026-09-13T09:30:56.241Z", "region": {"name": region}, "tradingCoordinates": []}


def _danggeun(monkeypatch, bodies, region_id=2121):
    mod = module("shopping-assistant", "tool_used")
    calls = []
    monkeypatch.setattr(mod, "_resolve_danggeun_region", lambda r: (region_id, "도 시 구 동A"))

    def fake_get(url, params=None, timeout=12):
        calls.append((url, dict(params or {})))
        body = bodies[min(len(calls), len(bodies)) - 1]
        return (body if isinstance(body, str) else json.dumps(body, ensure_ascii=False)), 200

    monkeypatch.setattr(mod, "_get", fake_get)
    return mod, calls


def _loader(articles, region_id="2121"):
    return {"keyword": "자전거", "buySellArticles": articles, "productAds": [],
            "currentFilters": {"regionId": region_id, "search": "자전거"}}


def test_danggeun_reads_search_loader_json(monkeypatch):
    mod, calls = _danggeun(monkeypatch, [_loader([_article(i, region=("동A" if i % 2 else "동B"))
                                                  for i in range(30)])])
    out = mod.search_danggeun("자전거", limit=5, region="동A", requested_limit=5)
    url, params = calls[0]
    assert url.endswith("/kr/search/buy-sell/")
    assert params["in"] == "x-2121" and params["q"] == "자전거"
    assert params["_data"] == "routes/kr.search.buy-sell._index"
    assert len(out["items"]) == 5 and out["total"] == 30
    row = out["items"][0]
    assert row["price"] == 170000 and row["region"] == "동B" and row["search_region"] == "도 시 구 동A"
    assert row["url"].startswith("https://www.daangn.com/kr/buy-sell/")
    # 명시 limit 을 채운 절단은 선택(selection) — 판본 2 에서 실패가 아니다
    assert out["truncations"][0]["scope"] == "selection"
    assert decode(json.dumps(out))["items"]


def test_danggeun_structure_miss_is_source_changed(monkeypatch):
    # 옛 판이 읽던 JSON-LD 페이지(HTML)나 목록 칸 없는 JSON = 구조 변경. 0건 성공 금지.
    html = '<script type="application/ld+json">{"@type":"ItemList","itemListElement":[]}</script>'
    for body in (html, {"keyword": "자전거"}):
        mod, _ = _danggeun(monkeypatch, [body])
        out = mod.search_danggeun("자전거", limit=5, region="동A")
        assert out["success"] is False and out["error_type"] == "source_changed"


def test_danggeun_empty_retries_then_says_unverified(monkeypatch):
    mod, calls = _danggeun(monkeypatch, [_loader([]), _loader([])])
    monkeypatch.setattr(mod, "DANGGEUN_RETRY_GAP_S", 0)
    out = mod.search_danggeun("자전거", limit=5, region="동A")
    assert len(calls) == 1 + mod.DANGGEUN_EMPTY_RETRIES       # 0건이면 간격을 두고 더 묻는다(상한)
    assert out["items"] == [] and out.get("success") is not False
    assert out["empty_notes"] and "단정" in out["empty_notes"][0]
    mod, calls = _danggeun(monkeypatch, [_loader([]), _loader([_article(1)])])
    monkeypatch.setattr(mod, "DANGGEUN_RETRY_GAP_S", 0)
    out = mod.search_danggeun("자전거", limit=5, region="동A")
    assert len(out["items"]) == 1 and out["retried"] == 1 and "empty_notes" not in out


def test_danggeun_requires_region_and_matching_scope(monkeypatch):
    mod, calls = _danggeun(monkeypatch, [_loader([_article(1)])])
    out = mod.search_danggeun("자전거", limit=5, region=None)
    assert out["success"] is False and out["error_type"] == "missing_param" and not calls
    mod, _ = _danggeun(monkeypatch, [_loader([_article(1)], region_id="9999")])
    out = mod.search_danggeun("자전거", limit=5, region="동A")
    assert out["success"] is False and out["error_type"] == "source_changed"


def test_used_declares_every_source_variant():
    decl = yaml.safe_load((TOOLS / "shopping-assistant/ibl_actions.yaml").read_text())["actions"]["used"]
    assert set(decl["shape_variants"]) == {"source=danggeun", "source=joongna", "source=naver"}


# ── B79-4 번개장터 ─────────────────────────────────────────────────────────

def _bunjang(monkeypatch, pages, num_found=1000):
    mod = module("shopping-assistant", "tool_used")
    seen = []

    def fake_page(query, page, n):
        seen.append(page)
        rows = pages[page] if page < len(pages) else []
        return {"list": rows, "num_found": num_found}

    monkeypatch.setattr(mod, "_bunjang_page", fake_page)
    return mod, seen


def _bj(i, loc=""):
    return {"pid": i, "name": f"스위치 {i}", "price": "300000", "location": loc, "status": "0"}


def test_bunjang_region_scans_past_first_page(monkeypatch):
    page0 = [_bj(i, "서울특별시 강남구" if i % 4 == 0 else "") for i in range(40)]
    page1 = [_bj(100, "충청북도 지역시 어느동")] + [_bj(101 + i) for i in range(39)]
    mod, seen = _bunjang(monkeypatch, [page0, page1, [_bj(200 + i) for i in range(10)]])
    out = mod.search_bunjang("스위치", limit=15, region="지역시")
    assert [r["title"] for r in out["items"]] == ["스위치 100"]    # 41번째 행을 찾는다
    assert out["scanned"] == 90 and out["unlocated"] == 30 + 39 + 10
    assert "truncations" not in out                               # 원천 끝까지 훑었다(10행 쪽)
    assert seen == [0, 1, 2]


def test_bunjang_region_scan_limit_is_reported(monkeypatch):
    full = [[_bj(p * 100 + i, "부산광역시 해운대구") for i in range(40)] for p in range(10)]
    mod, seen = _bunjang(monkeypatch, full)
    out = mod.search_bunjang("스위치", limit=15, region="지역시")
    assert out["items"] == [] and out["truncated"] is True
    cut = out["truncations"][0]
    assert cut["scope"] == "source" and cut["reason"] == "scan_limit" and cut["scanned"] == 200
    assert len(seen) == mod.BUNJANG_REGION_SCAN_PAGES
    with pytest.raises(Exception) as exc:       # 판본 2 는 표본 한계를 성공 0건으로 넘기지 않는다
        decode(json.dumps(out))
    assert "PARTIAL_SOURCE" in str(getattr(exc.value, "code", exc.value)) or "불완전" in str(exc.value)


# ── 다나와: 구조 미발견 ≠ 0건 ────────────────────────────────────────────────

def test_danawa_distinguishes_empty_from_structure_change(monkeypatch):
    mod = module("shopping-assistant", "tool_danawa")
    monkeypatch.setattr(mod, "_fetch", lambda params: '<div id="productListArea"><div id="nosearchArea"></div></div>')
    assert mod.search_danawa("없는상품", 5) == {"total": 0, "items": [], "empty_reason": "no_results"}
    monkeypatch.setattr(mod, "_fetch", lambda params: "<html>renamed layout</html>")
    out = mod.search_danawa("노트북", 5)
    assert out["success"] is False and out["error_type"] == "source_changed"


# ── B79-5 블로그 지역어 ────────────────────────────────────────────────────

def test_blog_region_comes_from_row_address_not_query(monkeypatch):
    mod = module("location-services")
    assert mod._blog_region_term("충북 지역시 어느구 어느로 12") == "지역"
    assert mod._blog_region_term("서울 강남구 테헤란로 1") == "강남"
    assert mod._blog_region_term("서울 중구 세종대로 1") == "중구"        # 접미를 떼면 한 글자 → 원형 유지
    seen = []
    monkeypatch.setattr(mod, "_blog_evidence", lambda region, name: seen.append((region, name)) or None)
    rows = [{"name": "가게1", "lat": 36.6, "lng": 127.4, "address": "충북 지역시 어느구 어느로 12"}]
    monkeypatch.setattr(mod, "search_kakao_restaurants", lambda *a: {"restaurants": rows})
    monkeypatch.setattr(mod, "search_naver_local", lambda *a: {"restaurants": []})
    monkeypatch.setattr(mod, "build_location_map", lambda **kw: {})
    mod.search_restaurants_combined("돈까스", x="127.4", y="36.6", radius=700, enrich=True)
    assert seen == [("지역", "가게1")]                                     # 옛 판: ("돈까스", "가게1")


def test_restaurant_limit_and_radius_clamps_are_reported(monkeypatch):
    mod = module("location-services")
    monkeypatch.setattr(mod, "check_api_key", lambda k: (True, None))
    sent = []

    def fake_api(provider, path, params=None, timeout=10):
        sent.append(dict(params))
        return {"documents": [], "meta": {"total_count": 0, "is_end": True}}

    monkeypatch.setattr(mod, "api_call", fake_api)
    monkeypatch.setattr(mod, "search_naver_local", lambda *a: {"restaurants": []})
    out = mod.search_restaurants_combined("밥", x="127.4", y="36.6", radius=50000, kakao_size=60, enrich=False)
    assert sent[0]["radius"] == 20000
    assert out["clamped"] is True and out["requested"] == {"radius": 50000, "limit": 60}
    assert out["applied"] == {"radius": 20000, "limit": 45}


# ── B79-7 show_map 좌표 별칭 ──────────────────────────────────────────────

def test_show_map_reads_coordinate_aliases_before_geocoding(monkeypatch):
    mod = module("location-services")

    def no_geocode(term):
        raise AssertionError(f"좌표가 있는데 지오코딩함: {term}")

    monkeypatch.setattr(mod, "_geocode_place", no_geocode)
    markers = [{"title": "전시1", "gpsX": "127.49", "gpsY": "36.64"},
               {"name": "B", "latitude": 36.1, "longitude": 127.1},
               {"name": "C", "y": "36.2", "x": "127.2"},
               {"name": "D", "lat": 36.3, "lon": 127.3}]
    norm, geocoded, failed = mod._normalize_markers(markers)
    assert [(m["lat"], m["lng"]) for m in norm] == [(36.64, 127.49), (36.1, 127.1), (36.2, 127.2), (36.3, 127.3)]
    assert not geocoded and not failed
    monkeypatch.setattr(mod, "_geocode_place", lambda term: (127.0, 37.0, "찾은곳"))
    norm, geocoded, _ = mod._normalize_markers([{"name": "좌표없음"}])
    assert norm[0]["lat"] == 37.0 and geocoded == [("좌표없음", "찾은곳")]


def test_coordinate_contract_invariant_spans_packages():
    from honesty_invariants_sweep import check_envelope, coord_contract_violations
    assert coord_contract_violations([{"gpsX": "127.4", "gpsY": "36.6"}]) == [0]
    assert coord_contract_violations([{"gpsX": "127.4", "gpsY": "36.6", "lat": 36.6, "lng": 127.4}]) == []
    assert coord_contract_violations([{"gpsX": "", "gpsY": ""}]) == []
    probs = check_envelope("sense:exhibit", "items", {"items": [{"latitude": 36.6, "longitude": 127.4}]})
    assert [p[0] for p in probs] == ["F"]


def test_exhibit_rows_carry_contract_coordinates_and_title_key(monkeypatch):
    mod = module("culture")
    kcisa = SimpleNamespace(quick_search_culture=lambda keyword, rows: {"success": True, "data": [
        {"title": "[전주] 무명의 용병사 ", "place": "예술나눔 터 ", "gpsX": "127.49", "gpsY": "36.64",
         "startDate": "20261003", "endDate": "20261004"}]})
    monkeypatch.setitem(sys.modules, "tool_kcisa", kcisa)
    row = json.loads(mod.execute({"query": "전주"}, SimpleNamespace(tool_name="kcisa_quick_search")))["items"][0]
    assert row["lat"] == 36.64 and row["lng"] == 127.49
    assert row["title_key"] == mod._title_key("무명의 용병사 [전주]") == "무명의용병사"
    assert row["place_key"] == mod._title_key("예술나눔 터") == "예술나눔터"
    assert row["title"] == "[전주] 무명의 용병사 "                      # 표시 제목은 원문 그대로


# ── B79-2 코드표 거절 · F79-1 공연 title_key ──────────────────────────────

@pytest.mark.parametrize("field,value,label", [("region", "전주", "지역"), ("genre", "어린이극", "장르"),
                                               ("status", "곧", "공연상태")])
def test_kopis_rejects_unknown_codes_concisely(field, value, label):
    mod = module("culture")
    args = {"date_from": "2026-10-03", "date_to": "2026-10-04", field: value}
    out = json.loads(mod.execute(args, SimpleNamespace(tool_name="performance_op")))
    assert out["success"] is False and out["error_type"] == "invalid_value"
    assert f"알 수 없는 {label}: {value}" in out["error"]
    assert "{" not in out["error"] and "seoul" not in out["error"]       # dict 덤프 금지
    assert out["allowed"] and all(any("가" <= c <= "힣" for c in n) for n in out["allowed"])
    if field == "region":
        assert "충북" in out["allowed"] and "시도" in out["hint"]


def test_kopis_known_values_still_resolve():
    kopis = module("culture", "tool_kopis")
    assert kopis._resolve_region("충북") == "43" and kopis._resolve_region("seoul") == "11"
    assert kopis._resolve_region("43") == "43" and kopis._resolve_genre("뮤지컬") == "GGGA"
    assert kopis._resolve_status("ongoing") == "02" and kopis._resolve_status(None) is None


def test_performance_rows_carry_title_key_and_place(monkeypatch):
    mod = module("culture")
    kopis = SimpleNamespace(get_performances=lambda **kw: {"data": [
        {"prfnm": "무명의 용병사 [전주]", "fcltynm": "예술나눔 터", "prfpdfrom": "2026.10.03", "prfpdto": "2026.10.04"}]},
        search_by_keyword=None)
    monkeypatch.setitem(sys.modules, "tool_kopis", kopis)
    row = mod._perf_search({"date_from": "2026-10-03", "date_to": "2026-10-04"})["items"][0]
    assert row["title_key"] == "무명의용병사" and row["place"] == "예술나눔 터" and row["place_key"] == "예술나눔터"


# ── F79-2 공모전 ──────────────────────────────────────────────────────────

def test_contest_korean_or_empty_query_points_to_web_search(monkeypatch):
    mod = module("contest")
    monkeypatch.setattr(mod, "check_api_key", lambda k: (True, None))
    monkeypatch.setattr(mod, "api_call", lambda *a, **k: [])
    out = mod.search_kaggle("어린이 그림 공모전")
    assert out["count"] == 0 and mod.DOMESTIC_HINT in out["hint"] and out["empty_notes"]
    monkeypatch.setattr(mod, "api_call", lambda *a, **k: [{"title": "LLM Challenge"}])
    assert "hint" not in mod.search_kaggle("LLM")
    decl = yaml.safe_load((TOOLS / "contest/ibl_actions.yaml").read_text())["actions"]["contest"]
    assert mod.DOMESTIC_HINT in decl["description"]                     # 선언과 응답 안내가 한 문장


# ── 침묵 클램프: 기간·반경·이름 붙은 상한 ────────────────────────────────────

def test_weather_days_uses_api_cap_and_reports_clamp(monkeypatch):
    mod = module("location-services")
    sent = []

    def fake_get(url, params=None, timeout=10):
        sent.append(params)
        n = params["forecast_days"]
        daily = {"time": [f"2026-10-{i + 1:02d}" for i in range(n)], "temperature_2m_max": [20] * n,
                 "temperature_2m_min": [10] * n, "weather_code": [0] * n, "precipitation_sum": [0] * n}
        return SimpleNamespace(ok=True, json=lambda: {"current": {}, "daily": daily})

    monkeypatch.setattr(mod.requests, "get", fake_get)
    out = mod.get_weather_openmeteo(lat=36.6, lon=127.4, days=10)
    assert sent[-1]["forecast_days"] == 10 and len(out["items"]) == 10 and "clamped" not in out
    out = mod.get_weather_openmeteo(lat=36.6, lon=127.4, days=20)
    assert len(out["items"]) == 16 and out["clamped"] is True and out["requested"] == {"days": 20}
    assert mod.get_weather_openmeteo(lat=36.6, lon=127.4, days="x")["success"] is False


def test_place_radius_and_limit_clamps_are_in_envelope(monkeypatch):
    mod = module("location-services", "tool_place")
    monkeypatch.setattr(mod, "check_api_key", lambda k: (True, None))
    captured = {}

    def fake_paged(endpoint, params, limit):
        captured.update(params)
        return [], 0, None

    monkeypatch.setattr(mod, "_paged", fake_paged)
    out = mod.place_search({"query": "카페", "lat": 36.6, "lng": 127.4, "radius": 50000, "limit": 99})
    assert captured["radius"] == 20000
    assert out["clamped"] is True and out["requested"] == {"limit": 99, "radius": 50000}
    assert out["applied"] == {"limit": 45, "radius": 20000}


def test_silent_clamp_gate_sees_ranges_and_named_caps(tmp_path):
    import check_silent_clamp as gate
    bad = tmp_path / "bad.py"
    bad.write_text("_MAX_RADIUS = 20000\n"
                   "def a(days):\n    return {'forecast_days': min(days, 7)}\n"
                   "def b(radius):\n    return min(radius, _MAX_RADIUS)\n", encoding="utf-8")
    assert sorted(h[1] for h in gate.scan_file(bad)) == ["days", "radius"]
    ok = tmp_path / "ok.py"
    ok.write_text("def a(days):\n    used = min(days, 16)\n    return {'clamped': used != days}\n", encoding="utf-8")
    assert gate.scan_file(ok) == []
    assert gate.main() == 0                                             # 저장소 전체 통과


# ── 구조 미발견 관문 · 원천 변이 축 관문 ─────────────────────────────────────

def test_source_miss_gate_catches_old_danggeun_shape(tmp_path):
    import iblbuild_source_honesty as gate
    old = tmp_path / "old.py"
    old.write_text(
        "import requests\n"
        "def search(q):\n"
        "    return {'source': 'x', 'total': 0, 'items': [], 'note': '결과 없음 또는 페이지 구조 변경'}\n"
        "def fetch(q):\n"
        "    try:\n        return requests.get(q).json()['rows']\n"
        "    except Exception:\n        return []\n"
        "def fallback(q):\n"
        "    try:\n        return requests.get(q).json()['rows']\n"
        "    except Exception:  # empty-ok: 호출자가 다른 원천으로 폴백\n        return []\n", encoding="utf-8")
    hits = gate.scan_source_miss(old)
    assert [h[1][:2] for h in hits] == ["R1", "R2"] and hits[1][0] == 8
    assert gate.validate_source_miss(ROOT) == []


def test_source_axis_gate_passes_on_built_vocabulary():
    import iblbuild_source_honesty as gate
    data = yaml.safe_load((ROOT / "data/ibl_nodes.yaml").read_text())
    assert gate.validate_source_axes(data, ROOT) == []
    used = data["nodes"]["sense"]["actions"]["used"]
    used = {**used, "shape_variants": {}}
    data["nodes"]["sense"]["actions"]["used"] = used
    issues = gate.validate_source_axes(data, ROOT)
    assert any("source=danggeun" in i for i in issues)


def test_weekly_honesty_sweep_alarms_on_empty_source_variant():
    # 일일 건강 점검은 액션 fixture 만(외부 API 를 매일 더 두드리지 않는다 — new_action_checklist 결정).
    # 원천 변이의 0건 경보는 주간 정직성 스윕(fixture + shape_variants 우주)이 맡는다.
    from honesty_invariants_sweep import check_variant_empty
    fx = json.loads((ROOT / "data/ibl_fixtures.json").read_text())
    assert "sense:used@source=danggeun" in fx["shape_variants"]
    empty = {"items": [], "total": 0, "empty_notes": ["미확인"]}
    assert [p[0] for p in check_variant_empty("sense:used@source=danggeun", empty)] == ["G"]
    assert check_variant_empty("sense:used", empty) == []                 # 액션 fixture 는 일일 점검 몫
    assert check_variant_empty("sense:used@source=danggeun", {"items": [{"title": "x"}]}) == []
    assert check_variant_empty("sense:used@source=danggeun", {"success": False, "error": "x", "items": []}) == []


# ── 길찾기 대안 경로 ──────────────────────────────────────────────────────

def _route(dist, dur, vx):
    return {"result_code": 0, "result_msg": "ok",
            "summary": {"distance": dist, "duration": dur, "fare": {"toll": 0}, "priority": "RECOMMEND",
                        "origin": {}, "destination": {}},
            "sections": [{"roads": [{"vertexes": vx}], "guides": []}]}


def test_navigation_keeps_alternative_routes(monkeypatch):
    mod = module("location-services")
    monkeypatch.setattr(mod, "check_api_key", lambda k: (True, None))
    monkeypatch.setattr(mod, "_geocode_place", lambda s: (127.0, 36.0, s))
    captured = {}
    monkeypatch.setattr(mod, "generate_route_map_data",
                        lambda **kw: captured.update(kw) or {"type": "route_map"})
    data = {"routes": [_route(10000, 900, [127.0, 36.0, 127.1, 36.1]),
                       _route(12000, 840, [127.0, 36.0, 127.5, 36.5])]}
    monkeypatch.setattr(mod, "api_call", lambda *a, **k: data)
    out = json.loads(mod.execute({"from": "A", "to": "B", "alternatives": True},
                                 SimpleNamespace(tool_name="kakao_navigation")))
    assert out["summary"]["distance_km"] == 10.0
    assert out["alternatives"] == [{"distance_km": 12.0, "duration_min": 14, "toll": 0, "priority": "RECOMMEND"}]
    assert captured["path_coords"] == [(127.0, 36.0), (127.1, 36.1)]      # 지도 선 = 첫 경로만


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
