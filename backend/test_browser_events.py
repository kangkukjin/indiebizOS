"""48회차 사건 조사: 조작 방식과 무관한 영수증·수명·파일 전달 계약."""
import boot_paths  # noqa: F401
import asyncio
import json
from pathlib import Path

import pytest
from test_browser_session import browser  # noqa: F401
from tool_context import ToolContext


@pytest.mark.parametrize('method', ['click', 'press_key', 'evaluate'])
def test_event_receipts_across_operations(browser, tmp_path, method):
    handler, module = browser
    context = ToolContext(str(tmp_path), 'browser_op', task_id=method)

    async def call(**params):
        return json.loads(await handler.execute({'driver': 'playwright', **params}, context))

    async def run():
        try:
            first = await call(op='navigate', url='about:blank', wait='load')
            session = next(iter(module.BrowserSession._sessions.values()))
            html = '''<title>Events</title>
                <a id="popup" href="/child" target="_blank">Open</a>
                <button id="open" onclick="window.open('/child')">Window</button>
                <button id="close" onclick="window.close()">Close</button>
                <a id="download" href="/download">Download</a>
                <button id="blob" onclick="let a=document.createElement('a'); a.href=window.URL.createObjectURL(new Blob([new Uint8Array([0,255,13,10,128])])); a.download='bytes.bin'; a.click()">Blob</button>
                <input id="choose" type="file" multiple>
                <button id="error" onclick="throw new Error('intentional-page-error')">Error</button>
                <button id="push" onclick="history.pushState({},'', '/pushed')">Push</button>
                <a id="missing" href="/missing">404</a>
                <button id="alert" onclick="alert('notice')">Alert</button>
                <button id="confirm" onclick="confirm('approve')">Confirm</button>
                <input id="range" type="range" aria-label="Price" min="10000" max="60000" step="1000" value="42000">
            '''
            async def serve(route):
                if route.request.url.endswith('/download'):
                    await route.fulfill(body=b'\x00\xff\r\n\x80', headers={
                        'Content-Type': 'application/octet-stream',
                        'Content-Disposition': 'attachment; filename="bytes.bin"'})
                else:
                    await route.fulfill(body=html, status=404 if route.request.url.endswith('/missing') else 200,
                                        content_type='text/html')
            await session._context.route('http://events.test/**', serve)
            await call(op='navigate', url='http://events.test/', wait='load')

            async def trigger(selector, **params):
                if method == 'click':
                    return await call(op='click', selector=selector, **params)
                if method == 'press_key':
                    await session.raw_page.locator(selector).focus()
                    return await call(op='press_key', key='Enter', **params)
                return await call(op='evaluate', expression=f'document.querySelector({json.dumps(selector)}).click()', **params)

            for selector in ('#popup', '#open'):
                opened = await trigger(selector)
                assert opened['success'], opened
                assert len(opened['opened_tabs']) == 1, opened
                new = opened['opened_tabs'][0]
                assert new['url'] == 'http://events.test/child', opened
                assert opened['active_tab_changed'] == {'from': first['tab_id'], 'to': new['tab_id']}
                snap = await call(op='snapshot')
                assert snap['tab_id'] == new['tab_id'] and snap['url'] == new['url'], snap
                logs = await call(op='logs', mode='network')
                assert any(x['url'] == new['url'] and x['status'] == 200 for x in logs['logs']), logs
                closed = await trigger('#close')
                assert closed['success'], closed
                assert closed['closed_tabs'][0]['tab_id'] == new['tab_id'], closed
                assert closed['active_tab_changed']['to'] == first['tab_id'], closed
                assert (await call(op='tab', mode='list'))['count'] == 1
                assert (await call(op='snapshot'))['tab_id'] == first['tab_id']

            for selector in ('#download', '#blob'):
                saved = await trigger(selector, path=str(tmp_path / (selector[1:] + '.bin')))
                assert saved['success'], saved
                assert saved.get('downloads'), (selector, saved)
                download = saved['downloads'][0]
                assert download['saved'] and download['size'] == 5, saved
                assert Path(download['path']).read_bytes() == b'\x00\xff\r\n\x80'
            chooser = await trigger('#choose')
            assert chooser['success'] and chooser['file_chooser'][0]['multiple'], chooser
            error = await trigger('#error')
            assert error['success'] and 'intentional-page-error' in error['page_errors'][0]['message'], error
            logs = await call(op='logs', mode='console')
            assert any(x.get('source') == 'pageerror' for x in logs['logs'])
            alert = await trigger('#alert')
            assert alert['success'] and alert['dialogs'][0]['type'] == 'alert', alert
            confirm = await trigger('#confirm')
            assert not confirm['success'] and confirm['error_code'] == 'DIALOG_NOT_ACCEPTED', confirm
            pushed = await trigger('#push')
            assert pushed['success'] and pushed['navigated'][-1]['url'].endswith('/pushed'), pushed
            missing = await trigger('#missing')
            assert missing['success'] and missing['navigated'][-1]['status_code'] == 404, missing
            snap = await call(op='snapshot')
            slider = next(x for x in snap['snapshot'] if x['role'] == 'slider')
            assert {k: slider[k] for k in ('min','max','step')} == {'min':'10000','max':'60000','step':'1000'}
            error = await call(op='type', ref=slider['ref'], text='30000')
            assert not error['success'] and 'Home/End' in error['error'], error
        finally:
            await call(op='close')
    asyncio.run(run())


