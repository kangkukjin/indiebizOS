"""Browser tab contracts, frame-scoped observations and explicit DOM actions."""
import boot_paths  # noqa: F401
import asyncio
import json
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest
from test_browser_session import browser  # noqa: F401
from tool_context import ToolContext

ROOT = Path(__file__).resolve().parents[1]


def test_tab_id_is_valid_in_closed_contract():
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    code = '#!ibl edition=2\nreturn [limbs:browser]{op:"tab",mode:"switch",tab_id:"observed-tab"}'
    plan = compile_program(code, load_registry(str(ROOT)))
    assert not plan.issues, plan.report()


def test_frames_navigation_and_explicit_consent(browser, tmp_path):
    handler, module = browser
    context = ToolContext(str(tmp_path), 'browser_op', task_id='frame-contract')
    async def call(**args):
        return json.loads(await handler.execute({'driver': 'playwright', **args}, context))
    async def run():
        try:
            first = await call(op='navigate', url='about:blank', wait='load')
            assert first['success'], first
            session = next(iter(module.BrowserSession._sessions.values()))
            page = session.raw_page
            # All former auto-consent triggers remain untouched even after load timers/mutations.
            for new in (False, True):
                if new:
                    assert (await call(op='tab', mode='new', url='about:blank'))['success']
                    page = session.raw_page
                html = ('<form action="/consent"><button type="submit" '
                        'onclick="event.preventDefault();window.clicked=(window.clicked||0)+1">필수만 동의</button></form>')
                await page.route('https://consent.test/**', lambda route: route.fulfill(body=html, content_type='text/html; charset=utf-8'))
                await page.goto('https://consent.test/')
                await page.evaluate("document.body.appendChild(document.createElement('p'))")
                await asyncio.sleep(2.1)
                assert await page.evaluate('window.clicked||0') == 0
                snap = await call(op='snapshot')
                ref = next(e['ref'] for e in snap['snapshot'] if e['name'] == '필수만 동의')
                assert (await call(op='click', ref=ref))['success']
                assert await page.evaluate('window.clicked') == 1
            assert not (await call(op='tab', mode='switch', index=-1))['success']
            assert (await call(op='tab', mode='switch', index=0))['tab_id'] == first['tab_id']
            assert (await call(op='tab', mode='switch', tab_id=first['tab_id']))['success']
            page = session.raw_page
            await page.set_content('<button>Main only</button><iframe name="same"></iframe><iframe name="same"></iframe>')
            for i, frame in enumerate(page.frames[1:]):
                await frame.set_content(f'<label><input type="checkbox">Frame {i}</label>')
            for i in (0, 1):
                assert (await call(op='iframe', mode='switch', index=i))['success']
                snap = await call(op='snapshot')
                assert snap['frame']['kind'] == 'iframe', snap
                names = [e['name'] for e in snap['snapshot']]
                assert f'Frame {i}' in names and 'Main only' not in names, snap
                ref = next(e['ref'] for e in snap['snapshot'] if e['role'] == 'checkbox')
                assert (await call(op='check', ref=ref))['success']
                assert await page.frames[i+1].locator('input').is_checked()
            # Cross-site iframe target also uses its own AX tree, never the parent document.
            await call(op='iframe', mode='reset')
            await page.route('https://terms.test/**', lambda route: route.fulfill(
                body='<label><input type="checkbox">Cross site terms</label>', content_type='text/html'))
            await page.route('https://consent.test/cross', lambda route: route.fulfill(
                body='<button>Main only</button><iframe src="https://terms.test/"></iframe>', content_type='text/html'))
            await page.goto('https://consent.test/cross')
            assert await asyncio.wait_for(page.frames[1].evaluate('document.body.innerText'), timeout=5) == 'Cross site terms'
            assert (await call(op='iframe', mode='switch', index=0))['success']
            snap = await call(op='snapshot')
            assert snap['success'], snap
            assert any(e['role'] == 'checkbox' and e['name'] == 'Cross site terms' for e in snap['snapshot']), snap
            ref = next(e['ref'] for e in snap['snapshot'] if e['role'] == 'checkbox')
            assert (await call(op='check', ref=ref))['success']
            assert await page.frames[1].locator('input').is_checked()
            # An operation failure can leave a frame selected; every page navigation resets it.
            assert not (await call(op='click', ref='missing'))['success']
            assert (await call(op='navigate', url='about:blank', wait='load'))['success']
            assert session.page is session.raw_page and session._active_frame is None
            assert (await call(op='snapshot'))['frame']['kind'] == 'main'
        finally:
            await call(op='close')
    asyncio.run(asyncio.wait_for(run(), timeout=35))


