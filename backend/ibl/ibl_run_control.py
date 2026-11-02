"""Scoped next-invocation argument steering, persisted in the existing run journal.

Only statically known adapter calls are exposed. Writes retain their resource
footprint and durable receipt; parallel steering is restricted to read-only plans.
Running calls, ambiguous repeated parallel sites and dynamic definitions are not replaced.
"""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from common.expression_eval import Binding
from ibl_v2_ir import digest

KIND = 'ibl_run'
SAFE = {'pure', 'read_external'}
SUPPORTED = SAFE | {'write_external'}


def register():
    import task_receipts
    from ibl_continuations import task_status, task_cancel
    task_receipts.register(KIND, task_status, task_cancel, steer_fn=steer)


def publish(journal, plan, project_path):
    from ibl_v2_repair_graph import walk
    from ibl_run_journal import receipt_access_scope
    from thread_context import get_current_task_id
    from task_receipts import ref
    register()
    targets = {}
    nodes = list(walk([plan.root, plan.functions]))
    parallel = any(n.kind == 'parallel' for n in nodes)
    each = any(n.kind == 'each' or (n.kind == 'call' and
               (n.data.get('node'), n.data.get('action')) == ('table', 'each')) for n in nodes)
    # Shared function/lambda bodies have no deterministic global invocation
    # order across branches. Their route needs a separate addressable contract.
    shared = {n.id for n in walk(plan.functions)}
    for n in nodes:
        if n.kind in {'def', 'lambda'}:
            shared.update(child.id for child in walk(n))
    for node in nodes:
        key = f"{node.data.get('node')}:{node.data.get('action')}"
        spec = plan.registry.get(key)
        if (node.kind != 'call' or not spec or spec.dependency or spec.stateful
                or node.data.get('target') or spec.specialize):
            continue
        contract = spec.contract
        effects = set(contract['effects'])
        variants = contract.get('variants', [])
        if not effects <= SUPPORTED or any(
                set(v.get('effects', contract['effects'])) != effects for v in variants):
            continue
        if each or (parallel and (not plan.effects <= SAFE or node.id in shared)):
            continue
        if 'write_external' in effects and not contract.get('write_resources'):
            continue
        targets[node.id] = {'action': key, 'revision': digest(contract), 'contract': contract,
                            'effects': sorted(effects),
                            'resource_policy': 'unchanged' if 'write_external' in effects else 'read_only'}
    metadata = {'root_task': get_current_task_id() or '', 'plan_hash': plan.fingerprint,
                'access_scope': receipt_access_scope(), 'targets': targets,
                'task_ref': ref(KIND, journal.run_id, str(Path(project_path).resolve()))}
    journal.db.executescript('CREATE TABLE IF NOT EXISTS control_meta(data TEXT);'
                            'CREATE TABLE IF NOT EXISTS control_requests('
                            'request_id TEXT PRIMARY KEY,payload TEXT,state TEXT,reason TEXT);'
                            'CREATE TABLE IF NOT EXISTS control_boundaries(node_id TEXT PRIMARY KEY,ordinal INTEGER);'
                            'CREATE TABLE IF NOT EXISTS control_invocations('
                            'node_id TEXT,ordinal INTEGER,call_id TEXT,PRIMARY KEY(node_id,ordinal));')
    previous = journal.db.execute('SELECT data FROM control_meta').fetchone()
    if previous:
        old = json.loads(previous[0])
        metadata['root_task'] = old['root_task']
        if old['plan_hash'] != plan.fingerprint:
            # Definition repair is owned by the existing stopped-run repair path.
            journal.db.execute("UPDATE control_requests SET state='not_applied',reason='definition changed' WHERE state='accepted'")
    journal.db.execute('DELETE FROM control_meta')
    journal.db.execute('INSERT INTO control_meta VALUES(?)', (json.dumps(metadata),))
    journal.db.execute('DELETE FROM control_boundaries')
    journal.db.commit()
    journal.control = metadata
    journal.control_counts = {}
    return metadata['task_ref']


