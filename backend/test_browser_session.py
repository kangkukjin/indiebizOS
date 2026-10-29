"""Playwright action contracts: isolation, explicit dialogs, frames and waits."""
import boot_paths  # noqa: F401
import asyncio
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from tool_context import ToolContext

ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / 'data/packages/installed/tools/browser-action'


def load_handler():
    spec = importlib.util.spec_from_file_location('browser_contract_handler', FOLDER / 'handler.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def browser(monkeypatch, tmp_path):
    import thread_context
    monkeypatch.setattr(thread_context, 'get_task_origin', lambda: 'user')   # 입회 턴 — 화면·공유 상태 동작의 실행 전 문맥 검사(CONTROL_DRIVER §6) 통과
    from runtime_utils import setup_playwright_browsers_path
    setup_playwright_browsers_path()
    handler = load_handler()
    module = handler._load('browser_session')
    monkeypatch.setattr(module, 'get_cookies_dir', lambda: tmp_path)
    monkeypatch.setattr(module.BrowserSession, '_sessions', {})
    return handler, module


def test_auto_storage_coalesces_parallel_saves_and_publishes_atomically(browser, tmp_path):
    _, module = browser
    async def run():
        session = module.BrowserSession()
        calls = []
        async def snapshot():
            calls.append(True)
            await asyncio.sleep(.02)
            return {'cookies': [{'name': 'session', 'value': 'test'}], 'origins': []}
        session._context = SimpleNamespace(storage_state=snapshot)
        results = await asyncio.gather(session.save_storage_state(), session.save_storage_state())
        assert all(r['success'] for r in results) and len(calls) == 1
        path = tmp_path / module.AUTO_STATE_FILENAME
        assert json.loads(path.read_text())['cookies'][0]['name'] == 'session'
        assert path.stat().st_mode & 0o777 == 0o600
        assert not list(tmp_path.glob('.auto-state-*'))
    asyncio.run(run())


def test_auto_storage_timeout_keeps_last_good_file_and_waits_for_new_activity(browser, tmp_path, monkeypatch):
    _, module = browser
    monkeypatch.setattr(module, 'STORAGE_STATE_TIMEOUT_SECONDS', .01)
    path = tmp_path / module.AUTO_STATE_FILENAME
    path.write_text('{"cookies":[],"origins":[]}')
    async def run():
        session = module.BrowserSession()
        calls = []
        async def snapshot():
            calls.append(True)
            if len(calls) == 1:
                await asyncio.Event().wait()
            return {'cookies': [], 'origins': [{'origin': 'https://example.test', 'localStorage': []}]}
        session._context = SimpleNamespace(storage_state=snapshot)
        failed = await session.save_storage_state()
        assert failed == {'success': False, 'error': 'TimeoutError'}
        assert json.loads(path.read_text()) == {'cookies': [], 'origins': []}
        # 종료 직전의 같은 저장 호출도 재시도하지 않는다.
        assert (await session.save_storage_state())['skipped'] and len(calls) == 1
        session._close_generation += 1
        assert (await session.save_storage_state())['success'] and len(calls) == 2
        assert json.loads(path.read_text())['origins']
    asyncio.run(run())


def test_real_isolated_sessions_dialogs_and_frames(browser, tmp_path):
    handler, module = browser
    async def run():
        contexts = [ToolContext(str(tmp_path), 'browser_op', agent_id='test', task_id=key) for key in ('a', 'b')]
        async def call(which, **params):
            return json.loads(await handler.execute({'driver': 'playwright', **params}, contexts[which]))
        try:
            a, b = await asyncio.gather(*[call(i, op='navigate', url='about:blank', wait='load') for i in range(2)])
            assert a['success'] and b['success'], (a, b)
            assert a['session_started'] and b['session_started']
            assert a['session_owner'] != b['session_owner'] and a['tab_id'] != b['tab_id']
            assert not (await call(1, op='tab', mode='switch', tab_id=a['tab_id']))['success']
            for i in range(2):
                result = await call(i, op='evaluate', expression=f"window.marker={i}; document.body.innerHTML = `<button onclick=\"if(confirm('Proceed?')) window.marker=99\">Confirm</button><button id=\"prompt\" onclick=\"window.answer=prompt('Name?')\">Prompt</button><iframe name=\"notice\" srcdoc=\"<p>frame only content that contains enough text for the content extractor to retain this frame.</p>\"></iframe>`")
                assert result['success'], result
            denied = await call(0, op='click', selector='button:first-child')
            assert not denied['success'] and denied['dialog_dismissed'], denied
            accepted = await call(0, op='click', selector='button:first-child', dialog='accept')
            assert accepted['success'] and accepted['dialogs'][0]['handled'], accepted
            assert (await call(0, op='evaluate', expression='window.marker'))['result'] == 99
            assert (await call(1, op='evaluate', expression='window.marker'))['result'] == 1
            answer = await call(0, op='click', selector='#prompt', dialog='accept', dialog_text='한글 응답')
            assert answer['success'], answer
            assert (await call(0, op='evaluate', expression='window.answer'))['result'] == '한글 응답'
            assert not (await call(0, op='click', selector='#prompt'))['success']  # approval does not persist
            frames = await call(0, op='iframe', mode='list')
            assert frames['iframes'][0]['index'] == 0
            for selector in ({'index': 0}, {'name': 'notice'}):
                assert (await call(0, op='iframe', mode='switch', **selector))['success']
                assert 'frame only' in (await call(0, op='content'))['text']
                await call(0, op='iframe', mode='reset')
            assert not (await call(0, op='iframe', mode='switch', url='about:blank'))['success']
            assert not (tmp_path / module.AUTO_STATE_FILENAME).exists()
        finally:
            for i in range(2):
                await call(i, op='close')
        assert not (tmp_path / module.AUTO_STATE_FILENAME).exists()
    asyncio.run(run())


def test_load_wait_skips_dynamic_polling_and_invalid_wait_fails(browser, monkeypatch):
    handler, module = browser
    nav = handler._load('browser_navigate')
    events = []
    class Page:
        url = 'https://example.test'
        def on(self, *args): pass
        def remove_listener(self, *args): pass
        async def goto(self, *args, **kwargs): return SimpleNamespace(status=200)
        async def title(self): return 'test'
        async def evaluate(self, *args): return 200
        async def wait_for_load_state(self, state, **kwargs): events.append(state)
    page = Page()
    async def ensure(**kwargs): return page
    fake = SimpleNamespace(is_active=True, _headless=True, ensure_browser=ensure,
                           reset_frame=lambda: None, raw_page=page, active_tab_id='t1')
    monkeypatch.setattr(module.BrowserSession, 'get_instance', lambda: fake)
    async def stable(*args): events.append('stable')
    monkeypatch.setattr(nav, '_wait_for_dynamic_content', stable)
    async def run():
        for mode, expected in [('load', []), ('idle', ['networkidle']), ('stable', ['networkidle', 'stable'])]:
            result = await nav.browser_navigate({'url': page.url, 'wait': mode})
            assert result['success'] and not result['session_started']
            assert events == expected
        assert not (await nav.browser_navigate({'url': page.url, 'wait': 'typo'}))['success']
    asyncio.run(run())


@pytest.mark.system
@pytest.mark.parametrize('repaired,flaky,variant', [(False, False, False), (False, True, False), (True, False, False), (True, True, True)])
def test_complete_portal_program(browser, monkeypatch, tmp_path, repaired, flaky, variant):
    """Original whole program and new reordered/special-character input; real portal and Chromium.

    Desktop pixels/frontmost app are synthetic so unattended tests never capture the user's desktop.
    Everything from capture PNG bytes through the file sink and original verifier runs normally.
    """
    import base64
    import io
    import threading
    from dataclasses import replace
    from http.server import ThreadingHTTPServer
    from PIL import Image
    from ibl_v2_adapters import load_registry, Adapted, decode_envelope
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime, Budget

    harness = ROOT / 'docs/experiments/long_sentence_imagination/round_44/harness'
    def load(name):
        spec = importlib.util.spec_from_file_location('portal_test_' + name, harness / (name + '.py'))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    prepare, portal, verify = load('prepare'), load('site_server'), load('verify')
    prepare.OUT = tmp_path / 'fixture'
    prepare.main()
    site = prepare.OUT / '_site/trainer'
    if variant:
        data = json.loads((site / 'loans.json').read_text())
        data['loans'].reverse()
        data['loans'][0]['title'] = '새 변형: 따옴표 " & < > 한글'
        (site / 'loans.json').write_text(json.dumps(data, ensure_ascii=False))
    app = portal.App(site / 'loans.json', site / 'state.json', flaky)
    handler_class = type('IsolatedPortal', (portal.Handler,), {'app': app})
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler_class)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    inp, out = prepare.OUT / 'trainer/input', prepare.OUT / 'trainer/out'
    account = {**prepare.ACCOUNT, 'portal_url': f'http://127.0.0.1:{server.server_port}/'}
    (inp / 'account.json').write_text(json.dumps(account))
    code = (harness.parent / 'drafts/main_v1.ibl').read_text()
    if repaired:
        code = (harness.parent / 'drafts/main_repaired.ibl').read_text()
    handler, session_module = browser
    registry = load_registry(str(tmp_path))
    context = ToolContext(str(tmp_path), 'browser_op', task_id='full-portal')
    loop = asyncio.new_event_loop()
    def browser_call(runtime, args):
        result = loop.run_until_complete(handler.execute({'driver': 'playwright', **args}, context))
        value, evidence = decode_envelope(result, registry['limbs:browser'].contract['adapter'])
        return Adapted(value, evidence)
    registry['limbs:browser'] = replace(registry['limbs:browser'], run=browser_call)
    spec = importlib.util.spec_from_file_location('portal_screen', ROOT / 'data/packages/installed/tools/computer-use/handler.py')
    screen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(screen)
    buffer = io.BytesIO()
    Image.new('RGB', (1280, 800), 'white').save(buffer, format='PNG')
    monkeypatch.setattr(screen, '_capture_screenshot', lambda region=None: {'base64': base64.b64encode(buffer.getvalue()).decode(), 'media_type': 'image/png'})
    monkeypatch.setattr(screen, '_get_screen_size', lambda: (1280, 800))
    screen_context = ToolContext(str(tmp_path), 'computer_op')
    def capture(runtime, args):
        value, evidence = decode_envelope(screen.execute(args, screen_context), registry['limbs:screen'].contract['adapter'])
        return Adapted(value, evidence)
    registry['limbs:screen'] = replace(registry['limbs:screen'], run=capture)
    registry['sense:host'] = replace(registry['sense:host'], run=lambda runtime, args: {'frontmost_app': 'Synthetic test desktop'})
    try:
        values = {'src': str(inp), 'out': str(out)}
        plan = compile_program(code, registry, values)
        assert not plan.issues, plan.report()
        result = Runtime(plan, values, budget=Budget(steps=1_000_000, rows=100_000)).run()
        assert result['success'], result
        qa_path = tmp_path / 'qa.json'
        monkeypatch.setattr('sys.argv', ['verify', str(out), str(site / 'state.json'), str(prepare.OUT / '_oracle'), str(qa_path)] + (['--flaky'] if flaky else []))
        verify.main()
        qa = json.loads(qa_path.read_text())
        assert qa['passed'] == qa['total'], qa
        assert result['source_complete']
        if repaired:
            assert 'base64' not in json.dumps(result['recordings'])
            assert not any(r['action'] == 'self:script' for r in result['recordings'])
    finally:
        loop.run_until_complete(handler.execute({'op': 'close', 'driver': 'playwright'}, context))
        loop.close()
        server.shutdown()
        server.server_close()
        thread.join(2)



