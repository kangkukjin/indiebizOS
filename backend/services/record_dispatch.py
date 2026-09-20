"""영속 사건/타이머/outbox 소비. 만료된 원격 lease를 무조건 재발송하지 않는다."""
import json
import logging
import threading
import time

from common.record_contract import RecordError, dump, fail
from record_policy import delegated, roles, allowed
from record_store import transaction, root_path, meta, definition, get_record

_ADAPTERS = {}
_stop = threading.Event()
_thread = None


def register_adapter(name, send, *, lookup=None, idempotent=False):
    """호스트 코드가 감사한 어댑터만 등록한다. 앱 입력에서 import/코드 실행 금지."""
    _ADAPTERS[name] = {'send': send, 'lookup': lookup, 'idempotent': idempotent}


def tick(space, root=None):
    with transaction(space, root, write=True) as conn:
        if meta(conn, 'paused') or meta(conn, 'recovery_required'):
            return False
        now = time.time()
        row = conn.execute("SELECT * FROM deliveries WHERE (state='pending' AND due<=?) OR (state='leased' AND lease_until<=?) ORDER BY due LIMIT 1", (now, now)).fetchone()
        if not row:
            return False
        item = dict(row)
        item['payload'] = json.loads(item['body'])
        item['attempt'] += 1
        conn.execute("UPDATE deliveries SET state='leased',attempt=?,lease_until=? WHERE id=?", (item['attempt'], now + 60, item['id']))
    auth = delegated(item['subject'], space, item['payload'].get('command', ''))
    try:
        with transaction(space, root) as conn:
            member_roles = roles(conn, auth)
            if item['kind'] == 'effect' and item['payload'].get('origin_command'):
                active, _ = definition(conn)
                payload = item['payload']
                command = active['commands'].get(payload['origin_command'])
                if not command or payload['effect_name'] not in active.get('effects', {}):
                    fail('forbidden', '현재 업무 정의가 외부 처리를 중지했습니다.')
                env = dict(payload['authorization'])
                for alias, value in list(env.items()):
                    if isinstance(value, dict) and '_collection' in value and '_id' in value:
                        env[alias] = get_record(conn, value['_collection'], value['_id'])
                primary = next((env[k] for k in command.get('read', {}) if k in env), None)
                if not allowed(command['allow'], auth, member_roles, primary, env):
                    fail('forbidden', '외부 처리의 위임 권한이 회수되었습니다.')
        if item['kind'] == 'command':
            from record_commands import apply
            payload = item['payload']
            if payload.get('task_id'):
                with transaction(space, root) as conn:
                    task = conn.execute('SELECT state,target_revision FROM tasks WHERE id=?', (payload['task_id'],)).fetchone()
                    if not task or task['state'] != 'open' or task['target_revision'] != payload['target_revision']:
                        return finish(space, item, 'cancelled', {'reason': 'stale_task'}, root)
            result = apply(space, {'command': payload['command'], 'input': payload.get('input', {}),
                                  'expected': payload.get('expected', []), 'definition_revision': item['definition_revision'],
                                  'request_id': item['id'], 'reason': '저장된 후속 업무'}, auth, root,
                           task_guard=payload if payload.get('task_id') else None)
            state = 'succeeded'
        else:
            config = item['payload']['config']
            adapter = _ADAPTERS.get(config.get('adapter'))
            if adapter is None:
                return finish(space, item, 'blocked', {'reason': 'adapter_not_registered'}, root)
            result = None
            if item['state'] == 'leased':
                if adapter['lookup']:
                    result = adapter['lookup'](item['id'], config)
                if result is None and not adapter['idempotent']:
                    return finish(space, item, 'unknown', {'reason': 'delivery_outcome_unknown'}, root)
            if result is None:
                result = adapter['send'](item['payload']['payload'], item['id'], config)
            if not isinstance(result, dict) or result.get('status') not in {'succeeded', 'failed', 'unknown'}:
                result = {'status': 'unknown', 'reason': 'adapter_result_invalid'}
            state = result['status']
        return finish(space, item, state, result, root)
    except RecordError as exc:
        return finish(space, item, 'blocked', exc.result(), root)
    except Exception:
        logging.getLogger(__name__).exception('관리 기록 후속 처리 실패: %s', item['id'])
        return finish(space, item, 'unknown' if item['kind'] == 'effect' else 'pending', {'reason': 'worker_error'}, root)


def finish(space, item, state, result, root=None):
    with transaction(space, root, write=True) as conn:
        changed = conn.execute('UPDATE deliveries SET state=?,result=?,lease_until=0,due=? WHERE id=? AND state=? AND attempt=?',
                               (state, dump(result), time.time() + min(300, 2 ** min(item['attempt'], 8)), item['id'], 'leased', item['attempt'])).rowcount
        if changed and item['kind'] == 'effect' and state in {'succeeded', 'failed'}:
            from record_tasks import effect_followup
            effect_followup(conn, item['id'], item['payload'], result, item['subject'], item['definition_revision'], state)
    return bool(changed)


def _run():
    while not _stop.wait(2):
        try:
            from vocabulary_state import is_active
            if not is_active('record-ops'):
                continue
            for db in root_path().glob('*/records.db'):
                try:
                    tick(db.parent.name)
                except Exception:
                    logging.getLogger(__name__).exception('관리 기록 큐 확인 실패')
        except Exception:
            logging.getLogger(__name__).exception('관리 기록 워커 오류')


def start():
    global _thread
    if _thread is None or not _thread.is_alive():
        from record_adapters import register
        register()
        _stop.clear()
        _thread = threading.Thread(target=_run, name='record-dispatch', daemon=True)
        _thread.start()


def stop():
    _stop.set()
    if _thread:
        _thread.join(timeout=3)
