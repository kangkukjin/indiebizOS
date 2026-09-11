"""Cross-ledger read contracts on synthetic stores; no live DB writes or providers."""
import boot_paths  # noqa: F401
import hashlib
import json
import sqlite3
from pathlib import Path

import pytest

from execution_trace import ExecutionTrace
from execution_trace_scope import TraceAccess
from episode_logger import trajectory_run_id

FIXTURE = json.loads((Path(__file__).parent / 'fixtures/execution_trace_cases.json').read_text())
ACCESS = TraceAccess(None, True)


@pytest.fixture
def trace(tmp_path):
    (tmp_path / 'data/spill/supervision').mkdir(parents=True)
    (tmp_path / 'projects/project-a').mkdir(parents=True)
    (tmp_path / 'projects/project-b').mkdir()
    (tmp_path / 'projects/projects.json').write_text(json.dumps([
        {'id': p, 'type': 'project', 'path': str(tmp_path / 'projects' / p)} for p in FIXTURE['projects']]))
    pulse = tmp_path / 'data/world_pulse.db'
    with sqlite3.connect(pulse) as c:
        c.executescript('''CREATE TABLE episode_log(id INTEGER PRIMARY KEY,task_id,run_id,parent_run_id,ended_at,started_at,log);
            CREATE TABLE trajectory_event(run_id,event_seq,episode_id,task_id,parent_run_id,ts,kind,data,source,
            PRIMARY KEY(run_id,event_seq));''')
        for eid, task in [(1, 'shared-task'), (2, 'shared-task'), (3, 'concurrent-task')]:
            c.execute('INSERT INTO episode_log VALUES(?,?,?,?,?,?,?)',
                      (eid, task, trajectory_run_id(task), '', 'closed', '2026-09-11T10:00:00', 'raw episode log'))
        for seq, e in enumerate(FIXTURE['events'], 1):
            c.execute('INSERT INTO trajectory_event VALUES(?,?,?,?,?,?,?,?,?)',
                      (trajectory_run_id('shared-task'), seq, 1, 'shared-task', '', '2026-09-11T10:00:00', e['kind'], json.dumps(e['data']), 'usage'))
        c.execute('INSERT INTO trajectory_event VALUES(?,?,?,?,?,?,?,?,?)',
                  (trajectory_run_id('shared-task'), 100, 2, 'shared-task', '', '', 'other.project', '{}', 'usage'))
        c.execute('INSERT INTO trajectory_event VALUES(?,?,?,?,?,?,?,?,?)',
                  (trajectory_run_id('concurrent-task'), 1, 3, 'concurrent-task', '', '', 'other.task', '{}', 'usage'))
    from conversation_db import ConversationDB
    from pursuit_ledger import PursuitLedger
    for p, eid in [('project-a', 1), ('project-b', 2)]:
        db = tmp_path / 'projects' / p / 'conversations.db'
        ConversationDB(str(db)).create_task('shared-task', 'requester', 'gui', 'raw task request', 'Display Name')
        with sqlite3.connect(db) as c:
            c.execute("UPDATE tasks SET status='completed',result='task result bytes' WHERE task_id='shared-task'")
        ledger = PursuitLedger(db, 'agent-a')
        row = ledger.create('title', 'criteria', 'shared-task')
        ledger.begin_turn(row['id'], 'shared-task', 'raw original request', episode_id=eid)
    # These are observations of the same event, followed by an actual repeated write.
    write = {'episode_id': 1, 'run': trajectory_run_id('shared-task'), 'event_seq': 8,
             'task': 'shared-task', 'event': 'write', 'gate': 'fixture'}
    (tmp_path / 'data/write_ledger.jsonl').write_text(json.dumps(write) + '\n' + json.dumps(write) + '\n')
    return ExecutionTrace(tmp_path), tmp_path


def pages(service, **kwargs):
    out, cursor = [], None
    for _ in range(100):
        page = service.query(ACCESS, cursor=cursor, **kwargs)
        out.append(page)
        cursor = page['next_cursor']
        if not cursor:
            return out
    pytest.fail('non-advancing cursor')


def source_files(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file() and p.suffix not in {'.db-shm', '.db-wal'}}


def test_cost_rounds_parent_child_and_snapshot_dedup(trace):
    svc, root = trace
    before = source_files(root)
    result = pages(svc, episode_id=1, limit=2)
    assert all(p['status'] == 'ok' for p in result), result
    assert result[-1]['usage']['measured'] == FIXTURE['expected_usage']
    assert result[-1]['usage']['records'] == 3
    events = [e for p in result for e in p['events']]
    assert len([e for e in events if e['source'] == 'writes']) + sum(len(e.get('observations', [])) for e in events) == 2
    assert all(e['kind'] not in {'other.project', 'other.task'} for e in events)
    assert all('raw original' not in json.dumps(e) for e in events)
    assert source_files(root) == before


