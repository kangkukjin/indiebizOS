"""TLS LAN listener: isolated surface, pinned certificate and device auth."""
import boot_paths
import hashlib
import ssl
import urllib.error
import urllib.request
import socket
from types import SimpleNamespace

import resident_terminal_lan as lan


def test_listener_tls_pin_and_surface(monkeypatch):
    import asyncio
    import websockets
    monkeypatch.setattr(lan, 'address_candidates', lambda: [
        {'address': '127.0.0.1', 'interface': 'bridge0', 'kind': 'thunderbolt'}])
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
        assert offer['preferred_urls'] == offer['urls']
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


def test_candidates_include_link_local_and_prioritize_hardware_not_ip(monkeypatch):
    import psutil
    monkeypatch.setattr(lan, 'thunderbolt_interfaces', lambda: {'bridge0'})
    monkeypatch.setattr(psutil, 'net_if_stats', lambda: {
        name: SimpleNamespace(isup=name != 'down') for name in ['bridge0', 'en0', 'other', 'down']})

    def addr(ip):
        return SimpleNamespace(family=socket.AF_INET, address=ip)

    monkeypatch.setattr(psutil, 'net_if_addrs', lambda: {
        'en0': [addr('192.168.0.10'), addr('8.8.8.8'), addr('127.0.0.1')],
        'other': [addr('169.254.1.2')] + [addr(f'10.0.0.{i}') for i in range(1, 12)],
        'bridge0': [addr('169.254.254.233'), addr('192.168.99.1')],
        'down': [addr('192.168.2.1')],
    })
    candidates = lan.address_candidates()
    assert len(candidates) == 8
    assert [c['address'] for c in candidates[:2]] == ['169.254.254.233', '192.168.99.1']
    assert all(c['kind'] == 'thunderbolt' for c in candidates[:2])
    assert all(c['kind'] == 'lan' for c in candidates[2:])
    # A link-local address on another adapter remains ordinary LAN.
    monkeypatch.setattr(psutil, 'net_if_addrs', lambda: {'other': [addr('169.254.1.2')]})
    assert lan.address_candidates() == [
        {'address': '169.254.1.2', 'interface': 'other', 'kind': 'lan'}]


def test_thunderbolt_hardware_lookup_is_bounded_and_cached(monkeypatch):
    monkeypatch.setattr(lan.sys, 'platform', 'darwin')
    monkeypatch.setattr(lan, '_thunderbolt_cache', (0, frozenset()))
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs['timeout']))
        return SimpleNamespace(stdout='Hardware Port: Ethernet\nDevice: en0\n\n'
                               'Hardware Port: Thunderbolt Bridge\nDevice: bridge0\n\n'
                               'Hardware Port: Thunderbolt 1\nDevice: en2\n')

    monkeypatch.setattr(lan.subprocess, 'run', run)
    assert lan.thunderbolt_interfaces() == {'bridge0', 'en2'}
    assert lan.thunderbolt_interfaces() == {'bridge0', 'en2'}
    assert len(calls) == 1 and calls[0][1] == 2
    monkeypatch.setattr(lan.sys, 'platform', 'linux')
    assert not lan.thunderbolt_interfaces()


def test_connection_network_reports_reached_interface(monkeypatch):
    candidates = [{'address': '169.254.2.1', 'interface': 'bridge0', 'kind': 'thunderbolt'},
                  {'address': '192.168.0.1', 'interface': 'en0', 'kind': 'lan'}]
    monkeypatch.setattr(lan, 'address_candidates', lambda: candidates)
    ws = SimpleNamespace(scope={'terminal_lan': True, 'server': ('192.168.0.1', 1234)})
    assert lan.connection_network(ws) == candidates[1]
    ws.scope['server'] = ('169.254.2.1', 1234)
    assert lan.connection_network(ws) == candidates[0]
    ws.scope.pop('terminal_lan')
    assert lan.connection_network(ws) == {}


if __name__ == '__main__':
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
