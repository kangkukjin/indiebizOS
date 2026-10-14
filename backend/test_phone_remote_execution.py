"""Remote negotiation, cancellation race, owner checks and local AI reuse."""
import boot_paths  # noqa: F401
import json
import threading
import time
import pytest
import phone_remote_execution as runtime
import resident_pcs as pcs
import resident_store
import principal
from test_limb_client import hub, phone_env, _client, _enroll_phone  # noqa: F401


class Bridge:
    def __init__(self):
        self.seen = []
        self.registered = threading.Event()
        self.cancelled = threading.Event()

    def capabilities(self):
        return json.dumps({'execution_contract': 1, 'shell': True, 'runtimes': {'python': {'ready': True}}})

    def execute(self, job_id, command):
        command = json.loads(command)
        self.seen.append((job_id, command))
        if command.get('code') == 'block':
            time.sleep(.15)  # Deliberately cancel before native registration.
            self.registered.set()
            assert self.cancelled.wait(3)
            return json.dumps({'success': False, 'cancelled': True, 'error': 'cancelled'})
        return json.dumps({'success': True, 'value': command.get('inputs'), 'exit_code': None})

    def cancel(self, job_id):
        if self.registered.is_set():
            self.cancelled.set()
            return True
        return False


@pytest.fixture
def bridge(monkeypatch):
    fake = Bridge()
    monkeypatch.setattr(runtime, '_bridge_factory', lambda: fake)
    return fake


def test_negotiation_receipt_exactly_once_and_structured_value(hub, phone_env, bridge):
    rec = _enroll_phone()
    c = _client(hub, rec, lambda *args: pytest.fail('IBL fallback forbidden'))
    with pytest.raises(ValueError, match='unsupported_on_this_body'):
        pcs.submit(rec['device_id'], {'op': 'python', 'code': 'result = 1'})
    c.step(inline=True, wait=0)  # New capabilities must actually reach the hub.
    cmd = {'op': 'python', 'code': 'result = inputs', 'inputs': {'hello': '한글'}}
    receipt = pcs.submit(rec['device_id'], cmd, 'once')
    assert pcs.submit(rec['device_id'], cmd, 'once')['job_id'] == receipt['job_id']
    with pytest.raises(ValueError, match='request_id_conflict'):
        pcs.submit(rec['device_id'], {**cmd, 'code': 'result = 2'}, 'once')
    c.step(inline=True, wait=0)
    c.step(inline=True, wait=0)
    assert resident_store.wait_result(receipt['job_id'], timeout=0)['value'] == {'hello': '한글'}
    assert len(bridge.seen) == 1
    assert bridge.seen[0][1]['timeout'] == 120


def test_non_owner_cannot_submit_or_execute(hub, phone_env, bridge):
    rec = _enroll_phone()
    c = _client(hub, rec, lambda *args: {})
    c.step(inline=True, wait=0)
    with principal._Scope(principal.ANONYMOUS):
        with pytest.raises(PermissionError, match='owner_required'):
            pcs.submit(rec['device_id'], {'op': 'python', 'code': 'result = 1'})
        assert runtime.execute('x', {'op': 'shell', 'cmd': 'id'})['error'] == 'phone_execution_owner_required'
    assert not bridge.seen


def test_cancel_before_native_registration_is_not_lost(bridge):
    cancel = threading.Event()
    out = []
    worker = threading.Thread(target=lambda: out.append(runtime.execute('race', {'op': 'python', 'code': 'block'}, cancel)))
    worker.start()
    cancel.set()
    worker.join(4)
    assert not worker.is_alive()
    assert out[0]['cancelled'] is True


def test_info_and_cancel_do_not_wait_behind_python(hub, phone_env, bridge):
    rec = _enroll_phone()
    c = _client(hub, rec, lambda *args: {})
    c.step(inline=True, wait=0)
    run = pcs.submit(rec['device_id'], {'op': 'python', 'code': 'block'}, 'blocking')
    c.step(wait=0)
    assert bridge.registered.wait(2)
    info = pcs.submit(rec['device_id'], {'op': 'info'}, 'probe')
    c.step(wait=0)
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        c.step(wait=0)
        if resident_store.wait_result(info['job_id'], timeout=0):
            break
        time.sleep(.01)
    assert resident_store.wait_result(info['job_id'], timeout=0)['success']
    c._cancel(run['job_id'])
    c._worker.join(3)
    c.step(wait=0)
    assert resident_store.wait_result(run['job_id'], timeout=0)['cancelled']


def test_local_execution_does_not_need_registration(bridge, phone_env):
    result = runtime.run_local({'runtime': 'python', 'command': 'result = inputs', 'inputs': {'n': 7}})
    assert result['value'] == {'n': 7}
    assert bridge.seen[0][0].startswith('local_')


def test_native_execution_does_not_escape_repair_scope(bridge, monkeypatch):
    import repair_context
    monkeypatch.setattr(repair_context, 'active', lambda: {'task_id': 'repair'})
    result = runtime.run_local({'runtime': 'python', 'command': 'result = 1'})
    assert result['error'] == 'phone_execution_has_no_repair_sandbox'
    assert not bridge.seen


def test_permission_failure_is_http_403(hub, phone_env, bridge, monkeypatch):
    rec = _enroll_phone()
    c = _client(hub, rec, lambda *args: {})
    c.step(inline=True, wait=0)
    def denied():
        raise PermissionError('phone_execution_owner_required')
    monkeypatch.setattr(runtime, 'require_owner', denied)
    response = hub.post('/remote-pcs/command', json={
        'target': rec['device_id'], 'command': {'op': 'python', 'code': 'result = 1'}})
    assert response.status_code == 403
    assert response.json()['detail'] == 'phone_execution_owner_required'


def test_guest_helper_python_and_local_ai_tool_use_same_runtime(hub, phone_env, bridge, monkeypatch):
    import importlib.util
    from pathlib import Path
    from types import SimpleNamespace
    root = Path(__file__).resolve().parents[1]
    def handler(package):
        path = root / 'data/packages/installed/tools' / package / 'handler.py'
        spec = importlib.util.spec_from_file_location('phone_test_' + package, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    rec = _enroll_phone()
    client = _client(hub, rec, lambda *args: pytest.fail('unexpected IBL'))
    client.step(inline=True, wait=0)
    remote = handler('guest-helper')
    monkeypatch.setattr(remote, '_guestpc_begin', lambda args: (rec['device_id'], rec['alias'], None))
    ticket = remote._op_python({'code': 'result = inputs', 'inputs': {'n': 1}, 'background': True})
    client.step(inline=True, wait=0)
    client.step(inline=True, wait=0)
    assert resident_store.wait_result(ticket['job_id'], timeout=0)['value'] == {'n': 1}
    local = handler('system_essentials')
    context = SimpleNamespace(tool_name='run_command', project_path=str(phone_env), agent_id='phone')
    result = json.loads(local.execute({'runtime': 'python', 'command': 'result = inputs', 'inputs': {'n': 2}}, context))
    assert result['value'] == {'n': 2}
    assert len(bridge.seen) == 2


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
