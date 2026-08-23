"""세계 명사 반증 계약 (2026-08-24 #repair A4 — 오매칭 대역판).

IBL 헌법 '명사의 자리': **몸의 명사=코드, 세계의 명사=반증 가능한 데이터.**
sense:* 는 세계의 명사를 다룬다 — "수원", "TIGER 200", "삼성전자". 그 명사를
못 대면 액션은 **거절해야** 한다. 가장 비슷한 것을 조용히 돌려주는 순간 답은
반증 불가능해진다: 사용자는 자기가 물은 것을 받았다고 믿을 뿐, 확인할 방법이
결과 안에 없다.

★대역은 `None`(못 찾음)이 아니라 **실제로 관측된 오매칭 값**을 돌려준다.
  '못 찾으면 거절한다'는 쉬운 계약이고, 이 부류의 사고는 전부 **찾긴 찾았는데
  다른 것을 찾은** 자리에서 났기 때문이다:
    · '전주'  → 압록강변 40.4N (Open-Meteo 지오코더, handler 주석의 실측)
    · '수원'  → 이집트 룩소르 (전세계 폴백이 동음 지명을 물어오는 자리)
    · '12345' → Schenectady, US
    · 이름 검색 첫 줄 채택 (`chosen = … or quotes[0]`)
    · '삼성전자' → '삼성공조' (DART corp 사전의 부분 매칭 첫 히트)

계약 세 줄:
  ① 해소기는 (코드, 해소된 이름) 을 함께 돌려준다
  ② 정확/접두/토큰 일치가 없으면 **후보를 들고 거절**한다(하나를 몰래 고르지 않는다)
  ③ 성공 봉투는 `success: true` + `resolved` 를 싣는다(답이 무엇에 대한 답인지 말한다)

옛 시험 ②(한글 지명에 특정 해소기 호출 금지)는 여기서 **삭제**했다 — 어떤 해소기를
부르는가는 구현이고, 이 증거 규칙이 그 자리를 결과로 대신 막는다.
"""
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: F401,E402  — 층 디렉토리 등재


def _weather():
    from tool_loader import load_tool_handler
    return load_tool_handler("get_weather")


def _investment():
    from tool_loader import load_tool_handler
    return load_tool_handler("stock_op")


class _Geo:
    """지오코더 3종을 오매칭 값으로 갈아끼우는 컨텍스트."""

    def __init__(self, h, nominatim=None, kakao=None, openmeteo=None):
        self.h, self.vals = h, (nominatim, kakao, openmeteo)

    def __enter__(self):
        h = self.h
        self.saved = (h._geocode_nominatim, h._geocode_kakao, h._geocode_openmeteo)
        n, k, o = self.vals
        h._geocode_nominatim = lambda c: n
        h._geocode_kakao = lambda c: k
        h._geocode_openmeteo = lambda c: o
        return h

    def __exit__(self, *exc):
        (self.h._geocode_nominatim, self.h._geocode_kakao,
         self.h._geocode_openmeteo) = self.saved


def test_weather_refuses_when_the_geocoder_found_somewhere_else():
    """① '수원…' 을 물었는데 이집트가 오면 그 좌표를 쓰지 않는다."""
    h = _weather()
    h._CITY_COORDS.pop("수원시장안구", None)
    with _Geo(h, nominatim=(25.69, 32.64, "الأقصر, Luxor, Egypt", "Egypt")):
        out = h.get_weather_openmeteo(city="수원시장안구")
    h._CITY_COORDS.pop("수원시장안구", None)
    assert out.get("success") is False, out
    assert "Luxor" in (out.get("error") or ""), out          # 무엇으로 해석됐는지 말한다
    assert out.get("asked") == "수원시장안구", out
    # ★거절은 '조용한 성공'의 반대편 — 좌표·기온이 딸려오면 안 된다
    for leaked in ("current", "items", "lat", "lon", "latitude", "longitude"):
        assert leaked not in out, (leaked, out)


def test_weather_refuses_a_code_that_resolves_to_a_far_away_town():
    """① 같은 계약, 숫자 질의 — '12345' 는 Schenectady 가 아니다."""
    h = _weather()
    h._CITY_COORDS.pop("12345", None)
    with _Geo(h, openmeteo=(42.81, -73.94, "Schenectady", "United States"),
              nominatim=(42.81, -73.94, "Schenectady, New York", "United States")):
        out = h.get_weather_openmeteo(city="12345")
    h._CITY_COORDS.pop("12345", None)
    assert out.get("success") is False and "Schenectady" in (out.get("error") or ""), out


