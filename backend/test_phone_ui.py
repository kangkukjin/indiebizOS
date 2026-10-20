"""Android UI driver: native boundary, postconditions and no-replay recovery."""
import boot_paths  # noqa: F401
import copy
import importlib.util
import json
from pathlib import Path

import pytest
from test_android_control import pc, flow  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('phone_ui_test', ROOT / 'data/instruments/phone_ui.py')
ui = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ui)


def screen(text='', package='com.example.app'):
    return {'success': True, 'ui_contract': 1, 'snapshot_id': 'a' * 64, 'package': package,
            'window_id': 1, 'width': 1080, 'height': 2400, 'count': 1, 'truncated': False,
            'elements': [{'ref': 0, 'path': '0/1', 'resource_id': 'app:id/input', 'text': text,
                          'label': text, 'focused': True, 'editable': True, 'enabled': True, 'password': False}]}


def request(action, **extra):
    return pc.validate({'action': action, **({'snapshot_id': 'a' * 64} if action in {'tap', 'back', 'type_text'} else {}), **extra})


def exercise(req, after=None, reply=None, error=None):
    before = screen()
    calls = []
    dispatch = reply if reply is not None else {
        'success': True, 'dispatched': True, 'before': before,
        'target_element': before['elements'][0], 'expected_package': 'com.example.app'}
    def bridge(method, *args):
        calls.append((method, args))
        if method == 'uiControl':
            sent = json.loads(args[0])
            assert sent['op'] == req['action']
            return {'control': dispatch}
        if len(calls) == 1:
            return before
        if error:
            raise RuntimeError(error)
        return after if after is not None else screen()
    args = {**req, 'op': req['action']}
    args.pop('action')
    value = ui.run(args, bridge=bridge, verifier=lambda v: pc.readback(req, v), sleep=lambda _: None)
    return value, calls


@pytest.mark.parametrize('req,after', [
    (request('ui_snapshot'), screen()),
    (request('app_launch', package='com.example.app'), screen()),
    (request('home'), screen()),
    (request('tap', ref=0, expect={'text': '다음'}), screen('다음')),
    (request('back', expect={'package': 'com.example.app', 'text': '뒤로'}), screen('뒤로')),
    (request('type_text', ref=0, text='한글\nhello'), screen('한글\nhello')),
    (request('type_text', ref=0, text=''), screen('')),
])
def test_verified_ui_readback(req, after):
    value, calls = exercise(req, after)
    assert pc.readback(req, value)
    assert sum(m == 'uiControl' for m, _ in calls) == (req['action'] != 'ui_snapshot')


@pytest.mark.parametrize('req,after', [
    (request('app_launch', package='com.example.other'), screen()),
    (request('home'), screen(package='com.android.resolver')),
    (request('tap', x=30, y=40, expect={'text': '없음'}), screen('다름')),
    (request('back', expect={'package': 'com.example.other', 'text': 'ok'}), screen('ok')),
    (request('type_text', ref=0, text='new'), screen('old')),
    (request('type_text', ref=0, text='new'), screen('new', package='com.example.other')),
])
def test_unconfirmed_ui_is_unknown_and_never_replayed(req, after):
    value, calls = exercise(req, after)
    assert value['driver_status'] == 'unknown' and not pc.readback(req, value)
    assert sum(m == 'uiControl' for m, _ in calls) == 1
    assert sum(m == 'snapshot' for m, _ in calls) == 9


@pytest.mark.parametrize('action,extra', [('tap', {'ref': 0}), ('back', {})])
def test_unqualified_ui_dispatch_is_not_verified(action, extra):
    req = request(action, **extra)
    value, calls = exercise(req)
    assert not pc.readback(req, value) and pc.completion_allowed(req, value, False)
    assert pc.condition(action, req)['verification_scope'] == 'ui_dispatch_observed'
    value['before']['snapshot_id'] = 'b' * 64
    assert not pc.completion_allowed(req, value, False)


def test_lost_observation_retains_dispatch_evidence():
    req = request('type_text', ref=0, text='hello')
    value, calls = exercise(req, error='accessibility disabled after apply')
    assert value['driver_status'] == 'unknown' and value['dispatched']
    assert value['before']['snapshot_id'] == req['snapshot_id']
    assert sum(m == 'uiControl' for m, _ in calls) == 1