def test_late_events_multiple_downloads_and_failed_save(browser, tmp_path, monkeypatch):
    handler, module = browser
    context = ToolContext(str(tmp_path), 'browser_op', task_id='late')
    async def call(**params):
        return json.loads(await handler.execute({'driver':'playwright', **params}, context))
    async def run():
        try:
            await call(op='navigate', url='about:blank', wait='load')
            session = next(iter(module.BrowserSession._sessions.values()))
            script = """for (let i=0;i<2;i++) {let a=document.createElement('a'); a.href=window.URL.createObjectURL(new Blob(['file'+i])); a.download='same.txt'; a.click();}"""
            result = await call(op='evaluate', expression=script, path=str(tmp_path/'same.txt'))
            assert result['success'] and len(result['downloads']) == 2, result
            paths = [Path(x['path']) for x in result['downloads']]
            assert len(set(paths)) == 2 and {p.read_text() for p in paths} == {'file0', 'file1'}
            # A late browser event is not erased at the start of the next command.
            await session.raw_page.evaluate("setTimeout(()=>{throw new Error('late-error')},100)")
            await asyncio.sleep(.2)
            result = await call(op='snapshot')
            assert result['page_errors'][0]['message'].endswith('late-error'), result
            assert 'page_errors' not in await call(op='snapshot')
            monkeypatch.setattr(ToolContext, 'resolve_output_path', lambda *args: {'error': 'test denied destination'})
            failed = await call(op='evaluate', expression=script)
            assert not failed['success'] and failed['error_code'] == 'DOWNLOAD_NOT_SAVED', failed
            assert all(not x['saved'] and 'path' not in x for x in failed['downloads'])
        finally:
            await call(op='close')
    asyncio.run(run())


if __name__ == '__main__':
    import pytest
    raise SystemExit(pytest.main([__file__]))


def test_snapshot_switch_does_not_publish_refs_for_wrong_tab(browser, tmp_path, monkeypatch):
    handler, module = browser
    context = ToolContext(str(tmp_path), 'browser_op', task_id='snapshot-race')
    async def call(**params):
        return json.loads(await handler.execute({'driver':'playwright', **params}, context))
    async def run():
        try:
            first = await call(op='navigate', url='about:blank', wait='load')
            session = next(iter(module.BrowserSession._sessions.values()))
            await session.raw_page.set_content('<button>Old page</button>')
            snapshot = handler._load('browser_snapshot')
            original = snapshot._extract_selectors_via_cdp
            async def switched(*args):
                result = await original(*args)
                await session.new_tab('about:blank')
                return result
            monkeypatch.setattr(snapshot, '_extract_selectors_via_cdp', switched)
            result = await call(op='snapshot')
            assert not result['success'] and result['error_code'] == 'SNAPSHOT_TAB_CHANGED', result
            assert result['tab_id'] == first['tab_id']
            assert session._ref_map == {}
        finally:
            await call(op='close')
    asyncio.run(run())