def test_selector_timeout_preserves_accessibility_identity(browser, monkeypatch):
    handler, module = browser
    snapshot = handler._load('browser_snapshot')
    class Page:
        url = 'https://fixture.test'
        async def title(self): return 'Fixture'
    class CDP:
        async def send(self, *args):
            return {'nodes': [{'role': {'value': 'checkbox'}, 'name': {'value': 'Keep AX identity'}}]}
        async def detach(self): pass
    page = Page()
    session = SimpleNamespace(page=page, raw_page=page, active_tab_id='fixture-tab', clear_refs=lambda: None,
                              add_ref=lambda info: 'e1')
    async def cdp(*args): return CDP(), False
    async def timeout(*args): raise asyncio.TimeoutError()
    monkeypatch.setattr(module.BrowserSession, 'get_instance', lambda: session)
    monkeypatch.setattr(snapshot, 'ensure_active', lambda: None)
    monkeypatch.setattr(snapshot, '_frame_cdp', cdp)
    monkeypatch.setattr(snapshot, '_extract_selectors_via_cdp', timeout)
    result = asyncio.run(snapshot.browser_snapshot({}))
    assert result['snapshot'][0]['role'] == 'checkbox', result
    assert result['snapshot'][0]['name'] == 'Keep AX identity'


def test_chrome_tab_index_never_falls_back_to_first(browser, monkeypatch):
    handler, _ = browser
    chrome = handler._load('browser_chrome')
    async def invoke(*args): return {'tabs': [{'id': 11}, {'id': 22}]}
    driver = SimpleNamespace(call_tool=invoke, _tab_id=11, _ref_map={}, _reverse_ref={})
    monkeypatch.setattr(chrome, '_get_driver', lambda: driver)
    async def run():
        assert (await chrome.browser_tab_switch({'index': 1}))['chrome_id'] == 22
        for args in ({}, {'tab_id': 'typo'}, {'index': -1}, {'index': True}, {'index': 2}):
            assert not (await chrome.browser_tab_switch(args))['success']
            assert driver._tab_id == 22
        assert (await chrome.browser_tab_switch({'tab_id': 't1'}))['chrome_id'] == 11
    asyncio.run(run())


def test_navigation_resets_frame_even_when_goto_fails(browser, monkeypatch):
    handler, module = browser
    nav = handler._load('browser_navigate')
    class Page:
        def on(self, *args): pass
        def remove_listener(self, *args): pass
        async def goto(self, *args, **kwargs): raise RuntimeError('net::ERR_CONNECTION_REFUSED')
        async def go_back(self, **kwargs): raise RuntimeError('history failure')
        async def go_forward(self, **kwargs): raise RuntimeError('history failure')
    page = Page()
    frame = object()
    session = SimpleNamespace(is_active=True, _headless=True, raw_page=page, _active_frame=frame)
    async def ensure(**kwargs): return page
    session.ensure_browser = ensure
    session.reset_frame = lambda: setattr(session, '_active_frame', None)
    monkeypatch.setattr(module.BrowserSession, 'get_instance', lambda: session)
    monkeypatch.setattr(nav, 'ensure_active', lambda: None)
    async def run():
        for fn in (nav.browser_navigate, nav.browser_navigate_back, nav.browser_navigate_forward):
            session._active_frame = frame
            result = await fn({'url': 'https://unreachable.invalid', 'wait': 'load'})
            assert not result['success'] and session._active_frame is None
    asyncio.run(run())


