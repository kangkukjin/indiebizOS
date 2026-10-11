"""TLS LAN listener: isolated surface, pinned certificate and device auth."""
import boot_paths
import hashlib
import ssl
import urllib.error
import urllib.request

import resident_terminal_lan as lan


def test_listener_tls_pin_and_surface(monkeypatch):
    import asyncio
    import websockets
    monkeypatch.setattr(lan, 'addresses', lambda: ['127.0.0.1'])
    monkeypatch.setattr(lan, '_retry_at', 0)
    calls = []

    async def handler(ws, sid):
        calls.append((sid, ws.scope.get('terminal_lan')))
        await ws.accept()
        await ws.send_json({'ok': True})
        await ws.close()

    try:
        offer = lan.offer(handler)
        assert len(offer['sha256']) == 64
        assert lan.offer(handler) == offer
        context = ssl._create_unverified_context()  # peer fingerprint verified below

        async def check():
            address = offer['urls'][0].replace('https:', 'wss:') + '/limb/resident/terminal/test'
            async with websockets.connect(address, ssl=context) as ws:
                cert = ws.transport.get_extra_info('ssl_object').getpeercert(binary_form=True)
                assert hashlib.sha256(cert).hexdigest() == offer['sha256']
                assert await ws.recv() == '{"ok":true}'
        asyncio.run(check())
        assert calls == [('test', True)]
        try:
            urllib.request.urlopen(offer['urls'][0] + '/remote-pcs', context=context)
        except urllib.error.HTTPError as exc:
            assert exc.code == 404
        else:
            raise AssertionError('owner APIs exposed on LAN listener')
    finally:
        lan.stop()


if __name__ == '__main__':
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
