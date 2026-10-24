import boot_paths  # noqa: F401
import json
from pathlib import Path
import sys
import threading
from types import SimpleNamespace

import pytest
import phone_native_control as native
import phone_remote_execution as remote
import principal
from test_limb_client import hub, phone_env, _client, _enroll_phone  # noqa: F401

ROOT = Path(__file__).resolve().parents[1]


class Bridge:
    def __init__(self):
        self.entered = []
        self.released = []
        self.active = True

    def capabilities(self):
        return json.dumps({'execution_contract': 1, 'native_control': 1})

    def beginControl(self, job, timeout):
        self.entered.append(job)
        return self.active

    def controlActive(self, job):
        return self.active

    def endControl(self, job):
        self.released.append(job)
        return self.active

    def cancel(self, job):
        self.active = False


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setattr(native, '_root', lambda: ROOT)
    bridge = Bridge()
    monkeypatch.setattr(remote, '_bridge_factory', lambda: bridge)
    calls = []

    def call(method, argument):
        calls.append((method, json.loads(argument)))
        return {'success': True, 'verified': True, 'brightness': 120, 'brightness_auto': False}

    monkeypatch.setitem(sys.modules, 'indiebiz_android', SimpleNamespace(call=call))
    return bridge, calls


def command(request=None):
    driver, _, caps = native._installed()
    request = request or {'action': 'brightness', 'value': 120}
    filename = 'phone_ui.py' if request['action'] in driver.UI else 'phone_device.py'
    return {'op': 'control', 'inputs': {'request': request, 'request_id': 'a' * 32,
            'helper_sha256': caps['helper_sha256'], 'source_sha256': caps['sources'][filename]}}


def test_fixed_installed_control_uses_native_result_and_verifier(setup):
    bridge, calls = setup
    out = native.execute('job', command(), threading.Event())
    assert out['success'] and out['execution_mode'] == 'native_control'
    assert out['value']['verified'] and out['value']['driver_status'] == 'completed'
    assert calls == [('hardware', {'op': 'brightness', 'value': 120})]
    assert bridge.entered == bridge.released == ['job']


@pytest.mark.parametrize('field,value', [('code', 'raise Exception()'), ('env', {}), ('cwd', '/tmp')])
def test_control_never_accepts_executable_source_or_environment(setup, field, value):
    with pytest.raises(ValueError, match='no_code_or_environment'):
        native.validate({**command(), field: value})
    assert setup[0].entered == []


def test_version_mismatch_and_pre_cancel_are_before_dispatch(setup):
    cmd = command()
    cmd['inputs']['source_sha256'] = '0' * 64
    out = native.execute('bad-version', cmd, threading.Event())
    assert not out['success'] and not out['side_effects_possible']
    assert 'VERSION_MISMATCH' in out['error']
    cancel = threading.Event(); cancel.set()
    out = native.execute('cancelled', command(), cancel)
    assert not out['side_effects_possible'] and not setup[1] and not setup[0].entered


def test_cancel_during_call_waits_for_return_and_never_replays(setup, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    calls, results = [], []
    def call(*args):
        calls.append(args); entered.set()
        assert release.wait(3)
        return {'success': True, 'verified': True, 'brightness': 120, 'brightness_auto': False}
    monkeypatch.setitem(sys.modules, 'indiebiz_android', SimpleNamespace(call=call))
    cancel = threading.Event()
    thread = threading.Thread(target=lambda: results.append(native.execute('inflight', command(), cancel)))
    thread.start()
    assert entered.wait(2)
    cancel.set()
    assert results == [] and setup[0].released == []
    release.set(); thread.join(3)
    assert not thread.is_alive() and len(calls) == 1
    assert results[0]['unknown'] and results[0]['side_effects_possible']
    assert setup[0].released == ['inflight']


def test_non_owner_and_repair_cannot_use_direct_path(setup, monkeypatch):
    with principal._Scope(principal.ANONYMOUS):
        assert native.execute('anon', command(), threading.Event())['error'] == 'phone_execution_owner_required'
    import repair_context
    monkeypatch.setattr(repair_context, 'active', lambda: {'task_id': 'repair'})
    assert native.execute('repair', command(), threading.Event())['error'] == 'phone_execution_has_no_repair_sandbox'
    assert setup[0].entered == [] and setup[1] == []


def test_receipt_deduplication_and_screen_context_owned_by_hub(hub, phone_env, setup):
    import resident_pcs as pcs
    import resident_store
    from thread_context import actor_context
    rec = _enroll_phone()
    c = _client(hub, rec, lambda *a: pytest.fail('no IBL fallback'))
    c.step(inline=True, wait=0)
    cmd = command()
    first = pcs.submit(rec['device_id'], cmd)
    assert pcs.submit(rec['device_id'], cmd)['job_id'] == first['job_id']
    with pytest.raises(ValueError, match='request_id_mismatch'):
        pcs.submit(rec['device_id'], cmd, 'b' * 32)
    c.step(inline=True, wait=0); c.step(inline=True, wait=0)
    observed = resident_store.wait_result(first['job_id'], 0)
    assert observed.get('value', {}).get('verified'), observed
    assert len(setup[1]) == 1
    ui = {**command({'action': 'home'}), 'screen_context': {'available': True, 'origin': 'user'}}
    with actor_context(origin='scheduler'):
        with pytest.raises(PermissionError, match='화면'):
            pcs.submit(rec['device_id'], ui)
    with principal._Scope(principal.ANONYMOUS):
        with pytest.raises(PermissionError):
            pcs.submit(rec['device_id'], cmd)
if __name__ == '__main__':
    import pytest
    raise SystemExit(pytest.main([__file__]))
