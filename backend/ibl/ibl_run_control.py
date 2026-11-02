"""Scoped next-invocation argument steering, persisted in the existing run journal.

Only statically known adapter calls are exposed. Writes retain their resource
footprint and durable receipt; parallel steering retains admitted branch resources.
Repeated sites are addressed within a live execution scope.
Stopped-run repair replays applied arguments through existing durable call IDs.
Running calls and dynamic definitions are not replaced.
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
    writes = 'write_external' in plan.effects
    scoped = each or (parallel and (bool(shared) or writes))
    unknown_write = any('write_external' in spec.contract['effects'] and not spec.contract.get('write_resources')
                        for n in nodes if n.kind == 'call'
                        if (spec := plan.registry.get(f"{n.data.get('node')}:{n.data.get('action')}")))
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
        if (each or parallel) and (not plan.effects <= SUPPORTED or (writes and unknown_write)):
            continue
        if 'write_external' in effects and not contract.get('write_resources'):
            continue
        targets[node.id] = {'action': key, 'revision': digest(contract), 'contract': contract,
                            'effects': sorted(effects), 'addressing': 'scope' if scoped else 'node',
                            'resource_policy': 'unchanged' if 'write_external' in effects else
                                               'admitted' if writes and (each or parallel) else 'read_only'}
    metadata = {'scoped': scoped, 'root_task': get_current_task_id() or '', 'plan_hash': plan.fingerprint,
                'access_scope': receipt_access_scope(), 'targets': targets,
                'task_ref': ref(KIND, journal.run_id, str(Path(project_path).resolve()))}
    journal.db.executescript('CREATE TABLE IF NOT EXISTS control_meta(data TEXT);'
                            'CREATE TABLE IF NOT EXISTS control_requests('
                            'request_id TEXT PRIMARY KEY,payload TEXT,state TEXT,reason TEXT);'
                            'CREATE TABLE IF NOT EXISTS control_boundaries(node_id TEXT PRIMARY KEY,ordinal INTEGER);'
                            'CREATE TABLE IF NOT EXISTS control_invocations('
                            'node_id TEXT,ordinal INTEGER,call_id TEXT,PRIMARY KEY(node_id,ordinal));'
                            'CREATE TABLE IF NOT EXISTS control_scopes('
                            'scope_id TEXT PRIMARY KEY,route TEXT,targets TEXT,active INTEGER);'
                            'CREATE TABLE IF NOT EXISTS control_scope_boundaries('
                            'scope_id TEXT,node_id TEXT,ordinal INTEGER,PRIMARY KEY(scope_id,node_id));'
                            'CREATE TABLE IF NOT EXISTS control_scope_invocations('
                            'scope_id TEXT,node_id TEXT,ordinal INTEGER,call_id TEXT,PRIMARY KEY(scope_id,node_id,ordinal));')
    previous = journal.db.execute('SELECT data FROM control_meta').fetchone()
    if previous:
        old = json.loads(previous[0])
        metadata['root_task'] = old['root_task']
        if old['plan_hash'] == plan.fingerprint:
            # Previously addressable sites keep their wire coordinate on resume.
            # New scoped sites must not orphan an already applied legacy request.
            for node_id, target in targets.items():
                if node_id in old['targets']:
                    target['addressing'] = old['targets'][node_id].get('addressing', 'node')
        if old['plan_hash'] != plan.fingerprint:
            # Definition repair is owned by the existing stopped-run repair path.
            journal.db.execute("UPDATE control_requests SET state='not_applied',reason='definition changed' WHERE state='accepted'")
    metadata['scoped'] = any(t['addressing'] == 'scope' for t in targets.values())
    journal.db.execute('DELETE FROM control_meta')
    journal.db.execute('INSERT INTO control_meta VALUES(?)', (json.dumps(metadata),))
    journal.db.execute('DELETE FROM control_boundaries')
    journal.db.execute('DELETE FROM control_scope_boundaries')
    journal.db.execute('UPDATE control_scopes SET active=0')
    journal.db.commit()
    journal.control = metadata
    journal.control_counts = {}
    journal.control_scope_nodes = {}
    journal.control_replay = {}
    if journal.node_map:
        for rid, payload, call_id, action in repair_applications(journal.db, different_plan=plan.fingerprint):
            journal.control_replay.setdefault(call_id, []).append((rid, json.loads(payload), action))
    return metadata['task_ref']


class UnsupportedControl(ValueError):
    pass


def scope_nodes(value):
    """Calls in this frame only; child frames own their own live coordinates."""
    from ibl_v2_ir import Node
    if isinstance(value, Node):
        if value.kind in {'def', 'lambda', 'parallel'}:
            return
        yield value
        for key, child in value.data.items():
            if (key == 'body' and value.kind == 'call'
                    and (value.data.get('node'), value.data.get('action')) == ('table', 'each')):
                continue
            yield from scope_nodes(child)
    elif isinstance(value, dict):
        for child in value.values():
            yield from scope_nodes(child)
    elif isinstance(value, (tuple, list)):
        for child in value:
            yield from scope_nodes(child)


@contextmanager
def scope(runtime, body):
    """A live frame is an address, never a new task/effect owner or permission."""
    journal = runtime.journal
    if not journal or not getattr(journal, 'control', {}).get('scoped'):
        yield
        return
    with journal.lock:
        cache = getattr(journal, 'control_scope_nodes', None)
        if cache is None:
            journal.control_scope_nodes = cache = {}
        if body.id not in cache:
            cache[body.id] = sorted({n.id for n in scope_nodes(body)
                                    if journal.control['targets'].get(n.id, {}).get('addressing') == 'scope'})
        targets = cache[body.id]
    previous = getattr(runtime.local, 'control_scope', None)
    runtime.local.control_scope = None
    scope_id = None
    try:
        if targets:
            route = getattr(runtime.local, 'route', ())
            entry = runtime.ordinal('control_scope:' + body.id)
            context = {'route': route, 'body_id': body.id, 'entry_ordinal': entry}
            scope_id = digest(context)
            with journal.lock:
                journal.db.execute('INSERT OR REPLACE INTO control_scopes VALUES(?,?,?,1)',
                                   (scope_id, json.dumps(context), json.dumps(targets)))
                journal.db.commit()
            runtime.local.control_scope = (scope_id, targets)
        yield
    finally:
        runtime.local.control_scope = previous
        if scope_id:
            with journal.lock:
                db = journal.db
                db.execute('BEGIN IMMEDIATE')
                try:
                    db.execute('UPDATE control_scopes SET active=0 WHERE scope_id=?', (scope_id,))
                    for rid, payload in db.execute("SELECT request_id,payload FROM control_requests WHERE state='accepted'").fetchall():
                        if json.loads(payload).get('scope') == scope_id:
                            db.execute("UPDATE control_requests SET state='not_applied',reason='scope_closed' WHERE request_id=?", (rid,))
                    db.commit()
                except BaseException:
                    db.rollback()
                    raise


def boundary_count(db, node_id, scope_id=None):
    if scope_id is not None:
        return db.execute('SELECT ordinal FROM control_scope_boundaries WHERE scope_id=? AND node_id=?',
                          (scope_id, node_id)).fetchone()
    return db.execute('SELECT ordinal FROM control_boundaries WHERE node_id=?', (node_id,)).fetchone()


def boundaries(db, meta):
    def target(node_id, scope_id=None, context=None):
        spec = {k: v for k, v in meta['targets'][node_id].items() if k != 'contract'}
        current = boundary_count(db, node_id, scope_id)
        spec.update(node_id=node_id, next_ordinal=(current[0] if current else 0) + 1)
        if scope_id is not None:
            spec.update(scope=scope_id, scope_context=context)
        return spec
    result = [target(n) for n, spec in meta['targets'].items() if spec.get('addressing') != 'scope']
    if meta.get('scoped'):
        for scope_id, context, targets in db.execute('SELECT scope_id,route,targets FROM control_scopes WHERE active=1 ORDER BY scope_id'):
            result.extend(target(n, scope_id, json.loads(context)) for n in json.loads(targets) if n in meta['targets'])
    return result


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
            targets = boundaries(db, meta)
            requests = []
            linked = db.execute("SELECT 1 FROM sqlite_master WHERE name='control_invocations'").fetchone()
            for rid, state, reason, payload in db.execute(
                    'SELECT request_id,state,reason,payload FROM control_requests ORDER BY rowid'):
                item = {'request_id': rid, 'state': state, 'reason': reason}
                request = json.loads(payload)
                row = invocation(db, request['node_id'], request['ordinal'], request.get('scope')) if linked else None
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
    if base['state'] != 'running':
        targets = []
    base['progress'] = {**(base.get('progress') or {}), 'root_task': meta['root_task'],
                        'plan_hash': meta['plan_hash'], 'boundaries': targets, 'requests': requests}
    return base


def steer(ref, message, request_id):
    if not isinstance(request_id, str) or not request_id.strip():
        raise ValueError('request_id가 필요합니다')
    try:
        payload = json.loads(message) if isinstance(message, str) else message
        fields = {'root_task', 'plan_hash', 'node_id', 'revision', 'ordinal', 'expected_args_hash', 'changes'}
        if (not isinstance(payload, dict) or set(payload) not in (fields, fields | {'scope'}) or not isinstance(payload['changes'], dict)
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
            scope_id = payload.get('scope')
            if target.get('addressing') == 'scope':
                if not isinstance(scope_id, str):
                    raise ValueError('반복·공유 호출은 status의 실행 scope가 필요합니다')
                active = db.execute('SELECT targets FROM control_scopes WHERE scope_id=? AND active=1', (scope_id,)).fetchone()
                if not active or payload['node_id'] not in json.loads(active[0]):
                    raise ValueError('종료됐거나 대상이 다른 실행 scope입니다')
            elif 'scope' in payload:
                raise ValueError('이 호출은 실행 scope 주소를 지원하지 않습니다')
            if set(payload['changes']) - target['contract']['params'].keys():
                raise ValueError('계약에 없는 변경 인자입니다')
            linked = db.execute("SELECT 1 FROM sqlite_master WHERE name='control_invocations'").fetchone()
            if linked and invocation(db, payload['node_id'], payload['ordinal'], scope_id):
                raise ValueError('이미 시작한 호출은 영수증 재사용만 가능하며 다시 조향할 수 없습니다')
            current = boundary_count(db, payload['node_id'], scope_id)
            if payload['ordinal'] != (current[0] if current else 0) + 1:
                raise ValueError('이미 시작한 호출 또는 다음 경계가 아닌 호출은 변경할 수 없습니다')
            if db.execute('SELECT status FROM lifecycle').fetchone()[0] != 'running' or path.with_suffix('.cancel').exists():
                raise ValueError('종료·취소 중인 실행은 변경할 수 없습니다')
            db.execute("INSERT INTO control_requests VALUES(?,?,'accepted',NULL)", (request_id, encoded))
        return {'success': True, 'accepted': True, 'delivery': 'accepted', 'task_ref': ref}
    except (TypeError, KeyError, json.JSONDecodeError) as exc:
        raise ValueError('부분 조향 요청 형식이 올바르지 않습니다') from exc


def invocation(db, node_id, ordinal, scope_id=None):
    """An existing effect marker is authoritative even without a return receipt."""
    if scope_id is not None:
        return db.execute('SELECT c.id,c.receipt FROM control_scope_invocations i JOIN calls c ON c.id=i.call_id '
                          'WHERE i.scope_id=? AND i.node_id=? AND i.ordinal=?', (scope_id, node_id, ordinal)).fetchone()
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


def repair_applications(db, *, different_plan=None):
    """Existing applied controls, bound to the original durable call identities.

    No second effect ledger: a control without a durable call cannot yet be
    certified across definition repair (including pure adapter applications).
    """
    from ibl_v2_ir import Fault
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='control_requests'").fetchone():
        return []
    result = []
    for rid, payload in db.execute("SELECT request_id,payload FROM control_requests WHERE state='applied' ORDER BY rowid"):
        request = json.loads(payload)
        if request['plan_hash'] == different_plan:
            continue
        row = invocation(db, request['node_id'], request['ordinal'], request.get('scope'))
        if not row:
            raise Fault('REPAIR_UNSUPPORTED', '효과 원장에 연결되지 않은 적용 조향은 정의 수정으로 계승할 수 없습니다.', kind='protocol')
        info = db.execute('SELECT call_info FROM calls WHERE id=?', (row[0],)).fetchone()
        action = (json.loads(info[0]) if info and info[0] else {}).get('action')
        if not action:
            raise Fault('REPAIR_UNSUPPORTED', '적용 조향의 원래 호출 계약을 확인할 수 없습니다.', kind='protocol')
        result.append((rid, payload, row[0], action))
    return result


def replay_applied(runtime, node, args, spec):
    """Restore accepted history, never reinterpret it as a new live request."""
    entries = getattr(runtime.journal, 'control_replay', {})
    if not entries:
        return args, False
    _, _, call_id = runtime.call_coordinate(node)
    from ibl_callable_contract import checked_values
    from ibl_v2_ir import Fault
    replayed = False
    for rid, request, action in entries.get(call_id, ()):
        if (action != f"{node.data['node']}:{node.data['action']}"
                or request['revision'] != digest(spec.contract)
                or request['expected_args_hash'] != digest(args.value)):
            raise Fault('CONTROL_REPLAY_CHANGED', '이미 적용한 조향의 호출·인자·정의 판본이 달라졌습니다.', node, kind='protocol')
        _, values = checked_values(spec.contract, {**args.value, **request['changes']})
        eid = runtime.event(node, 'steer_replayed', args.evidence, request_id=rid, call_id=call_id,
                            original_plan=request['plan_hash'], root_task=runtime.journal.control['root_task'])
        parts = {k: Binding(v, frozenset({eid})) if k in request['changes'] else
                 args.select(k) if k in args.value else Binding(v) for k, v in values.items()}
        args = Binding.record(parts).controlled(args.control | {eid})
        runtime.control_resource_guard = True
        replayed = True
    return args, replayed


def bind_invocation(runtime, node, call_id):
    """Link the steering coordinate to the existing durable effect owner."""
    coordinate = getattr(runtime.local, 'control_boundary', None)
    if not runtime.journal or not coordinate or coordinate[0] != node.id:
        return
    with runtime.journal.lock:
        db = runtime.journal.db
        node_id, ordinal, scope_id = coordinate
        if scope_id is None:
            old = db.execute('SELECT call_id FROM control_invocations WHERE node_id=? AND ordinal=?', (node_id, ordinal)).fetchone()
        else:
            old = db.execute('SELECT call_id FROM control_scope_invocations WHERE scope_id=? AND node_id=? AND ordinal=?',
                             (scope_id, node_id, ordinal)).fetchone()
        if old and old[0] != call_id:
            from ibl_v2_ir import Fault
            raise Fault('CONTROL_COORDINATE_CHANGED', '부분 개입의 호출 좌표가 달라졌습니다. 효과를 시작하지 않습니다.', kind='protocol')
        if scope_id is None:
            db.execute('INSERT OR IGNORE INTO control_invocations VALUES(?,?,?)', (node_id, ordinal, call_id))
        else:
            db.execute('INSERT OR IGNORE INTO control_scope_invocations VALUES(?,?,?,?)', (scope_id, node_id, ordinal, call_id))
        db.commit()


def boundary(runtime, node, args, spec):
    journal = runtime.journal
    runtime.local.control_boundary = None
    if not journal or not getattr(journal, 'control', None) or node.id not in journal.control['targets']:
        return args
    args, replayed = replay_applied(runtime, node, args, spec)
    scope_id = None
    if journal.control['targets'][node.id].get('addressing') == 'scope':
        current_scope = getattr(runtime.local, 'control_scope', None)
        if not current_scope or node.id not in current_scope[1]:
            return args
        scope_id = current_scope[0]
    from ibl_callable_contract import checked_values
    with journal.lock:
        key = (scope_id, node.id)
        ordinal = journal.control_counts.get(key, 0) + 1
        journal.control_counts[key] = ordinal
        runtime.local.control_boundary = (node.id, ordinal, scope_id)
        # Serialize acceptance and application across processes, including cancel.
        db = journal.db
        db.execute('BEGIN IMMEDIATE')
        try:
            if scope_id is None:
                db.execute('INSERT OR REPLACE INTO control_boundaries VALUES(?,?)', (node.id, ordinal))
            else:
                db.execute('INSERT OR REPLACE INTO control_scope_boundaries VALUES(?,?,?)', (scope_id, node.id, ordinal))
            rows = db.execute("SELECT request_id,payload,state FROM control_requests WHERE state IN ('accepted','applied') ORDER BY rowid").fetchall()
            for rid, encoded, state in rows:
                request = json.loads(encoded)
                if state == 'applied' and request['plan_hash'] != runtime.plan.fingerprint:
                    continue  # Historical applications use the certified call lineage above.
                if request['node_id'] != node.id or request['ordinal'] != ordinal or request.get('scope') != scope_id:
                    continue
                reason = None
                if (journal.root / (journal.run_id + '.cancel')).exists() or (runtime.cancel_check and runtime.cancel_check()):
                    reason = 'cancelled_before_boundary'
                elif request['plan_hash'] != runtime.plan.fingerprint or request['revision'] != digest(spec.contract):
                    reason = 'definition_revision_mismatch'
                elif state == 'accepted' and (replayed or invocation(db, node.id, ordinal, scope_id)):
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
                        from ibl_v2_access import ensure_admitted
                        from ibl_v2_ir import Fault
                        try:
                            ensure_admitted(runtime, spec, effective, values, force=True)
                        except Fault as exc:
                            raise ValueError(exc.code) from exc
                    except (ValueError, TypeError) as exc:
                        reason = str(exc)
                if reason:
                    db.execute("UPDATE control_requests SET state='not_applied',reason=? WHERE request_id=?", (reason, rid))
                    continue
                eid = runtime.event(node, 'steer_applied', args.evidence, request_id=rid,
                                    root_task=journal.control['root_task'], ordinal=ordinal, scope=scope_id,
                                    old_args_hash=digest(args.value), new_args_hash=digest(values))
                parts = {k: Binding(v, frozenset({eid})) if k in request['changes'] else
                         args.select(k) if k in args.value else Binding(v) for k, v in values.items()}
                args = Binding.record(parts).controlled(args.control | {eid})
                runtime.control_resource_guard = True
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
