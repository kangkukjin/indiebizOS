"""Local execution liveness, separate from model output and business progress.

A random per-turn channel connects both CLI adapters to their MCP waiter. Only
an existing channel can be updated; tool arguments cannot choose a file path.
"""
import json
import os
import re
import time
import uuid

LEASE_TTL_S = 45
TRANSPORT_LOSS_S = 120
from common.completion_contract import MCP_CLIENT_TIMEOUT_S, process_identity, owner_alive


def _directory(token):
    if not isinstance(token, str) or not re.fullmatch(r'[a-f0-9]{32}', token):
        return None
    from runtime_utils import get_base_path
    return get_base_path() / 'data' / 'completion_wait' / token


def _write(path, value):
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        tmp.write_text(json.dumps(value), encoding='utf-8')
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def _read(path):
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
        return value if isinstance(value, dict) else None
    except (OSError, ValueError):
        return None


def create_channel():
    token = uuid.uuid4().hex
    directory = _directory(token)
    directory.mkdir(parents=True, mode=0o700)
    # Closed channels carry cooperative cancellation until their workers observe it.
    # Only our own expired runtime records are collected; live turns are retained.
    import shutil
    for old in directory.parent.iterdir():
        try:
            if (old.is_dir() and time.time() - old.stat().st_mtime > 86400 and
                    ((old / 'cancelled').exists() or
                     owner_alive(_read(old / 'owner.json')) is False)):
                shutil.rmtree(old)
        except OSError:
            pass
    _write(directory / 'owner.json', process_identity())
    return token


def cancel_channel(token):
    directory = _directory(token)
    if directory and directory.is_dir():
        (directory / 'cancelled').touch()


def channel_cancelled(token):
    directory = _directory(token)
    if not directory:
        return False  # external MCP users have no local channel
    return (directory / 'cancelled').exists() or owner_alive(_read(directory / 'owner.json')) is False


def pulse(token, ticket, active=True):
    directory = _directory(token)
    if not directory or not directory.is_dir() or not re.fullmatch(r'[a-f0-9]{8,32}', ticket):
        return
    _write(directory / (ticket + '.json'),
           {'active': active, 'at': time.monotonic(), 'waiter': process_identity()})


def is_waiting(token):
    directory = _directory(token)
    if not directory or not directory.is_dir():
        return False
    now = time.monotonic()
    for path in directory.glob('*.json'):
        if path.name == 'owner.json':
            continue
        rec = _read(path) or {}
        if (rec.get('active') and isinstance(rec.get('at'), (int, float))
                and 0 <= now - rec['at'] < LEASE_TTL_S
                and owner_alive(rec.get('waiter')) is True):
            return True
    return False


def pending_tickets(token):
    directory = _directory(token)
    if not directory or not directory.is_dir():
        return []
    return [path.stem for path in directory.glob('*.json')
            if re.fullmatch(r'[a-f0-9]{8,32}', path.stem)
            and (_read(path) or {}).get('active') is not False]


def channel_from_context(ctx):
    try:
        request = ctx.request_context.request if ctx is not None else None
        if request is not None:
            return request.headers.get('x-indiebiz-completion-channel', '')
    except (AttributeError, LookupError):
        pass
    return os.environ.get('INDIEBIZOS_COMPLETION_CHANNEL', '')
