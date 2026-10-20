"""Desktop capture file sink preserves bytes and the legacy image result."""
import boot_paths  # noqa: F401
import base64
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace as NS

import pytest

from tool_context import ToolContext

ROOT = Path(__file__).resolve().parents[1]


def test_screenshot_path_is_guarded_and_writes_exact_bytes(monkeypatch, tmp_path):
    spec = importlib.util.spec_from_file_location('screen_contract_handler', ROOT / 'data/packages/installed/tools/computer-use/handler.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    raw = b'\x89PNG\r\n\x1a\nsynthetic screenshot'
    captures = []
    def capture(region=None):
        captures.append(region)
        return {'base64': base64.b64encode(raw).decode(), 'media_type': 'image/png'}
    monkeypatch.setattr(module, '_capture_screenshot', capture)
    monkeypatch.setattr(module, '_get_screen_size', lambda: (1280, 800))
    import thread_context
    monkeypatch.setattr(thread_context, 'get_task_origin', lambda: 'user')   # 입회 턴 — 실행 전 문맥 검사 통과
    context = ToolContext(str(tmp_path), 'computer_op')
    monkeypatch.setattr(context, '_scope_refusal', lambda path, guard=None: None)
    legacy = module.execute({'op': 'screenshot'}, context)
    assert legacy['images'][0]['base64'] == base64.b64encode(raw).decode()
    result = module.execute({'op': 'screenshot', 'path': 'proof.png'}, context)
    assert Path(result['file_path']) == tmp_path / 'outputs/proof.png'
    assert Path(result['file_path']).read_bytes() == raw and 'images' not in result
    monkeypatch.setattr(context, '_scope_refusal', lambda path, guard=None: 'denied')
    denied = json.loads(module.execute({'op': 'screenshot', 'path': '/outside.png'}, context))
    assert not denied['success'] and len(captures) == 2






@pytest.fixture
def screen(monkeypatch):
    spec = importlib.util.spec_from_file_location('screen_focus_handler', ROOT / 'data/packages/installed/tools/computer-use/handler.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # 이 묶음은 사용자가 입회한 턴의 앱 가드를 검사한다 — 실행 전 문맥 검사(CONTROL_DRIVER §6)는
    # test_control_driver 가 따로 본다. 출처 미세팅(None)은 화면을 쓸 수 없는 문맥이라 먼저 거절된다.
    import thread_context
    monkeypatch.setattr(thread_context, 'get_task_origin', lambda: 'user')
    monkeypatch.setattr(mod, '_capture_png', lambda: 'synthetic.png')
    monkeypatch.setattr(mod, '_ocr_lines', lambda path: [])
    return mod


def test_frontmost_reads_ax_server_on_every_call(screen, monkeypatch):
    focus = [101]
    monkeypatch.setitem(sys.modules, 'ApplicationServices', NS(
        AXUIElementCreateSystemWide=lambda: 'system',
        AXUIElementCopyAttributeValue=lambda root, key, out: (0, focus[0]),
        AXUIElementGetPid=lambda element, out: (0, element)))
    monkeypatch.setitem(sys.modules, 'AppKit', NS(NSRunningApplication=NS(
        runningApplicationWithProcessIdentifier_=lambda pid: NS(
            localizedName=lambda: f'app-{pid}', bundleIdentifier=lambda: f'test.{pid}'))))
    assert screen._frontmost_app()['pid'] == 101
    focus[0] = 202
    assert screen._frontmost_app() == {'name': 'app-202', 'pid': 202, 'bundle_id': 'test.202'}


@pytest.mark.parametrize('op,params', [
    ('click', {'x': 10, 'y': 10}), ('type', {'text': 'secret'}), ('key', {'key': 'cmd+q'}),
    ('mouse_move', {'x': 10, 'y': 10}), ('drag', {}), ('scroll', {}),
])
def test_app_guard_refuses_before_any_input(screen, monkeypatch, tmp_path, op, params):
    monkeypatch.setattr(screen, '_frontmost_app', lambda: {'name': 'Other', 'pid': 9})
    monkeypatch.setattr(screen, '_get_pyautogui', lambda: pytest.fail('input driver must not load'))
    result = json.loads(screen.execute({'op': op, 'expect_app': 'Calculator', **params}, ToolContext(str(tmp_path), 'computer_op')))
    assert not result['success'] and 'APP_MISMATCH' in result['error']


def test_ref_pid_guard_and_snapshot_focus_change(screen, monkeypatch, tmp_path):
    monkeypatch.setattr(screen, '_frontmost_app', lambda: {'name': 'Other', 'pid': 9})
    screen._AX_SESSION['old:e0'] = {'pid': 8, 'el': object()}
    monkeypatch.setattr(screen, '_ax_press', lambda el: pytest.fail('stale AX must not receive input'))
    ctx = ToolContext(str(tmp_path), 'computer_op')
    denied = json.loads(screen.execute({'op': 'click', 'ref': 'old:e0'}, ctx))
    assert not denied['success'] and 'STALE_REF' in denied['error']
    apps = iter([{'name': 'Calculator', 'pid': 8}, {'name': 'Other', 'pid': 9}])
    monkeypatch.setattr(screen, '_frontmost_app', lambda: next(apps))
    seen = []
    monkeypatch.setattr(screen, '_ax_elements', lambda pid: seen.append(pid) or [{'title': '8'}])
    result = json.loads(screen.execute({'op': 'snapshot'}, ctx))
    assert seen == [8] and result['error_code'] == 'FOCUS_CHANGED'
    assert not result['elements'] and not screen._AX_SESSION


def test_guard_allows_bundle_id_and_ref_fallback_rechecks_focus(screen, monkeypatch, tmp_path):
    app = {'name': '계산기', 'pid': 8, 'bundle_id': 'com.apple.calculator'}
    monkeypatch.setattr(screen, '_frontmost_app', lambda: app)
    events = []
    monkeypatch.setattr(screen, '_get_pyautogui', lambda: NS(press=lambda key: events.append(key)))
    ctx = ToolContext(str(tmp_path), 'computer_op')
    assert json.loads(screen.execute({'op': 'key', 'key': 'enter', 'expect_app': 'com.apple.calculator'}, ctx))['success']
    assert events == ['enter']
    screen._AX_SESSION['s:e0'] = {'pid': 8, 'el': object(), 'center': [10, 10]}
    def fail_set(*args):
        app['pid'] = 9
        return False
    monkeypatch.setattr(screen, '_ax_set_value', fail_set)
    denied = json.loads(screen.execute({'op': 'type', 'ref': 's:e0', 'text': '123'}, ctx))
    assert not denied['success'] and 'APP_MISMATCH' in denied['error']


def test_wait_success_timeout_and_bad_constraints(screen, monkeypatch, tmp_path):
    ctx = ToolContext(str(tmp_path), 'computer_op')
    clock = [0.0]
    monkeypatch.setattr(screen.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(screen.time, 'sleep', lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    monkeypatch.setattr(screen, '_frontmost_app', lambda: {'name': 'Calculator' if clock[0] >= .2 else 'Other', 'pid': 8})
    monkeypatch.setattr(screen, '_idle_seconds', lambda: clock[0])
    result = json.loads(screen.execute({'op': 'wait', 'expect_app': 'Calculator', 'idle_seconds': .3, 'timeout': 500}, ctx))
    assert result['success'] and result['waited_ms'] >= 300
    result = json.loads(screen.execute({'op': 'wait', 'expect_app': 'Missing', 'timeout': 0}, ctx))
    assert result['error_code'] == 'WAIT_TIMEOUT'
    for extra in ({'timeout': -1}, {'timeout': float('nan')}, {'idle_seconds': -1}, {'expect_app': ''}):
        assert not json.loads(screen.execute({'op': 'wait', 'expect_app': 'Calculator', **extra}, ctx))['success']


def test_focus_lookup_failure_fails_closed(screen, monkeypatch, tmp_path):
    def unavailable():
        raise RuntimeError('AX permission denied')
    monkeypatch.setattr(screen, '_frontmost_app', unavailable)
    ctx = ToolContext(str(tmp_path), 'computer_op')
    for params in ({'op': 'snapshot'}, {'op': 'key', 'key': 'enter', 'expect_app': 'Calculator'},
                   {'op': 'wait', 'expect_app': 'Calculator'}):
        result = json.loads(screen.execute(params, ctx))
        assert not result['success'] and 'permission denied' in result['error']


def test_snapshot_refs_expire_across_generations(screen, monkeypatch, tmp_path):
    app = {'name': 'Calculator', 'pid': 42, 'bundle_id': 'com.apple.calculator'}
    monkeypatch.setattr(screen, '_frontmost_app', lambda: app)
    button = {'AXRole': 'AXButton', 'AXTitle': '7'}
    root = {'AXChildren': [button]}
    queried = []
    monkeypatch.setitem(sys.modules, 'ApplicationServices', NS(
        AXUIElementCreateApplication=lambda pid: queried.append(pid) or root,
        AXUIElementCopyAttributeValue=lambda el, key, out: (0, el.get(key)),
        AXValueGetValue=lambda *args: (False, None)))
    ctx = ToolContext(str(tmp_path), 'computer_op')
    first = json.loads(screen.execute({'op': 'snapshot'}, ctx))
    second = json.loads(screen.execute({'op': 'snapshot'}, ctx))
    assert queried == [42, 42] and second['app'] == 'Calculator'
    old, fresh = first['elements'][0]['ref'], second['elements'][0]['ref']
    assert old != fresh
    presses = []
    monkeypatch.setattr(screen, '_ax_press', lambda el: presses.append(el) or True)
    assert not json.loads(screen.execute({'op': 'click', 'ref': old}, ctx))['success']
    assert json.loads(screen.execute({'op': 'click', 'ref': fresh}, ctx))['success']
    assert presses == [button]


@pytest.mark.parametrize('intent,title,role', [
    ('화면 읽고 로그인 버튼 눌러', '로그인', 'AXButton'),
    ('저장 버튼 클릭해', '저장', 'AXButton'),
    ('검색창에 텍스트 입력해', '검색', 'AXTextField'),
])
@pytest.mark.parametrize('count', [0, 1, 2])
def test_repaired_examples_select_unique_observed_ref(intent, title, role, count):
    from dataclasses import replace
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    evidence = json.loads((ROOT / 'docs/experiments/long_sentence_imagination/round_45/evidence/repaired_examples.json').read_text())
    code = next(e['ibl_code'] for e in evidence['replacement'] if e['intent'] == intent)
    registry = load_registry()
    mutations = []
    def screen_call(runtime, args):
        if args['op'] == 'snapshot':
            return {'app': 'Synthetic', 'elements': [
                {'title': title, 'role': role, 'ref': f'unpredictable:{i}'} for i in range(count)]}
        mutations.append(args)
        assert args['ref'] == 'unpredictable:0' and args['expect_app'] == 'Synthetic'
        return {'success': True}
    registry['limbs:screen'] = replace(registry['limbs:screen'], run=screen_call)
    plan = compile_program(code, registry)
    assert not plan.issues, plan.report()
    result = Runtime(plan).run()
    assert result['success'] is (count == 1)
    assert len(mutations) == (1 if count == 1 else 0)


if __name__ == "__main__":
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))


def _ax_mock(system_err, app_err, front_pid=303, front=True):
    """system-wide 포커스 조회와 앱 단위 조회의 AX 오류 코드를 흉내 낸다 (10-20 입회 측정의 두 코드)."""
    def copy_attr(element, key, out):
        if element == 'system':
            return (system_err, None if system_err else front_pid)
        return (app_err, [] if not app_err else None)
    return NS(AXUIElementCreateSystemWide=lambda: 'system',
              AXUIElementCreateApplication=lambda pid: ('app', pid),
              AXUIElementCopyAttributeValue=copy_attr,
              AXUIElementGetPid=lambda element, out: (0, element),
              AXIsProcessTrusted=lambda: app_err == 0), NS(
        NSWorkspace=NS(sharedWorkspace=lambda: NS(
            frontmostApplication=lambda: NS(processIdentifier=lambda: front_pid) if front else None)),
        NSRunningApplication=NS(runningApplicationWithProcessIdentifier_=lambda pid: NS(
            localizedName=lambda: f'app-{pid}', bundleIdentifier=lambda: f'test.{pid}')))


def test_frontmost_falls_back_to_workspace_when_systemwide_cannot_complete(screen, monkeypatch):
    """-25204(kAXErrorCannotComplete)는 권한이 아니다 — NSWorkspace 폴백 + 앱 단위 조회로 앞 앱을 얻는다."""
    services, appkit = _ax_mock(system_err=-25204, app_err=0, front_pid=303)
    monkeypatch.setitem(sys.modules, 'ApplicationServices', services)
    monkeypatch.setitem(sys.modules, 'AppKit', appkit)
    assert screen._frontmost_app() == {'name': 'app-303', 'pid': 303, 'bundle_id': 'test.303'}
    # 폴백마저 앞 앱을 못 주면 "완료 불가(권한 아님)" — 권한 안내가 섞이면 안 된다
    services, appkit = _ax_mock(system_err=-25204, app_err=0, front=False)
    monkeypatch.setitem(sys.modules, 'ApplicationServices', services)
    monkeypatch.setitem(sys.modules, 'AppKit', appkit)
    with pytest.raises(RuntimeError) as exc:
        screen._frontmost_app()
    assert '-25204' in str(exc.value) and '권한 아님' in str(exc.value) and '손쉬운 사용' not in str(exc.value)


def test_frontmost_reports_permission_only_for_api_disabled_with_responsible_app(screen, monkeypatch):
    """-25211(kAXErrorAPIDisabled)만 권한 안내 — 권한 주체(책임 프로세스 경로)를 문장에 싣는다."""
    monkeypatch.setattr(screen, '_responsible_app',
                        lambda: {'pid': 1, 'path': '/Applications/IndieBiz 시작.app', 'name': 'IndieBiz 시작.app'})
    services, appkit = _ax_mock(system_err=-25204, app_err=-25211)
    monkeypatch.setitem(sys.modules, 'ApplicationServices', services)
    monkeypatch.setitem(sys.modules, 'AppKit', appkit)
    with pytest.raises(RuntimeError) as exc:
        screen._frontmost_app()
    msg = str(exc.value)
    assert '-25211' in msg and '손쉬운 사용' in msg and '/Applications/IndieBiz 시작.app' in msg and 'Python 이 아님' in msg
    # system-wide 자체가 -25211 이어도 같은 권한 문장
    services, appkit = _ax_mock(system_err=-25211, app_err=-25211)
    monkeypatch.setitem(sys.modules, 'ApplicationServices', services)
    with pytest.raises(RuntimeError, match='IndieBiz 시작.app'):
        screen._frontmost_app()


def test_screen_info_reports_ax_trust_and_responsible_app(screen, monkeypatch, tmp_path):
    monkeypatch.setattr(screen.platform, 'system', lambda: 'Darwin')
    monkeypatch.setattr(screen, '_ax_trusted', lambda: False)
    monkeypatch.setattr(screen, '_responsible_app',
                        lambda: {'pid': 1, 'path': '/Applications/IndieBiz 시작.app', 'name': 'IndieBiz 시작.app'})
    monkeypatch.setattr(screen, '_get_screen_size', lambda: (1920, 1080))
    monkeypatch.setattr(screen.subprocess, 'run', lambda *a, **k: open(a[0][-1], 'wb').write(b'x' * 200))
    info = json.loads(screen.execute({'op': 'screen_info'}, ToolContext(str(tmp_path), 'computer_op')))
    assert info['ax_trusted'] is False and info['responsible_app']['name'] == 'IndieBiz 시작.app'
    assert '손쉬운 사용' in info['note'] and '/Applications/IndieBiz 시작.app' in info['note'] and '-25211' in info['note']
    monkeypatch.setattr(screen, '_ax_trusted', lambda: True)
    info = json.loads(screen.execute({'op': 'screen_info'}, ToolContext(str(tmp_path), 'computer_op')))
    assert info['ax_trusted'] is True and 'OK' in info['note']
