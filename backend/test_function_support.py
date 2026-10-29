"""Explicit catalog fixtures for tests of runtime consumers (not publication)."""
import json
from pathlib import Path
import function_store


def legacy_library(codes):
    # Deliberately malformed/historical snapshot for isolation tests. No converter.
    return {'generation': 0, 'records': {name: {'function_id': name, 'name': name,
            'source': source, 'edition': 1, 'state': 'retired'} for name, source in codes.items()}}


def use_legacy(monkeypatch, codes):
    """Allow a callable provider to exercise stale/corrupt runtime snapshots."""
    real = function_store.snapshot
    def snapshot(root=None, *, index=None):
        if index is not None:
            return real(root, index=index)
        return legacy_library(codes() if callable(codes) else codes)
    monkeypatch.setattr(function_store, 'snapshot', snapshot)


def import_memory(conn):
    """Publish explicit current fixtures and attach their immutable references."""
    from function_library import register
    cursor = conn.execute("SELECT * FROM ibl_examples WHERE COALESCE(alias,'') != ''")
    columns = [c[0] for c in cursor.description]
    id_sql = '' if 'id' in columns else 'rowid AS id,'
    conn.execute(f'CREATE VIEW IF NOT EXISTS ibl_current_examples AS SELECT {id_sql}* FROM ibl_examples')
    for raw in cursor.fetchall():
        row = dict(zip(columns, raw))
        name, code = row['alias'], row['ibl_code']
        old = function_store.resolve(name, include_inactive=True)
        register_fixture_dependencies(code)
        ref = register(name, code, row.get('intent', ''),
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
        conn.execute('INSERT INTO ibl_examples VALUES(?,?,?)', ('fixture', '#!ibl edition=2\n[def:fixture](){return 1}', 'test'))
        assert function_store.resolve('fixture') is None
        import_memory(conn)
        assert function_store.resolve('fixture', include_inactive=True)['source'] == '#!ibl edition=2\n[def:fixture](){return 1}'
        assert function_store.resolve('fixture', include_inactive=True)['state'] == 'active'


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
        if function_store.resolve(name,include_inactive=True) is not None:
            continue
        dependency=current_source(name)
        register_fixture_dependencies(dependency)
        register(name,dependency)


def historical_decisions(registry, decide):
    """Recorded decision seam for historical replay only; no provider or live vocabulary."""
    from ibl_v2_adapters import Adapter
    registry = dict(registry)
    registry['fixture:decision'] = Adapter({
        'version': 1,
        'params': {'items': 'List|Record|Text', 'instruction': 'Text', 'threshold': 'Number',
                   'type': 'Text', 'as': 'Text', 'criteria': 'Unknown'},
        'open_params': False, 'required': ['instruction'], 'result': 'Record',
        'effects': ['model'], 'model_reuse': {'role': 'execution'},
        'pipe_input': 'items',
    }, lambda runtime, args: decide(args), model_identity=lambda: "recorded-fixture-v1")
    return registry


def historical_source(source):
    """Explicitly replace a retired leaf inside a test; archived source is unchanged."""
    return source.replace('[table:judge]', '[fixture:decision]')