@pytest.fixture
def shop_site(monkeypatch, tmp_path):
    import importlib.util
    import sys
    import threading
    from http.server import ThreadingHTTPServer
    from test_browser_session import ROOT
    harness = ROOT / 'docs/experiments/long_sentence_imagination/round_48/harness'
    def load(name):
        spec = importlib.util.spec_from_file_location('shop_test_' + name, harness / (name + '.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    site = load('site_server')
    monkeypatch.setitem(sys.modules, 'site_server', site)
    prepare, verify = load('prepare'), load('verify')
    prepare.OUT = verify.OUT = tmp_path / 'fixture'
    verify.HERE = tmp_path
    (tmp_path / 'evidence').mkdir()
    prepare.main()
    app = site.App(prepare.OUT / '_site/trainer.json', None)
    server = ThreadingHTTPServer(('127.0.0.1', 0), site.make_handler(app))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield app, f'http://127.0.0.1:{server.server_port}/', prepare, verify
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


@pytest.mark.system
@pytest.mark.parametrize('mode,repaired', [('base',False),('flaky',False),('b',False),('base',True),('flaky',True),('b',True)])
def test_complete_shop_program(browser, shop_site, monkeypatch, tmp_path, mode, repaired):
    from dataclasses import replace
    from ibl_v2_adapters import load_registry, Adapted, decode_envelope
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime, Budget
    from test_browser_session import ROOT
    handler, _ = browser
    app, url, prepare, verify = shop_site
    suffix = {'base':'', 'flaky':'_flaky', 'b':'_b'}[mode]
    app.fail_once = 'P-05' if mode == 'flaky' else None
    app.path = prepare.OUT / f'_site/trainer{suffix}.json'
    inp, out = prepare.OUT / f'trainer/input{suffix}', prepare.OUT / f'trainer/out{suffix}'
    (inp / 'console.json').write_text(json.dumps({'url':url}))
    code = (ROOT / 'docs/experiments/long_sentence_imagination/round_48/drafts' /
            ('shop_repaired.ibl' if repaired else 'shop_v1.ibl')).read_text()
    registry = load_registry(str(tmp_path))
    context = ToolContext(str(tmp_path), 'browser_op', task_id='complete-shop')
    loop = asyncio.new_event_loop()
    receipts = []
    def browser_call(runtime, args):
        result = loop.run_until_complete(handler.execute({'driver':'playwright', **args}, context))
        receipts.append({'op':args['op'], 'result':json.loads(result)})
        if repaired and mode == 'b' and args['op'] == 'click':
            # 사건이 다음 영수증에 도착하는 계약도 강제로 실행한다. 실제 탭은 유지된다.
            raw = json.loads(result)
            raw.pop('opened_tabs', None)
            result = json.dumps(raw)
        value, evidence = decode_envelope(result, registry['limbs:browser'].contract['adapter'])
        return Adapted(value, evidence)
    registry['limbs:browser'] = replace(registry['limbs:browser'], run=browser_call)
    try:
        values = {'src':str(inp), 'out':str(out)}
        plan = compile_program(code, registry, values)
        assert not plan.issues, plan.report()
        result = Runtime(plan, values, budget=Budget(steps=1_000_000, rows=100_000)).run()
        assert result['success'], result
        monkeypatch.setattr('sys.argv', ['verify', 'trainer', mode])
        verify.main()
        qa = json.loads((tmp_path / f'evidence/trainer_{mode}_qa.json').read_text())
        assert qa['passed'] == qa['total'], qa
        if repaired:
            downloads = [d for r in receipts for d in r['result'].get('downloads', [])]
            assert len(downloads) == 1 and downloads[0]['saved'], downloads
            assert Path(downloads[0]['path']).read_bytes() == (out / 'display.csv').read_bytes()
    finally:
        loop.run_until_complete(handler.execute({'op':'close','driver':'playwright'}, context))
        loop.close()


def test_chrome_download_path_is_rejected_before_action(browser, tmp_path, monkeypatch):
    handler, _ = browser
    async def unexpected(*args):
        pytest.fail('unsupported download must not click Chrome')
    monkeypatch.setattr(handler, '_execute', unexpected)
    context = ToolContext(str(tmp_path), 'browser_op', task_id='chrome-download')
    result = json.loads(asyncio.run(handler.execute(
        {'op':'click','driver':'chrome','selector':'a','path':'file.bin'}, context)))
    assert not result['success'] and result['error_code'] == 'UNSUPPORTED_OPERATION'


def test_last_tab_close_keeps_context_and_failed_close_keeps_tab(browser, tmp_path, monkeypatch):
    handler, module = browser
    context = ToolContext(str(tmp_path), 'browser_op', task_id='last-tab')
    async def call(**params):
        return json.loads(await handler.execute({'driver':'playwright', **params}, context))
    async def run():
        try:
            first = await call(op='navigate', url='about:blank', wait='load')
            session = next(iter(module.BrowserSession._sessions.values()))
            original_context = session._context
            await original_context.add_cookies([{'name':'keep','value':'yes','url':'https://example.test'}])
            page = session.raw_page
            async def fail():
                raise RuntimeError('close failed')
            with monkeypatch.context() as patch:
                patch.setattr(page, 'close', fail)
                denied = await call(op='tab', mode='close')
                assert not denied['success'] and 'closed_tabs' not in denied, denied
                assert session.active_tab_id == first['tab_id']
            await page.close()  # A browser-origin close, outside the explicit tab op.
            receipt = await call(op='navigate', url='about:blank', wait='load')
            assert receipt['success'] and session._context is original_context, receipt
            assert any(x['name']=='keep' for x in await original_context.cookies())
            assert receipt['closed_tabs'][0]['tab_id'] == first['tab_id']
        finally:
            await call(op='close')
    asyncio.run(run())
