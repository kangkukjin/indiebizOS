"""정의 관측·버전 검증·기존 날짜 이관·상태 격리의 통합 계약."""
import json
import sqlite3

import boot_paths  # noqa: F401
import pytest
import yaml
import capability_age as age
import capability_history as history
from capability_inventory import collect


@pytest.fixture
def body(tmp_path):
    def write(name, value):
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(value)
    write('data/ibl_nodes.yaml', yaml.safe_dump({'nodes': {'sense': {'actions': {'sample': {'tool': 'sample'}}}}}))
    write('data/ibl_nodes_src/sense.yaml', 'nodes: {}\n')
    write('data/package_meta.json', json.dumps({'action_owner': {'sense:sample': 'sample'}}))
    write('data/packages/installed/tools/sample/handler.py', 'def run(): return 1\n')
    write('data/scripts/registry.yaml', yaml.safe_dump({'legacy': {'file': 'legacy.py', 'registered_at': '2026-01-02'}}))
    write('data/scripts/legacy.py', 'print(1)\n')
    write('backend/base/core.py', 'VALUE = 1\n')
    conn = sqlite3.connect(tmp_path / 'data/ibl_usage.db')
    conn.execute('CREATE TABLE ibl_examples (id INTEGER,alias TEXT,ibl_code TEXT,intent TEXT,signature TEXT,returns TEXT,created_at TEXT,updated_at TEXT)')
    conn.execute('INSERT INTO ibl_examples VALUES (1,?,?,?,?,?,?,?)',
                 ('fn', '[sense:sample]{}', 'example', '[]', 'items', '2026-01-01', '2026-10-01'))
    conn.commit(); conn.close()
    return tmp_path


def test_legacy_dates_not_misrepresented_as_verified_or_repaired(body):
    out = age.operate({'limit': 100}, root=body)
    assert out['success'] and out['total'] == 3
    rows = {r['key']: r for r in out['items']}
    assert rows['script:legacy']['created_at'] is None
    assert rows['script:legacy']['metadata']['legacy_registered_at'] == '2026-01-02'
    assert rows['idiom:db:1']['created_at'] == '2026-01-01'
    assert all(r['last_repaired_at'] is None and r['last_verified_at'] is None for r in rows.values())


def test_package_backend_helper_and_nested_definition_changes_stale(body):
    before = collect(body)
    (body / 'data/packages/installed/tools/sample/handler.py').write_text('def run(): return 2\n')
    changed = collect(body)
    assert before['action:sense:sample']['implementation_revision'] != changed['action:sense:sample']['implementation_revision']
    assert before['idiom:db:1']['revision'] != changed['idiom:db:1']['revision']
    (body / 'backend/base/core.py').write_text('VALUE = 2\n')
    backend = collect(body)
    assert backend['action:sense:sample']['implementation_revision'] == changed['action:sense:sample']['implementation_revision']
    assert backend['action:sense:sample']['revision'] != changed['action:sense:sample']['revision']
    (body / 'data/scripts/helper.py').write_text('VALUE = 3\n')
    helper = collect(body)
    assert helper['script:legacy']['revision'] != backend['script:legacy']['revision']
    assert helper['idiom:db:1']['revision'] != backend['idiom:db:1']['revision']


def test_execution_and_registration_timestamps_do_not_change_revision(body):
    before = collect(body)
    conn = sqlite3.connect(body / 'data/ibl_usage.db')
    conn.execute("UPDATE ibl_examples SET updated_at='2026-10-20'")
    conn.commit(); conn.close()
    p = body / 'data/scripts/registry.yaml'
    registry = yaml.safe_load(p.read_text())
    registry['legacy']['registered_at'] = '2026-10-20'
    registry['legacy']['lifecycle'] = {'candidate_since': '2026-10-20'}
    p.write_text(yaml.safe_dump(registry))
    after = collect(body)
    assert {k: v['revision'] for k, v in before.items()} == {k: v['revision'] for k, v in after.items()}


def test_record_requires_current_revision_and_roundtrips_scope(body):
    row = age.operate({'key': 'action:sense:sample'}, root=body)['items'][0]
    args = {'op': 'verify', 'key': row['key'], 'expected_revision': row['revision'],
            'scope': 'fixture', 'outcome': 'passed', 'evidence': 'test report'}
    assert age.operate(args, root=body)['items'][0]['verification_status'] == 'current'
    (body / 'data/packages/installed/tools/sample/handler.py').write_text('CHANGED = True\n')
    assert 'REVISION_CHANGED' in age.operate(args, root=body)['error']
    assert age.operate({'key': row['key']}, root=body)['items'][0]['verification_status'] == 'stale'


@pytest.mark.parametrize('source', ['{}', '[', 'nodes: []', 'nodes: {sense: null}'])
def test_malformed_source_does_not_mark_everything_absent(body, source):
    age.operate({}, root=body)
    (body / 'data/ibl_nodes.yaml').write_text(source)
    assert age.operate({}, root=body)['success'] is False
    assert all(r['present'] for r in history.rows(history.storage_path(body)))


def test_daily_maintenance_observes_without_verifying(body, monkeypatch):
    monkeypatch.setattr(age, '_locations', lambda root=None: (body, history.storage_path(body)))
    assert age.run_age_check()['success']
    assert age.run_age_check()['skipped']
    assert all(r['verification_status'] == 'unverified' for r in history.rows(history.storage_path(body)))


def test_idiom_usage_records_execution_without_verification(body, monkeypatch):
    from types import SimpleNamespace
    from contextlib import contextmanager
    from ibl_usage_db import IBLUsageDB

    path = body / 'data/ibl_usage.db'
    conn = sqlite3.connect(path)
    for name in ('success_count', 'fail_count'):
        conn.execute(f'ALTER TABLE ibl_examples ADD COLUMN {name} INTEGER DEFAULT 0')
    conn.commit()
    conn.close()

    @contextmanager
    def connect():
        connection = sqlite3.connect(path)
        try:
            yield connection
        finally:
            connection.close()

    monkeypatch.setenv('INDIEBIZ_RUNTIME_STATE_DIR', str(body / 'data'))
    age.operate({}, root=body)
    IBLUsageDB.update_success(SimpleNamespace(_get_connection=connect, AVG_MS_ALPHA=0.3), 1, True)
    row = age.operate({'key': 'idiom:db:1'}, root=body)['items'][0]
    assert row['last_execution']['success'] == 1
    assert row['last_execution']['at'].endswith('+00:00')
    assert row['last_verified_at'] is None


def test_runtime_state_directory_does_not_write_canonical_ledger(body, tmp_path, monkeypatch):
    state = tmp_path / 'isolated'
    monkeypatch.setenv('INDIEBIZ_RUNTIME_STATE_DIR', str(state))
    monkeypatch.setattr(age, 'get_base_path', lambda: body)
    monkeypatch.setattr('thread_context.get_repair_workspace', lambda **kw: None)
    assert age.operate({})['success']
    assert (state / 'capability_history.db').is_file()
    assert not (body / 'data/capability_history.db').exists()


def test_member_cannot_read_owner_inventory(body, monkeypatch):
    monkeypatch.setattr('principal.is_owner', lambda: False)
    assert age.operate({}, root=body)['success'] is False
    assert not (body / 'data/capability_history.db').exists()


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
