"""[sense:stock] 세계 명사 해소 회귀 (2026-09-04, ep2817 실측).

재현: 'DX-Y.NYB'(야후 달러지수 심볼)가 코드 모양 검사에 안 맞아 이름으로 오인 → 검색 후보의
이름("ICE US Dollar Index - Index - C")과 접두 불일치 → 후보를 들고 거절. 에이전트는 표시명을
티커로 재시도했다. 계약: ①야후 심볼 모양(하이픈·접미·=X)은 코드다 ②안정된 시장 명사(DXY·달러지수·
원달러)는 검색 전에 별칭으로 정규화 ③후보의 심볼이 질의와 등치면 이름이 달라도 정확 일치다.

실행: .venv/bin/python -m pytest backend/test_ticker_resolver.py -q
"""
import importlib.util
import os
import sys
import types

import pytest

BACKEND = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BACKEND)
sys.path.insert(0, BACKEND)
import boot_paths  # noqa: E402,F401


@pytest.fixture
def h():
    path = os.path.join(ROOT, "data", "packages", "installed", "tools", "investment", "handler.py")
    spec = importlib.util.spec_from_file_location("investment_handler_probe", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_symbol_shapes_are_codes(h):
    for sym in ("DX-Y.NYB", "BRK-B", "BTC-USD", "KRW=X", "EURUSD=X", "^TNX", "005930", "102110.KS", "AAPL"):
        assert h._looks_like_code(sym), sym
    for name in ("삼성전자", "TIGER 200", "ICE US Dollar Index - Index - C"):
        assert not h._looks_like_code(name), name


def test_stable_market_nouns_resolve_without_search(h, monkeypatch):
    monkeypatch.setattr(h, "load_module", lambda name: (_ for _ in ()).throw(AssertionError("검색 불필요")))
    for q, sym in (("DXY", "DX-Y.NYB"), ("달러지수", "DX-Y.NYB"), ("dxy", "DX-Y.NYB"), ("USD/KRW", "KRW=X"), ("원달러", "KRW=X")):
        assert h._resolve_ticker(q)[0] == sym, q


def test_symbol_equality_counts_as_exact(h, monkeypatch):
    fake = types.SimpleNamespace(search_stock=lambda query, search_type: {"data": {"quotes": [
        {"name": "ICE US Dollar Index - Index - C", "symbol": "DX-Y.NYB", "exchange": "NYB"}]}})
    monkeypatch.setattr(h, "load_module", lambda name: fake)
    monkeypatch.setattr(h, "_looks_like_code", lambda t: False)      # 이름 경로로 강제
    sym, name, refused = h._resolve_ticker("dx-y.nyb")
    assert sym == "DX-Y.NYB" and refused is None
    sym, name, refused = h._resolve_ticker("달러 뭐시기")               # 여전히 추측하지 않는다
    assert refused and refused["success"] is False and refused["candidates"]


if __name__ == "__main__":
    import pytest as _pytest
    raise SystemExit(_pytest.main([__file__, "-q"]))
