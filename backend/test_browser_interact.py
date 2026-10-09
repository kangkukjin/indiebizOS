"""Browser gestures and complete order-console replay against real Chromium."""
import boot_paths  # noqa: F401
import asyncio
import importlib.util
import json
import threading
from dataclasses import replace
from http.server import ThreadingHTTPServer

import pytest
from tool_context import ToolContext
from test_browser_session import browser, ROOT  # noqa: F401


@pytest.fixture
def order_site(monkeypatch, tmp_path):
    harness = ROOT / 'docs/experiments/long_sentence_imagination/round_47/harness'
    def load(name):
        spec = importlib.util.spec_from_file_location('order_test_' + name, harness / (name + '.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    site = load('site_server')
    monkeypatch.setitem(__import__('sys').modules, 'site_server', site)
    prepare, verify = load('prepare'), load('verify')
    prepare.OUT = verify.OUT = tmp_path / 'fixture'
    verify.HERE = tmp_path
    (tmp_path / 'evidence').mkdir()
    prepare.main()
    app = site.App(prepare.OUT / '_site/trainer.json', None)
    handler_class = type('OrderTestHandler', (site.Handler,), {'app': app})
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler_class)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield app, f'http://127.0.0.1:{server.server_port}/', prepare, verify
    finally:
        server.shutdown()
        server.server_close()
        thread.join(2)


def test_drag_region_moves_only_requested_card_and_records_identity(browser, order_site, tmp_path):
    handler, _ = browser
    app, url, _, _ = order_site
    async def run():
        context = ToolContext(str(tmp_path), 'browser_op', task_id='region-drag')
        async def call(**params):
            return json.loads(await handler.execute({'driver': 'playwright', **params}, context))
        try:
            await call(op='navigate', url=url+'login', wait='load')
            await call(op='type', selector='input[name=user]', text='synthetic')
            await call(op='type', selector='input[name=password]', text='synthetic', submit=True)
            await call(op='navigate', url=url+'board', wait='load')
            snap = (await call(op='snapshot'))['snapshot']
            source = next(x['ref'] for x in snap if x['role']=='button' and x['name'].startswith('W-1004 '))
            target = next(x['ref'] for x in snap if x['role']=='region' and x['name']=='오늘 처리 칸')
            result = await call(op='drag', source_ref=source, target_ref=target)
            assert result['success'], result
            assert result['source']['name'].startswith('W-1004 ')
            assert result['target']['name'] == '오늘 처리 칸'
            assert 'W-1004' in result['dragged']
            assert result['verification'] == 'gesture_only'
            await call(op='navigate', url=url+'board', wait='load')
            assert [(m['id'], m['to']) for m in app.state['moves']] == [('W-1004', '오늘 처리')]
            assert app.by['W-1033']['status'] == '지연'
        finally:
            await call(op='close')
    asyncio.run(run())


@pytest.mark.parametrize('mode', ['pointer', 'distant', 'scroll', 'nested_scroll', 'covered'])
def test_drag_pointer_and_unsafe_geometry(browser, tmp_path, mode):
    handler, _ = browser
    async def run():
        context = ToolContext(str(tmp_path), 'browser_op', task_id='geometry')
        async def call(**params):
            return json.loads(await handler.execute({'driver':'playwright', **params}, context))
        try:
            await call(op='navigate', url='about:blank', wait='load')
            gap = 1600 if mode == 'distant' else 50
            body = f'<div id="wrap" style="height:600px;overflow:auto"><button id="source" style="margin:50px;width:150px;height:70px">원본</button><div style="height:{gap}px"></div><div role="region" aria-label="도착" id="target" style="width:200px;height:100px;background:#ddd">도착</div><div style="height:1800px"></div></div><div style="height:1000px"></div>'
            js = '''window.moves=0; window.held=false;
                source.addEventListener('pointerdown',()=>{window.held=true; EXTRA });
                target.addEventListener('pointerup',()=>{if(window.held)window.moves++});
                document.addEventListener('pointerup',()=>window.held=false);'''
            extra = {'scroll':'window.scrollBy(0,100)', 'nested_scroll':'wrap.scrollTop=100'}.get(mode, '')
            await call(op='evaluate', expression=f'document.body.innerHTML={json.dumps(body)};'+js.replace('EXTRA', extra))
            if mode == 'covered':
                await call(op='evaluate', expression="document.body.insertAdjacentHTML('beforeend','<div style=\"position:fixed;inset:0;background:white;z-index:99\"></div>')")
            snap = (await call(op='snapshot'))['snapshot']
            src = next(x['ref'] for x in snap if x['name']=='원본' and x['role']=='button')
            dst = next(x['ref'] for x in snap if x['name']=='도착' and x['role']=='region')
            result = await call(op='drag', source_ref=src, target_ref=dst)
            moves = (await call(op='evaluate', expression='window.moves'))['result']
            if mode=='pointer':
                assert result['success'] and moves==1, (result, moves)
            else:
                assert not result['success'] and moves==0, (result, moves)
                if mode in ('scroll','nested_scroll'):
                    assert result['scrolled_during_drag']
        finally:
            await call(op='close')
    asyncio.run(run())


@pytest.mark.system
@pytest.mark.parametrize('mode,region', [('base',False),('flaky',False),('b',False),('flaky',True)])
def test_complete_order_console_program(browser, order_site, monkeypatch, tmp_path, mode, region):
    """Original program plus region target variation, with HTTP 409 and saved-state verification."""
    from ibl_v2_adapters import load_registry, Adapted, decode_envelope
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime, Budget
    handler, session_module = browser
    storage = handler._load('browser_storage')
    monkeypatch.setattr(storage, 'get_cookies_dir', lambda: tmp_path)
    app, url, prepare, verify = order_site
    suffix = {'base':'', 'flaky':'_flaky', 'b':'_b'}[mode]
    app.locked = 'W-1017' if mode=='flaky' else None
    app.state_path = prepare.OUT / f'_site/trainer{suffix}.json'
    inp, out = prepare.OUT / f'trainer/input{suffix}', prepare.OUT / f'trainer/out{suffix}'
    console = json.loads((inp / 'console.json').read_text())
    (inp / 'console.json').write_text(json.dumps({**console, 'url':url}))
    code = (ROOT / 'docs/experiments/long_sentence_imagination/round_47/drafts/tidy_v1.ibl').read_text()
    if region:
        code = code.replace('role:"heading", name:f"${pol.to} "', 'role:"region", name:f"${pol.to} 칸"')
    registry = load_registry(str(tmp_path))
    context = ToolContext(str(tmp_path), 'browser_op', task_id='complete-orders')
    loop = asyncio.new_event_loop()
    receipts = []
    def browser_call(runtime, args):
        result = loop.run_until_complete(handler.execute({'driver':'playwright', **args}, context))
        receipts.append({'op':args['op'], 'result':json.loads(result)})
        value, evidence = decode_envelope(result, registry['limbs:browser'].contract['adapter'])
        return Adapted(value, evidence)
    registry['limbs:browser'] = replace(registry['limbs:browser'], run=browser_call)
    try:
        values = {'src':str(inp), 'out':str(out)}
        plan = compile_program(code, registry, values)
        assert not plan.issues, plan.report()
        result = Runtime(plan, values, budget=Budget(steps=1_000_000, rows=100_000)).run()
        assert result['success'], json.dumps([r for r in receipts if r['op']=='drag'], ensure_ascii=False)
        monkeypatch.setattr('sys.argv', ['verify', 'trainer', mode])
        verify.main()
        qa = json.loads((tmp_path / f'evidence/trainer_{mode}_qa.json').read_text())
        assert qa['passed']==qa['total'], qa
        assert all(r['result']['source']['name'].startswith('W-') for r in receipts if r['op']=='drag')
        network = json.loads((out / 'result.json').read_text())['network']
        assert network['capturing'], network
        logs = [r['result'] for r in receipts if r['op']=='logs' and 'capturing' in r['result']]
        assert any(row['status']==409 for batch in logs for row in batch['logs']) == (mode=='flaky')
    finally:
        loop.run_until_complete(handler.execute({'op':'close','driver':'playwright'}, context))
        loop.close()


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