def test_idle_close_keeps_identity_for_waiting_operation(browser, monkeypatch):
    _, module = browser
    async def run():
        with module.owner_scope('idle-close-race'):
            session = module.BrowserSession.get_instance()
            session._timeout_seconds = 0
            entered, finish = asyncio.Event(), asyncio.Event()
            async def closing():
                entered.set()
                await finish.wait()
            monkeypatch.setattr(session, '_close_internal', closing)
            closer = asyncio.create_task(session._auto_close(0))
            await entered.wait()
            async def queued():
                held = module.BrowserSession.get_instance()
                assert held is session
                async with held._operation_lock:
                    assert module.BrowserSession.get_instance() is held
            pending = asyncio.create_task(queued())
            await asyncio.sleep(0)
            finish.set()
            await asyncio.gather(closer, pending)
    asyncio.run(run())






def test_select_labels_values_and_async_options(browser, tmp_path):
    handler, module = browser
    async def run():
        context = ToolContext(str(tmp_path), 'browser_op', task_id='select')
        async def call(**params):
            return json.loads(await handler.execute({'driver': 'playwright', **params}, context))
        try:
            assert (await call(op='navigate', url='about:blank', wait='load'))['success']
            html = '<select id="city"><option value="">선택</option><option value="suwon">가상 수원체육센터</option></select><select id="multi" multiple><option value="a">서울</option><option value="b">부산</option></select>'
            assert (await call(op='evaluate', expression=f'document.body.innerHTML={json.dumps(html)}'))['success']
            for args in ({'value': 'suwon'}, {'value': '가상 수원체육센터'}, {'values': ['suwon']}, {'label': '가상 수원체육센터'}):
                result = await call(op='select', selector='#city', **args)
                assert result['success'] and result['selected'] == ['suwon'], result
            result = await call(op='select', selector='#multi', values=['a', '부산'])
            assert result['success'] and result['selected'] == ['a', 'b'], result
            assert (await call(op='select', selector='#multi', values=[]))['selected'] == []
            await call(op='evaluate', expression="setTimeout(() => document.querySelector('#city').add(new Option('늦은 옵션', 'later')), 100)")
            assert (await call(op='select', selector='#city', label='늦은 옵션'))['selected'] == ['later']
            for args in ({'value': 'suwon', 'label': '다름'}, {'values': 'suwon'}, {}):
                assert not (await call(op='select', selector='#city', **args))['success']
        finally:
            await call(op='close')
    asyncio.run(run())