@pytest.mark.system
@pytest.mark.parametrize('variant', ['base', 'flaky', 'breakfast', 'expired', 'short_expiry', 'other_tab'])
def test_complete_two_portal_program(browser, monkeypatch, tmp_path, variant):
    """Run original two-call IBL, PDF re-read and original oracle on real Chromium."""
    import importlib.util
    import threading
    from http.server import ThreadingHTTPServer
    from ibl_v2_adapters import load_registry, Adapted, decode_envelope
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime, Budget
    harness = ROOT / 'docs/experiments/long_sentence_imagination/round_46/harness'
    def load(name):
        spec = importlib.util.spec_from_file_location('hotel_' + name, harness / (name + '.py'))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    prepare, portal, verify = [load(n) for n in ('prepare', 'site_server', 'verify')]
    prepare.OUT = tmp_path / 'fixture'
    prepare.main()
    src, out = prepare.OUT / 'trainer/input', prepare.OUT / 'trainer/out'
    if variant == 'breakfast':
        (src / 'trip.json').write_text(json.dumps(prepare.TRIP_B))
    servers, threads, apps, portals = [], [], [], []
    for site in ('A', 'B'):
        app = portal.App(site, tmp_path / (site + '.json'), variant == 'flaky' and site == 'B',
                         (5 if variant == 'short_expiry' else 8) if site == 'B' else 0, prepare.ACCOUNT)
        # Separate module instances preserve each portal's title, as the original separate processes do.
        site_module = load('site_server')
        site_module.SITE_NAME[0] = app.cfg['name']
        server = ThreadingHTTPServer(('127.0.0.1', 0), type('Hotel', (site_module.Handler,), {'app': app}))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        servers.append(server); threads.append(thread); apps.append(app)
        portals.append({'name': app.cfg['name'], 'url': f'http://127.0.0.1:{server.server_port}/'})
    (src / 'portals.json').write_text(json.dumps(portals))
    handler, session_module = browser
    registry = load_registry(str(tmp_path))
    context = ToolContext(str(tmp_path), 'browser_op', task_id='two-call-hotel')
    loop = asyncio.new_event_loop()
    def call(args):
        return loop.run_until_complete(handler.execute({'driver': 'playwright', **args}, context))
    def browser_call(runtime, args):
        value, evidence = decode_envelope(call(args), registry['limbs:browser'].contract['adapter'])
        return Adapted(value, evidence)
    registry['limbs:browser'] = replace(registry['limbs:browser'], run=browser_call)
    try:
        values = {'src': str(src), 'out': str(out)}
        compare = (harness.parent / 'drafts/compare_v2.ibl').read_text()
        hold_name = 'hold_v4.ibl' if variant in ('expired', 'short_expiry') else 'hold_v3.ibl'
        hold = (harness.parent / 'drafts' / hold_name).read_text()
        for index, code in enumerate((compare, hold)):
            if index:
                cmp = json.loads((out / 'compare.json').read_text())
                values.update(compare=cmp, choice=None, desk=False)
                if variant == 'expired':
                    # Expire once during the hold flow; a fresh session has enough requests to finish.
                    for sess in apps[1].sessions.values(): sess['n'] = 6
                if variant == 'other_tab':
                    assert json.loads(call({'op': 'tab', 'mode': 'switch', 'tab_id': cmp['portals'][0]['tab_id']}))['success']
                    code = code.replace('$cl = [limbs:browser]{op:"tab", mode:"close"}',
                                        '$cl = [limbs:browser]{op:"tab", mode:"switch", tab_id:$포털.tab_id}').replace('"active_closed"', '"switched"')
            plan = compile_program(code, registry, values)
            assert not plan.issues, plan.report()
            result = Runtime(plan, values, budget=Budget(steps=1_000_000, rows=100_000)).run()
            assert result['success'], result.get('diagnostic', result)
        res = json.loads((out / 'result.json').read_text())
        if variant == 'short_expiry':
            assert res['verdict'] == '보류 실패'
            assert not apps[1].state['holds'] and apps[1].state['expired_sessions'] > 0
            return
        qa_path = tmp_path / 'qa.json'
        flags = ['--flaky'] if variant == 'flaky' else ['--b'] if variant == 'breakfast' else []
        monkeypatch.setattr('sys.argv', ['verify', str(out), str(apps[0].state_path), str(apps[1].state_path),
                                       str(prepare.OUT / '_oracle'), str(qa_path), *flags])
        verify.main()
        qa = json.loads(qa_path.read_text())
        assert qa['passed'] == qa['total'], qa
        if variant == 'expired':
            assert apps[1].state['expired_sessions'] > 0 and res['hold']['retried']
        if variant == 'other_tab':
            assert res['tab_action'] == 'switched' and len(res['tabs_after']) == 2
    finally:
        call({'op': 'close'})
        loop.close()
        for server in servers: server.shutdown(); server.server_close()
        for thread in threads: thread.join(2)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
