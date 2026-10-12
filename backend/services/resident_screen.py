"""Ephemeral screen sessions. No images, keystrokes or credentials enter job history."""
import math
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field

import resident_pcs
import resident_store

_lock = threading.RLock()
_sessions = {}
LEASE = 20
MAX_FRAME = 4 * 1024 * 1024


@dataclass
class Session:
    id: str
    device: str
    job: str = ''
    state: str = 'starting'
    reason: str = ''
    seen: float = field(default_factory=time.monotonic)
    frame: bytes = b''
    serial: int = 0
    inputs: deque = field(default_factory=deque)
    input_bytes: int = 0
    helper: bool = False
    owner: bool = False
    waiters: dict = field(default_factory=dict)


def create(target, sid, lan=None):
    if not isinstance(sid, str) or not re.fullmatch(r'[a-f0-9]{32}', sid):
        raise ValueError('invalid_screen_id')
    rec = resident_pcs.resolve(target)
    if not (rec['registration'].get('capabilities') or {}).get('desktop_stream'):
        raise ValueError('이 PC의 헬퍼를 교체한 뒤 화면 공유를 다시 여세요.')
    if time.time() - (rec['registration'].get('last_seen') or 0) > 90:
        raise ValueError('원격 PC가 오프라인입니다.')
    with _lock:
        for key, old in list(_sessions.items()):
            if time.monotonic() - old.seen > LEASE:
                _close(old, '화면 공유 연결이 종료됐습니다.')
                del _sessions[key]
        if sid in _sessions:
            raise ValueError('screen_id_conflict')
        if len(_sessions) >= 32 or any(s.device == rec['device_id'] and s.state != 'closed' for s in _sessions.values()):
            raise ValueError('이 PC에 열린 화면 공유 창을 먼저 닫으세요.')
        s = Session(sid, rec['device_id'])
        _sessions[sid] = s
        try:
            receipt = resident_pcs.submit(s.device, {'op': 'desktop', 'screen_id': sid,
                'lan': lan or {}, 'timeout': 86400}, 'desktop-' + sid, allow_desktop=True)
            s.job = receipt['job_id']
        except Exception:
            del _sessions[sid]
            raise
        return {'id': sid}


def _get(sid):
    if sid not in _sessions:
        raise ValueError('화면 공유를 다시 열어 주세요.')
    return _sessions[sid]


def _notify(s, side):
    waiter = s.waiters.get(side)
    if waiter:
        loop, event = waiter
        try:
            loop.call_soon_threadsafe(event.set)
        except RuntimeError:
            pass


def watch(sid, side, loop, event):
    with _lock:
        s = _get(sid)
        if side in s.waiters:
            raise ValueError('screen_already_attached')
        s.waiters[side] = (loop, event)


def unwatch(sid, side):
    with _lock:
        if sid in _sessions:
            _sessions[sid].waiters.pop(side, None)


def attach(sid, device=None):
    with _lock:
        s = _get(sid)
        resident_pcs.resolve(s.device)
        if s.state == 'closed' or time.monotonic() - s.seen > LEASE:
            raise ValueError('screen_session_expired')
        if device is None:
            if s.owner:
                raise ValueError('screen_owner_already_attached')
            s.owner = True
        else:
            if s.device != device or s.helper:
                raise ValueError('screen_device_mismatch')
            s.helper = True


def _close(s, reason):
    if s.state != 'closed':
        s.state, s.reason = 'closed', reason
        s.frame = b''
        s.inputs.clear()
        s.input_bytes = 0
        for side in ('owner', 'helper'):
            _notify(s, side)
        if s.job:
            resident_store.cancel(s.job, s.device)


def close(sid, reason='화면 공유가 종료됐습니다.'):
    with _lock:
        if sid in _sessions:
            _close(_sessions[sid], reason)