def test_chrome_select_never_silently_discards_selection(browser, monkeypatch):
    handler, _ = browser
    chrome = handler._load('browser_chrome')
    calls = []
    async def invoke(name, args):
        calls.append((name, args))
        return {}
    monkeypatch.setattr(chrome, '_get_driver', lambda: SimpleNamespace(
        _tab_id='tab', _to_chrome_ref=lambda ref: ref, call_tool=invoke))
    async def run():
        for args in ({'value': 'a'}, {'values': ['a']}):
            assert (await chrome.browser_select_option({'ref': 'e1', **args}))['success']
        for args in ({'label': '서울'}, {'values': ['a', 'b']}, {'values': []}):
            assert (await chrome.browser_select_option({'ref': 'e1', **args}))['error_code'] == 'UNSUPPORTED_OPERATION'
        assert len(calls) == 2 and all(args['value'] == 'a' for _, args in calls)
    asyncio.run(run())


def test_guide_select_and_screen_contracts_compile():
    import re
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    registry = load_registry()
    guide = (ROOT / 'data/guides/browser_action.md').read_text()
    cases = re.findall(r'\[limbs:browser\]\{op: "select"[^\n]+?\}', guide)
    assert cases
    cases += ['[limbs:browser]{op:"select",ref:"e1",label:"표시명"}',
              '[limbs:screen]{op:"wait",expect_app:"Calculator",timeout:200,idle_seconds:1}',
              '[limbs:screen]{op:"key",key:"enter",expect_app:"Calculator"}']
    for code in cases:
        plan = compile_program(code, registry)
        assert not plan.issues, (code, plan.report())


