"""공급자 폴백도 선언된 이력 열과 일일 등락의 뜻을 보존한다."""
import boot_paths  # noqa: F401
from datetime import date, timedelta
import pytest
import yaml

from tool_loader import load_tool_handler


@pytest.mark.parametrize("ticker,source", [("^GSPC", "yahoo"), ("MU", "fallback"), ("^KS11", "naver")])
@pytest.mark.parametrize("size", [1, 4, 60])
def test_history_contract_survives_source_and_sampling(monkeypatch, tmp_path, ticker, source, size):
    handler = load_tool_handler("stock_op")
    yf = handler.load_module("tool_yfinance")
    original = handler.load_module
    rows = [{"date": str(date(2026, 7, 1) + timedelta(days=i)), "open": 5,
             "high": 200, "low": 5, "close": 100 + i, "volume": 10} for i in range(size)]
    monkeypatch.setattr(yf, "_naver_index_daily", lambda *a, **k: rows if source == "naver" else [])
    monkeypatch.setattr(yf, "_yahoo_chart", lambda *a, **k: rows)
    monkeypatch.setattr(yf, "_naver_realtime", lambda *a, **k: None)
    monkeypatch.setattr(yf, "save_large_data", lambda *a, **k: str(tmp_path / "full.json"))
    fmp = original("tool_fmp")
    monkeypatch.setattr(fmp, "get_stock_price", lambda **k: {
        "success": False, "error": "FMP API error: HTTP 402 Payment Required"})
    monkeypatch.setattr(handler, "load_module", lambda name: {"tool_yfinance": yf, "tool_fmp": fmp}[name])
    out = handler._stock_history({"ticker": ticker, "start_date": rows[0]["date"],
                                 "end_date": rows[-1]["date"], "max_points": 4})
    assert out["success"], out
    if source == "fallback":
        assert out["fallback_to"] == "yahoo_chart"
    catalog = yaml.safe_load((handler.current_dir / "ibl_actions.yaml").read_text())
    # Compare with the actual advertised contract, not a second field list.
    spec = catalog["actions"]["stock"]["result_shape_variants"]["op=history"]
    for row in out["items"]:
        assert set(spec["cols"]) <= row.keys()
        assert row["vwap"] is None
        if row["date"] == rows[0]["date"]:
            assert row["change"] is None and row["change_percent"] is None
        else:
            assert row["change"] == 1
            assert row["change_percent"] == round(100 / (row["close"] - 1), 2)
    if size > 50:
        assert out["data"]["truncated"] and len(out["items"]) < size


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