def test_same_task_other_project_and_same_agent_concurrency(trace):
    svc, _ = trace
    a = svc.query(ACCESS, project='project-a', owner='agent-a', task_id='shared-task')
    b = svc.query(ACCESS, project='project-b', owner='agent-a', task_id='shared-task')
    assert a['identity']['episode_ids'] == [1]
    assert b['identity']['episode_ids'] == [2]
    assert a['identity']['run_id'] == b['identity']['run_id']
    assert b['events'][0]['kind'] == 'other.project'
    denied = svc.query(TraceAccess(frozenset({'project-a'}), True), episode_id=2)
    assert denied['status'] == 'forbidden'
    assert 'identity' not in denied


def test_missing_empty_lock_corrupt_and_no_mutation(trace):
    svc, root = trace
    from episode_logger import read_trajectory_page
    from trace_read import jsonl_page
    assert read_trajectory_page(root / 'data/no.db', [1])['status'] == 'missing'
    assert not (root / 'data/no.db').exists()
    assert read_trajectory_page(root / 'data/world_pulse.db', [99])['status'] == 'empty'
    db = sqlite3.connect(root / 'data/world_pulse.db')
    db.execute('BEGIN EXCLUSIVE')
    try:
        assert read_trajectory_page(root / 'data/world_pulse.db', [1])['status'] == 'unavailable'
    finally:
        db.rollback(); db.close()
    path = root / 'bad.db'; path.write_text('not sqlite')
    assert read_trajectory_page(path, [1])['status'] == 'malformed'
    path = root / 'data/write_ledger.jsonl'
    with path.open('a') as f:
        f.write('{bad}\n{"cut":')
    page = jsonl_page('writes', path)
    assert page['status'] == 'partial'
    assert 'truncated_tail' in page['reason'] and 'malformed_record' in page['reason']


def test_pagination_frozen_append_rotation_and_delete(trace):
    svc, root = trace
    first = svc.query(ACCESS, episode_id=1, limit=1)
    with sqlite3.connect(root / 'data/world_pulse.db') as c:
        c.execute('INSERT INTO trajectory_event VALUES(?,?,?,?,?,?,?,?,?)',
                  (trajectory_run_id('shared-task'), 101, 1, 'shared-task', '', '', 'late.complete', '{}', 'usage'))
    cursor = first['next_cursor']; kinds = []
    while cursor:
        page = svc.query(ACCESS, episode_id=1, limit=1, cursor=cursor)
        assert not page['cursor_expired']
        kinds += [e['kind'] for e in page['events']]
        cursor = page['next_cursor']
    assert 'late.complete' not in kinds
    assert any(e['kind'] == 'late.complete' for p in pages(svc, episode_id=1) for e in p['events'])
    path = root / 'data/write_ledger.jsonl'
    path.rename(root / 'data/write_ledger.jsonl.1')
    path.write_text('')
    page = svc.query(ACCESS, episode_id=1, limit=1, cursor=first['next_cursor'])
    assert page['cursor_expired'] and page['partial']
    assert page['next_cursor'] is None


def test_runtime_conflict_late_completion_never_repairs(trace):
    svc, root = trace
    svc.runtime_probe = lambda ids: {'status': 'running', 'episode_ids': ids, 'observed_at': 'now'}
    before = source_files(root)
    row = svc.query(ACCESS, episode_id=1)
    assert row['state']['task'] == 'completed'
    assert row['state']['assessment'] == 'conflict'
    assert source_files(root) == before
    svc.runtime_probe = lambda ids: {'status': 'unknown'}
    assert svc.query(ACCESS, episode_id=1)['state']['task'] == 'completed'


def add_store(svc, root, *, duplicate=False):
    from supervision_store import TurnStore
    store_id = 'a' * 32
    store = TurnStore(root / 'data/spill/supervision' / store_id)
    ev = store.evidence('PRIVATE EVIDENCE' * 10)
    row = store.log('tool.finished', task_id='shared-task', result=ev)
    if duplicate:
        store.sequence = 0
        store.log('tool.finished', task_id='shared-task', result=ev)
    with sqlite3.connect(root / 'data/world_pulse.db') as c:
        c.execute('INSERT INTO trajectory_event VALUES(?,?,?,?,?,?,?,?,?)',
                  (trajectory_run_id('shared-task'), 9, 1, 'shared-task', '', '',
                   'supervision.tool.finished', json.dumps({**row, 'store': str(store.directory)}), 'usage'))
    return store, ev