@pytest.mark.system
@pytest.mark.parametrize('repaired,flaky', [(False, False), (True, False), (True, True)])
def test_complete_registration_program(browser, monkeypatch, tmp_path, repaired, flaky):
    """45회차 원본/표시명 수리/일시 오류·마감: PDF·업로드·서버 접수까지 대조."""
    import threading
    from dataclasses import replace
    from http.server import ThreadingHTTPServer
    from ibl_v2_adapters import load_registry, Adapted, decode_envelope
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime, Budget
    harness = ROOT / 'docs/experiments/long_sentence_imagination/round_45/harness'
    def load(name):
        spec = importlib.util.spec_from_file_location('registration_test_' + name, harness / (name + '.py'))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    prepare, portal, verify = load('prepare'), load('site_server'), load('verify')
    prepare.OUT = tmp_path / 'fixture'
    prepare.main()
    site = prepare.OUT / '_site/trainer'
    app = portal.App(site / 'data.json', site / 'state.json', flaky)
    server = ThreadingHTTPServer(('127.0.0.1', 0), type('RegistrationPortal', (portal.Handler,), {'app': app}))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    inp, out = prepare.OUT / 'trainer/input', prepare.OUT / 'trainer/out'
    (inp / 'account.json').write_text(json.dumps({**prepare.ACCOUNT, 'portal_url': f'http://127.0.0.1:{server.server_port}/'}))
    code = (harness.parent / 'drafts' / ('main_repaired.ibl' if repaired else 'main_v3.ibl')).read_text()
    if repaired:
        # 값 목록도 전체 프로그램에서 연결; 표시명 label은 수리 프로그램 본문에 있다.
        code = code.replace('value:$a.course', 'values:[$a.course]')
    handler, _ = browser
    registry = load_registry(str(tmp_path))
    context = ToolContext(str(tmp_path), 'browser_op', task_id='registration')
    loop = asyncio.new_event_loop()
    def browser_call(runtime, args):
        result = loop.run_until_complete(handler.execute({'driver': 'playwright', **args}, context))
        value, evidence = decode_envelope(result, registry['limbs:browser'].contract['adapter'])
        return Adapted(value, evidence)
    registry['limbs:browser'] = replace(registry['limbs:browser'], run=browser_call)
    registry['sense:host'] = replace(registry['sense:host'], run=lambda runtime, args: {'frontmost_app': 'Synthetic desktop'})
    def no_desktop(*args):
        pytest.fail('desk:false must never read or manipulate the user desktop')
    registry['limbs:screen'] = replace(registry['limbs:screen'], run=no_desktop)
    try:
        values = {'src': str(inp), 'out': str(out), 'desk': False, 'only': None}
        plan = compile_program(code, registry, values)
        assert not plan.issues, plan.report()
        result = Runtime(plan, values, budget=Budget(steps=1_000_000, rows=100_000)).run()
        assert result['success'] and result['source_complete'], result
        qa_path = tmp_path / 'qa.json'
        monkeypatch.setattr('sys.argv', ['verify', str(out), str(site / 'state.json'), str(prepare.OUT / '_oracle'), str(qa_path)] + (['--flaky'] if flaky else []))
        verify.main()
        qa = json.loads(qa_path.read_text())
        assert qa['passed'] == qa['total'], qa
    finally:
        loop.run_until_complete(handler.execute({'op': 'close', 'driver': 'playwright'}, context))
        loop.close()
        server.shutdown()
        server.server_close()
        thread.join(2)


