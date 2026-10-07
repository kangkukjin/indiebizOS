"""Task-completion wakeups over the existing journal, independent of HTTP leases.

Only a persisted owner invocation can run unattended. Approval suspensions never
wake automatically; all other principals retain explicit, authenticated resume.
"""
import json
import sqlite3
import threading
from pathlib import Path
import runtime_work

_stop = threading.Event()
_worker = None


def remember(journal, request, project_path, agent_id, input_evidence=None):
    import principal
    from thread_context import get_allowed_nodes, get_task_origin, get_current_task_id, snapshot
    from ibl_v2_ir import pack
    journal.db.execute('CREATE TABLE IF NOT EXISTS continuation(request TEXT, result TEXT)')
    if not journal.resuming:
        payload = {'request': pack({k: v for k, v in request.items() if k not in ('approval', 'resume')}),
                   'project_path': str(Path(project_path).resolve()), 'agent_id': agent_id,
                   'allowed': sorted(get_allowed_nodes()) if get_allowed_nodes() is not None else None,
                   'origin': get_task_origin(), 'task_id': get_current_task_id(),
                   'input_evidence': input_evidence,
                   'context': {k: v for k, v in snapshot().items() if k in (
                       'project_id', 'agent_name', 'call_channel', 'delegation_chain')},
                   'automatic': principal.current() == principal.OWNER}
        journal.db.execute('INSERT INTO continuation(request,result) VALUES(?,NULL)', (json.dumps(payload),))
        journal.db.commit()


def finished(journal, result, project_path):
    from ibl_v2_ir import projection
    import task_receipts as T
    result['task_ref'] = T.ref('ibl_run', journal.run_id, str(Path(project_path).resolve()))
    journal.db.execute('UPDATE continuation SET result=?', (json.dumps(projection(result), ensure_ascii=False),))
    journal.db.commit()
    wake = journal.root / (journal.run_id + '.wake')
    if result.get('suspended') and (result.get('diagnostic') or {}).get('code') == 'TASK_PENDING':
        wake.touch(mode=0o600)
    else:
        wake.unlink(missing_ok=True)


def _read(path):
    if path.is_symlink() or not path.is_file():
        return None
    try:
        with sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=1) as db:
            row = db.execute('SELECT request,result FROM continuation').fetchone()
            if not row or not row[1]:
                return None
            saved, result = json.loads(row[0]), json.loads(row[1])
            times = db.execute('SELECT created,ended FROM lifecycle').fetchone()
            result['_run_times'] = times
            return saved, result
    except (sqlite3.Error, ValueError):
        return None


def task_status(ref):
    import task_receipts as T
    from ibl_run_journal import journal_root
    import re
    if not re.fullmatch('[0-9a-f]{32}', str(ref.get('task_id', ''))):
        return T.view(ref, T.UNKNOWN)
    path = journal_root(ref.get('owner') or '.') / (ref['task_id'] + '.sqlite')
    row = _read(path.absolute())
    if not row:
        return T.view(ref, T.UNKNOWN)
    result = row[1]
    state = T.SUCCEEDED if result.get('success') else T.WAITING_CHILDREN if result.get('suspended') else T.FAILED
    if (result.get('diagnostic') or {}).get('kind') == 'cancelled':
        state = T.CANCELLED
    elif state not in T.TERMINAL and path.with_suffix('.cancel').exists():
        state = T.CANCEL_REQUESTED
    return T.view(ref, state, result=result.get('value'), error=None if result.get('success') else result.get('error'),
                  accepted_at=(result.get('_run_times') or [None, None])[0],
                  ended_at=(result.get('_run_times') or [None, None])[1] if state in T.TERMINAL else None,
                  progress={'resume': result.get('resume'), 'waiting': result.get('waiting')})


def task_cancel(ref):
    import task_receipts as T
    from ibl_run_journal import journal_root
    current = task_status(ref)
    if current['state'] in T.TERMINAL or current['state'] == T.UNKNOWN:
        return current
    path = journal_root(ref.get('owner') or '.') / (ref['task_id'] + '.cancel')
    path.touch(mode=0o600)
    # A suspended owner wait is picked up by the same worker, even if its child
    # remains live. Child cancellation has its own explicit task contract.
    path.with_suffix('.wake').touch(mode=0o600)
    return task_status(ref)


@runtime_work.tracked('ibl-continuation', defer=True)
def sweep():
    """Bounded scan of durable waits; journal file locks arbitrate manual resumes."""
    import task_receipts as T
    import principal
    from ibl_run_journal import runs_root, journal_root
    from ibl_v2_ir import unpack
    from thread_context import snapshot, restore, set_allowed_nodes, actor_context
    from ibl_v2_entry import handle_request
    for wake in runs_root().glob('*/*.wake'):
        path = wake.with_suffix('.sqlite')
        row = _read(path.absolute())
        if not row:
            continue
        saved, result = row
        if not saved.get('automatic') or not result.get('suspended'):
            continue
        diagnostic = result.get('diagnostic') or {}
        cancelled = path.with_suffix('.cancel').is_file()
        if diagnostic.get('code') != 'TASK_PENDING' and not cancelled:
            continue
        ref = (result.get('waiting') or {}).get('task_ref')
        if not cancelled and (not ref or T.status(ref)['state'] not in T.TERMINAL | {T.UNKNOWN}):
            continue
        before = snapshot()
        try:
            restore({**before, **saved.get('context', {})})
            with principal.narrow(principal.OWNER), actor_context(agent_id=saved['agent_id'],
                    task_id=saved.get('task_id'), origin=saved.get('origin')):
                set_allowed_nodes(set(saved['allowed']) if saved['allowed'] is not None else None)
                if path.parent != journal_root(saved['project_path']):
                    continue
                request = unpack(saved['request'])
                resumed = handle_request({**request, 'resume': {'run_id': path.stem}}, saved['project_path'], saved['agent_id'],
                                         input_evidence=saved.get('input_evidence'))
                if resumed.get('executed') is False and (resumed.get('diagnostic') or {}).get('code') != 'RESUME_BUSY':
                    # Preserve the rejection (changed definition/authority) as
                    # the observable outcome, rather than a permanent wait.
                    from filelock import FileLock, Timeout
                    try:
                        with FileLock(str(path) + '.lock', timeout=0):
                            with sqlite3.connect(path, timeout=10) as db:
                                db.execute('UPDATE continuation SET result=?', (json.dumps(resumed),))
                            wake.unlink(missing_ok=True)
                    except Timeout:
                        pass
        finally:
            restore(before)


def start():
    global _worker
    import task_receipts as T
    T.register('ibl_run', task_status, task_cancel)
    if _worker and _worker.is_alive():
        return
    _stop.clear()
    def loop():
        while not _stop.wait(2):
            try:
                sweep()
            except Exception as exc:
                import logging
                logging.getLogger(__name__).warning('IBL continuation wakeup: %s', exc)
    _worker = threading.Thread(target=loop, name='ibl-continuations', daemon=True)
    _worker.start()


def stop():
    _stop.set()
