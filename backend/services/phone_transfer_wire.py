"""Phone consumer of the same durable binary protocol as the PC helper."""
import base64
import hashlib
import ipaddress
import json
import ssl
import struct
import time
from urllib.parse import urlsplit


class PhoneTransferWire:
    def __init__(self, client, tid, check):
        self.client, self.tid, self.check = client, tid, check
        self.socket = None
        self.offer = None
        self.route = 'json'

    def close(self):
        if self.socket:
            self.socket.close()
            self.socket = None

    def _open(self):
        import websocket
        root = self.client.cfg['hub'].rstrip('/')
        parsed = urlsplit(root)
        if parsed.scheme != 'https' and not (parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1')):
            raise ValueError('HTTPS_required')
        offer = self.offer or {}
        lan = offer.get('lan') or {}
        candidates = []
        fingerprint = lan.get('sha256', '')
        if len(fingerprint) == 64:
            for base in (lan.get('urls') or [])[:8]:
                url = urlsplit(base)
                try:
                    ip = ipaddress.ip_address(url.hostname)
                except ValueError:
                    continue
                if (url.scheme == 'https' and ip.version == 4 and (ip.is_private or ip.is_loopback)
                        and not url.username and not url.query and not url.fragment and not url.path):
                    candidates.append((base, True))
        candidates.append((root, False))
        last = None
        for base, direct in candidates:
            self.check()
            try:
                url = base.replace('https://', 'wss://', 1).replace('http://', 'ws://', 1)
                options = {'sslopt': {'cert_reqs': ssl.CERT_NONE, 'check_hostname': False}} if direct else {}
                ws = websocket.create_connection(url + '/limb/resident/transfer/' + self.tid,
                                                  timeout=min(1 if direct else 10, self.check()), **options)
                self.socket = ws
                if direct:
                    actual = hashlib.sha256(ws.sock.getpeercert(binary_form=True)).hexdigest()
                    if actual != fingerprint:
                        raise ValueError('LAN_certificate_mismatch')
                ws.send(json.dumps(self.client._auth()))
                ready = json.loads(ws.recv())
                if ready.get('error'):
                    raise ValueError(ready['error'])
                if ready.get('type') != 'ready' or ready.get('version') != 1:
                    raise ValueError('invalid_transfer_handshake')
                self.route = ready.get('route', 'public')
                return
            except (OSError, websocket.WebSocketException, ValueError) as exc:
                last = exc
                self.close()
                if not direct:
                    raise
        raise last or OSError('transfer_connection_failed')

    def request(self, action, **values):
        if self.offer is None:
            values['binary_version'] = 1
        if not self.offer:
            if isinstance(values.get('data'), bytes):
                values['data'] = base64.b64encode(values['data']).decode('ascii')
            row = self.client._post('transfers/' + self.tid,
                                    {**self.client._auth(), 'action': action, **values}, min(30, self.check()))
            if self.offer is None:
                offer = row.get('binary') or {}
                self.offer = offer if offer.get('version') == 1 else {}
            return row
        import websocket
        for attempt in range(5):
            self.check()
            try:
                if not self.socket:
                    try:
                        self._open()
                    except (OSError, websocket.WebSocketException):
                        self.close()
                        self.check()
                        self.offer = {}
                        self.route = 'https-fallback'
                        return self.request(action, **values)
                self.socket.settimeout(min(30, self.check()))
                if action == 'write':
                    data = values['data']
                    if isinstance(data, str):
                        data = base64.b64decode(data, validate=True)
                    self.socket.send_binary(struct.pack('!Q', values['offset']) + data)
                else:
                    self.socket.send(json.dumps({'action': action, **values}))
                raw = self.socket.recv()
                if isinstance(raw, bytes):
                    if action != 'read' or len(raw) < 8 or struct.unpack('!Q', raw[:8])[0] != values['offset']:
                        raise ValueError('invalid_transfer_offset')
                    return {'data': raw[8:], 'offset': values['offset'] + len(raw) - 8}
                row = json.loads(raw)
                if row.get('error'):
                    raise ValueError(row['error'])
                return row
            except (OSError, websocket.WebSocketException):
                self.close()
                if attempt == 4:
                    raise
                self.offer['lan'] = {}
                time.sleep(min(.2 * 2 ** attempt, self.check()))
