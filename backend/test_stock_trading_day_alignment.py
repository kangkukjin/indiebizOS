"""[sense:stock] quote/history 거래일 정합 회귀 (2026-09-01 수리).

증상이었던 것: quote 와 history 가 서로 다른 거래일을 가리켜 등락 부호까지 뒤집혔다.
원인은 둘이었고(전일종가 역산 · Yahoo 의 close=null 바 탈락), 잔여 항목 수리에서
지수 일봉 소스와 행별 change 의 의미까지 통일했다. 네 결함의 재현 케이스를 남긴다.

    T1. 장전 스냅샷의 전일종가 역산      → 일봉의 마지막 완결 장에 고정
    T2. Yahoo close=null 바 조용한 탈락  → series_gap 신고
    T3. 구멍 감지 시 전일종가 재조정     → history 소스(krx/fmp)로 다시 잡고 표지
    T4. 한국 지수 일봉이 Yahoo 라 끊김   → 네이버 일봉 우선(series_source)
    T5. 행별 change 가 소스마다 다른 양  → KR·US 모두 '전일 종가 대비'

실행: python3 -m pytest backend/test_stock_trading_day_alignment.py
망은 타지 않는다 — 모든 외부 호출은 monkeypatch 로 막는다.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: F401,E402


def _handler():
    from tool_loader import load_tool_handler

    return load_tool_handler("stock_op")


def _yf(handler):
    return handler.load_module("tool_yfinance")


def _bar(date, close, **kw):
    return {"date": date, "open": kw.get("open", close), "high": kw.get("high", close),
            "low": kw.get("low", close), "close": close, "volume": kw.get("volume", 1000)}


# ── T1. 장전 스냅샷은 전일종가를 역산하지 않는다 ────────────────────
def test_premarket_snapshot_keeps_series_prev_close(monkeypatch):
    """옛 버그: prev_close = price - change. 장전엔 change=0 이라 전일종가가
    그 장 종가 자신이 되어 quote 만 하루 앞선 날을 가리켰다."""
    yf = _yf(_handler())
    monkeypatch.setattr(yf, "_naver_index_daily", lambda *a, **k: [])
    monkeypatch.setattr(yf, "_yahoo_chart",
                        lambda *a, **k: [_bar("2026-08-28", 257000), _bar("2026-08-31", 260000)])
    monkeypatch.setattr(yf, "_naver_realtime", lambda s: {
        "price": 260000, "change": 0, "change_percent": 0,
        "open": None, "high": None, "low": None, "volume": None,
        "quote_time": "2026-09-01T08:30:00+09:00", "market_status": "CLOSE"})

    d = yf.get_stock_price("005930.KS")["data"]

    assert d["as_of"] == "2026-08-31"                 # 마지막 *완결* 장
    assert d["previous_close_date"] == "2026-08-28"   # 역산이면 8/31 자신이 됐다
    assert d["previous_close"] == 257000
    assert d["change"] == 3000


# ── T2. 최신 close=null 바를 조용히 버리지 않는다 ────────────────────
def test_null_latest_yahoo_bar_is_reported(monkeypatch):
    yf = _yf(_handler())

    class Response:
        @staticmethod
        def json():
            return {"chart": {"result": [{
                "meta": {"currency": "USD"},
                "timestamp": [1787788800, 1787875200],
                "indicators": {"quote": [{
                    "open": [314.58, None], "high": [314.58, None],
                    "low": [314.58, None], "close": [314.58, None],
                    "volume": [1000, None],
                }]},
            }]}}

    monkeypatch.setattr(yf.requests, "get", lambda *a, **k: Response())
    meta = {}

    rows = yf._yahoo_chart("AAPL", meta_sink=meta)

    assert [row["date"] for row in rows] == ["2026-08-27"]
    assert meta["_dropped_dates"] == ["2026-08-28"]


def test_missing_middle_bar_is_reported_as_series_gap(monkeypatch):
    yf = _yf(_handler())

    def chart(symbol, period="5d", interval="1d", meta_sink=None):
        if meta_sink is not None:
            meta_sink["_dropped_dates"] = ["2026-08-28"]   # close=null 이던 거래일
            meta_sink["currency"] = "USD"
        return [_bar("2026-08-27", 314.58), _bar("2026-08-31", 316.85)]

    monkeypatch.setattr(yf, "_naver_index_daily", lambda *a, **k: [])
    monkeypatch.setattr(yf, "_yahoo_chart", chart)
    monkeypatch.setattr(yf, "_naver_realtime", lambda s: None)

    d = yf.get_stock_price("AAPL")["data"]

    assert d["series_gap"] == ["2026-08-28"]          # 조용한 탈락이면 이 키가 없다
    assert d["previous_close_date"] == "2026-08-27"   # 아직 밀린 상태 — 보정은 핸들러(T3)


# ── T3. quote/history 가 같은 거래일·전일종가·등락을 쓴다 ────────────
def test_quote_and_history_share_trade_day_and_prev_close(monkeypatch):
    handler = _handler()

    class Yahoo:
        @staticmethod
        def get_stock_price(**kw):
            return {"success": True, "data": {
                "symbol": "AAPL", "currency": "USD", "current_price": 316.85,
                "as_of": "2026-08-31", "previous_close": 314.58,
                "previous_close_date": "2026-08-27", "change": 2.27,
                "change_percent": 0.72, "series_gap": ["2026-08-28"]}}

    class Fmp:
        @staticmethod
        def get_stock_price(**kw):
            return {"success": True, "data": {"prices": [
                {"date": "2026-08-27", "close": 314.58,
                 "change": None, "change_percent": None},
                {"date": "2026-08-28", "close": 319.70,
                 "change": 5.12, "change_percent": 1.63},
                {"date": "2026-08-31", "close": 316.85,
                 "change": -2.85, "change_percent": -0.89}]}}

    modules = {"tool_yfinance": Yahoo, "tool_fmp": Fmp}
    monkeypatch.setattr(handler, "_stock_common",
                        lambda ti, op: ("AAPL", "us", None))
    monkeypatch.setattr(handler, "load_module", modules.__getitem__)

    quote = handler._stock_quote({"ticker": "AAPL"})
    history = handler._stock_history({"ticker": "AAPL", "period": "5d"})
    qd, prices = quote["data"], history["data"]["prices"]

    assert qd["as_of"] == prices[-1]["date"] == "2026-08-31"
    assert qd["previous_close_date"] == prices[-2]["date"] == "2026-08-28"
    assert qd["previous_close"] == prices[-2]["close"] == 319.70
    assert qd["change"] == prices[-1]["change"] == -2.85
    assert qd["change_percent"] == prices[-1]["change_percent"] == -0.89
    assert qd["prev_close_source"] == "fmp"
    assert qd["quote_lag"]["reason"] == "yahoo_series_gap_reconciled"


def test_reconcile_is_silent_when_no_gap(monkeypatch):
    """구멍이 없으면 손대지 않는다 — 보정이 평시에 끼어들지 않아야 한다."""
    handler = _handler()
    res = {"success": True, "data": {"symbol": "AAPL", "current_price": 316.85,
                                     "as_of": "2026-08-31", "previous_close": 319.70,
                                     "previous_close_date": "2026-08-28"}}

    def boom(name):
        raise AssertionError("구멍이 없는데 참조 소스를 불렀다")

    monkeypatch.setattr(handler, "load_module", boom)
    handler._reconcile_quote_prev_close(res, "AAPL", "us")

    assert "prev_close_source" not in res["data"]


# ── T4. 한국 지수 일봉은 네이버가 먼저 ──────────────────────────────
def test_kr_index_series_comes_from_naver_daily(monkeypatch):
    """지수는 quote·history 가 같은 Yahoo 를 써서 대조 소스가 없었다 — Yahoo 가
    8/28·8/31 을 통째로 빠뜨리면 둘 다 8/27 에서 멈췄다(실측)."""
    yf = _yf(_handler())
    naver_bars = [_bar("2026-08-27", 6912.37), _bar("2026-08-28", 6788.88),
                  _bar("2026-08-31", 6820.02)]

    def chart(*a, **k):
        raise AssertionError("네이버 일봉이 있는데 Yahoo 를 불렀다")

    monkeypatch.setattr(yf, "_naver_index_daily", lambda s, p="5d": naver_bars)
    monkeypatch.setattr(yf, "_yahoo_chart", chart)
    monkeypatch.setattr(yf, "_naver_realtime", lambda s: None)

    d = yf.get_stock_price("^KS11", period="1mo")["data"]

    assert d["series_source"] == "naver_daily"
    assert [r["date"] for r in d["prices"]][-3:] == ["2026-08-27", "2026-08-28", "2026-08-31"]
    assert d["as_of"] == "2026-08-31"
    assert d["previous_close_date"] == "2026-08-28"
    assert "series_gap" not in d


def test_kr_index_falls_back_to_yahoo_when_naver_dies(monkeypatch):
    yf = _yf(_handler())
    monkeypatch.setattr(yf, "_naver_index_daily", lambda s, p="5d": [])
    monkeypatch.setattr(yf, "_yahoo_chart",
                        lambda *a, **k: [_bar("2026-08-26", 6808.21), _bar("2026-08-27", 6912.37)])
    monkeypatch.setattr(yf, "_naver_realtime", lambda s: None)

    d = yf.get_stock_price("^KS11")["data"]

    assert d.get("series_source") is None        # 폴백은 표지를 달지 않는다(기본 소스)
    assert d["as_of"] == "2026-08-27"


# ── T5. 행별 change 는 KR·US 모두 '전일 종가 대비' ──────────────────
def test_kr_row_change_is_prev_close_based(monkeypatch):
    krx = _handler().load_module("tool_krx")
    rows = [{"date": "2026-08-27", "open": 1, "close": 266000},
            {"date": "2026-08-28", "open": 2, "close": 257000}]

    krx._normalize_row_change(rows)

    assert rows[0]["change"] is None             # 창 밖의 전일은 모른다 — 추측 금지
    assert rows[0]["change_percent"] is None
    assert rows[1]["change"] == -9000            # 옛 KRX 경로는 여기에 등락'률'을 넣었다
    assert rows[1]["change_percent"] == -3.38


def test_us_row_change_is_prev_close_not_open(monkeypatch):
    """옛 FMP 경로는 change = 종가 − 시가라, 같은 열 이름에 다른 양이 담겼다."""
    fmp = _handler().load_module("tool_fmp")
    raw = [  # FMP 는 최신순
        {"date": "2026-08-31", "open": 319.60, "high": 321.24, "low": 312.80,
         "close": 316.85, "volume": 1, "change": -2.75, "changePercent": -0.86},
        {"date": "2026-08-28", "open": 316.85, "high": 322.37, "low": 315.45,
         "close": 319.70, "volume": 1, "change": 2.85, "changePercent": 0.90},
    ]
    monkeypatch.setattr(fmp, "_api_request", lambda *a, **k: {"success": True, "data": raw})

    prices = fmp.get_stock_price("AAPL")["data"]["prices"]

    assert prices[-1]["date"] == "2026-08-31"
    assert prices[-1]["change"] == -2.85         # 종가−시가였다면 -2.75
    assert prices[-1]["change_percent"] == -0.89  # 옛 값 -0.86 — quote 와 갈리던 자리
    assert prices[0]["change"] is None


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
