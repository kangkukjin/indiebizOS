"""Chart resolution must not change the meaning of the daily quote snapshot."""
import boot_paths  # noqa: F401
from datetime import datetime, timezone
from types import SimpleNamespace
import pytest
from tool_loader import load_tool_handler


def _quote_modules(monkeypatch):
    handler = load_tool_handler('stock_op')
    loader = handler.load_module
    yf = loader('tool_yfinance')
    # The package reloads siblings; pin the patched instance so tests never hit the network.
    monkeypatch.setattr(handler, 'load_module', lambda name: yf if name == 'tool_yfinance' else loader(name))
    return handler, yf


def test_quote_declared_rows_match_single_acquisition(monkeypatch):
    from pathlib import Path
    import yaml
    handler, yf = _quote_modules(monkeypatch)
    calls = []

    def chart(*args, **kwargs):
        calls.append(1)
        return [{'date': day, 'open': price, 'high': price, 'low': price,
                 'close': price, 'volume': 5} for day, price in [('2026-10-19', 90), ('2026-10-20', 110)]]

    monkeypatch.setattr(yf, '_yahoo_chart', chart)
    monkeypatch.setattr(yf, '_naver_realtime', lambda *a, **k: None)
    result = handler._stock_quote({'ticker': 'AAPL', 'period': '5d'})
    spec = yaml.safe_load((Path(handler.__file__).parent / 'ibl_actions.yaml').read_text())
    columns = spec['actions']['stock']['result_shape_variants']['op=quote']['cols']
    assert result['success'] and len(result['items']) == 1 and len(calls) == 1
    row = result['items'][0]
    assert all(row[key] == result['data'][key] for key in columns)
    assert row['current_price'] == 110 and row['as_of'] == '2026-10-20'
    assert 'current_price' not in result and 'price' not in result


@pytest.mark.parametrize('interval', ['1h', '1wk', '1mo'])
def test_non_daily_chart_uses_daily_quote_baseline(monkeypatch, interval):
    handler, yf = _quote_modules(monkeypatch)
    calls = []
    def fetch(url, *, params, **kwargs):
        calls.append(params['interval'])
        daily = params['interval'] == '1d'
        times = ([datetime(2026, 10, 19, 14, tzinfo=timezone.utc), datetime(2026, 10, 20, 14, tzinfo=timezone.utc)]
                 if daily else [datetime(2026, 10, 20, h, tzinfo=timezone.utc) for h in (14, 15)])
        closes = [90, 110] if daily else [100, 110]
        payload = {'chart': {'result': [{'meta': {'currency': 'USD', 'exchangeTimezoneName': 'America/New_York'},
            'timestamp': [int(t.timestamp()) for t in times],
            'indicators': {'quote': [{'open': closes, 'high': closes, 'low': closes,
                                     'close': closes, 'volume': [5, 6]}]}}]}}
        return SimpleNamespace(json=lambda: payload)
    monkeypatch.setattr(yf.requests, 'get', fetch)
    monkeypatch.setattr(yf, '_naver_realtime', lambda *a, **k: None)
    result = handler._stock_quote({'ticker': 'AAPL', 'interval': interval, 'period': '1d'})
    assert result['success'], result
    data = result['data']
    assert data['previous_close'] == 90 and data['previous_close_date'] == '2026-10-19'
    assert data['change_percent'] == 22.22 and data['snapshot_interval'] == '1d'
    assert data['total_bars'] == 2 and 'total_days' not in data
    assert '최근 2거래일' not in result['summary']
    assert data['prices'][1]['change_percent'] is None
    assert data['prices'][1]['bar_change_percent'] == 10
    if interval == '1h':
        assert [r['date'] for r in data['prices']] == ['2026-10-20T10:00:00-04:00', '2026-10-20T11:00:00-04:00']
    assert calls == [interval, '1d']


def test_single_daily_bar_does_not_invent_zero_change(monkeypatch):
    handler, yf = _quote_modules(monkeypatch)
    monkeypatch.setattr(yf, '_yahoo_chart', lambda *a, **k: [
        {'date': '2026-10-20', 'open': 110, 'high': 110, 'low': 110, 'close': 110, 'volume': 5}])
    monkeypatch.setattr(yf, '_naver_realtime', lambda *a, **k: None)
    result = handler._stock_quote({'ticker': 'AAPL', 'period': '1d'})
    assert result['success'], result
    assert all(result['data'][k] is None for k in ('change', 'change_percent', 'previous_close'))
    assert '미상' in result['summary']


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