def test_evidence_inspection_bounds_hash_missing_and_permissions(trace):
    svc, root = trace
    store, ev = add_store(svc, root)
    page = svc.query(ACCESS, episode_id=1)
    ref = page['links']['evidence'][0]['source_ref']
    before = source_files(root)
    doc = svc.document(ACCESS, ref, episode_id=1, limit=12)
    assert doc['text'] == 'PRIVATE EVID'
    assert doc['next_offset'] == 12
    assert not store.evidence_coverage and not store.coverage
    assert source_files(root) == before
    assert svc.document(ACCESS, ref, episode_id=2)['status'] == 'forbidden'
    assert svc.document(TraceAccess(None, False), ref, episode_id=1)['status'] == 'forbidden'
    assert svc.document(ACCESS, '../../secret', episode_id=1)['status'] == 'forbidden'
    assert svc.document(ACCESS, ref, episode_id=1, offset=-1)['status'] == 'malformed'
    assert svc.document(ACCESS, ref, episode_id=1, limit=12001)['status'] == 'malformed'
    (store.directory / (ev['id'] + '.txt')).unlink()
    assert svc.document(ACCESS, ref, episode_id=1)['status'] == 'missing'
    (store.directory / (ev['id'] + '.txt')).symlink_to(root / 'data/world_pulse.db')
    assert svc.document(ACCESS, ref, episode_id=1)['status'] == 'forbidden'


def test_supervision_restarted_seq_is_ambiguous_not_collapsed(trace):
    svc, root = trace
    add_store(svc, root, duplicate=True)
    page = svc.query(ACCESS, episode_id=1)
    rows = [r for r in page['events'] if r['source'] == 'supervision']
    assert len(rows) == 2
    assert rows[0]['source_record_id'] != rows[1]['source_record_id']
    assert 'ambiguous_supervision_sequence' in page['diagnostics']


def test_response_review_hash_cas_remain_owner_contract(trace):
    svc, root = trace
    store, _ = add_store(svc, root)
    store.put_response('unapproved original')
    store.log('response.delivered', task_id='shared-task', response=store.manifest())
    ref = [r for r in svc.query(ACCESS, episode_id=1)['links']['evidence'] if r['label'] == 'response'][0]['source_ref']
    assert svc.document(ACCESS, ref, episode_id=1)['status'] == 'missing'
    (store.directory / 'review_status.json').write_text(json.dumps({'status': 'UNKNOWN', 'response': store.manifest()}))
    assert svc.document(ACCESS, ref, episode_id=1)['status'] == 'forbidden'
    (store.directory / 'review_status.json').write_text(json.dumps({'status': 'ACHIEVED', 'response': store.manifest()}))
    before = source_files(root)
    assert svc.document(ACCESS, ref, episode_id=1)['text'] == 'unapproved original'
    assert not store.fully_read()
    assert source_files(root) == before
    store.patch(1, [{'id': '0', 'hash': store.blocks[0]['hash'], 'text': 'changed after review'}])
    assert svc.document(ACCESS, ref, episode_id=1)["status"] == "forbidden"
    with pytest.raises(ValueError):
        store.patch(1, [{'id': '0', 'hash': store.blocks[0]['hash'], 'text': 'stale'}])


def test_jsonl_read_budget_advances(trace, monkeypatch):
    from trace_read import jsonl_page
    import trace_read
    _, root = trace
    monkeypatch.setattr(trace_read, 'JSON_BYTES', 30)
    path = root / 'data/budget.jsonl'
    path.write_text(''.join(json.dumps({'task': 'unrelated', 'x': i}) + '\n' for i in range(20)))
    page = jsonl_page('test', path, predicate=lambda r: False)
    assert page['more'] and page['high_water']['after'] > 0
    cursor = page['high_water']; total = page['scanned_bytes']
    while not cursor['done']:
        page = jsonl_page('test', path, cursor, predicate=lambda r: False)
        total += page['scanned_bytes']; cursor = page['high_water']
    assert total == path.stat().st_size


def test_bad_cursor_and_changed_task_metadata(trace):
    svc, root = trace
    page = svc.query(ACCESS, episode_id=1, limit=1)
    assert svc.query(ACCESS, episode_id=2, cursor=page['next_cursor'])['status'] == 'forbidden'
    with sqlite3.connect(root / 'projects/project-a/conversations.db') as c:
        c.execute("UPDATE tasks SET status='pending'")
    changed = svc.query(ACCESS, episode_id=1, cursor=page['next_cursor'])
    assert changed['cursor_expired']


