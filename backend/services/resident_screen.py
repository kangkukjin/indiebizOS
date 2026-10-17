"""Ephemeral screen sessions. No images, keystrokes or credentials enter job history.

임대·멱등 종료는 session_lease(프로필 "screen", 수치는 data/session_lease_policy.yaml)가 맡는다 — 2026-10-13
미디어 세션과 같은 수명 논리를 쓰고 모듈 상수를 두지 않는다.
"""
import math
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field

import resident_pcs
import resident_store
import session_lease

_lock = threading.RLock()
_sessions = {}
MAX_FRAME = 4 * 1024 * 1024


@dataclass
class Session:
    id: str
    device: str
    job: str = ''
    state: str = 'starting'
    reason: str = ''
    lease: session_lease.Lease = field(default_factory=lambda: session_lease.Lease('screen'))
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
        raise ValueError('폰 앱을 업데이트한 뒤 화면 공유를 다시 여세요.' if rec['registration'].get('kind') == 'phone' else '이 PC의 헬퍼를 교체한 뒤 화면 공유를 다시 여세요.')
    if time.time() - (rec['registration'].get('last_seen') or 0) > 90:
        raise ValueError('원격 기기가 오프라인입니다.')
    with _lock:
        session_lease.sweep(_sessions, lambda old: _close(old, '화면 공유 연결이 종료됐습니다.'), profile_name='screen')
        if sid in _sessions:
            raise ValueError('screen_id_conflict')
        live = [s for s in _sessions.values() if s.state != 'closed']
        if len(live) >= 32 or any(s.device == rec['device_id'] for s in live):
            raise ValueError('이 기기에 열린 화면 공유 창을 먼저 닫으세요.')
        s = Session(sid, rec['device_id'])
        _sessions[sid] = s
        try:
            receipt = resident_pcs.submit(s.device, {'op': 'desktop', 'screen_id': sid,
                'lan': lan or {}, 'timeout': 86400}, 'desktop-' + sid, allow_desktop=True)
            s.job = receipt['job_id']
        except Exception:
            del _sessions[sid]
            raise
        return {'id': sid, 'device_kind': rec['registration'].get('kind', 'pc')}


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
        if s.state == 'closed' or s.lease.expired():
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
    if s.lease.close(reason):
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
        if s.lease.expired():
            _close(s, '화면 공유 연결이 끊겼습니다.')
        if touch:
            s.lease.renew()
        if s.state == 'starting':
            tasks = resident_store.history(job=s.job)['tasks']
            if tasks and tasks[0]['state'] in {'failed', 'cancelled', 'unknown', 'expired', 'succeeded'}:
                _close(s, '원격 기기의 화면 접근 권한을 확인한 뒤 다시 연결하세요.')
        return {'type': 'status', 'state': s.state, 'message': s.reason}


PHONE_STATUS = {
    'permission': '폰에서 IndieBiz 앱이나 화면 공유 알림을 열고 화면 전체 공유를 승인하세요.',
    'accessibility': '폰 설정 → 접근성 → 설치된 서비스에서 IndieBiz를 켠 뒤 다시 연결하세요.',
    'denied': '폰에서 화면 공유가 거절되거나 종료됐습니다.',
    'capture_failed': '폰 화면을 가져올 수 없습니다. 잠금과 화면 공유 권한을 확인하세요.',
    'input_failed': '폰 조작에 실패했습니다. 접근성 권한과 현재 입력창을 확인하세요.',
}


def device_status(sid, value):
    """Only fixed phone diagnostics cross the stream; never arbitrary device text."""
    code = value.get('code') if isinstance(value, dict) else None
    if code not in PHONE_STATUS:
        raise ValueError('invalid_screen_status')
    with _lock:
        s = _get(sid)
        if s.state == 'closed':
            return
        if code in {'accessibility', 'denied', 'capture_failed', 'input_failed'}:
            _close(s, PHONE_STATUS[code])
        else:
            s.reason = PHONE_STATUS[code]
            _notify(s, 'owner')


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
    if kind == 'navigation' and value.get('action') in {'back', 'home', 'recents'}:
        return {'type': kind, 'action': value['action']}
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
        if s.lease.expired() or s.state == 'closed':
            return [{'type': 'close'}]
        messages = list(s.inputs)
        s.inputs.clear()
        s.input_bytes = 0
        return messages