def test_weather_success_carries_the_resolved_name():
    """③ 정당한 해소는 통과하고, 답이 자기가 무엇에 대한 답인지 말한다."""
    h = _weather()

    class _Resp:
        ok, status_code = True, 200

        @staticmethod
        def json():
            return {"current": {"temperature_2m": 21.0, "relative_humidity_2m": 50,
                                "apparent_temperature": 21.0, "weather_code": 0,
                                "wind_speed_10m": 1.0},
                    "daily": {"time": ["2026-08-24"], "temperature_2m_max": [28.0],
                              "temperature_2m_min": [20.0], "weather_code": [0],
                              "precipitation_sum": [0.0],
                              "sunrise": ["2026-08-24T05:50"], "sunset": ["2026-08-24T19:20"]}}

    saved_get = h.requests.get
    h.requests.get = lambda *a, **k: _Resp()
    h._CITY_COORDS.pop("청주시흥덕구", None)
    try:
        with _Geo(h, nominatim=(36.64, 127.49, "충청북도 청주시 흥덕구, 대한민국", "대한민국")):
            out = h.get_weather_openmeteo(city="청주시흥덕구")
    finally:
        h.requests.get = saved_get
        h._CITY_COORDS.pop("청주시흥덕구", None)
    assert out.get("success") is True, out
    assert "청주시" in (out.get("resolved") or ""), out
    assert out.get("city") == "청주시흥덕구", out


def test_ticker_resolution_refuses_instead_of_taking_the_first_hit():
    """② 이름 검색이 엉뚱한 것만 물어오면 첫 줄을 채택하지 않는다.

    옛 코드: `chosen = exact[0] if exact else (starts[0] if starts else quotes[0])`
    — 마지막 가지가 '아무거나 첫 줄'이었다."""
    h = _investment()
    # ★load_module 은 매 호출 **새 모듈을 로드**한다(pkg_utils.load_sibling, cache=None).
    #   그래서 로드된 인스턴스를 고쳐도 핸들러가 보는 인스턴스는 옛것이다 — 대역은
    #   load_module 자리에 끼운다(실측으로 배운 함정).
    saved = h.load_module
    _stub = types.SimpleNamespace(search_stock=lambda **kw: {"data": {"quotes": [
        {"name": "Kodiak Gas Services", "symbol": "KGS", "exchange": "NYQ"},
        {"name": "Kingsoft Cloud", "symbol": "KC", "exchange": "NMS"},
    ]}})
    h.load_module = lambda n: _stub if n == "tool_yfinance" else saved(n)
    try:
        symbol, name, refused = h._resolve_ticker("TIGER 200")
    finally:
        h.load_module = saved
    assert refused is not None, (symbol, name)
    assert refused.get("success") is False and refused.get("asked") == "TIGER 200", refused
    assert [c["symbol"] for c in refused["candidates"]] == ["KGS", "KC"], refused
    assert name is None, name          # 엉뚱한 이름을 해소명이라 부르지 않는다


def test_ticker_resolution_accepts_an_exact_or_prefix_match():
    """② 의 반대편 — 맞는 게 있으면 그대로 통과하고 해소명을 돌려준다."""
    h = _investment()
    # ★load_module 은 매 호출 **새 모듈을 로드**한다(pkg_utils.load_sibling, cache=None).
    #   그래서 로드된 인스턴스를 고쳐도 핸들러가 보는 인스턴스는 옛것이다 — 대역은
    #   load_module 자리에 끼운다(실측으로 배운 함정).
    saved = h.load_module
    _stub = types.SimpleNamespace(search_stock=lambda **kw: {"data": {"quotes": [
        {"name": "TIGER 200 IT", "symbol": "139260.KS"},
        {"name": "TIGER 200", "symbol": "102110.KS"},
    ]}})
    h.load_module = lambda n: _stub if n == "tool_yfinance" else saved(n)
    try:
        symbol, name, refused = h._resolve_ticker("TIGER 200")
    finally:
        h.load_module = saved
    assert refused is None and symbol == "102110.KS" and name == "TIGER 200", (symbol, name, refused)


def test_corp_code_refuses_when_the_partial_match_is_ambiguous():
    """② DART — '삼성전자'를 물었는데 사전 순회 첫 히트가 '삼성공조'면 안 된다."""
    h = _investment()
    dart = h.load_module("tool_dart")
    saved = dart._load_corp_codes
    dart._load_corp_codes = lambda: {
        "삼성공조": {"corp_code": "00111111"},
        "삼성전자서비스": {"corp_code": "00222222"},
        "삼성전자판매": {"corp_code": "00333333"},
    }
    try:
        code, name, refused = dart._find_corp_code("삼성전자")
    finally:
        dart._load_corp_codes = saved
    assert code is None and name is None, (code, name)
    assert refused and refused.get("success") is False, refused
    assert "삼성전자서비스" in refused["candidates"], refused


def test_corp_code_accepts_an_exact_match_and_names_it():
    """③ 정확 일치는 통과하고 해소명을 함께 돌려준다."""
    h = _investment()
    dart = h.load_module("tool_dart")
    saved = dart._load_corp_codes
    dart._load_corp_codes = lambda: {
        "삼성공조": {"corp_code": "00111111"},
        "삼성전자": {"corp_code": "00126380"},
        "삼성전자서비스": {"corp_code": "00222222"},
    }
    try:
        code, name, refused = dart._find_corp_code("삼성전자")
    finally:
        dart._load_corp_codes = saved
    assert refused is None and code == "00126380" and name == "삼성전자", (code, name, refused)


if __name__ == "__main__":                      # 러너는 하나 — pytest (2026-08-23)
    # -q 를 넘기지 않는다: pytest.ini 의 addopts=-q 와 겹쳐 요약 줄이 사라진다(#repair C8).
    import sys as _sys
    import pytest as _pytest
    raise SystemExit(_pytest.main([__file__] + _sys.argv[1:]))
