"""내장 수집은 본문 조각·프레임을 보존하고 자신이 연 탭만 정리한다."""
import asyncio
from pathlib import Path

import boot_paths  # noqa: F401
import pytest
from common.pkg_utils import load_sibling

WEB = Path(__file__).resolve().parents[1] / 'data/packages/installed/tools/web/handler.py'


@pytest.fixture
def embedded():
    return load_sibling(WEB, 'webcrawl_embedded')


class Bridge:
    def __init__(self, *, capture=False, broken=False):
        self.calls, self.frame = [], 0
        self.capture, self.broken = capture, broken

    async def __call__(self, **args):
        self.calls.append(args)
        if args['op'] == 'tab':
            return {'success': True, 'tab_id': 'new-owned-tab'}
        if args['op'] == 'iframe':
            if args['mode'] == 'switch':
                self.frame = 1
            return {'success': True, 'frames': [{'url': 'https://example.test/frame'}]}
        if args['op'] == 'content':
            offset = args.get('offset', 0)
            if self.broken and offset:
                return {'success': False, 'error': 'STALE_CURSOR'}
            return {'success': True, 'document_id': f'doc-{self.frame}', 'cursor': f'cursor-{self.frame}',
                    'url': 'https://example.test/frame' if self.frame else 'https://example.test',
                    'title': 'Title', 'offset': offset, 'content': 'second' if offset else 'first ',
                    'next_offset': None if offset else 6, 'capture_truncated': self.capture}
        return {'success': True}


def test_all_chunks_and_frames_are_collected_and_owned_tab_closed(embedded):
    call = Bridge()
    out = asyncio.run(embedded.collect(call, 'https://example.test', lambda *a: None))
    assert out['success'] and out['text'] == 'first second\n\nfirst second'
    assert out['truncated'] is False
    assert len(out['_content_selection']) == 2
    assert call.calls[-2] == {'op': 'tab', 'mode': 'close', 'tab_id': 'new-owned-tab', 'timeout': 2000}
    assert call.calls[-1]['op'] == 'close'


def test_capture_limit_is_reported_as_partial(embedded):
    out = asyncio.run(embedded.collect(Bridge(capture=True), 'https://example.test', lambda *a: None))
    assert out['success'] and out['source_complete'] is False and out['errors']
    assert out['truncated'] is True


def test_cursor_failure_cannot_become_complete_body(embedded):
    call = Bridge(broken=True)
    out = asyncio.run(embedded.collect(call, 'https://example.test', lambda *a: None))
    assert out['success'] is False and 'STALE_CURSOR' in out['error']
    assert call.calls[-1]['op'] == 'close'


def test_nonowner_does_not_load_owner_connection(embedded, monkeypatch):
    import principal
    monkeypatch.setattr(principal, 'is_owner', lambda: False)
    monkeypatch.setattr(embedded, 'load_singleton', lambda *a: pytest.fail('owner connection accessed'))
    assert embedded.prepare() is None


def test_prepare_uses_protocol_owner_and_fixed_embedded_driver(embedded, monkeypatch):
    import principal
    import re
    from types import SimpleNamespace
    seen = []
    async def route(args, tool, owner, allowed, chrome):
        seen.append((args, owner, allowed, chrome))
        return 'embedded', {'success': True}
    monkeypatch.setattr(principal, 'is_owner', lambda: True)
    monkeypatch.setattr(embedded, 'load_singleton', lambda *a: SimpleNamespace(
        connection=lambda: True, route=route))
    call = embedded.prepare()
    asyncio.run(call(op='tab', mode='list'))
    assert re.fullmatch('[a-f0-9]{64}', seen[0][1])
    assert seen[0][0]['driver'] == 'embedded' and seen[0][2:] == (True, False)


def test_unavailable_connection_before_navigation_can_fall_back(embedded):
    calls = []
    async def call(**args):
        calls.append(args)
        return {'success': False, 'error_code': 'BROWSER_UNAVAILABLE', 'error': 'offline'}
    out = asyncio.run(embedded.collect(call, 'https://example.test', lambda *a: None))
    assert out['fallback_safe'] is True
    assert all(args.get('mode') != 'new' for args in calls)


def test_selected_embedded_failure_does_not_change_login_session(monkeypatch):
    crawl = load_sibling(WEB, 'tool_webcrawl')
    from types import SimpleNamespace
    async def failure(*args):
        return {'success': False, 'method': 'embedded', 'error': 'login required'}
    monkeypatch.setattr(crawl, '_resolve_google_news', lambda url: None)
    monkeypatch.setattr(crawl, '_crawl_static', lambda *a, **kw: {
        'success': False, 'reason': 'login_required', 'method': 'curl_cffi'})
    monkeypatch.setattr(crawl, 'load_sibling', lambda *a: SimpleNamespace(prepare=lambda: object(), collect=failure))
    monkeypatch.setattr(crawl, '_run_async', asyncio.run)
    monkeypatch.setattr(crawl, '_get_chrome_driver', lambda: pytest.fail('different login session'))
    out = crawl._crawl_website_impl('https://example.test')
    assert out['success'] is False and out['methods_tried'] == ['curl_cffi', 'embedded']


def test_content_only_snapshot_is_not_reused_for_metadata(monkeypatch, tmp_path):
    store = load_sibling(WEB, 'webcrawl_store')
    monkeypatch.setattr(store, '_policy', lambda: {'reuse_seconds': 900})
    calls = []
    def fetch():
        calls.append(True)
        return {'success': True, 'text': 'body', 'length': 4}
    store.fetch_once('https://example.test', fetch, project_path=str(tmp_path))
    store.fetch_once('https://example.test', fetch, project_path=str(tmp_path), op='metadata')
    assert len(calls) == 2


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
