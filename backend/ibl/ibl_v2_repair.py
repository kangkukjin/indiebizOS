"""CAS-bound result-computation repair within the existing journal and execution lineage.

Only result computations outside effect dependencies may change.
Logical operation identity is the original AST path in this lineage, not an
action/argument hash. Reordering, inserted effects and uncertain receipts stop.
"""
import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from filelock import FileLock, Timeout
from ibl_v2_ir import Node, Fault, digest
from ibl_v2_parser import parse


def structural(value):
    if isinstance(value, Node):
        return [value.kind, structural(value.data)]
    if isinstance(value, dict):
        return {k: structural(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [structural(v) for v in value]
    from ibl_v2_ir import pack
    return pack(value)


def node_paths(value, path=()):
    if isinstance(value, Node):
        yield path, value.id
        yield from node_paths(value.data, path + ('data',))
    elif isinstance(value, dict):
        for key, child in value.items():
            yield from node_paths(child, path + (key,))
    elif isinstance(value, (list, tuple)):
        for i, child in enumerate(value):
            yield from node_paths(child, path + (i,))


def snapshot(plan, inputs, project_path, agent_id, input_evidence=None, policy=None):
    from ibl_run_journal import identity
    from dataclasses import replace
    # Source coordinates and plan hashes change with editing. Executable assets,
    # language semantics, authority and input evidence must remain identical.
    deps = {k: v for k, v in plan.dependencies.items() if k not in ('source', 'source_map', 'calls', 'libraries', 'function_refs')}
    deps['calls'] = sorted(digest(v) for v in plan.dependencies.get('calls', {}).values())
    stable = replace(plan, fingerprint=digest(deps))
    context = identity(stable, inputs, project_path, agent_id, input_evidence=input_evidence)
    source = plan.source[:plan.dependencies['source_map'][0]['end']]
    from ibl_v2_repair_graph import frontier
    return {'source': source, 'library_source': plan.source[len(source):],
            'context': digest([context, policy]), 'plan': plan.fingerprint,
            'frontier': frontier(plan), 'function_refs': plan.dependencies.get('function_refs', [])}


def remember(journal, record):
    journal.db.execute('CREATE TABLE IF NOT EXISTS repair_snapshot(record TEXT)')
    if not journal.db.execute('SELECT 1 FROM repair_snapshot').fetchone():
        journal.db.execute('INSERT INTO repair_snapshot VALUES(?)', (json.dumps(record),))
        journal.db.commit()


@contextmanager
def locked(root, handle):
    from ibl_run_journal import Journal
    Journal(root, '', {'run_id': handle.get('run_id')})
    path = Path(root) / (handle['run_id'] + '.sqlite')
    if path.is_symlink() or not path.is_file():
        raise Fault('RESUME_NOT_FOUND', '수정할 실행 기록이 없습니다.', kind='permission')
    lock = FileLock(str(path) + '.lock', timeout=0)
    try:
        lock.acquire()
    except Timeout as exc:
        raise Fault('RESUME_BUSY', '같은 실행이 진행 중입니다.', kind='protocol') from exc
    try:
        with sqlite3.connect(path, timeout=10) as db:
            yield db
    finally:
        lock.release()


def propose(db, record, handle):
    if not db.execute("SELECT 1 FROM sqlite_master WHERE name='repair_snapshot'").fetchone():
        raise Fault('REPAIR_UNSUPPORTED', '이전 기록에는 수정 계승 계약이 없습니다.', kind='protocol')
    old = json.loads(db.execute('SELECT record FROM repair_snapshot').fetchone()[0])
    if old['context'] != record['context']:
        raise Fault('REPAIR_CHANGED', '입력·주체·권한·부품·계약·구현·완료 의무가 달라졌습니다.', kind='permission')
    from ibl_v2_repair_graph import mapping as frontier_mapping
    mapping = frontier_mapping(old.get('frontier'), record.get('frontier'))
    if db.execute('SELECT 1 FROM calls WHERE receipt IS NULL').fetchone():
        raise Fault('EFFECT_UNCERTAIN', '완료 불명 효과는 자동 계승하거나 재실행하지 않습니다.', kind='protocol')
    rows = db.execute('SELECT id,request,receipt,state_change FROM calls ORDER BY rowid').fetchall()
    # A completed read failure is an observation of this execution. The fixed
    # prefix replays its original Fault through the same recovery branch.
    # Failed writes and incomplete/approval receipts still cannot be inherited.
    if any('value' not in (receipt := json.loads(r[2]))
           and (r[3] or 'error' not in receipt or receipt.get('effects') != ['read_external'])
           for r in rows):
        raise Fault('REPAIR_UNSUPPORTED', '실패한 쓰기·승인 대기 효과의 변경 재개는 지원하지 않습니다.', kind='protocol')
    # A second repair keeps the first execution's node identities.
    for new, prior in list(mapping.items()):
        if new.split(':')[0] in ('named_call', 'pure_call'):
            mapping['call:' + new.split(':', 1)[1]] = 'call:' + prior.split(':', 1)[1]
    ancestry = old.get('node_map', {})
    mapping = {new: ancestry.get(prior, prior) for new, prior in mapping.items()}
    original_identity = db.execute('SELECT identity FROM meta').fetchone()[0]
    fingerprint = digest([original_identity, record, rows, mapping])
    plan = {'protocol': 'ibl-repair/1', 'run_id': handle['run_id'], 'plan_hash': fingerprint,
            'status': 'ready', 'steps': [{'call_id': r[0], 'kind': 'inherit_completed_effect' if r[3] else 'inherit_completed_read'} for r in rows],
            'new_computation': 'effect_independent_results', 'external_state': 'not_revalidated',
            'new_effects': ('certified_iteration_continuations_only'
                            if record['frontier'].get('iteration_effects') else 'none')}
    return plan, mapping


def prepare(root, handle, record, expected_identity, *, check=False):
    if (not isinstance(handle, dict) or set(handle) - {'run_id', 'plan_hash'} or 'run_id' not in handle):
        raise Fault('REPAIR_ARGUMENT', 'repair에는 run_id와 검사에서 받은 plan_hash를 지정하세요.', kind='compile')
    with locked(root, handle) as db:
        plan, mapping = propose(db, record, handle)
        if check:
            return plan
        # The caller takes the normal Journal lock again. Its identity/CAS must
        # be checked under that lock before any effect can be inherited.
        if handle.get('plan_hash') != plan['plan_hash']:
            raise Fault('REPAIR_CHANGED', '수정 계획 지문이 달라졌습니다. check로 다시 검사하세요.', kind='protocol')
        return plan, mapping


def activate(journal, handle, record, expected_identity):
    if journal.db.execute("SELECT 1 FROM sqlite_master WHERE name='repair_lineage'").fetchone():
        previous = journal.db.execute('SELECT record FROM repair_lineage WHERE plan=?', (handle.get('plan_hash'),)).fetchone()
        stored = json.loads(journal.db.execute('SELECT record FROM repair_snapshot').fetchone()[0])
        current_identity = journal.db.execute('SELECT identity FROM meta').fetchone()[0]
        if previous and current_identity == expected_identity and all(stored.get(k) == v for k,v in record.items()):
            journal.repair_plan, journal.node_map = json.loads(previous[0]), stored.get('node_map', {})
            return
    plan, mapping = propose(journal.db, record, handle)
    if handle.get('plan_hash') != plan['plan_hash']:
        raise Fault('REPAIR_CHANGED', '잠금 획득 전 수정 계획이 변경되었습니다.', kind='protocol')
    journal.db.execute('CREATE TABLE IF NOT EXISTS repair_lineage(plan TEXT PRIMARY KEY, record TEXT)')
    journal.db.execute('INSERT INTO repair_lineage VALUES(?,?)', (plan['plan_hash'], json.dumps(plan)))
    journal.db.execute('UPDATE meta SET identity=?', (expected_identity,))
    journal.db.execute('UPDATE repair_snapshot SET record=?', (json.dumps({**record, 'node_map': mapping}),))
    if journal.db.execute("SELECT 1 FROM sqlite_master WHERE name='function_snapshot'").fetchone():
        journal.db.execute('UPDATE function_snapshot SET refs=?', (json.dumps(record.get('function_refs', [])),))
    journal.db.commit()
    journal.repair_plan, journal.node_map = plan, mapping


def continuation_sites(record):
    """Certified source loop/call pairs, translated to the original lineage."""
    frontier = record.get('frontier', {})
    if frontier.get('protocol') != 'ibl-repair-frontier/6':
        return set()
    mapping, nodes = record.get('node_map', {}), frontier['nodes']
    result = set()
    for loop, call in frontier.get('iteration_effects', []):
        loop, call = nodes[loop], nodes[call]
        result.add((mapping.get(loop, loop), mapping.get(call, call)))
        if call.split(':')[0] in ('named_call', 'pure_call'):
            synthetic = 'call:' + call.split(':', 1)[1]
            result.add((mapping.get(loop, loop), mapping.get(synthetic, synthetic)))
    return result


def inherited_request(before, after):
    return bool(before and after and {k: v for k, v in before.items() if k != 'plan'} ==
                {k: v for k, v in after.items() if k != 'plan'})
