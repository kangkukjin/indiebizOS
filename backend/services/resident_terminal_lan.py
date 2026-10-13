"""Optional LAN terminal listener. Only the device-authenticated terminal route.

The normal authenticated job delivers the ephemeral TLS certificate fingerprint.
No discovery broadcast, plaintext credentials, owner APIs, or public port mapping.
"""
import atexit
import datetime
import hashlib
import ipaddress
import logging
import socket
import tempfile
import threading
import time
from pathlib import Path

_lock = threading.Lock()
_server = None
_port = 0
_fingerprint = ''
_retry_at = 0
_handlers = {}


def addresses():
    import psutil
    nets = [ipaddress.ip_network(n) for n in ('10.0.0.0/8', '172.16.0.0/12', '192.168.0.0/16')]
    stats = psutil.net_if_stats()
    return sorted({a.address for name, rows in psutil.net_if_addrs().items()
                   if name in stats and stats[name].isup
                   for a in rows if a.family == socket.AF_INET
                   and any(ipaddress.ip_address(a.address) in n for n in nets)})[:8]


def _start(handler, channel="terminal"):
    _handlers[channel] = handler
    import uvicorn
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    from starlette.applications import Starlette
    from starlette.routing import WebSocketRoute
    from runtime_work import service_scope

    async def endpoint(ws):
        ws.scope['terminal_lan'] = True
        selected = _handlers.get(ws.path_params.get('channel', 'terminal'))
        if selected is None:
            await ws.close(code=1008)
            return
        await selected(ws, ws.path_params['sid'])

    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'IndieBiz terminal')])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(minutes=1))
            .not_valid_after(now + datetime.timedelta(days=30)).sign(key, hashes.SHA256()))
    fingerprint = hashlib.sha256(cert.public_bytes(serialization.Encoding.DER)).hexdigest()
    app = Starlette(routes=[WebSocketRoute('/limb/resident/{channel}/{sid}', endpoint)])
    # Uvicorn loads the private key into its SSLContext before the temp files vanish.
    with tempfile.TemporaryDirectory(prefix='indiebiz-terminal-tls-') as root:
        cert_path, key_path = Path(root) / 'cert.pem', Path(root) / 'key.pem'
        key_path.touch(mode=0o600)
        key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
                            serialization.PrivateFormat.PKCS8, serialization.NoEncryption()))
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        config = uvicorn.Config(app, log_level='error', access_log=False, lifespan='off',
                                ssl_certfile=str(cert_path), ssl_keyfile=str(key_path),
                                ws_max_size=4 * 1024 * 1024, ws_max_queue=16)
        config.load()
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        listener.bind(('0.0.0.0', 0))
        server = uvicorn.Server(config)
        with service_scope():
            threading.Thread(target=server.run, kwargs={'sockets': [listener]},
                             daemon=True, name='resident-terminal-lan').start()
        until = time.monotonic() + 2
        while not server.started and time.monotonic() < until:
            time.sleep(.01)
        if not server.started:
            server.should_exit = True
            raise RuntimeError('LAN listener startup timeout')
        return server, listener.getsockname()[1], fingerprint
    except Exception:
        listener.close()
        raise


def offer(handler, channel='terminal'):
    global _server, _port, _fingerprint, _retry_at
    if channel not in {'terminal', 'screen', 'media'}:
        raise ValueError('invalid_stream_channel')
    with _lock:
        _handlers[channel] = handler
        try:
            hosts = addresses()
            if not hosts or time.monotonic() < _retry_at:
                return {}
            if _server is None or _server.should_exit:
                _server, _port, _fingerprint = _start(handler, channel)
            return {'urls': [f'https://{host}:{_port}' for host in hosts],
                    'sha256': _fingerprint}
        except Exception as exc:
            # LAN is an optimization. Existing public TLS transport still works.
            _retry_at = time.monotonic() + 60
            logging.getLogger(__name__).warning('Terminal LAN unavailable: %s', type(exc).__name__)
            return {}


def stop():
    global _server
    with _lock:
        if _server:
            _server.should_exit = True
            _server = None


atexit.register(stop)
