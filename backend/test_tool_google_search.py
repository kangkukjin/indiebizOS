"""Google search: extraction, authority, partial batches, fixed browser capture."""
import boot_paths  # noqa: F401
import asyncio
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from common.pkg_utils import load_sibling

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / 'data/packages/installed/tools/web/handler.py'
HTML = '''<div id="rso"><div><a href="https://example.com/product?id=1#details"><h3>울 캐시 코트</h3></a>
<div class="VwiC3b">cashmere hooded coat</div></div>
<div id="bottomads"><a href="https://ads.test"><h3>Ad</h3></a></div>
<div hidden><a href="https://hidden.test"><h3>Hidden</h3></a></div>
<a href="/url?q=https%3A%2F%2Fexample.com%2Fproduct%3Fid%3D1"><h3>Duplicate</h3></a>
<div><a href="/url?url=https%3A%2F%2Fsqlite.org%2Fwal.html"><h3>Write-Ahead Logging</h3></a></div></div>'''
URL = 'https://www.google.com/search?q=coat'


@pytest.fixture
def google():
    return load_sibling(WEB, 'tool_google_search')


def test_organic_urls_snippets_ads_and_duplicates(google):
    result = google._parser().parse_results(HTML, URL)
    assert result['success'] and result['count'] == 2
    assert result['items'][0] == {'title': '울 캐시 코트', 'url': 'https://example.com/product?id=1',
                                 'summary': 'cashmere hooded coat', 'meta': 'Google', 'rank': 1}
    assert result['items'][1]['summary'] == ''
    assert result['items'][1]['url'] == 'https://sqlite.org/wal.html'


@pytest.mark.parametrize('html,url,code', [('', URL, 'RESULTS_UNRECOGNIZED'),
    ('<div id="rso">No results found</div>', URL, 'RESULTS_UNRECOGNIZED'),
    ('', 'https://www.google.com/sorry/index', 'CAPTCHA_REQUIRED'),
    ('<iframe src="https://x/recaptcha"></iframe>', URL, 'CAPTCHA_REQUIRED'),
    ('', 'https://consent.google.com/m', 'CONSENT_REQUIRED'),
    ('', 'https://accounts.google.com/', 'UNEXPECTED_PAGE')])
def test_block_and_unknown_are_failures(google, html, url, code):
    assert google._parser().parse_results(html, url)['error_code'] == code


def test_only_explicit_empty_is_success(google):
    assert google._parser().parse_results('<div id="topstuff">No results found</div>', URL) == {
        'success': True, 'items': [], 'count': 0, 'message': 'Google이 검색 결과 없음으로 표시했습니다.'}


def test_nonowner_never_opens_browser(google, monkeypatch):
    import principal
    monkeypatch.setattr(google, '_run', lambda *_: pytest.fail('browser used'))
    with principal.narrow(principal.member('test')):
        assert google.search({'query': 'x'})['error_code'] == 'FORBIDDEN'


@pytest.mark.parametrize('args', [{'queries': []}, {'queries': ['x'] * 11}, {'query': ''},
    {'query': 'x', 'limit': -1}, {'query': 'x', 'country': 'invalid'}, {'query': 'x', 'language': 'invalid'}])
def test_bad_inputs_do_not_open_browser(google, monkeypatch, args):
    monkeypatch.setattr(google, '_run', lambda *_: pytest.fail('browser used'))
    assert not google.search(args)['success']


class Bridge:
    def __init__(self, pages):
        self.pages = iter(pages)
        self.calls = []

    async def __call__(self, **args):
        self.calls.append(args)
        if args['op'] == 'tab':
            return {'success': True, 'tab_id': 'owned-google-tab'}
        if args['op'] == 'google_results':
            return next(self.pages)
        return {'success': True}


def test_batch_partial_and_cleanup_no_driver_fallback(google, monkeypatch):
    monkeypatch.setattr(google, '_session_module', lambda: pytest.fail('fallback attempted'))
    call = Bridge([{'url': URL, 'html': HTML, 'query': 'coat'}, {'url': 'https://www.google.com/sorry', 'html': ''}])
    out = asyncio.run(google._collect(['coat', 'SQLite', 'third'], 5, '', 'auto', 'owner', True, call))
    assert not out['success'] and out['count'] == 2
    assert all(x['query'] == 'coat' for x in out['items'])
    assert [e['error_code'] for e in out['errors']] == ['CAPTCHA_REQUIRED', 'SKIPPED_AFTER_BLOCK']
    assert len([c for c in call.calls if c['op'] == 'navigate']) == 2
    assert call.calls[-2] == {'op': 'tab', 'mode': 'close', 'tab_id': 'owned-google-tab', 'timeout': 2000}
    assert call.calls[-1]['op'] == 'close'


