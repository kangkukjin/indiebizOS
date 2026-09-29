"""일회성 패키지 감사 수리: 실제 핸들러 출구·저장 위치·교재 계약의 회귀."""
import boot_paths  # noqa: F401
import asyncio
import base64
import importlib.util
import json
import re
import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest
from ibl_v2_adapters import decode_envelope, load_registry
from ibl_v2_compile import compile_program
from ibl_v2_ir import Fault
from tool_context import ToolContext

ROOT = Path(__file__).resolve().parents[1]
TOOLS = ROOT / 'data/packages/installed/tools'


def module(package, name='handler'):
    spec = importlib.util.spec_from_file_location('boundary_repair_' + package.replace('-', '_') + name,
                                                TOOLS / package / (name + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope='module')
def registry():
    return load_registry()


def test_memory_read_survives_public_adapter(monkeypatch, tmp_path, registry):
    memory = {'content': 'synthetic memory', 'category': '기타', 'keywords': 'fixture',
              'created_at': '2026-09-29', 'used_at': None}
    monkeypatch.setitem(sys.modules, 'memory_db', NS(read=lambda *a: memory))
    raw = module('memory').execute({'op': 'read', 'memory_id': 42},
                                   ToolContext(str(tmp_path), 'memory_op'))
    decode_envelope(raw, registry['self:memory'].contract['adapter'])
    result = json.loads(raw)
    assert result['success'] and result['memory_id'] == 42
    assert result['content'] == memory['content']
    assert result['category'] == memory['category']
    assert result['source'] and '[출처·적용 범위]' in result['text']
    assert memory['content'] in result['text']


def test_glob_failure_remains_tool_error(monkeypatch, tmp_path, registry):
    mod = module('system_essentials')
    def failed_glob(*args, **kwargs):
        raise OSError('synthetic filesystem failure')
    monkeypatch.setattr(mod.glob, 'glob', failed_glob)
    raw = mod.execute({'pattern': 'folder/*.txt'}, ToolContext(str(tmp_path), 'glob_files'))
    assert json.loads(raw)['success'] is False
    with pytest.raises(Fault) as exc:
        decode_envelope(raw, registry['self:file_find'].contract['adapter'])
    assert exc.value.code == 'TOOL' and 'synthetic filesystem failure' in str(exc.value)


@pytest.fixture
def path_scope(tmp_path, monkeypatch):
    import runtime_utils
    monkeypatch.setenv('PLAYWRIGHT_BROWSERS_PATH', str(runtime_utils.get_playwright_browsers_path()))
    monkeypatch.setattr(runtime_utils, 'get_base_path', lambda: tmp_path)
    # Exercise the real path resolver and directory creation with an isolated scope gate.
    monkeypatch.setattr(ToolContext, '_scope_refusal',
                        lambda self, path, guard=None: None if Path(path).is_relative_to(tmp_path) else 'outside fixture scope')
    return tmp_path


@pytest.mark.parametrize('driver', ['playwright', 'chrome'])
@pytest.mark.parametrize('raw,expected', [
    ('~workspace/reports/a.png', 'reports/a.png'),
    ('reports/deep/a.jpeg', 'project/reports/deep/a.png'),
    ('a.png', 'project/outputs/a.png'),
])
def test_screenshot_dispatch_resolves_paths(driver, raw, expected, path_scope, monkeypatch):
    handler = module('browser-action')
    content = handler._load('browser_content')
    chrome = handler._load('browser_chrome')
    async def screenshot(**kwargs):
        Path(kwargs['path']).write_bytes(b'fixture PNG')
    async def chrome_call(*args):
        return {'image_data': base64.b64encode(b'fixture PNG').decode()}
    monkeypatch.setattr(content, 'ensure_active', lambda: None)
    monkeypatch.setattr(content.BrowserSession, 'get_instance', lambda: NS(raw_page=NS(screenshot=screenshot)))
    monkeypatch.setattr(chrome, '_get_driver', lambda: NS(call_tool=chrome_call, _tab_id=1))
    result = json.loads(asyncio.run(handler.execute(
        {'op': 'screenshot', 'driver': driver, 'path': raw},
        ToolContext(str(path_scope / 'project'), 'browser_op'))))
    assert result['success'], result
    assert result['file_path'] == str(path_scope / expected)
    assert Path(result['file_path']).read_bytes() == b'fixture PNG'


def test_pdf_path_and_options_reach_page(path_scope, monkeypatch):
    handler = module('browser-action')
    mod = handler._load('browser_content')
    calls = []
    async def pdf(**kwargs):
        calls.append(kwargs)
        Path(kwargs['path']).write_bytes(b'%PDF-fixture')
    monkeypatch.setattr(mod, 'ensure_active', lambda: None)
    monkeypatch.setattr(mod.BrowserSession, 'get_instance', lambda: NS(raw_page=NS(pdf=pdf)))
    result = json.loads(asyncio.run(handler.execute(
        {'op': 'pdf', 'driver': 'playwright', 'path': '~workspace/reports/report.pdf',
         'landscape': True, 'print_background': False},
        ToolContext(str(path_scope / 'project'), 'browser_op'))))
    assert result['success'], result
    assert result['file_path'] == str(path_scope / 'reports/report.pdf')
    assert calls == [{'path': result['file_path'], 'format': 'A4', 'landscape': True, 'print_background': False}]
    assert Path(result['file_path']).read_bytes().startswith(b'%PDF')


def test_chrome_pdf_does_not_open_print_dialog(tmp_path, monkeypatch, registry):
    handler = module('browser-action')
    chrome = handler._load('browser_chrome')
    monkeypatch.setattr(chrome, '_get_driver', lambda: pytest.fail('unsupported operation must have no browser effects'))
    raw = asyncio.run(handler.execute({'op': 'pdf', 'driver': 'chrome', 'path': 'report.pdf'},
                                     ToolContext(str(tmp_path), 'browser_op')))
    assert json.loads(raw)['success'] is False
    with pytest.raises(Fault) as exc:
        decode_envelope(raw, registry['limbs:browser'].contract['adapter'])
    assert exc.value.code == 'TOOL' and 'playwright' in str(exc.value)
    assert not (tmp_path / 'report.pdf').exists()


@pytest.mark.parametrize('driver', ['playwright', 'chrome'])
def test_browser_refused_path_never_captures(driver, path_scope, monkeypatch):
    handler = module('browser-action')
    mod = handler._load('browser_content')
    chrome = handler._load('browser_chrome')
    async def fail(*args, **kwargs):
        pytest.fail('refused write must not capture')
    monkeypatch.setattr(mod, 'ensure_active', lambda: None)
    monkeypatch.setattr(mod.BrowserSession, 'get_instance', lambda: NS(raw_page=NS(screenshot=fail)))
    monkeypatch.setattr(chrome, '_get_driver', lambda: NS(call_tool=fail, _tab_id=1))
    result = json.loads(asyncio.run(handler.execute(
        {'op': 'screenshot', 'driver': driver, 'path': '/outside-fixture/refused.png'},
        ToolContext(str(path_scope), 'browser_op'))))
    assert result['success'] is False and 'outside fixture scope' in result['error']


def test_chrome_missing_image_is_failure(path_scope, monkeypatch):
    chrome = module('browser-action')._load('browser_chrome')
    async def no_image(*args):
        return {'text': 'no image'}
    monkeypatch.setattr(chrome, '_get_driver', lambda: NS(call_tool=no_image, _tab_id=1))
    result = asyncio.run(chrome.browser_screenshot({'path': 'empty.png'}, str(path_scope)))
    assert result['success'] is False
    assert not (path_scope / 'outputs/empty.png').exists()


@pytest.mark.parametrize('requested,expected', [
    ('reports/nested/frame.jpg', 'project/reports/nested/frame.jpg'),
    ('~workspace/reports/frame.png', 'reports/frame.png'),
    ('frame', 'project/outputs/frame.jpg'),
    (None, None),
])
def test_cctv_context_reaches_capture_engine(requested, expected, path_scope, monkeypatch):
    handler = module('cctv')
    engine = handler.load_module('capture')
    def capture(url, path):
        Path(path).write_bytes(b'fixture JPEG')
        return {'success': True, 'file_size': 12, 'method': 'fixture'}
    monkeypatch.setattr(engine, '_capture_image', capture)
    monkeypatch.setattr(engine, '_find_ffmpeg', lambda: None)
    result = json.loads(handler.execute(
        {'op': 'capture', 'url': 'https://example.invalid/frame.jpg', 'save_path': requested},
        ToolContext(str(path_scope / 'project'), 'cctv_op')))
    assert result['success'], result
    path = Path(result['file_path'])
    if expected:
        assert path == path_scope / expected
    else:
        assert path.parent == path_scope / 'project/outputs/cctv_captures'
    assert path.read_bytes() == b'fixture JPEG'


@pytest.mark.parametrize('op,mode', [('play', 'client'), ('download', 'client'), ('download', 'server')])
def test_youtube_supported_modes_compile_and_dispatch(op, mode, registry, monkeypatch, tmp_path):
    source = '[limbs:music]{op:"' + op + '",mode:"' + mode + '",query:"fixture",url:"https://example.invalid/v"}'
    assert compile_program(source, registry).report()['status'] != 'invalid'
    handler = module('youtube')
    calls = []
    def yt_call(**kwargs):
        calls.append(kwargs)
        return {'success': True}
    monkeypatch.setattr(handler, 'load_tool_youtube', lambda: NS(play_youtube=yt_call, download_youtube_music=yt_call))
    assert handler.execute({'op': op, 'mode': mode, 'query': 'fixture'}, ToolContext(str(tmp_path), 'music_op'))['success']
    assert calls[-1]['mode'] == mode


@pytest.mark.parametrize('op,mode', [('play', 'server'), ('download', 'video'), ('relay', 'client')])
def test_youtube_wrong_operation_mode_fails_before_action(op, mode):
    handler = module('youtube')
    result = handler._OP_DISPATCHERS['music_op'][op]({'mode': mode}, NS())
    assert result['success'] is False and 'mode' in result['error']


def test_repaired_document_examples_compile(registry):
    photo = (TOOLS / 'photo-manager/guide.md').read_text()
    for code in re.findall(r'```ibl\n(.*?)```', photo, re.S):
        report = compile_program(code, registry).report()
        assert report['status'] != 'invalid', report
    doc = (TOOLS / 'real-estate/README.md').read_text()
    snippet = re.search(r'`(\[table:filter\].*?)`', doc).group(1)
    from ibl_v2_runtime import Runtime
    from common.expression_ir import unpack
    plan = compile_program('$result={items:[{deposit:10000},{deposit:20000}]}\n' + snippet, registry)
    result = Runtime(plan).run()
    assert result['success'], result
    assert unpack(result['value_wire']['data']) == [{'deposit': 20000}]


def test_cctv_refused_path_never_downloads(path_scope, monkeypatch):
    handler = module('cctv')
    engine = handler.load_module('capture')
    monkeypatch.setattr(engine, '_capture_image', lambda *a: pytest.fail('refused write must not download'))
    result = json.loads(handler.execute(
        {'op': 'capture', 'url': 'https://example.invalid/frame.jpg', 'save_path': '/outside-fixture/refused.jpg'},
        ToolContext(str(path_scope), 'cctv_op')))
    assert result['success'] is False and 'outside fixture scope' in result['error']


def test_real_playwright_pdf_and_png(path_scope, monkeypatch):
    from runtime_utils import setup_playwright_browsers_path
    from playwright.async_api import async_playwright
    setup_playwright_browsers_path()
    handler = module('browser-action')
    content = handler._load('browser_content')
    async def capture():
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.set_content('<h1>Package boundary repair</h1><p>Local fixture</p>')
                monkeypatch.setattr(content, 'ensure_active', lambda: None)
                monkeypatch.setattr(content.BrowserSession, 'get_instance', lambda: NS(raw_page=page))
                for op, suffix in [('pdf', 'pdf'), ('screenshot', 'png')]:
                    raw = await handler.execute(
                        {'op': op, 'driver': 'playwright', 'path': f'~workspace/reports/actual.{suffix}'},
                        ToolContext(str(path_scope / 'project'), 'browser_op'))
                    assert json.loads(raw)['success'], raw
            finally:
                await browser.close()
    asyncio.run(capture())
    assert (path_scope / 'reports/actual.pdf').read_bytes().startswith(b'%PDF')
    assert (path_scope / 'reports/actual.png').read_bytes().startswith(b'\x89PNG')


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