@pytest.mark.parametrize('reply,status', [
    ({'success': False, 'dispatched': False, 'error': 'STALE_SCREEN'}, 'failed'),
    ({'success': False, 'dispatched': False, 'error': 'APP_NOT_LAUNCHABLE'}, 'failed'),
    ({'success': False, 'needs_accessibility': True, 'error': 'disabled'}, 'failed'),
    ({'success': False, 'dispatched': True, 'error': 'gesture cancelled'}, 'unknown'),
])
def test_native_failure_phase_preserved(reply, status):
    value, calls = exercise(request('tap', ref=0), reply=reply)
    assert value['driver_status'] == status
    assert len(calls) == 2


def test_old_apk_and_disabled_accessibility_never_dispatch():
    calls = []
    def bridge(method, *args):
        calls.append(method)
        return {'success': True, 'elements': [], 'count': 0}
    value = ui.run({'op': 'home'}, bridge=bridge)
    assert value['driver_status'] == 'failed' and calls == ['snapshot']
    def disabled(*_):
        raise RuntimeError('accessibility disabled')
    assert ui.run({'op': 'home'}, bridge=disabled)['execution_phase'] == 'before_dispatch'


@pytest.mark.parametrize('change', [
    {'path': '0/2'}, {'focused': False}, {'password': True}, {'editable': False}, {'resource_id': 'other'},
])
def test_same_text_in_wrong_field_cannot_verify(change):
    req = request('type_text', ref=0, text='new')
    after = screen('new')
    after['elements'][0].update(change)
    value, _ = exercise(req, after)
    assert value['driver_status'] == 'unknown'


@pytest.mark.parametrize('req', [
    {'action': 'tap', 'snapshot_id': 'a'*64},
    {'action': 'tap', 'snapshot_id': 'a'*64, 'ref': 0, 'x': 1, 'y': 1},
    {'action': 'tap', 'snapshot_id': 'a'*64, 'x': True, 'y': 1},
    {'action': 'back', 'snapshot_id': 'old'},
    {'action': 'back', 'snapshot_id': 'a'*64, 'expect': {}},
    {'action': 'back', 'snapshot_id': 'a'*64, 'expect': {'unknown': 'a'}},
    {'action': 'app_launch', 'package': 'com.example.app;rm'},
    {'action': 'type_text', 'snapshot_id': 'a'*64, 'ref': 0, 'text': 1},
    {'action': 'type_text', 'snapshot_id': 'a'*64, 'ref': 0, 'text': 'a'*10001},
])
def test_invalid_ui_request_never_prepares(req):
    with pytest.raises(ValueError):
        pc.prepare({'request': req, 'source': 'raise AssertionError()'})


def test_prepared_script_executes_real_primitive_and_verifier(monkeypatch):
    import sys
    import types
    monkeypatch.setitem(sys.modules, 'indiebiz_android', types.SimpleNamespace(call=lambda method: screen()))
    req = request('ui_snapshot')
    plan = pc.prepare({'request': req, 'source': (ROOT / 'data/instruments/phone_ui.py').read_text()})
    ns = {}
    exec(plan['code'], ns)
    assert ns['result']['verified'] and ns['result']['screen']['package'] == 'com.example.app'
    assert ns['result']['condition']['needs_front'] is True
    assert ns['result']['condition']['shared_state'] is False


@pytest.mark.parametrize('req', [request('app_launch', package='com.example.app'), request('home'),
    request('back', expect={'text':'다음'}), request('tap', ref=0, expect={'text':'다음'}),
    request('type_text', ref=0, text='다음'), request('ui_snapshot')])
def test_ui_pending_followup_queries_original_receipt(flow, req):
    run, state = flow
    task = run('return [fn:Android제어]{대상:"pc-1",요청:$request,대기:0}', {'request': req})
    assert task['status'] == 'pending'
    assert any(k == 'self:read' and 'phone_ui.py' in str(p) for k, p in state['calls'])
    value, _ = exercise(req, screen('다음'))
    state['native_override'] = {'action': req['action'], **value}
    state['terminal'] = True
    result = run('return [fn:Android제어확인]{작업:$task,대기:0}', {'task': task})
    assert result['status'] == 'completed' and result['verified'], result
    assert sum(k == 'limbs:guestpc' for k, _ in state['calls']) == 1


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
