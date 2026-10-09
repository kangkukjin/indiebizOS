"""기기 작업 전달 원장. 접수·전달·결과를 재기동 너머 보존한다.

전달한 명령은 재전송하지 않는다: 응답 유실 때 실행 여부를 알 수 없으므로
상태를 unknown으로 관측하고 같은 job의 늦은 결과를 받아 확정한다.
"""
import json
import os
import sqlite3
import threading
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

JOB_TTL = 600.0             # 아직 전달하지 않은 명령의 유효기간
RESULT_TTL = 7 * 86400.0    # 완료/회수 기록 보존
_GENERATION = uuid.uuid4().hex
_WAKE = threading.Condition()


def _db_path():
    from runtime_utils import get_base_path
    root = os.environ.get("INDIEBIZ_RUNTIME_STATE_DIR")
    return (Path(root) if root else get_base_path() / "data") / "phone_jobs.db"


@contextmanager
def _db():
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=15)
    os.chmod(path, 0o600)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY, device TEXT NOT NULL, code TEXT NOT NULL,
            agent TEXT, created REAL NOT NULL, updated REAL NOT NULL,
            state TEXT NOT NULL, generation TEXT, deadline REAL,
            result TEXT, partial TEXT, consumed INTEGER NOT NULL DEFAULT 0)""")
        conn.execute("CREATE INDEX IF NOT EXISTS jobs_device_state ON jobs(device,state)")
        conn.execute("BEGIN IMMEDIATE")
        now = time.time()
        conn.execute("UPDATE jobs SET state='expired',updated=? WHERE state='queued' AND created<?",
                     (now, now - JOB_TTL))
        # 실행 중 소유 정보는 TTL로 버리지 않는다. 늦은 결과도 받아 확정한다.
        conn.execute("UPDATE jobs SET state='unknown',updated=? WHERE state='dispatched' AND deadline<?",
                     (now, now))
        conn.execute("DELETE FROM jobs WHERE state IN ('completed','cancelled','expired') AND updated<?",
                     (now - RESULT_TTL,))
        yield conn
        conn.commit()
    except BaseException:
        conn.rollback()
        raise
    finally:
        conn.close()


def _wake():
    with _WAKE:
        _WAKE.notify_all()


def _pause(seconds):
    # 짧은 상한은 다른 프로세스의 회신도 관측하게 한다. 정상 same-process는 즉시 깨어난다.
    with _WAKE:
        _WAKE.wait(min(0.25, max(0.0, seconds)))


def enqueue(device_id, code, agent_id=None):
    now = time.time()
    jid = uuid.uuid4().hex[:12]
    with _db() as conn:
        conn.execute("INSERT INTO jobs(id,device,code,agent,created,updated,state) VALUES(?,?,?,?,?,?,'queued')",
                     (jid, device_id, code, agent_id, now, now))
    _wake()
    return jid


def pull_blocking(device_id, wait=0.0, member_session=None):
    deadline = time.monotonic() + max(0.0, float(wait))
    while True:
        fresh = []
        with _db() as conn:
            for row in conn.execute("SELECT * FROM jobs WHERE device=? AND state='queued' ORDER BY created,id",
                                    (device_id,)).fetchall():
                try:
                    command = json.loads(row['code'])
                except (ValueError, TypeError):
                    command = {}
                if not isinstance(command, dict):
                    command = {}
                if member_session is not None and not (command.get('member') is True
                        and command.get('body_session') == member_session):
                    continue
                try:
                    timeout = max(120.0, float(command.get('timeout') or 1800))
                except (ValueError, TypeError):
                    timeout = 1800.0
                now = time.time()
                conn.execute("UPDATE jobs SET state='dispatched',generation=?,updated=?,deadline=? WHERE id=?",
                             (_GENERATION, now, now + timeout + 3600, row['id']))
                job = {'id': row['id'], 'code': row['code'], 'ts': row['created']}
                if row['agent']:
                    job['agent_id'] = row['agent']
                fresh.append(job)
        if fresh or time.monotonic() >= deadline:
            return fresh
        _pause(deadline - time.monotonic())


def owner_of(job_id):
    with _db() as conn:
        row = conn.execute("SELECT device FROM jobs WHERE id=?", (job_id,)).fetchone()
        return row['device'] if row else None


def set_result(job_id, result):
    """재전송된 결과는 최초 확정 내용을 보존한다. 임의 job 생성은 하지 않는다."""
    with _db() as conn:
        conn.execute("""UPDATE jobs SET result=?,state='completed',partial=NULL,updated=?
                        WHERE id=? AND state IN ('queued','dispatched','unknown')""",
                     (json.dumps(result, ensure_ascii=False), time.time(), job_id))
    _wake()


def set_partial(job_id, partial):
    with _db() as conn:
        conn.execute("""UPDATE jobs SET partial=?,state='dispatched',generation=?,updated=?
                        WHERE id=? AND state IN ('queued','dispatched','unknown')""",
                     (json.dumps(partial, ensure_ascii=False), _GENERATION, time.time(), job_id))
    _wake()


def get_partial(job_id):
    with _db() as conn:
        row = conn.execute("SELECT partial FROM jobs WHERE id=?", (job_id,)).fetchone()
        return json.loads(row['partial']) if row and row['partial'] else None


def job_status(job_id):
    with _db() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            return {'state': 'unknown', 'reason': 'unknown_job'}
        state = row['state']
        if state == 'dispatched' and row['generation'] != _GENERATION:
            state = 'unknown'
        return {'state': state, 'reason': 'delivery_unconfirmed' if state == 'unknown' else state,
                'consumed': bool(row['consumed']), 'updated': row['updated']}


def peek_result(job_id):
    with _db() as conn:
        row = conn.execute("SELECT result,consumed,state FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row or row['state'] != 'completed':
            return None
        return {'consumed': True} if row['consumed'] else {'result': json.loads(row['result'])}


def wait_result(job_id, timeout=20.0):
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        with _db() as conn:
            row = conn.execute("SELECT state,result,consumed FROM jobs WHERE id=?", (job_id,)).fetchone()
            if row and row['state'] == 'completed':
                if row['consumed']:
                    return None
                conn.execute("UPDATE jobs SET consumed=1 WHERE id=?", (job_id,))
                return json.loads(row['result'])
            if not row or row['state'] in ('cancelled', 'expired'):
                return None
        if time.monotonic() >= deadline:
            return None
        _pause(deadline - time.monotonic())


def cancel_pending(job_id):
    with _db() as conn:
        changed = conn.execute("UPDATE jobs SET state='cancelled',updated=? WHERE id=? AND state='queued'",
                               (time.time(), job_id)).rowcount
    _wake()
    return bool(changed)