class UnsupportedControl(ValueError):
    pass


@contextmanager
def connection(ref, write=False):
    from ibl_run_journal import journal_root, receipt_access_scope
    import re
    if ref.get('kind') != KIND or not re.fullmatch('[0-9a-f]{32}', str(ref.get('task_id', ''))):
        raise ValueError('올바른 IBL 실행 참조가 필요합니다')
    owner = ref.get('owner')
    if not isinstance(owner, str) or not Path(owner).is_absolute():
        raise ValueError('실행 참조의 프로젝트 소유 범위가 없습니다')
    path = journal_root(owner) / (ref['task_id'] + '.sqlite')
    if path.is_symlink() or not path.is_file():
        raise ValueError('이 문맥의 실행 기록이 없습니다')
    with sqlite3.connect(path.as_uri() + ('?mode=rw' if write else '?mode=ro'), uri=True, timeout=10) as db:
        db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
        if not db.execute("SELECT 1 FROM sqlite_master WHERE name='control_meta'").fetchone():
            raise UnsupportedControl('이 실행은 부분 조향을 지원하지 않습니다')
        meta = json.loads(db.execute('SELECT data FROM control_meta').fetchone()[0])
        if meta['task_ref'] != ref or meta['access_scope'] != receipt_access_scope():
            raise ValueError('실행의 소유·접근 범위가 다릅니다')
        yield db, meta, path


def status(ref):
    from ibl_continuations import task_status
    return task_status(ref)


def enrich(ref, base):
    """Extend the existing continuation projection; keep its result/wait contract."""
    from ibl_run_journal import inspect_run, journal_root
    from task_receipts import view
    try:
        with connection(ref) as (db, meta, path):
            counts = dict(db.execute('SELECT node_id,ordinal FROM control_boundaries'))
            requests = []
            linked = db.execute("SELECT 1 FROM sqlite_master WHERE name='control_invocations'").fetchone()
            for rid, state, reason, payload in db.execute(
                    'SELECT request_id,state,reason,payload FROM control_requests ORDER BY rowid'):
                item = {'request_id': rid, 'state': state, 'reason': reason}
                request = json.loads(payload)
                row = invocation(db, request['node_id'], request['ordinal']) if linked else None
                if row:
                    receipt = json.loads(row[1]) if row[1] else None
                    item.update(call_ref={'run_id': ref['task_id'], 'call_id': row[0]},
                                effect_state=('not_started' if receipt and receipt.get('suspended') else
                                              'returned' if receipt and 'value' in receipt else 'unknown'))
                elif state == 'applied' and set(meta['targets'].get(request['node_id'], {}).get('effects', [])) - {'pure'}:
                    item['effect_state'] = 'not_started'
                requests.append(item)
    except UnsupportedControl:
        return base
    except (ValueError, sqlite3.Error) as exc:
        return view(ref, 'unknown', error=str(exc))
    observed = inspect_run(journal_root(ref['owner']), ref['task_id'])
    if observed.get('locked'):
        state = 'cancel_requested' if path.with_suffix('.cancel').exists() else 'running'
        base = view(ref, state, accepted_at=observed.get('created_at'))
    targets = [{k: v for k, v in spec.items() if k != 'contract'} |
               {'node_id': node, 'next_ordinal': counts.get(node, 0) + 1}
               for node, spec in meta['targets'].items()] if base['state'] == 'running' else []
    base['progress'] = {**(base.get('progress') or {}), 'root_task': meta['root_task'],
                        'plan_hash': meta['plan_hash'], 'boundaries': targets, 'requests': requests}
    return base


