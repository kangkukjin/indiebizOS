"""Explicit catalog fixtures for tests of runtime consumers (not publication)."""
import json
from pathlib import Path
import function_store
from function_migration import prepare, prepared_snapshot


def legacy_library(codes):
    return prepared_snapshot(prepare([
        {'key': 'fixture:' + name, 'name': name, 'edition': 1, 'source': code,
         'description': '', 'origin': 'user'} for name, code in codes.items()]))


def use_legacy(monkeypatch, codes):
    """Allow a callable provider to exercise stale/corrupt runtime snapshots."""
    real = function_store.snapshot
    def snapshot(root=None, *, index=None):
        if index is not None:
            return real(root, index=index)
        return legacy_library(codes() if callable(codes) else codes)
    monkeypatch.setattr(function_store, 'snapshot', snapshot)


def import_memory(conn):
    """Migrate minimal old SQL fixtures explicitly, with latest row resolution."""
    import sqlite3
    from ibl_edition import source_edition
    from function_library import register
    cursor = conn.execute("SELECT * FROM ibl_examples WHERE COALESCE(alias,'') != ''")
    columns = [c[0] for c in cursor.description]
    for raw in cursor.fetchall():
        row = dict(zip(columns, raw))
        name, code = row['alias'], row['ibl_code']
        edition = source_edition(code)
        old = function_store.resolve(name, edition=edition, include_inactive=True)
        if edition == 1:
            import uuid
            record = {'schema':1,'function_id':(old or {}).get('function_id') or uuid.uuid4().hex,
                      'name':name,'edition':1,'source':code,'description':row.get('intent','')}
            ref = function_store.publish([{'record':record,'state':'retired',
                'expected_revision':(old or {}).get('revision')}])['functions'][0]
        else:
            register_fixture_dependencies(code)
            ref = register(name, code, row.get('intent', ''), edition=edition,
                           legacy={k:row[k] for k in ('always_on','topic') if k in row},
                           expected_revision=(old or {}).get('revision'))
        if 'provenance' in columns and 'id' in columns:
            provenance = json.loads(row.get('provenance') or '{}')
            provenance['function_ref'] = ref
            conn.execute('UPDATE ibl_examples SET provenance=? WHERE id=?',
                         (json.dumps(provenance), row['id']))
    conn.commit()


def test_fixture_import_is_explicit(tmp_path):
    import sqlite3
    with sqlite3.connect(tmp_path / 'memory.db') as conn:
        conn.execute('CREATE TABLE ibl_examples(alias,ibl_code,intent)')
        conn.execute('INSERT INTO ibl_examples VALUES(?,?,?)', ('fixture', '$return=1', 'test'))
        assert function_store.resolve('fixture') is None
        import_memory(conn)
        assert function_store.resolve('fixture', include_inactive=True)['source'] == '$return=1'
        assert function_store.resolve('fixture', include_inactive=True)['state'] == 'retired'


if __name__ == '__main__':
    import pytest
    raise SystemExit(pytest.main([__file__]))


def current_source(name):
    root = Path(__file__).resolve().parents[1]
    from ibl_v2_store import definition_name
    sources = {row['alias']:row['ibl_code'] for row in json.loads((root/'data/idioms/ibl_v2_seeds.json').read_text()) if row.get('alias')}
    for path in (root/'data/idioms').glob('retirement_*.ibl'):
        source=path.read_text();sources[definition_name(source)]=source
    return sources[name]


def register_fixture_dependencies(source):
    import re
    from function_library import register
    for name in set(re.findall(r'\[fn:([^\]]+)\]',source)):
        if function_store.resolve(name,edition=2,include_inactive=True) is not None:
            continue
        dependency=current_source(name)
        register_fixture_dependencies(dependency)
        register(name,dependency)
