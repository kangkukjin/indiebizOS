"""Persistent TV ownership, cancellation and no-replay contracts (no real TV)."""
import boot_paths  # noqa: F401
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import importlib.util
import json
import socket
import threading
import time
from types import SimpleNamespace

import pytest

import tv_transport as transport


class Store:
    def __init__(self):
        self.rows = {key: {'device_id': key, 'driver': 'samsung-tizen',
                          'connection': {'ip': ip, 'token': 'old'}, 'paused': False}
                     for key, ip in [('tv-a', '192.0.2.1'), ('tv-b', '192.0.2.2')]}

    def connection(self, target):
        rec = self.rows['tv-a' if target == 'alias' else target]
        if rec['paused']:
            raise PermissionError('paused')
        return deepcopy(rec)

    def save_token(self, target, token, *, expected_connection):
        if expected_connection != self.connection(target)['connection']:
            raise PermissionError('changed')
        self.rows[target]['connection']['token'] = token

    def observe(self, target, reachable):
        pass


@pytest.fixture
def rig(monkeypatch):
    spec = importlib.util.spec_from_file_location('test_installed_tv', transport.DRIVER)
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    opened, sent = [], []

    class Remote:
        def __init__(self, cfg, sink, **kwargs):
            self.ip = cfg['ip']
            self.closed = threading.Event()
            self.s = SimpleNamespace(shutdown=lambda _: self.closed.set())
            self.check = kwargs.get('check', lambda: None)
            self._send = lambda *args: None
            opened.append(self)
        def _message(self, end):
            self.closed.wait(3)
            raise EOFError()
        def key(self, key):
            sent.append((self.ip, key))
        def close(self):
            self.closed.set()

    monkeypatch.setattr(driver, 'Remote', Remote)
    monkeypatch.setattr(driver, 'power_status', lambda cfg: {'power': 'on', 'verified': True})
    manager = transport.Manager(driver, store=Store())
    yield manager, opened, sent
    manager.close()


def key(manager, target='tv-a', keys=None, **kwargs):
    return manager.run({'target': target, 'op': 'key', 'keys': keys or ['KEY_HOME:0']},
                       timeout=kwargs.pop('timeout', 3), **kwargs)


def test_repeated_calls_aliases_ttl_and_distinct_devices(rig):
    manager, opened, sent = rig
    for _ in range(10):
        result = key(manager, 'alias')
        assert result['success'] and not result['verified']
    assert len(opened) == 1 and len(sent) == 10
    key(manager, 'tv-b')
    assert len(opened) == 2
    manager.sessions['tv-a'].last_used -= 61
    manager.sweep()
    assert opened[0].closed.is_set()
    key(manager)
    assert len(opened) == 3


def test_idle_limit_does_not_evict_active_or_waiting(rig):
    manager, opened, _ = rig
    manager.max_idle = 1
    key(manager)
    first = manager.sessions['tv-a']
    first.users = 1
    key(manager, 'tv-b')
    assert not opened[0].closed.is_set()
    first.users = 0
    manager.sweep()
    assert len(manager.sessions) == 1


@pytest.mark.parametrize('change', ['token', 'ip', 'paused'])
def test_configuration_or_revocation_closes_idle_session(rig, change):
    manager, opened, _ = rig
    key(manager)
    rec = manager.store.rows['tv-a']
    if change == 'paused':
        rec['paused'] = True
    else:
        rec['connection'][change] = 'new' if change == 'token' else '192.0.2.3'
    manager.sweep()
    assert opened[0].closed.is_set()
    if change == 'paused':
        with pytest.raises(PermissionError):
            key(manager)
    else:
        assert key(manager)['success']
        assert len(opened) == 2


def test_token_callback_updates_fingerprint_and_reuses_socket(rig, monkeypatch):
    manager, opened, _ = rig
    original = manager.driver.Remote
    def connect(cfg, sink, **kwargs):
        sink('new-token')
        return original(cfg, sink, **kwargs)
    monkeypatch.setattr(manager.driver, 'Remote', connect)
    assert key(manager)['success']
    assert key(manager)['success']
    assert len(opened) == 1
    assert manager.store.rows['tv-a']['connection']['token'] == 'new-token'


def test_configuration_change_during_pairing_rejects_stale_token(rig, monkeypatch):
    manager, opened, sent = rig
    def connect(cfg, sink, **kwargs):
        manager.store.rows['tv-a']['connection']['ip'] = '192.0.2.4'
        sink('stale-token')
        pytest.fail('stale token accepted')
    monkeypatch.setattr(manager.driver, 'Remote', connect)
    result = key(manager)
    assert not result['success'] and not sent
    assert manager.store.rows['tv-a']['connection']['token'] == 'old'


def test_known_dead_before_send_reconnects_but_partial_send_never_replays(rig):
    manager, opened, sent = rig
    key(manager)
    manager.sessions['tv-a'].dead.set()
    assert key(manager)['success']
    assert len(opened) == 2
    def partial(key):
        sent.append(('partial', key))
        raise OSError('bytes may have left')
    opened[-1].key = partial
    result = key(manager, keys=['KEY_MUTE:0', 'KEY_POWER:0'])
    assert not result['success'] and result['unknown'] and result['sent'] == []
    assert sent[-1] == ('partial', 'KEY_MUTE')
    assert len(opened) == 2 and opened[-1].closed.is_set()


