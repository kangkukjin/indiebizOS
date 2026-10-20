"""Search batches retain source estimates without confusing them with row counts."""
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

import boot_paths  # noqa: F401


@pytest.fixture
def web():
    path = Path(__file__).resolve().parents[1] / 'data/packages/installed/tools/web/handler.py'
    spec = importlib.util.spec_from_file_location('web_search_audit', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_partial_batch_still_filters_dates_and_recounts(web, monkeypatch):
    monkeypatch.setattr(web, '_execute', lambda args, ctx: {
        'success': False, 'items': [{'query': 'ok', 'date': '2020-01-01T00:00:00Z'}],
        'sections': [{'query': 'ok', 'count': 1}, {'query': 'bad', 'count': 0}],
        'errors': [{'query': 'bad', 'error': 'offline'}]})
    out = web.execute({'source': 'gnews', 'queries': ['ok', 'bad'], 'days': 7},
                      SimpleNamespace(tool_name='search'))
    assert out['success'] is False and out['items'] == []
    assert out['errors'] == [{'query': 'bad', 'error': 'offline'}]
    assert out['sections'][0]['count'] == 0


@pytest.mark.parametrize('batch', [False, True])
def test_news_filters_full_feed_before_limit(web, monkeypatch, batch):
    class Feed(dict):
        @property
        def entries(self):
            return self['entries']

    now = datetime.now(timezone.utc)
    def entry(title, age):
        return {'title': title, 'link': f'https://example.test/{title}',
                'published': (now - timedelta(days=age)).strftime('%a, %d %b %Y %H:%M:%S +0000')}
    monkeypatch.setattr(web, '_read_feed', lambda url: Feed(
        version='rss20', entries=[entry('old', 60), entry('new', 1)]))
    args = {'source': 'gnews', 'limit': 1, 'days': 7,
            **({'queries': ['fixture']} if batch else {'query': 'fixture'})}
    out = json.loads(web.execute(args, SimpleNamespace(tool_name='search', project_path='.')))
    assert out['success'] and [row['title'] for row in out['items']] == ['new']
    assert out['count'] == 1


def test_guardian_auth_error_does_not_return_secret(web, monkeypatch):
    import requests
    key = 'fixture-secret-do-not-return'
    monkeypatch.setenv('GUARDIAN_API_KEY', key)
    response = requests.Response()
    response.status_code = 401
    response.url = f'https://content.guardianapis.com/search?api-key={key}'
    monkeypatch.setattr(requests, 'get', lambda *a, **kw: response)
    out = web._search_guardian({'query': 'climate'})
    assert out['success'] is False and out['status_code'] == 401
    assert out['reason'] == 'authentication_failed'
    assert key not in json.dumps(out) and 'api-key=' not in json.dumps(out)


@pytest.mark.parametrize('batch', [False, True])
def test_guardian_failure_survives_news_merge(web, monkeypatch, batch):
    monkeypatch.setattr(web, 'search_gnews', lambda **kw: {
        'success': True, 'results': [{'title': 'kept', 'url': 'https://example.test'}]})
    monkeypatch.setattr(web, '_search_guardian', lambda args: {
        'success': False, 'items': [], 'error': 'HTTP 401'})
    monkeypatch.setattr(web, '_curate_sections_batch', lambda secs, keep: [
        {'picks': sec['items'], 'rest': []} for sec in secs])
    monkeypatch.setattr(web, '_load_perspective_core', lambda: '')
    args = {'source': 'gnews', 'curate': 1,
            **({'queries': ['climate']} if batch else {'query': 'climate'})}
    out = json.loads(web.execute(args, SimpleNamespace(tool_name='search', project_path='.')))
    assert out['success'] is False and out['errors']
    assert [row['title'] for row in out['items']] == ['kept']


def test_batch_preserves_zero_estimate_missing_estimate_and_failure(monkeypatch):
    path = Path(__file__).resolve().parents[1] / 'data/packages/installed/tools/web/handler.py'
    spec = importlib.util.spec_from_file_location('web_search_contract', path)
    handler = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(handler)
    responses = {'many': {'success': True, 'items': [{'title': 'a'}], 'total_estimate': 59515},
                 'zero': {'success': True, 'items': [], 'total_estimate': 0},
                 'unknown': {'success': True, 'items': []},
                 'failed': {'success': False, 'error': 'offline', 'items': []}}
    monkeypatch.setattr(handler, 'execute', lambda args, ctx: json.dumps(responses[args['query']]))
    monkeypatch.setattr(handler, '_fetch_sections', lambda jobs: [job() for _, job in jobs])
    out = handler._batch_search({'queries': list(responses)}, 'naver_search', 'naver', '.')
    assert [s['count'] for s in out['sections']] == [1, 0, 0, 0]
    assert out['sections'][0]['total_estimate'] == 59515
    assert out['sections'][1]['total_estimate'] == 0
    assert all('total_estimate' not in s for s in out['sections'][2:])
    assert out['count'] == 1 and out['errors']


if __name__ == "__main__":
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
