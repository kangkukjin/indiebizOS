"""데스크톱 v2 접수 원장. 본문/결과는 RAM, 최소 상태만 디스크에 둔다."""
from contextlib import contextmanager
import contextvars
import hashlib
import json
import os
import sqlite3
import threading
import time
from pathlib import Path

import client_agent
import limb_keys

LOCK = threading.RLock()
LIVE = {}
LEASE_SECONDS = 90


@contextmanager
def _db():
    path = limb_keys._store_path().parent / 'member_requests.sqlite3'
    path.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=10)
    os.chmod(path, 0o600)
    db.execute('CREATE TABLE IF NOT EXISTS requests (device TEXT, request TEXT, task TEXT, digest TEXT, epoch TEXT, state TEXT, updated REAL, PRIMARY KEY(device,request))')
    try:
        yield db
        db.commit()
    finally:
        db.close()


def _set(device, request, state):
    with _db() as db:
        db.execute('UPDATE requests SET state=?,updated=? WHERE device=? AND request=?',
                   (state, time.time(), device, request))


def submit(rec, envelope, resolved):
    device, rid = rec['device_id'], envelope['request_id']
    # The same request remains identifiable across HTTP retries and body reconnects.
    digest = hashlib.sha256(json.dumps(envelope, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    key = (device, rid)
    with LOCK, _db() as db:
        old = db.execute('SELECT digest,epoch,state FROM requests WHERE device=? AND request=?', key).fetchone()
        if old:
            if old[0] != digest:
                return {'success': False, 'error': 'request_id_conflict'}
            return status(rec, rid)
        if len(LIVE) >= 512:
            return {'success': False, 'error': 'request_capacity'}
        db.execute('INSERT INTO requests VALUES(?,?,?,?,?,?,?)',
                   (device, rid, envelope['conversation_id'], digest, client_agent.EPOCH, 'accepted', time.time()))
        db.commit()  # Persist acceptance BEFORE any work can start.
        row = {'state': 'accepted', 'events': [], 'seq': 0, 'lease': time.monotonic(),
               'session': rec.get('session'), 'member': rec['member_id'], 'result': None}
        LIVE[key] = row
        ctx = contextvars.copy_context()
        threading.Thread(target=lambda: ctx.run(_run, rec, envelope, resolved, row), daemon=True).start()
        threading.Thread(target=_watch, args=(rec, rid, row), daemon=True).start()
        return {'success': True, 'version': 2, 'state': 'accepted', 'request_id': rid, 'lease_seconds': LEASE_SECONDS}


def _run(rec, envelope, resolved, row):
    def event(value):
        with LOCK:
            row['seq'] += 1
            row['events'].append({'seq': row['seq'], 'event': value})
            row['events'] = row['events'][-256:]
    with LOCK:
        if row['state'] == 'cancelled':
            return
        row['state'] = 'running'
        _set(rec['device_id'], envelope['request_id'], 'running')
    result = client_agent.run({**envelope, 'version': 1}, resolved,
                              name=rec.get('alias', ''), body_session=rec.get('session', ''), on_event=event)
    with LOCK:
        if row['state'] != 'cancelled':
            row['state'] = 'completed' if result.get('success') else 'failed'
        row['result'] = result
        row['finished'] = time.monotonic()
        _set(rec['device_id'], envelope['request_id'], row['state'])


def _watch(rec, rid, row):
    while True:
        time.sleep(2)
        with LOCK:
            if row['state'] not in ('accepted', 'running'):
                return
            current = limb_keys.validate(rec['key'])
            if (not current or current.get('session') != row['session']
                    or time.monotonic() - row['lease'] > LEASE_SECONDS):
                cancel(rec, rid)
                return


def status(rec, rid, after=0):
    key = (rec['device_id'], rid)
    with LOCK:
        for old_key, old in list(LIVE.items()):
            if old.get('finished') and time.monotonic() - old['finished'] > 1800:
                del LIVE[old_key]
        row = LIVE.get(key)
        if row:
            if row['session'] != rec.get('session') and row['state'] in ('accepted', 'running'):
                cancel(rec, rid)
            row['lease'] = time.monotonic()
            return {'success': True, 'version': 2, 'request_id': rid, 'state': row['state'],
                    'events': [e for e in row['events'] if e['seq'] > after],
                    'cursor': row['seq'], 'result': row['result'], 'epoch': client_agent.EPOCH}
        with _db() as db:
            old = db.execute('SELECT epoch,state FROM requests WHERE device=? AND request=?', key).fetchone()
        if not old:
            return {'success': False, 'error': 'request_not_found'}
        return {'success': True, 'version': 2, 'state': 'unknown', 'request_id': rid,
                'error': '결과 본문이 만료되었거나 서버가 재시작했습니다. 로컬 결과를 확인하세요. 자동 재실행하지 않습니다.'}


def cancel(rec, rid):
    with LOCK:
        row = LIVE.get((rec['device_id'], rid))
        if not row:
            return status(rec, rid)
        if row['state'] in ('accepted', 'running'):
            row['state'] = 'cancelled'
            row['finished'] = time.monotonic()
            _set(rec['device_id'], rid, 'cancelled')
            from member_session import MemberSessionManager
            manager = MemberSessionManager._instance
            if manager:
                manager.close(row['member'], rec['device_id'])
        return {'success': True, 'state': row['state']}