def test_partial_sequence_and_cancellation_preserve_sent_prefix(rig):
    manager, opened, sent = rig
    checks = threading.Event()
    assert key(manager)['success']
    original = opened[0].key
    def send(key):
        original(key)
        checks.set()
    opened[0].key = send
    def check():
        if checks.is_set():
            raise RuntimeError('cancelled')
    result = key(manager, keys=['KEY_MUTE:0', 'KEY_POWER:0'], check=check)
    assert not result['success'] and result['unknown']
    assert result['sent'] == ['KEY_MUTE']
    assert not any(k == 'KEY_POWER' for _, k in sent)


def test_cancel_before_execution_sends_nothing(rig):
    manager, opened, sent = rig
    def check():
        raise RuntimeError('cancelled')
    result = key(manager, check=check)
    assert not result['success'] and not result['unknown']
    assert not opened and not sent


def test_same_device_fifo_other_device_independent_and_queue_deadline(rig):
    manager, opened, sent = rig
    entered, release = threading.Event(), threading.Event()
    original = manager.driver.execute
    def execute(args, *pos, **kw):
        if args.get('keys') == ['KEY_HOLD:0']:
            entered.set()
            assert release.wait(3)
        return original(args, *pos, **kw)
    manager.driver.execute = execute
    with ThreadPoolExecutor(max_workers=4) as pool:
        first = pool.submit(key, manager, keys=['KEY_HOLD:0'])
        assert entered.wait(1)
        second = pool.submit(key, manager, keys=['KEY_SECOND:0'])
        # Wait until the second request is actually queued, not a scheduler guess.
        until = time.monotonic() + 1
        while len(manager.sessions['tv-a'].queue) < 2 and time.monotonic() < until:
            time.sleep(.005)
        expired = pool.submit(key, manager, timeout=.05).result()
        assert expired['timed_out'] and not expired['unknown']
        assert key(manager, 'tv-b')['success']
        release.set()
        assert first.result()['success'] and second.result()['success']
    assert [k for ip, k in sent if ip == '192.0.2.1'] == ['KEY_HOLD', 'KEY_SECOND']


def test_shutdown_closes_reader_and_prevents_new_commands(rig):
    manager, opened, _ = rig
    key(manager)
    reader = manager.sessions['tv-a'].reader
    manager.start()
    manager.close()
    assert opened[0].closed.is_set() and not reader.is_alive()
    assert not manager.reaper.is_alive()
    with pytest.raises(RuntimeError):
        key(manager)


def test_pinned_adapter_falls_back_before_invocation(monkeypatch, tmp_path):
    import principal
    import thread_context
    monkeypatch.setattr(principal, 'is_owner', lambda: True)
    monkeypatch.setattr(thread_context, 'get_allowed_nodes', lambda: None)
    monkeypatch.setattr(thread_context, 'get_repair_workspace', lambda: None)
    entry = {'interpreter': 'python'}
    assert hashlib.sha256(transport.DRIVER.read_bytes()).hexdigest() == transport.DRIVER_SHA256
    assert transport.registered_process(tmp_path / 'tv_control.py', entry, {}, timeout=1) is None
    monkeypatch.setattr(transport, 'DRIVER_SHA256', 'mismatch')
    assert transport.registered_process(transport.DRIVER, entry, {}, timeout=1) is None
    monkeypatch.setattr(thread_context, 'get_repair_workspace', lambda: '/repair')
    assert transport.registered_process(transport.DRIVER, entry, {}, timeout=1) is None


def test_registered_adapter_keeps_json_contract_and_host_cancellation(rig, monkeypatch):
    import principal
    import thread_context
    import script_process
    manager, opened, sent = rig
    monkeypatch.setattr(transport, '_manager', manager)
    monkeypatch.setattr(principal, 'is_owner', lambda: True)
    monkeypatch.setattr(thread_context, 'get_allowed_nodes', lambda: None)
    monkeypatch.setattr(thread_context, 'get_repair_workspace', lambda: None)
    args = {'op': 'key', 'target': 'tv-a', 'keys': ['KEY_HOME:0']}
    def cancel():
        raise RuntimeError('cancelled')
    with script_process.invocation_scope(cancel):
        result = transport.registered_process(transport.DRIVER, {'interpreter': 'python'}, args, timeout=1)
    assert result['exit_code'] == 0
    assert json.loads(result['stdout'])['success'] is False
    assert not opened and not sent


