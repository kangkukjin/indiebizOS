"""미국 주가 이력의 FMP 유료벽 폴백 회귀."""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: F401,E402


def _investment():
    from tool_loader import load_tool_handler

    return load_tool_handler("stock_op")


def test_history_falls_back_to_yahoo_only_for_fmp_402(monkeypatch):
    handler = _investment()
    monkeypatch.setattr(handler, "_stock_common", lambda ti, op: ("MU", "us", None))

    class Fmp:
        @staticmethod
        def get_stock_price(**kwargs):
            return {"success": False, "error": "FMP API error: HTTP 402 Payment Required"}

    class Yahoo:
        @staticmethod
        def get_stock_price(**kwargs):
            return {
                "success": True,
                "data": {
                    "symbol": kwargs["symbol"],
                    "prices": [{
                        "date": "2026-08-27",
                        "open": 967.01,
                        "high": 968.71,
                        "low": 906.89,
                        "close": 935.39,
                        "volume": 28838500,
                    }],
                },
            }

    modules = {"tool_fmp": Fmp, "tool_yfinance": Yahoo}
    monkeypatch.setattr(handler, "load_module", modules.__getitem__)

    out = handler._stock_history({"ticker": "MU", "period": "5d"})

    assert out["success"] is True
    assert out["_fallback_used"] is True
    assert out["fallback_from"] == "fmp_http_402"
    assert out["fallback_to"] == "yahoo_chart"
    assert out["data"]["source"] == "yahoo_chart"
    assert out["items"][0]["close"] == 935.39


def test_history_does_not_hide_non_402_fmp_errors(monkeypatch):
    handler = _investment()
    monkeypatch.setattr(handler, "_stock_common", lambda ti, op: ("MU", "us", None))

    class Fmp:
        @staticmethod
        def get_stock_price(**kwargs):
            return {"success": False, "error": "FMP API error: HTTP 429 Too Many Requests"}

    def load_module(name):
        assert name == "tool_fmp"
        return Fmp

    monkeypatch.setattr(handler, "load_module", load_module)

    out = handler._stock_history({"ticker": "MU", "period": "5d"})

    assert out["success"] is False
    assert "HTTP 429" in out["error"]
    assert "_fallback_used" not in out


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