def status(sid, touch=False):
    with _lock:
        s = _get(sid)
        resident_pcs.resolve(s.device)
        if time.monotonic() - s.seen > LEASE:
            _close(s, '화면 공유 연결이 끊겼습니다.')
        if touch:
            s.seen = time.monotonic()
        if s.state == 'starting':
            tasks = resident_store.history(job=s.job)['tasks']
            if tasks and tasks[0]['state'] in {'failed', 'cancelled', 'unknown', 'expired', 'succeeded'}:
                _close(s, '원격 PC의 화면 접근 권한을 확인한 뒤 다시 연결하세요.')
        return {'type': 'status', 'state': s.state, 'message': s.reason}


def put_frame(sid, data):
    if not 4 <= len(data) <= MAX_FRAME or not data.startswith(b'\xff\xd8'):
        raise ValueError('invalid_screen_frame')
    with _lock:
        s = _get(sid)
        if s.state != 'closed':
            s.frame, s.serial, s.state = data, s.serial + 1, 'running'
            _notify(s, 'owner')


def frame(sid, serial):
    with _lock:
        s = _get(sid)
        return (s.serial, s.frame) if s.serial != serial else (serial, b'')


def validate_input(value):
    if not isinstance(value, dict):
        raise ValueError('invalid_screen_input')
    kind = value.get('type')
    if kind == 'reset':
        return {'type': kind}
    if kind in {'pointer', 'wheel'}:
        x, y = value.get('x'), value.get('y')
        if any(type(v) not in (int, float) or not math.isfinite(v) or not 0 <= v <= 1 for v in (x, y)):
            raise ValueError('invalid_screen_coordinates')
        out = {'type': kind, 'x': x, 'y': y}
        if kind == 'pointer':
            mask = value.get('buttons')
            if type(mask) is not int or not 0 <= mask <= 7:
                raise ValueError('invalid_screen_buttons')
            out['buttons'] = mask
        else:
            for key in ('dx', 'dy'):
                v = value.get(key, 0)
                if type(v) not in (int, float) or not math.isfinite(v) or abs(v) > 2000:
                    raise ValueError('invalid_screen_scroll')
                out[key] = v
        return out
    if kind == 'key':
        code, key, down = value.get('code'), value.get('key'), value.get('down')
        if not isinstance(code, str) or not re.fullmatch(r'[A-Za-z0-9]{1,32}', code) or type(down) is not bool:
            raise ValueError('invalid_screen_key')
        if not isinstance(key, str) or len(key) > 40:
            raise ValueError('invalid_screen_key')
        return {'type': kind, 'code': code, 'key': key, 'down': down}
    if kind == 'text' and isinstance(value.get('text'), str) and len(value['text'].encode()) <= 16384:
        return {'type': kind, 'text': value['text']}
    raise ValueError('invalid_screen_input')


def input_message(sid, value):
    message = validate_input(value)
    with _lock:
        s = _get(sid)
        resident_pcs.resolve(s.device)
        if s.state != 'running':
            raise ValueError('screen_not_running')
        # Coalesce only consecutive unbuttoned moves. Press/release/key order is never dropped.
        if message['type'] == 'pointer' and message['buttons'] == 0 and s.inputs and s.inputs[-1].get('type') == 'pointer' and s.inputs[-1].get('buttons') == 0:
            s.input_bytes += len(str(message).encode()) - len(str(s.inputs[-1]).encode())
            s.inputs[-1] = message
        else:
            size = len(str(message).encode())
            if len(s.inputs) >= 256 or s.input_bytes + size > 65536:
                raise ValueError('screen_input_backpressure')
            s.inputs.append(message)
            s.input_bytes += size
        _notify(s, 'helper')


def take(sid):
    with _lock:
        s = _get(sid)
        if time.monotonic() - s.seen > LEASE or s.state == 'closed':
            return [{'type': 'close'}]
        messages = list(s.inputs)
        s.inputs.clear()
        s.input_bytes = 0
        return messages