def test_http_reuses_origin_and_auth_without_redirect_or_retry(rig, monkeypatch):
    import requests
    manager, _, _ = rig
    made = []
    class Response:
        status_code = 200
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def iter_content(self, size): yield b'ok'
    class Client:
        def __init__(self): self.calls = []; made.append(self)
        def request(self, method, url, **kwargs):
            self.calls.append((method, url, kwargs))
            assert kwargs['allow_redirects'] is False
            return Response()
        def close(self): pass
    monkeypatch.setattr(requests, 'Session', Client)
    session = transport.Session()
    req = transport.Request(manager, session, manager.store.connection('tv-a'), time.monotonic()+3, lambda: None)
    for _ in range(10): assert req.request('http://192.0.2.1:8001/api/v2/') == b'ok'
    req.request('https://api.smartthings.com/status', headers={'Authorization': 'Bearer test'})
    req.request('https://api.smartthings.com/status', headers={'Authorization': 'Bearer changed'})
    assert len(made) == 3 and len(made[0].calls) == 10
    assert all(c.trust_env is False for c in made)
    session.close()


def test_single_reader_handles_ping_fragment_and_eof(rig):
    manager, _, _ = rig
    # Use the actual driver's parser over a socket pair, without TLS or a TV.
    spec = importlib.util.spec_from_file_location('wire_tv', transport.DRIVER)
    driver = importlib.util.module_from_spec(spec); spec.loader.exec_module(driver)
    left, right = socket.socketpair()
    remote = object.__new__(driver.Remote)
    remote.s = left
    remote.check = lambda: None
    try:
        right.sendall(b'\x01\x02he\x89\x01x\x80\x03llo')
        assert remote._message(time.monotonic()+1) == 'hello'
        pong = right.recv(20)
        assert pong[0] == 0x8a
        right.close()
        with pytest.raises(EOFError): remote._message(time.monotonic()+1)
    finally:
        remote.close(); right.close()


@pytest.mark.parametrize('restricted', ['member', 'allowed_nodes', 'repair', 'disabled'])
def test_trusted_boundary_rejects_in_process_execution_for_restricted_callers(monkeypatch, restricted):
    import principal
    import thread_context
    monkeypatch.setattr(principal, 'is_owner', lambda: restricted != 'member')
    monkeypatch.setattr(thread_context, 'get_allowed_nodes', lambda: [] if restricted == 'allowed_nodes' else None)
    monkeypatch.setattr(thread_context, 'get_repair_workspace', lambda: '/repair' if restricted == 'repair' else None)
    monkeypatch.setenv('INDIEBIZ_TV_PERSISTENT', '0' if restricted == 'disabled' else '1')
    assert transport.registered_process(transport.DRIVER, {'interpreter': 'python'},
                                        {'target': 'tv-a', 'op': 'status'}, timeout=1) is None


def test_cancellation_between_power_read_and_wol_sends_no_packet(rig, monkeypatch):
    manager, _, sent = rig
    manager.store.rows['tv-a']['connection'].update(mac='aa:bb:cc:dd:ee:ff', broadcast='192.0.2.255')
    cancelled = threading.Event()
    def power(cfg):
        cancelled.set()
        return {'power': 'unknown'}
    def check():
        if cancelled.is_set():
            raise RuntimeError('cancelled after read')
    monkeypatch.setattr(manager.driver, 'power_status', power)
    class UDP:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def setsockopt(self, *args): pass
        def sendto(self, *args): pytest.fail('WOL after cancellation')
    monkeypatch.setattr(manager.driver.socket, 'socket', lambda *a: UDP())
    result = manager.run({'target': 'tv-a', 'op': 'on'}, timeout=1, check=check)
    assert not result['success'] and not result['unknown'] and not sent


def test_wol_partial_failure_is_unknown_without_retry(rig, monkeypatch):
    manager, _, _ = rig
    manager.store.rows['tv-a']['connection'].update(mac='aa:bb:cc:dd:ee:ff', broadcast='192.0.2.255')
    monkeypatch.setattr(manager.driver, 'power_status', lambda cfg: {'power': 'unknown'})
    packets = []
    class UDP:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def setsockopt(self, *args): pass
        def sendto(self, packet, address):
            packets.append(address)
            raise OSError('delivery unknown')
    monkeypatch.setattr(manager.driver.socket, 'socket', lambda *a: UDP())
    result = manager.run({'target': 'tv-a', 'op': 'on'}, timeout=1)
    assert not result['success'] and result['unknown'] and len(packets) == 1


def test_standalone_handshake_header_remains_bounded(monkeypatch):
    spec = importlib.util.spec_from_file_location('bounded_tv', transport.DRIVER)
    driver = importlib.util.module_from_spec(spec); spec.loader.exec_module(driver)
    closed = []
    class SilentSocket:
        def settimeout(self, timeout): pass
        def sendall(self, payload): pass
        def recv(self, size): raise socket.timeout()
        def close(self): closed.append(True)
    wire = SilentSocket()
    monkeypatch.setattr(driver.socket, 'create_connection', lambda *a, **k: wire)
    monkeypatch.setattr(driver.ssl, 'create_default_context', lambda: SimpleNamespace(wrap_socket=lambda *a, **k: wire))
    clock = iter(range(50))
    monkeypatch.setattr(driver.time, 'monotonic', lambda: next(clock))
    with pytest.raises(TimeoutError):
        driver.Remote({'ip': '192.0.2.1'}, lambda _: None)
    assert closed


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