if __name__ == "__main__":
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))


def test_network_capture_lifecycle_and_failed_requests(browser, tmp_path):
    handler, module = browser
    async def run():
        context = ToolContext(str(tmp_path), 'browser_op', task_id='network')
        async def call(**params):
            return json.loads(await handler.execute({'driver':'playwright', **params}, context))
        try:
            await call(op='navigate', url='about:blank', wait='load')
            session = next(iter(module.BrowserSession._sessions.values()))
            # Real response/requestfailed hooks; intercept HTTP locally, no external traffic.
            await session.raw_page.route('**/conflict', lambda route: route.fulfill(status=409, body='conflict'))
            await session.raw_page.route('**/broken', lambda route: route.abort('connectionfailed'))
            await call(op='navigate', url='http://synthetic.test/conflict', wait='load')
            logs = await call(op='logs', mode='network')
            assert logs['success'] and logs['capturing']
            assert any(x['status']==409 for x in logs['logs']), logs
            await call(op='evaluate', expression="fetch('/broken').catch(()=>null)")
            logs = await call(op='logs', mode='network')
            assert any(x['status'] is None and x['failure'] for x in logs['logs']), logs
            session.stop_network_capture()
            stopped = await call(op='logs', mode='network')
            assert not stopped['success'] and stopped['error_code']=='NETWORK_CAPTURE_INACTIVE'
            assert stopped['logs']  # preserve earlier evidence
            await call(op='close')
            await call(op='navigate', url='about:blank', wait='load')
            fresh = await call(op='logs', mode='network')
            assert fresh['success'] and fresh['capturing'] and fresh['logs']==[]
        finally:
            await call(op='close')
    asyncio.run(run())


def test_chrome_drag_does_not_send_placeholder_coordinates(browser, monkeypatch):
    handler, _ = browser
    chrome = handler._load('browser_chrome')
    def unexpected():
        pytest.fail('Unsupported drag must not touch Chrome')
    monkeypatch.setattr(chrome, '_get_driver', unexpected)
    result = asyncio.run(chrome.browser_drag({'source_ref':'e1','target_ref':'e2'}))
    assert not result['success'] and result['error_code']=='UNSUPPORTED_OPERATION'