def test_cleanup_failure_preserves_results(google):
    call = Bridge([{'url': URL, 'html': HTML, 'query': 'q'}])
    async def broken(**args):
        if args['op'] == 'close' or args.get('mode') == 'close':
            raise OSError('gone')
        return await call(**args)
    out = asyncio.run(google._collect(['q'], 5, '', 'en', 'owner', False, broken))
    assert out['success'] and out['count'] == 2 and out['cleanup_error'] == 'OSError'


def test_router_uses_google_batch_and_rejects_days(monkeypatch):
    handler = load_sibling(WEB, 'handler')
    seen = []
    original = handler.load_module
    monkeypatch.setattr(handler, 'load_module', lambda name: SimpleNamespace(
        search=lambda args, project: seen.append((name, args, project)) or {'success': True, 'items': []})
        if name == 'tool_google_search' else original(name))
    context = SimpleNamespace(tool_name='search', project_path='/tmp/project')
    args = {'source': 'google', 'queries': ['a', 'b']}
    assert json.loads(handler.execute(args, context))['success']
    assert seen == [('tool_google_search', args, '/tmp/project')]
    assert not json.loads(handler.execute({**args, 'days': 3}, context))['success']
    assert len(seen) == 1


def test_fixed_embedded_capture_renders_and_excludes_private_fields(google):
    from playwright.async_api import async_playwright
    from runtime_utils import setup_playwright_browsers_path
    setup_playwright_browsers_path()
    expression = subprocess.check_output(['node', '--input-type=module', '-e',
        "import {expression} from './frontend/electron/embedded-browser-dom.js';"
        "process.stdout.write(expression('google_results', {}))"], cwd=ROOT, text=True)

    async def run():
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                html = HTML.replace('</div>', '<input value="PRIVATE"><script>/*PRIVATE*/</script></div>', 1)
                html += '<nav>PRIVATE ACCOUNT</nav><div style="display:none" id="extra">PRIVATE</div>'
                await page.route('https://www.google.com/**', lambda route: route.fulfill(body=html, content_type='text/html'))
                await page.goto(URL)
                value = await page.evaluate(expression)
                assert 'PRIVATE' not in value['html']
                out = google._parser().parse_results(value['html'], value['url'])
                assert out['success'] and out['count'] == 2
                assert out['items'][0]['url'].endswith('?id=1')
                await page.goto('about:blank')
                with pytest.raises(Exception, match='UNEXPECTED_PAGE'):
                    await page.evaluate(expression)
            finally:
                await browser.close()
    asyncio.run(run())


def test_aborted_navigation_observes_matching_results_without_renavigating(google):
    call = Bridge([{'url': URL, 'html': HTML, 'query': 'q'}])
    async def aborted(**args):
        if args['op'] == 'navigate':
            call.calls.append(args)
            return {'success': False, 'error_code': 'ERR_ABORTED'}
        return await call(**args)
    result = asyncio.run(google._one_embedded(aborted, 'owned-google-tab', 'q', 5, '', 'en'))
    assert result['success']
    assert len([x for x in call.calls if x['op'] == 'navigate']) == 1
    call = Bridge([{'url': URL, 'html': HTML, 'query': 'old query'}] * 25)
    result = asyncio.run(google._one_embedded(call, 'owned-google-tab', 'q', 5, '', 'en'))
    assert result['error_code'] == 'QUERY_MISMATCH'


def test_opaque_google_redirect_is_preserved_not_invented_or_dropped(google):
    html = '<div id="rso"><a href="/goto?url=opaque-token"><h3>Document</h3></a></div>'
    row = google._parser().parse_results(html, URL)['items'][0]
    assert row['url'] == 'https://www.google.com/goto?url=opaque-token'
    assert row['url_kind'] == 'google_redirect'
    assert google._parser().destination('https://[') is None
    assert google._parser().destination('/search?q=other') is None


def test_playwright_search_serializes_page_use_and_reports_reuse(google):
    class Session:
        def __init__(self):
            self._operation_lock = asyncio.Lock()
            self.is_active = False
            self.busy = False
            self.page = SimpleNamespace(url=URL, goto=self.goto, content=self.content)

        async def ensure_browser(self, headless):
            assert headless is True and self._operation_lock.locked()
            self.is_active = True
            return self.page

        async def goto(self, url, **kwargs):
            assert not self.busy
            self.busy = True
            self.page.url = url
            await asyncio.sleep(0)
            return SimpleNamespace(status=200)

        async def content(self):
            self.busy = False
            return HTML

    async def run():
        session = Session()
        a, b = await asyncio.gather(google._one(session, 'a', 1, '', 'en'),
                                    google._one(session, 'b', 1, '', 'en'))
        assert a['success'] and b['success']
        assert not a['session_reused'] and b['session_reused']
        assert a['count'] == b['count'] == 1
    asyncio.run(run())


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
