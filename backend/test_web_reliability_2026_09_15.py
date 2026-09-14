"""웹 감사의 실패 재현: 출처 혼선·본문 손실·거짓 성공·수신 시간 상한."""
import asyncio
import importlib.util
import json
import sys
import threading
from pathlib import Path
from types import SimpleNamespace
from urllib.error import URLError

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boot_paths  # noqa: F401,E402

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / 'data/packages/installed/tools/web'


def load(filename, directory=WEB):
    spec = importlib.util.spec_from_file_location('web_audit_' + filename, directory / (filename + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def crawl(monkeypatch, tmp_path):
    from common import spill
    monkeypatch.setattr(spill, '_root', lambda: str(tmp_path))
    return load('tool_webcrawl')


@pytest.fixture
def handler():
    return load('handler')


def search(handler, **args):
    return json.loads(handler.execute(args, SimpleNamespace(tool_name='search', project_path='.')))


def test_mixed_html_preserves_body_order_without_duplication(crawl, monkeypatch):
    text = 'Plain paragraph. ' * 25
    html = ('<html><title>Report</title><body><article><header><h1>Heading</h1></header>'
            f'<p>{text}</p><div>DIV_BODY</div><ul><li>PARENT_LIST<ul><li>CHILD_LIST</li></ul>'
            'PARENT_TAIL</li></ul><section class="shareholder-letter"><p>SHAREHOLDER</p></section>'
            '<section id="recommendations">RECOMMENDATION</section>'
            '<figure><figcaption>CAPTION</figcaption></figure>'
            '<pre>if ready:\n    run()</pre><div class="share-buttons">NOISE</div>'
            '<!-- COMMENT --></article></body></html>')
    response = SimpleNamespace(status_code=200, url='https://example.test/article',
                               content=html.encode(), headers={'Content-Type': 'text/html; charset=utf-8'},
                               encoding='utf-8', text=html)
    monkeypatch.setattr(crawl, '_http_get', lambda _: response)
    out = crawl.crawl_website(response.url)
    assert out['success'] and not out['truncated']
    markers = ['Heading', 'DIV_BODY', 'PARENT_LIST', 'CHILD_LIST', 'PARENT_TAIL',
               'SHAREHOLDER', 'RECOMMENDATION', 'CAPTION']
    offsets = [out['text'].index(marker) for marker in markers]
    assert offsets == sorted(offsets)
    assert all(out['text'].count(marker) == 1 for marker in markers)
    assert 'NOISE' not in out['text'] and 'COMMENT' not in out['text']
    assert 'if ready:\n    run()' in out['text']
    snapshot = json.loads(Path(out['source_ref']['path']).read_text())
    assert snapshot['text'] == out['text']
    again = crawl.crawl_website(response.url)
    assert again['cache']['hit'] and again['text'] == out['text']


class FakePage:
    def __init__(self, url='', status=200):
        self.url, self.status, self.closed = url, status, False
        self.frames = [self]
        self.fail = None

    def on(self, *args):
        pass

    async def add_init_script(self, script):
        pass

    async def goto(self, url, **kwargs):
        self.url = url
        await asyncio.sleep(0.01 if url.endswith('/a') else 0.02)
        if self.fail:
            raise self.fail
        return SimpleNamespace(status=self.status)

    async def wait_for_load_state(self, *args, **kwargs):
        pass

    async def inner_text(self, selector):
        return (self.url + ' body. ') * 20

    async def title(self):
        return self.url

    def is_closed(self):
        return self.closed

    async def close(self):
        self.closed = True


class FakeContext:
    def __init__(self, session, status=200):
        self.session, self.status, self.pages = session, status, []

    async def new_page(self):
        page = FakePage(status=self.status)
        self.pages.append(page)
        self.session._on_new_page(page)
        return page


def browser_session(monkeypatch, *, active=True, status=200):
    mod = load('browser_session', WEB.parent / 'browser-action')
    session = mod.BrowserSession()
    context = FakeContext(session, status)
    session._context = context
    session._headless = False
    session.starts = 0
    async def start(headless):
        session.starts += 1
        await asyncio.sleep(0.01)
        session._headless = headless
        session._browser = SimpleNamespace(is_connected=lambda: True)
        await context.new_page()
    async def save():
        pass
    monkeypatch.setattr(session, '_start_browser', start)
    monkeypatch.setattr(session, '_reset_timer', lambda: None)
    monkeypatch.setattr(session, 'save_storage_state', save)
    if active:
        session._browser = SimpleNamespace(is_connected=lambda: True)
        session._on_new_page(FakePage('existing'))
    return session


@pytest.mark.parametrize('active', [True, False])
def test_parallel_crawl_uses_own_tab_and_serializes_cold_start(crawl, monkeypatch, active):
    session = browser_session(monkeypatch, active=active)
    async def run():
        return await asyncio.gather(*[
            crawl._crawl_playwright_async(session, 'https://example.test/' + label, None)
            for label in ('a', 'b')])
    results = asyncio.run(run())
    for result in results:
        assert result['success'] and result['title'] == result['url']
        assert result['url'] in result['text']
        assert result['resolved_url'] == result['url']
    assert session.starts == (0 if active else 1)
    assert len(session._pages) == 1  # 기존/초기 탭만 남고 중복 등록·누수가 없어야 한다.
    assert all(p.closed for p in session._context.pages[(0 if active else 1):])
    if active:
        assert session._headless is False


@pytest.mark.parametrize('status', [401, 403, 404, 429, 500, 503])
def test_browser_http_error_never_becomes_cached_success(crawl, monkeypatch, status):
    session = browser_session(monkeypatch, status=status)
    monkeypatch.setattr(crawl, '_crawl_static', lambda *a: {'success': False, 'error': f'HTTP {status}'})
    monkeypatch.setattr(crawl, '_get_chrome_driver', lambda: None)
    monkeypatch.setattr(crawl, '_get_browser_session', lambda: session)
    monkeypatch.setattr(crawl, '_run_async', asyncio.run)
    for _ in range(2):
        out = crawl.crawl_website('https://example.test/error')
        assert not out['success'] and 'source_ref' not in out and 'cache' not in out
    assert len(session._context.pages) == 2
    assert all(page.closed for page in session._context.pages)


def test_cancelled_navigation_closes_its_tab(crawl, monkeypatch):
    session = browser_session(monkeypatch)
    async def run():
        task = asyncio.create_task(crawl._crawl_playwright_async(session, 'https://example.test/a', None))
        await asyncio.sleep(0)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    asyncio.run(run())
    assert len(session._pages) == 1
    assert all(page.closed for page in session._context.pages)


def test_new_tab_navigation_failure_does_not_leave_alias_or_tab(monkeypatch):
    session = browser_session(monkeypatch)
    new_page = session._context.new_page
    async def fail_page():
        page = await new_page()
        page.fail = RuntimeError('navigation failed')
        return page
    monkeypatch.setattr(session._context, 'new_page', fail_page)
    with pytest.raises(RuntimeError, match='navigation failed'):
        asyncio.run(session.new_tab('https://example.test/bad'))
    assert len(session._pages) == 1 and session._context.pages[0].closed


@pytest.mark.parametrize('status', [200, 404, 0, None])
def test_chrome_uses_private_tab_and_verified_status(crawl, monkeypatch, status):
    calls = []
    async def call(tool, params):
        calls.append((tool, params))
        if tool == 'tabs_create_mcp':
            return {'tabId': 17}
        assert params['tabId'] == 17
        if tool == 'javascript_tool':
            return {'text': json.dumps({'title': 'Article', 'url': 'https://example.test/final', 'status': status})}
        if tool == 'get_page_text':
            return {'text': 'Readable article. ' * 50}
        return {}
    async def no_sleep(*a):
        pass
    monkeypatch.setattr(crawl.asyncio, 'sleep', no_sleep)
    driver = SimpleNamespace(call_tool=call, _tab_id=3)
    out = asyncio.run(crawl._crawl_chrome_async(driver, 'https://example.test/start', None))
    assert out['success'] is (status == 200)
    assert calls[-1][0] == 'tabs_close_mcp' and driver._tab_id == 3
    if status == 200:
        assert out['resolved_url'] == 'https://example.test/final'
    else:
        assert not any(name == 'get_page_text' for name, _ in calls)


def test_runner_timeout_cancels_future(crawl, monkeypatch):
    import system_tools
    cancelled = []
    class Future:
        def result(self, timeout):
            raise TimeoutError('timeout')
        def cancel(self):
            cancelled.append(True)
    monkeypatch.setattr(system_tools, '_get_async_loop', lambda: object())
    monkeypatch.setattr(crawl.asyncio, 'run_coroutine_threadsafe', lambda *a: Future())
    with pytest.raises(TimeoutError):
        crawl._run_async(object())
    assert cancelled == [True]


def test_chrome_runner_timeout_still_reaches_playwright(crawl, monkeypatch):
    monkeypatch.setattr(crawl, '_crawl_static', lambda *a: {'success': False})
    monkeypatch.setattr(crawl, '_get_chrome_driver', lambda: object())
    monkeypatch.setattr(crawl, '_get_browser_session', lambda: object())
    monkeypatch.setattr(crawl, '_crawl_chrome_async', lambda *a: 'chrome')
    monkeypatch.setattr(crawl, '_crawl_playwright_async', lambda *a: 'pw')
    def run(stage):
        if stage == 'chrome':
            raise TimeoutError('Chrome timed out')
        return {'success': True, 'text': 'article', 'method': 'playwright'}
    monkeypatch.setattr(crawl, '_run_async', run)
    assert crawl.crawl_website('https://example.test')['success']


def test_hn_network_failure_is_not_successful_zero(handler, monkeypatch):
    monkeypatch.setattr('urllib.request.urlopen', lambda *a, **k: (_ for _ in ()).throw(URLError('offline')))
    out = search(handler, source='hn', query='test')
    assert not out['success'] and out['items'] == [] and 'offline' in out['error']


@pytest.mark.parametrize('queries', [['good', 'bad'], ['bad'], ['empty']])
def test_hn_batch_preserves_partial_results_and_distinguishes_empty(handler, monkeypatch, queries):
    def items(query='', *a, **kw):
        if query == 'bad':
            raise RuntimeError('upstream failed')
        return [] if query == 'empty' else [{'title': query, 'url': 'https://example.test'}]
    monkeypatch.setattr(handler, '_hn_items', items)
    out = search(handler, source='hn', queries=queries)
    assert out['success'] is ('bad' not in queries)
    assert len(out['items']) == int('good' in queries)
    if 'bad' in queries:
        assert out['errors'] == [{'query': 'bad', 'error': 'upstream failed'}]


def test_hn_malformed_payload_is_failure(handler, monkeypatch):
    monkeypatch.setattr(handler, 'load_module', lambda _: SimpleNamespace(read_json=lambda _: {'error': 'bad API'}))
    assert not search(handler, source='hn', query='test')['success']


def test_guardian_date_survives_direct_and_joined_results(handler, monkeypatch):
    import requests
    monkeypatch.setenv('GUARDIAN_API_KEY', 'test-placeholder')
    payload = {'response': {'results': [{'webTitle': 'T', 'webUrl': 'https://example.test',
                                      'webPublicationDate': '2026-09-15T01:02:03Z'}]}}
    monkeypatch.setattr(requests, 'get', lambda *a, **kw: SimpleNamespace(
        raise_for_status=lambda: None, json=lambda: payload))
    direct = search(handler, source='guardian', query='test')
    joined = handler._guardian_items('test')
    assert direct['items'][0]['date'] == joined[0]['date'] == '2026-09-15T01:02:03+00:00'
    assert handler._iso_date_field('yesterday') == handler._iso_date_field('2026-09-15') == {}
    payload['response']['results'] = []
    assert search(handler, source='guardian', query='empty')['success']


def test_feed_is_parsed_from_bounded_download(handler, monkeypatch):
    io = load('web_search_io')
    xml = b'<rss version="2.0"><channel><title>News</title></channel></rss>'
    seen = []
    monkeypatch.setattr(io, 'download', lambda url: (seen.append(url) or xml, {'Content-Type': 'application/rss+xml'}, url))
    monkeypatch.setattr(handler, 'load_module', lambda _: io)
    out = search(handler, source='gnews', query='empty')
    assert out['success'] and out['items'] == [] and len(seen) == 1


def test_download_has_socket_and_stream_deadlines(monkeypatch):
    io = load('web_search_io')
    clock = [0.0]
    class Response:
        headers = {}
        def __enter__(self): return self
        def __exit__(self, *a): self.closed = True
        def geturl(self): return 'https://example.test/feed'
        def read1(self, count):
            clock[0] += 11
            return b'x'
    response = Response()
    timeouts = []
    def open_url(req, timeout):
        timeouts.append(timeout)
        return response
    monkeypatch.setattr(io.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(io.urllib.request, 'urlopen', open_url)
    with pytest.raises(TimeoutError, match='수신 시간'):
        io.download('https://example.test/feed')
    assert timeouts == [5] and response.closed


def test_batch_deadline_returns_completed_results_without_waiting(monkeypatch):
    io = load('web_search_io')
    release = threading.Event()
    def blocked():
        release.wait(2)
        return {'items': [{'title': 'late'}]}
    try:
        result = io.fetch_sections([('fast', lambda: {'items': [{'title': 'kept'}]}),
                                    ('slow', blocked)], timeout=0.03)
        assert result[0]['items'][0]['title'] == 'kept'
        assert result[1]['items'] == [] and '시간 초과' in result[1]['error']
        assert not release.is_set()
    finally:
        release.set()


def test_crawl_module_reload_reuses_browser_session(monkeypatch):
    monkeypatch.delitem(sys.modules, 'browser_session', raising=False)
    monkeypatch.delitem(sys.modules, 'webcrawl_browser_session', raising=False)
    # Registering through monkeypatch also restores the global module map after this test.
    first = load('tool_webcrawl')._get_browser_session()
    module = sys.modules.pop('webcrawl_browser_session')
    monkeypatch.setitem(sys.modules, 'webcrawl_browser_session', module)
    second = load('tool_webcrawl')._get_browser_session()
    assert first is not None and first is second


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
