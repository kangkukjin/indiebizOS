"""Browser crawl content must match its declared scope and preserve source failures."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest
from common.pkg_utils import load_sibling, load_singleton
from ibl_v2_adapters import decode_envelope
from ibl_v2_ir import Fault

WEB = Path(__file__).resolve().parents[1] / 'data/packages/installed/tools/web/tool_webcrawl.py'
URL = 'https://fixture.test/research'
CODE = 'if ready:\n    save_backup()\n\n    check_values()'
BODY = ('Evidence with limitations. ' * 20).rstrip()
HTML = (f'<html><title>Research</title><body><nav>OUTSIDE MENU</nav><main>'
        f'<header><h1>Research</h1></header><p>{BODY}</p><pre>{CODE}</pre>'
        '<figure><figcaption>Important caption</figcaption></figure></main>'
        '<footer>OUTSIDE FOOTER</footer></body></html>')
TEXT = f'OUTSIDE MENU\n\nResearch\n\n{BODY}\n\n{CODE}\n\nOUTSIDE FOOTER'


@pytest.fixture
def crawl():
    return load_sibling(WEB, 'tool_webcrawl')


class Frame:
    def __init__(self, html=HTML, text=TEXT, url=URL):
        self.html, self.text, self.url = html, text, url
        self.text_calls = 0

    async def content(self):
        if self.html is None:
            raise RuntimeError('DOM unavailable')
        return self.html

    async def inner_text(self, selector):
        self.text_calls += 1
        if self.text is None:
            raise RuntimeError('frame detached')
        return self.text


class Session:
    def __init__(self, frames):
        self.frames = frames
        self.url = URL
        self.closed = []

    async def ensure_browser(self, **kwargs):
        pass

    async def new_tab(self):
        return 'owned'

    def get_tab_page(self, tab):
        return self

    async def goto(self, *args, **kwargs):
        return SimpleNamespace(status=200)

    async def wait_for_load_state(self, *args, **kwargs):
        pass

    async def title(self):
        return 'Research'

    async def close_tab(self, tab):
        self.closed.append(tab)


def playwright(crawl, frames):
    session = Session(frames)
    raw = asyncio.run(crawl._crawl_playwright_async(session, URL, None))
    assert session.closed == ['owned']
    return raw, crawl._structure().project(raw, 'content')


def chrome(crawl, monkeypatch, *, html=HTML, frames=0):
    calls = []

    async def call(tool, params):
        calls.append(tool)
        if tool == 'tabs_create_mcp':
            return {'tabId': 1}
        if tool == 'javascript_tool':
            if 'outerHTML' in params['text']:
                return {'text': json.dumps({'html': html, 'frames': frames})}
            return {'text': json.dumps({'title': 'Research', 'url': URL, 'status': 200})}
        if tool == 'get_page_text':
            return {'text': TEXT}
        return {}

    async def no_wait(*args):
        pass

    monkeypatch.setattr(crawl.asyncio, 'sleep', no_wait)
    raw = asyncio.run(crawl._crawl_chrome_async(SimpleNamespace(call_tool=call), URL, None))
    assert calls[-1] == 'tabs_close_mcp'
    return raw, crawl._structure().project(raw, 'content'), calls


@pytest.mark.parametrize('engine', ['playwright', 'chrome'])
def test_rendered_dom_uses_same_body_and_code_as_static_html(crawl, monkeypatch, engine):
    frame = Frame()
    if engine == 'playwright':
        raw, out = playwright(crawl, [frame])
        assert frame.text_calls == 0  # No second browser round trip for the same document.
    else:
        raw, out, calls = chrome(crawl, monkeypatch)
        assert 'get_page_text' not in calls
    assert out['text'] == crawl._parse_html(HTML, URL)[1]
    assert CODE in out['text'] and BODY in out['text'] and 'Important caption' in out['text']
    assert 'OUTSIDE' not in out['text']
    assert out['content_selection'][0]['scope'] == 'declared_content'
    assert raw['_page_structure']['documents'][0]['html'] == HTML
    assert '_content_selection' not in out


@pytest.mark.parametrize('engine', ['playwright', 'chrome'])
def test_dom_unavailable_uses_honest_rendered_fallback_without_stripping_code(crawl, monkeypatch, engine):
    if engine == 'playwright':
        _, out = playwright(crawl, [Frame(html=None)])
    else:
        _, out, calls = chrome(crawl, monkeypatch, html=None)
        assert calls.count('get_page_text') == 1
    assert out['success'] and CODE in out['text']
    assert out['content_selection'][0]['scope'] == 'rendered_body_fallback'


@pytest.mark.parametrize('engine', ['playwright', 'chrome'])
def test_missing_frame_becomes_partial_source_with_readable_evidence(crawl, monkeypatch, engine):
    if engine == 'playwright':
        raw, out = playwright(crawl, [Frame(), Frame(None, None, 'https://fixture.test/missing')])
    else:
        raw, out, _ = chrome(crawl, monkeypatch, frames=1)
    assert out['source_complete'] is False and out['errors']
    with pytest.raises(Fault) as exc:
        decode_envelope(out, {'protocol': 'legacy-envelope', 'value_path': ''})
    assert exc.value.code == 'PARTIAL_SOURCE'
    assert BODY in exc.value.partial['text']
    assert exc.value.partial['errors'][0]['source_url']


def test_missing_frame_result_is_saved_but_never_cached(crawl):
    raw, _ = playwright(crawl, [Frame(), Frame(None, None)])
    store = load_singleton(WEB, 'webcrawl_store')
    calls = []

    def fetch():
        calls.append(1)
        return raw

    first = store.fetch_once(URL, fetch)
    second = store.fetch_once(URL, fetch)
    assert len(calls) == 2 and not second['cache']['hit']
    assert first['source_ref']['path'] != second['source_ref']['path']
    saved = json.loads(Path(first['source_ref']['path']).read_text())
    assert saved['source_complete'] is False and saved['errors']


def test_structure_request_cannot_seed_complete_content_with_missing_frame(crawl):
    session = Session([Frame(), Frame(None, None)])
    raw = asyncio.run(crawl._crawl_playwright_async(session, URL, None, op='links'))
    store = load_singleton(WEB, 'webcrawl_store')
    store.fetch_once(URL, lambda: raw, op='links')
    calls = []

    def refetch():
        calls.append(1)
        return {'success': True, 'text': BODY, 'length': len(BODY)}

    out = store.fetch_once(URL, refetch, op='content')
    assert calls == [1] and not out['cache']['hit']


def test_multiple_frames_keep_order_and_declared_scope(crawl):
    frames = [Frame(), Frame('<article>Child evidence</article>', 'unused', URL + '/child')]
    _, out = playwright(crawl, frames)
    assert out['text'].endswith('Child evidence')
    assert out['text'].count(BODY) == 1
    assert [s['url'] for s in out['content_selection']] == [URL, URL + '/child']
    assert out.get('source_complete') is not False


def test_document_navigation_labels_do_not_become_research_evidence(crawl):
    html = ('<main><div class="searchoverlay">SEARCH UI</div>'
            '<div class="sidenavigation"><a>MENU</a></div>'
            '<article><header>Publication date</header><p>Verified finding</p>'
            '<section class="navigation-study">Navigation research remains</section>'
            '</article></main>')
    _, text = crawl._parse_html(html, URL)
    assert 'SEARCH UI' not in text and 'MENU' not in text
    assert all(t in text for t in ['Publication date', 'Verified finding', 'Navigation research remains'])


def test_longer_static_fallback_does_not_hide_observed_missing_frame(crawl, monkeypatch):
    raw, _ = playwright(crawl, [Frame(), Frame(None, None, URL + '/missing')])
    static = {'success': True, 'url': URL, 'title': 'Research', 'text': BODY * 3,
              'length': len(BODY) * 3, 'reason': 'insufficient_content'}
    monkeypatch.setattr(crawl, '_crawl_static', lambda *a, **k: static)
    monkeypatch.setattr(crawl, '_get_chrome_driver', lambda: None)
    monkeypatch.setattr(crawl, '_get_browser_session', lambda: object())

    async def partial(*args, **kwargs):
        return raw

    monkeypatch.setattr(crawl, '_crawl_playwright_async', partial)
    monkeypatch.setattr(crawl, '_run_async', asyncio.run)
    out = crawl.crawl_website(URL)
    assert out['text'] == BODY * 3
    assert out['source_complete'] is False and out['errors'][0]['source_url'] == URL + '/missing'
    with pytest.raises(Fault) as exc:
        decode_envelope(out, {'protocol': 'legacy-envelope', 'value_path': ''})
    assert exc.value.code == 'PARTIAL_SOURCE'


@pytest.mark.parametrize('empty', [False, True])
def test_research_collection_keeps_duplicate_and_partial_source_contract(crawl, tmp_path, empty):
    from dataclasses import replace
    from ibl_v2_adapters import Adapted, load_registry
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime

    good, _ = playwright(crawl, [Frame()])
    partial, _ = playwright(crawl, [Frame(), Frame(None, None, URL + '/missing')])
    store = load_sibling(WEB, 'webcrawl_store')
    calls = []

    def collect(rt, args):
        calls.append(args['url'])
        raw = dict(partial if args['url'].endswith('/partial') else good)
        raw['items'] = store.text_to_blocks(raw['title'], raw['text'])
        raw = crawl._structure().project(raw, 'content')
        return Adapted(*decode_envelope(raw, {'protocol': 'legacy-envelope', 'value_path': ''}))

    registry = load_registry(str(tmp_path))
    registry['sense:crawl'] = replace(registry['sense:crawl'], run=collect)
    source = [{'id': 'a', 'url': URL}, {'id': 'duplicate', 'url': URL},
              {'id': 'partial', 'url': URL + '/partial'}, {'id': 'b', 'url': URL + '/b'}]
    inputs = {'sources': [] if empty else source, 'out': str(tmp_path / 'report')}
    program = WEB.parents[5] / 'docs/experiments/long_sentence_imagination/round_38/drafts/collect_v0.ibl'
    plan = compile_program(program.read_text(), registry, inputs)
    assert not plan.issues
    result = Runtime(plan, inputs).run()
    assert result['success'], result
    saved = json.loads((tmp_path / 'report/source_index.json').read_text())
    assert saved == result['value']['index']
    if empty:
        assert not calls and not saved
    else:
        assert result['value']['requested'] == 4 and result['value']['unique'] == 3
        assert calls.count(URL) == 1 and len(calls) == 3
        assert [r['status'] for r in saved] == ['collected', 'failed', 'collected']
        assert saved[1]['error']['code'] == 'PARTIAL_SOURCE'
        assert BODY in saved[1]['error']['partial']['text']
        assert CODE in json.loads((tmp_path / 'report/sources/a.json').read_text())['text']


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
