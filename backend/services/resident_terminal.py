"""Owner terminal leases. Input is never replayed after a transport loss.

The durable resident job owns execution; this bounded in-memory bridge owns only
live keystrokes/output. A hub restart ends the session, never recreates its shell.
"""
import base64
import asyncio
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field

import resident_pcs
import resident_store

OUTPUT_LIMIT = 1024 * 1024
LEASE_SECONDS = 30
_lock = threading.RLock()
_sessions = {}


@dataclass
class Session:
    id: str
    device: str
    job: str = ''
    state: str = 'starting'
    reason: str = ''
    seen: float = field(default_factory=time.monotonic)
    output: bytearray = field(default_factory=bytearray)
    offset: int = 0
    messages: deque = field(default_factory=deque)
    input_bytes: int = 0
    sequence: int = 0
    attached: bool = False
    route: str = 'relay'
    waiters: dict = field(default_factory=dict)


def dimensions(cols, rows):
    if (type(cols) is not int or type(rows) is not int
            or not 2 <= cols <= 500 or not 2 <= rows <= 300):
        raise ValueError('invalid_terminal_size')
    return cols, rows


def create(target, sid, cols=100, rows=30, lan=None):
    dimensions(cols, rows)
    if not isinstance(sid, str) or not re.fullmatch(r'[0-9a-f]{32}', sid):
        raise ValueError('invalid_terminal_id')
    rec = resident_pcs.resolve(target)
    caps = rec['registration'].get('capabilities') or {}
    if not caps.get('terminal'):
        raise ValueError('이 PC는 헬퍼 교체 후 터미널을 사용할 수 있습니다.')
    if time.time() - (rec['registration'].get('last_seen') or 0) > 90:
        raise ValueError('PC가 오프라인입니다.')
    with _lock:
        for key, old in list(_sessions.items()):
            if time.monotonic() - old.seen > LEASE_SECONDS:
                _close(old, 'window_disconnected')
            if old.state == 'closed' and time.monotonic() - old.seen > 120:
                del _sessions[key]
        if sid in _sessions:
            s = _sessions[sid]
            if s.device != rec['device_id']:
                raise ValueError('terminal_id_conflict')
            return {'id': sid, 'job_id': s.job, 'state': s.state}
        if len(_sessions) >= 64 or sum(s.device == rec['device_id'] and s.state != 'closed'
                                       for s in _sessions.values()) >= 2:
            raise ValueError('열린 터미널을 닫은 뒤 다시 연결하세요.')
        s = Session(sid, rec['device_id'])
        _sessions[sid] = s
        try:
            receipt = resident_pcs.submit(s.device, {'op': 'terminal', 'terminal_id': sid,
                'cols': cols, 'rows': rows, 'lan': lan or {}, 'timeout': 86400}, 'terminal-' + sid,
                allow_terminal=True)
            s.job = receipt['job_id']
        except Exception:
            del _sessions[sid]
            raise
        return {'id': sid, 'job_id': s.job, 'state': s.state}


def _get(sid):
    s = _sessions.get(sid)
    if not s:
        raise ValueError('terminal_session_lost: 새 터미널을 연결하세요.')
    return s


def _close(s, reason):
    if s.state != 'closed':
        s.state, s.reason = 'closed', reason
        s.messages.clear()
        s.input_bytes = 0
        _notify(s, 'input')
        _notify(s, 'output')
        if s.job:
            resident_store.cancel(s.job, s.device)


def close(sid):
    with _lock:
        s = _get(sid)
        _close(s, 'window_closed')
        return {'state': s.state}


def poll(sid, cursor):
    with _lock:
        s = _get(sid)
        if type(cursor) is not int or cursor < 0 or cursor > s.offset + len(s.output):
            raise ValueError('invalid_terminal_cursor')
        if time.monotonic() - s.seen > LEASE_SECONDS:
            _close(s, 'window_disconnected')
        s.seen = time.monotonic()
        if s.state != 'closed':
            try:
                resident_pcs.resolve(s.device)
            except ValueError:
                _close(s, 'registration_closed')
            if s.state == 'starting':
                tasks = resident_store.history(job=s.job)['tasks']
                if tasks and tasks[0]['state'] in {'succeeded', 'failed', 'cancelled', 'unknown', 'expired'}:
                    _close(s, tasks[0]['state'])
        start = max(cursor, s.offset)
        data = bytes(s.output[start - s.offset:start - s.offset + 65536])
        return {'state': s.state, 'reason': s.reason, 'route': s.route, 'data': base64.b64encode(data).decode(),
                'cursor': start + len(data), 'gap': cursor < s.offset}


def input_message(sid, message):
    with _lock:
        s = _get(sid)
        resident_pcs.resolve(s.device)
        if s.state != 'running' or time.monotonic() - s.seen > LEASE_SECONDS:
            raise ValueError('terminal_not_connected')
        kind = message.get('type')
        if kind == 'input':
            data = message.get('data')
            if not isinstance(data, str) or len(data.encode()) > 16384:
                raise ValueError('terminal_input_too_large')
            seq = message.get('sequence')
            if type(seq) is not int or seq != s.sequence + 1:
                raise ValueError('terminal_input_sequence_mismatch')
            size = len(data.encode())
            if s.input_bytes + size > 65536 or len(s.messages) >= 128:
                raise ValueError('terminal_input_backpressure')
            s.sequence = seq
            s.input_bytes += size
            s.messages.append({'type': 'input', 'data': data})
        elif kind == 'resize':
            cols, rows = dimensions(message.get('cols'), message.get('rows'))
            if len(s.messages) >= 128:
                raise ValueError('terminal_input_backpressure')
            s.messages.append({'type': 'resize', 'cols': cols, 'rows': rows})
        else:
            raise ValueError('invalid_terminal_message')
        _notify(s, 'input')
        return {'accepted': True}


def attach(sid, device, route='relay'):
    with _lock:
        s = _get(sid)
        if s.device != device or s.attached or s.state != 'starting':
            raise ValueError('terminal_not_owned_or_already_attached')
        if time.monotonic() - s.seen > LEASE_SECONDS:
            _close(s, 'window_disconnected')
            raise ValueError('terminal_lease_expired')
        s.attached, s.state = True, 'running'
        s.route = route
        _notify(s, 'output')


def output(sid, data):
    with _lock:
        s = _get(sid)
        if s.state == 'closed':
            return
        s.output.extend(data)
        overflow = max(0, len(s.output) - OUTPUT_LIMIT)
        if overflow:
            del s.output[:overflow]
            s.offset += overflow
        _notify(s, 'output')


def take(sid):
    with _lock:
        s = _get(sid)
        if time.monotonic() - s.seen > LEASE_SECONDS:
            _close(s, 'window_disconnected')
        if s.state == 'closed':
            return [{'type': 'close'}]
        result = list(s.messages)
        s.messages.clear()
        s.input_bytes = 0
        return result


def detached(sid):
    with _lock:
        _close(_get(sid), 'terminal_disconnected')


def _notify(s, kind):
    waiter = s.waiters.get(kind)
    if waiter:
        loop, event = waiter
        if not loop.is_closed():
            loop.call_soon_threadsafe(event.set)


def watch(sid, kind, loop):
    """One helper and one owner, potentially on different event loops (LAN TLS)."""
    with _lock:
        s = _get(sid)
        if kind in s.waiters:
            raise ValueError('terminal_already_watched')
        event = asyncio.Event()
        s.waiters[kind] = (loop, event)
        return event


def unwatch(sid, kind):
    with _lock:
        _get(sid).waiters.pop(kind, None)
