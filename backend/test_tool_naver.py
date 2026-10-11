"""Pagination must retain successful listings and filter before limiting."""
import importlib.util
from pathlib import Path

import boot_paths  # noqa: F401
import pytest


@pytest.fixture
def mod(monkeypatch):
    path = Path(__file__).resolve().parents[1] / 'data/packages/installed/tools/real-estate/tool_naver.py'
    spec = importlib.util.spec_from_file_location('test_realty_naver', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, 'has_curl_cffi', lambda: True)
    monkeypatch.setattr(module, '_resolve_keyword', lambda q: dict(mode='region', matched=q, cortarNo='1'))
    return module


def article(iid, rent=30):
    return dict(articleNo=str(iid), tradeTypeName='월세', tradeTypeCode='B2',
                dealOrWarrantPrc='1,000', rentPrc=rent, area2=55)


def test_postfilter_fills_limit_from_next_page(mod, monkeypatch):
    calls = []
    def page(path, params):
        calls.append(params['page'])
        return dict(articleList=[article(1, 100)] if params['page'] == 1 else [article(2)], isMoreData=True)
    monkeypatch.setattr(mod, '_api_get', page)
    result = mod.get_naver_listings(dict(region='시험동', lease='월세', rent_max=50, limit=1))
    assert len(result['items']) == 1
    assert result['items'][0]['url'].endswith('/2')
    assert calls == [1, 2]
    assert result['truncations'][0]['scope'] == 'selection'


def test_later_page_failure_preserves_items(mod, monkeypatch):
    def page(path, params):
        if params['page'] == 2:
            raise TimeoutError('second page timeout')
        return dict(articleList=[article(1)], isMoreData=True)
    monkeypatch.setattr(mod, '_api_get', page)
    result = mod.get_naver_listings(dict(region='시험동', lease='월세', limit=2))
    assert result['items'][0]['url'].endswith('/1')
    assert result['source_complete'] is False
    assert result['errors'][0]['page'] == 2


def test_page_budget_is_not_empty_success(mod, monkeypatch):
    monkeypatch.setattr(mod, '_api_get', lambda *a: dict(articleList=[article(1, 100)], isMoreData=True))
    result = mod.get_naver_listings(dict(region='시험동', lease='월세', rent_max=50, limit=1))
    assert result['items'] == []
    assert result['source_complete'] is False
    assert result['truncations'][0]['reason'] == 'page_limit'
    assert '없습니다' not in result['message']


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
