"""NAVER Developers/HUB 자격증명과 엔드포인트는 함께 전환한다."""
from pathlib import Path

import boot_paths  # noqa: F401
import pytest
from common.pkg_utils import load_sibling


@pytest.fixture
def naver(monkeypatch):
    for name in ('NAVER_HUB_CLIENT_ID', 'NAVER_HUB_CLIENT_SECRET'):
        monkeypatch.delenv(name, raising=False)
    return load_sibling(Path(__file__).resolve().parents[1] /
                        'data/packages/installed/tools/web/handler.py', 'tool_naver_search')


def test_legacy_credentials_keep_legacy_endpoint(naver, monkeypatch):
    monkeypatch.setattr(naver, 'check_api_key', lambda service: (True, ''))
    calls = []
    monkeypatch.setattr(naver, 'api_call', lambda *a, **kw: calls.append((a, kw)) or {'items': []})
    out = naver.search_naver('query', type='news')
    assert out['success'] and out['api_backend'] == 'naver_developers'
    assert calls[0][0] == ('naver', '/v1/search/news.json')


@pytest.mark.parametrize('kind,path', [('webkr', 'webkr'), ('news', 'news'), ('cafe', 'cafearticle')])
def test_hub_credentials_change_host_path_and_headers(naver, monkeypatch, kind, path):
    monkeypatch.setenv('NAVER_HUB_CLIENT_ID', 'hub-id')
    monkeypatch.setenv('NAVER_HUB_CLIENT_SECRET', 'hub-secret')
    calls = []
    monkeypatch.setattr(naver, 'api_call', lambda *a, **kw: pytest.fail('legacy fallback'))
    monkeypatch.setattr(naver, 'api_call_raw', lambda *a, **kw: calls.append((a, kw)) or {
        'total': 1, 'items': [{'title': 'T', 'link': 'https://example.test', 'description': 'D'}]})
    out = naver.search_naver('query', type=kind)
    assert out['success'] and out['api_backend'] == 'naver_api_hub'
    assert calls[0][0] == (f'https://naverapihub.apigw.ntruss.com/search/v1/{path}',)
    assert calls[0][1]['headers'] == {'X-NCP-APIGW-API-KEY-ID': 'hub-id', 'X-NCP-APIGW-API-KEY': 'hub-secret'}
    assert calls[0][1]['params']['format'] == 'json'
    assert out['items'][0]['url'] == 'https://example.test'


def test_partial_hub_configuration_is_not_ignored(naver, monkeypatch):
    monkeypatch.setenv('NAVER_HUB_CLIENT_ID', 'hub-id')
    monkeypatch.setattr(naver, 'api_call', lambda *a, **kw: pytest.fail('legacy fallback'))
    assert naver.search_naver('query')['success'] is False


def test_hub_auth_failure_is_not_retried_with_old_key(naver, monkeypatch):
    monkeypatch.setenv('NAVER_HUB_CLIENT_ID', 'hub-id')
    monkeypatch.setenv('NAVER_HUB_CLIENT_SECRET', 'hub-secret')
    monkeypatch.setattr(naver, 'api_call', lambda *a, **kw: pytest.fail('legacy fallback'))
    monkeypatch.setattr(naver, 'api_call_raw', lambda *a, **kw: {'error': 'HTTP 401'})
    assert naver.search_naver('query')['error'] == 'HTTP 401'


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