def test_task_without_pursuit_returns_scoped_state_without_guessing_episode(trace):
    svc, root = trace
    with sqlite3.connect(root / 'projects/project-a/conversations.db') as c:
        c.execute("DELETE FROM pursuit_turn")
        c.execute("DELETE FROM pursuit")
    result = svc.query(ACCESS, project='project-a', owner='agent-a', task_id='shared-task')
    assert result['status'] == 'ok'
    assert result['state']['task'] == 'completed'
    assert result['identity']['episode_ids'] == []
    assert result['partial']


def test_episode_log_pages_detect_content_change_even_same_length(trace):
    svc, root = trace
    summary = svc.query(ACCESS, episode_id=1)
    ref = summary['links']['documents'][0]['source_ref']
    page = svc.document(ACCESS, ref, episode_id=1, limit=3)
    with sqlite3.connect(root / 'data/world_pulse.db') as c:
        c.execute("UPDATE episode_log SET log='RAW episode log' WHERE id=1")
    next_page = svc.document(ACCESS, ref, episode_id=1, offset=3, cursor=page['next_cursor'])
    assert next_page['reason'] == 'cursor_expired'


def test_supervision_file_bound_frozen_before_later_trajectory_page(trace):
    svc, root = trace
    store, _ = add_store(svc, root)
    page = svc.query(ACCESS, episode_id=1, limit=1)
    store.log('late.added', task_id='shared-task')
    cursor = page['next_cursor']; kinds = []
    while cursor:
        page = svc.query(ACCESS, episode_id=1, limit=1, cursor=cursor)
        kinds.extend(e['kind'] for e in page['events'])
        cursor = page['next_cursor']
    assert 'supervision.late.added' not in kinds


def test_missing_source_appearing_midpage_expires_and_retention_deletes(trace):
    svc, root = trace
    first = svc.query(ACCESS, episode_id=1, limit=1)
    (root / 'data/write_ledger.jsonl.1').write_text('{}\n')
    assert svc.query(ACCESS, episode_id=1, limit=1, cursor=first['next_cursor'])['cursor_expired']
    first = svc.query(ACCESS, episode_id=1, limit=1)
    with sqlite3.connect(root / 'data/world_pulse.db') as c:
        c.execute("DELETE FROM trajectory_event WHERE episode_id=1 AND event_seq=4")
    assert svc.query(ACCESS, episode_id=1, limit=1, cursor=first['next_cursor'])['cursor_expired']


def test_failed_runtime_and_malformed_private_metadata_preserve_other_sources(trace):
    svc, root = trace
    def broken(ids):
        raise RuntimeError('unavailable runtime observer')
    svc.runtime_probe = broken
    before = source_files(root)
    page = svc.query(ACCESS, episode_id=1)
    assert page['status'] == 'ok' and page['events']
    assert page['state']['task'] == 'completed'
    assert any(s['source'] == 'runtime' and s['status'] == 'unavailable' for s in page['sources'])
    assert source_files(root) == before
    store, ev = add_store(svc, root)
    ref = svc.query(ACCESS, episode_id=1)['links']['evidence'][0]['source_ref']
    path = store.directory / (ev['id'] + '.txt')
    path.write_text('changed bytes')
    before = source_files(root)
    assert svc.document(ACCESS, ref, episode_id=1)['reason'] == 'evidence_hash_mismatch'
    assert svc.document(ACCESS, 'invalid ref', episode_id=1)['status'] == 'forbidden'
    assert source_files(root) == before
    (root / 'projects/projects.json').write_text('[null]')
    before = source_files(root)
    assert svc.query(ACCESS, episode_id=1)['status'] == 'malformed'
    assert source_files(root) == before


def test_pending_publication_summary_never_exposes_or_delivers_bytes(trace):
    svc, root = trace
    store, _ = add_store(svc, root)
    store.log('delivery.pending', task_id='shared-task', manifest={
        'hash': 'b' * 64, 'artifacts': [{'staged': '/PRIVATE-DRAFT', 'bytes': 7}],
        'notifications': [{'body': 'PRIVATE-NOTIFICATION'}]})
    before = source_files(root)
    page = svc.query(ACCESS, episode_id=1)
    event = next(e for e in page['events'] if e['kind'] == 'supervision.delivery.pending')
    assert event['summary']['artifact_count'] == 1 and event['summary']['notification_count'] == 1
    assert 'PRIVATE-DRAFT' not in json.dumps(page)
    assert 'PRIVATE-NOTIFICATION' not in json.dumps(page)
    assert source_files(root) == before


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
