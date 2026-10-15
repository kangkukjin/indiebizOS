"""설치 회원의 일시 실행 전달. 본문은 RAM에만 두고 재시작 시 재전달하지 않는다."""
import copy
import json
import threading
import time
import uuid

_CONDITION = threading.Condition(threading.RLock())
_JOBS = {}


def _sweep():
    now = time.monotonic()
    for key, row in list(_JOBS.items()):
        if now - row['created'] > 1800:
            del _JOBS[key]


def enqueue(device, code, agent_id=None):
    command = json.loads(code)
    size = len(code.encode())
    if size > 4 * 1024 * 1024:
        raise ValueError('member_command_too_large')
    with _CONDITION:
        _sweep()
        if len(_JOBS) >= 2048 or sum(r['bytes'] for r in _JOBS.values()) + size > 64 * 1024 * 1024:
            raise ValueError('member_delivery_capacity')
        key = 'md-' + uuid.uuid4().hex
        _JOBS[key] = {'device': device, 'code': code, 'session': command.get('body_session'),
                      'state': 'queued', 'result': None, 'created': time.monotonic(), 'bytes': size}
        _CONDITION.notify_all()
        return key


def pull_blocking(device, wait=0, member_session=None):
    deadline = time.monotonic() + wait
    with _CONDITION:
        while True:
            _sweep()
            jobs = []
            for key, row in _JOBS.items():
                if row['device'] == device and row['state'] == 'queued' and row['session'] == member_session:
                    jobs.append({'id': key, 'code': row['code']})
                    row['state'] = 'dispatched'
            if jobs or time.monotonic() >= deadline:
                return jobs
            _CONDITION.wait(min(.5, deadline - time.monotonic()))


def owner_of(key):
    with _CONDITION:
        _sweep()
        return (_JOBS.get(key) or {}).get('device')


def set_result(key, result):
    with _CONDITION:
        row = _JOBS.get(key)
        if row and row['state'] in ('queued', 'dispatched'):
            size = len(json.dumps(result).encode())
            if size > 4 * 1024 * 1024:
                result = {'success': False, 'error': 'member_result_too_large'}
                size = 0
            row.update(state='completed', result=copy.deepcopy(result), code='', bytes=size)
        _CONDITION.notify_all()


def set_partial(key, partial):
    # Progress belongs to the local task ledger; the model receives final output.
    return None


def wait_result(key, timeout=20):
    deadline = time.monotonic() + timeout
    with _CONDITION:
        while True:
            row = _JOBS.get(key)
            if not row or row['state'] in ('consumed', 'cancelled'):
                return None
            if row['state'] == 'completed':
                result = row['result']
                row.update(state='consumed', result=None, code='', bytes=0)
                return result
            if time.monotonic() >= deadline:
                return None
            _CONDITION.wait(min(.5, deadline - time.monotonic()))


def cancel_pending(key):
    with _CONDITION:
        row = _JOBS.get(key)
        if row and row['state'] == 'queued':
            row.update(state='cancelled', code='', bytes=0)
            _CONDITION.notify_all()
            return True
        return False