def steer(ref, message, request_id):
    if not isinstance(request_id, str) or not request_id.strip():
        raise ValueError('request_id가 필요합니다')
    try:
        payload = json.loads(message) if isinstance(message, str) else message
        fields = {'root_task', 'plan_hash', 'node_id', 'revision', 'ordinal', 'expected_args_hash', 'changes'}
        if (not isinstance(payload, dict) or set(payload) != fields or not isinstance(payload['changes'], dict)
                or not payload['changes'] or type(payload['ordinal']) is not int or payload['ordinal'] < 1):
            raise ValueError('지원 범위는 아직 시작하지 않은 호출의 다음 경계 인자 변경입니다')
        encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, allow_nan=False)
        with connection(ref, True) as (db, meta, path):
            previous = db.execute('SELECT payload,state,reason FROM control_requests WHERE request_id=?', (request_id,)).fetchone()
            if previous:
                if previous[0] != encoded:
                    raise ValueError('같은 request_id로 다른 변경을 보낼 수 없습니다')
                return {'success': True, 'accepted': True, 'delivery': previous[1], 'reason': previous[2], 'task_ref': ref}
            target = meta['targets'].get(payload['node_id'])
            if (payload['root_task'] != meta['root_task'] or payload['plan_hash'] != meta['plan_hash']
                    or not target or payload['revision'] != target['revision']):
                raise ValueError('대상·정의 판본이 다르거나 지원하지 않는 경계입니다')
            if set(payload['changes']) - target['contract']['params'].keys():
                raise ValueError('계약에 없는 변경 인자입니다')
            linked = db.execute("SELECT 1 FROM sqlite_master WHERE name='control_invocations'").fetchone()
            if linked and invocation(db, payload['node_id'], payload['ordinal']):
                raise ValueError('이미 시작한 호출은 영수증 재사용만 가능하며 다시 조향할 수 없습니다')
            current = db.execute('SELECT ordinal FROM control_boundaries WHERE node_id=?', (payload['node_id'],)).fetchone()
            if payload['ordinal'] != (current[0] if current else 0) + 1:
                raise ValueError('이미 시작한 호출 또는 다음 경계가 아닌 호출은 변경할 수 없습니다')
            if db.execute('SELECT status FROM lifecycle').fetchone()[0] != 'running' or path.with_suffix('.cancel').exists():
                raise ValueError('종료·취소 중인 실행은 변경할 수 없습니다')
            db.execute("INSERT INTO control_requests VALUES(?,?,'accepted',NULL)", (request_id, encoded))
        return {'success': True, 'accepted': True, 'delivery': 'accepted', 'task_ref': ref}
    except (TypeError, KeyError, json.JSONDecodeError) as exc:
        raise ValueError('부분 조향 요청 형식이 올바르지 않습니다') from exc


def invocation(db, node_id, ordinal):
    """An existing effect marker is authoritative even without a return receipt."""
    return db.execute('SELECT c.id,c.receipt FROM control_invocations i JOIN calls c ON c.id=i.call_id '
                      'WHERE i.node_id=? AND i.ordinal=?', (node_id, ordinal)).fetchone()


def same_resources(spec, before_contract, before, after_contract, after):
    from ibl_run_journal import call_resources
    for mode in ('read', 'write'):
        if mode == 'read' and not (before_contract.get('read_resources') or after_contract.get('read_resources')
                                   or 'read_external' in before_contract['effects']):
            continue
        old = call_resources(spec, before_contract, before, mode, allow_bare=spec.resource_identity is None)
        new = call_resources(spec, after_contract, after, mode, allow_bare=spec.resource_identity is None)
        if old is None or new is None or digest(old) != digest(new):
            raise ValueError('write_resource_changed_or_unknown')


def bind_invocation(runtime, node, call_id):
    """Link the steering coordinate to the existing durable effect owner."""
    coordinate = getattr(runtime.local, 'control_boundary', None)
    if not runtime.journal or not coordinate or coordinate[0] != node.id:
        return
    with runtime.journal.lock:
        db = runtime.journal.db
        old = db.execute('SELECT call_id FROM control_invocations WHERE node_id=? AND ordinal=?', coordinate).fetchone()
        if old and old[0] != call_id:
            from ibl_v2_ir import Fault
            raise Fault('CONTROL_COORDINATE_CHANGED', '부분 개입의 호출 좌표가 달라졌습니다. 효과를 시작하지 않습니다.', kind='protocol')
        db.execute('INSERT OR IGNORE INTO control_invocations VALUES(?,?,?)', (*coordinate, call_id))
        db.commit()


