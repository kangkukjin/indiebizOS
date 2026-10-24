"""Real-TV transport acceptance without remote keys; uses a separate Manager.

Usage: .venv/bin/python probe_tv_connection.py DEVICE NEW_OUTPUT.json
Public hub status is measured separately. No URLs, addresses or tokens are saved.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401
import tv_transport  # noqa: E402


def main():
    target, output = sys.argv[1:]
    destination = Path(output)
    if destination.exists():
        raise SystemExit('Existing evidence must not be overwritten')
    source = tv_transport.DRIVER.read_bytes()
    assert hashlib.sha256(source).hexdigest() == tv_transport.DRIVER_SHA256
    spec = importlib.util.spec_from_loader('_tv_live_probe', loader=None)
    driver = importlib.util.module_from_spec(spec)
    driver.__file__ = str(tv_transport.DRIVER)
    exec(compile(source, str(tv_transport.DRIVER), 'exec'), driver.__dict__)
    handshakes = []
    original = driver.Remote

    class ObservedRemote(original):
        def __init__(self, *args, **kwargs):
            start = time.monotonic()
            super().__init__(*args, **kwargs)
            handshakes.append(round(time.monotonic() - start, 4))

        def key(self, key):
            raise AssertionError('This probe never sends remote keys')

    driver.Remote = ObservedRemote
    manager = tv_transport.Manager(driver)
    manager.start()
    record = {'target': target, 'scope': 'separate_manager_real_tv', 'keys_sent': 0}

    def save():
        destination.write_text(json.dumps(record, indent=2) + '\n')
        print(json.dumps(record), flush=True)

    def status():
        result = manager.run({'target': target, 'op': 'status'}, timeout=30)
        assert result.get('verified') is True and result.get('power') == 'on'
        return manager.sessions[target]

    def connect(session):
        with manager.lock:
            session.users += 1
        try:
            rec = manager.store.connection(target)
            request = tv_transport.Request(manager, session, rec, time.monotonic() + 35, lambda: None)
            request.executing = True
            with session.turn(request.check):
                session.connect(driver, rec['connection'], request.token_sink,
                                request.check, request.deadline)
        finally:
            with manager.lock:
                session.users -= 1
                session.last_used = time.monotonic()

    try:
        session = status()
        pools = dict(session.http)
        assert status() is session
        record['http_pool_objects_reused'] = bool(pools) and all(
            session.http.get(k) is v for k, v in pools.items())
        connect(session)
        remote = session.remote
        connect(session)
        record['websocket_reused'] = session.remote is remote and len(handshakes) == 1
        assert record['websocket_reused']
        record['handshake_seconds'] = list(handshakes)
        save()
        idle_start = time.monotonic()
        while time.monotonic() - idle_start < tv_transport.IDLE_TTL + 5:
            with manager.lock:
                expired = target not in manager.sessions
            if expired:
                break
            time.sleep(.2)
        record['idle_expiry_seconds'] = round(time.monotonic() - idle_start, 4)
        record['idle_session_removed'] = expired
        # The reaper removes the entry under lock, then closes outside that lock.
        close_deadline = time.monotonic() + 2
        while time.monotonic() < close_deadline:
            if session.remote is None and (remote.s is None or remote.s.fileno() == -1):
                break
            time.sleep(.02)
        record['idle_socket_closed'] = session.remote is None and (
            remote.s is None or remote.s.fileno() == -1)
        assert record['idle_session_removed'] and record['idle_socket_closed']
        replacement = status()
        connect(replacement)
        record['reconnected_after_idle'] = replacement is not session and len(handshakes) == 2
        record['handshake_seconds'] = list(handshakes)
        assert record['reconnected_after_idle']
        manager.close()
        record['shutdown_closed_socket'] = replacement.remote is None
        record['passed'] = True
        save()
    except Exception as exc:
        record.update(passed=False, error_type=type(exc).__name__)
        save()
        raise SystemExit(1) from None
    finally:
        manager.close()


if __name__ == '__main__':
    main()
