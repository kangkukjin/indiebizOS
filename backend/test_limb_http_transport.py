import boot_paths  # noqa: F401
import threading
from types import SimpleNamespace

import pytest
from limb_http_transport import LimbHttpTransport
from limb_client import LimbError


def test_connections_reused_per_thread_closed_without_post_retry(monkeypatch):
    import requests
    sessions = []
    replies = []

    class Session:
        def __init__(self):
            sessions.append(self)
            self.calls = []
            self.closed = False

        def post(self, url, **kwargs):
            self.calls.append((url, kwargs))
            reply = SimpleNamespace(status_code=200, json=lambda: {'ack': ['x']}, closed=False)
            reply.close = lambda: setattr(reply, 'closed', True)
            replies.append(reply)
            return reply

        def close(self):
            self.closed = True

    monkeypatch.setattr(requests, 'Session', Session)
    transport = LimbHttpTransport('https://hub/')
    transport('sync', {}, 20)
    transport('events', {}, 15)
    assert len(sessions) == 1 and len(sessions[0].calls) == 2
    def child():
        transport('events', {}, 15)
        transport.close()
    thread = threading.Thread(target=child)
    thread.start(); thread.join(2)
    assert len(sessions) == 2 and sessions[1].closed and not sessions[0].closed
    assert all(r.closed for r in replies)
    sessions[0].post = lambda *a, **k: (_ for _ in ()).throw(requests.ConnectionError('lost response'))
    with pytest.raises(requests.ConnectionError):
        transport('events', {}, 15)
    transport.close()
    assert sessions[0].closed


def test_http_error_still_releases_response(monkeypatch):
    import requests
    closed = []
    response = SimpleNamespace(status_code=403, json=lambda: {'detail': 'invalid_registration'},
                               close=lambda: closed.append(True))
    monkeypatch.setattr(requests, 'Session', lambda: SimpleNamespace(post=lambda *a, **k: response))
    with pytest.raises(LimbError, match='invalid_registration'):
        LimbHttpTransport('https://hub')('events', {}, 15)
    assert closed == [True]
if __name__ == '__main__':
    import pytest
    raise SystemExit(pytest.main([__file__]))