def boundary(runtime, node, args, spec):
    journal = runtime.journal
    runtime.local.control_boundary = None
    if not journal or not getattr(journal, 'control', None) or node.id not in journal.control['targets']:
        return args
    from ibl_callable_contract import checked_values
    with journal.lock:
        ordinal = journal.control_counts.get(node.id, 0) + 1
        journal.control_counts[node.id] = ordinal
        runtime.local.control_boundary = (node.id, ordinal)
        # Serialize acceptance and application across processes, including cancel.
        db = journal.db
        db.execute('BEGIN IMMEDIATE')
        try:
            db.execute('INSERT OR REPLACE INTO control_boundaries VALUES(?,?)', (node.id, ordinal))
            rows = db.execute("SELECT request_id,payload,state FROM control_requests WHERE state IN ('accepted','applied') ORDER BY rowid").fetchall()
            for rid, encoded, state in rows:
                request = json.loads(encoded)
                if request['node_id'] != node.id or request['ordinal'] != ordinal:
                    continue
                reason = None
                if (journal.root / (journal.run_id + '.cancel')).exists() or (runtime.cancel_check and runtime.cancel_check()):
                    reason = 'cancelled_before_boundary'
                elif request['plan_hash'] != runtime.plan.fingerprint or request['revision'] != digest(spec.contract):
                    reason = 'definition_revision_mismatch'
                elif state == 'accepted' and invocation(db, node.id, ordinal):
                    reason = 'already_started'
                elif request['expected_args_hash'] != digest(args.value):
                    reason = 'input_revision_mismatch'
                else:
                    try:
                        effective, values = checked_values(spec.contract, {**args.value, **request['changes']})
                        from ibl_callable_contract import selected
                        original = selected(spec.contract, args.value)
                        if set(effective['effects']) != set(original['effects']):
                            raise ValueError('effect_contract_changed')
                        if 'write_external' in effective['effects']:
                            same_resources(spec, original, args.value, effective, values)
                    except (ValueError, TypeError) as exc:
                        reason = str(exc)
                if reason:
                    db.execute("UPDATE control_requests SET state='not_applied',reason=? WHERE request_id=?", (reason, rid))
                    continue
                eid = runtime.event(node, 'steer_applied', args.evidence, request_id=rid,
                                    root_task=journal.control['root_task'], ordinal=ordinal,
                                    old_args_hash=digest(args.value), new_args_hash=digest(values))
                parts = {k: Binding(v, frozenset({eid})) if k in request['changes'] else
                         args.select(k) if k in args.value else Binding(v) for k, v in values.items()}
                args = Binding.record(parts).controlled(args.control | {eid})
                db.execute("UPDATE control_requests SET state='applied',reason=NULL WHERE request_id=?", (rid,))
            db.commit()
        except BaseException:
            db.rollback()
            raise
    return args


def cancel(ref):
    from ibl_continuations import task_cancel
    return task_cancel(ref)


def mark_cancel(ref):
    """Use the continuation owner's cancel/wakeup markers under acceptance lock."""
    try:
        with connection(ref, True) as (db, meta, path):
            path.with_suffix('.cancel').touch(mode=0o600)
            path.with_suffix('.wake').touch(mode=0o600)
            db.execute("UPDATE control_requests SET state='not_applied',reason='cancelled' WHERE state='accepted'")
    except UnsupportedControl:
        return False
    return True


def finish(journal, result):
    if not getattr(journal, 'control', None):
        return
    with journal.lock:
        journal.db.execute("UPDATE control_requests SET state='not_applied',reason='boundary_not_reached' WHERE state='accepted'")
        journal.db.commit()
    result['task_ref'] = journal.control['task_ref']
