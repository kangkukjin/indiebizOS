"""Cutover is explicit, repeatable and never silently chooses conflicting bodies."""
import json
import sqlite3
import yaml
import pytest

import function_store as store
from function_library import register
from function_migration import migrate, install


@pytest.fixture
def base(tmp_path, monkeypatch):
    import workflow_store
    root = tmp_path / 'owner'
    (root / 'data/workflows').mkdir(parents=True)
    monkeypatch.setattr(workflow_store, '_get_workflows_path', lambda: root / 'data/workflows')
    return root


def source(value):
    return f'#!ibl edition=2\n[def:value](){{return {value}}}'


def seed(base, *, conflict=False):
    root = base / 'data'
    (root / 'workflows/value.yaml').write_text(yaml.safe_dump({'name': 'value', 'edition': 2, 'code': source(1)}))
    with sqlite3.connect(root / 'ibl_usage.db') as db:
        db.execute('CREATE TABLE ibl_examples(id INTEGER PRIMARY KEY, alias TEXT, intent TEXT, ibl_code TEXT, provenance TEXT, updated_at TEXT)')
        db.execute('INSERT INTO ibl_examples VALUES(1,?,?,?,?,?)', ('value', 'test', source(2 if conflict else 1), '{}', 'today'))


def test_old_sources_are_invisible_until_explicit_migration(base):
    seed(base)
    assert store.resolve('value') is None
    dry = migrate(base)
    assert dry['validated'] and dry['functions'] == 1
    assert not (base / 'data/workflows/catalog.json').exists()
    result = migrate(base, apply=True)
    assert result['applied'] and result['references'] == 1
    assert store.resolve('value')['source'] == source(1)
    backup = __import__('pathlib').Path(result['backup'])
    assert (backup / 'ibl_usage.db').exists()
    assert (backup / 'data/workflows/value.yaml').exists()
    assert not (base / 'data/workflows/value.yaml').exists()
    assert migrate(base, apply=True)['already_migrated']


def test_conflict_is_explicit_and_previous_evidence_remains_addressable(base):
    seed(base, conflict=True)
    assert migrate(base, apply=True)['conflicts']
    assert not (base / 'data/workflows/catalog.json').exists()
    migrate(base, apply=True, resolutions={'2:value': 'workflow:value'})
    with sqlite3.connect(base / 'data/ibl_usage.db') as db:
        provenance = json.loads(db.execute('SELECT provenance FROM ibl_examples').fetchone()[0])
    ref = provenance['function_ref']
    assert ref['revision'] != store.resolve('value')['revision']
    assert store.revision(ref['function_id'], ref['revision'])['source'] == source(2)
    assert provenance['legacy_statistics'] == 'legacy_unattributed'


def test_projection_interruption_recovers_without_republishing(base, monkeypatch):
    seed(base)
    import function_migration
    real = function_migration.project_references
    monkeypatch.setattr(function_migration, 'project_references', lambda *a: (_ for _ in ()).throw(OSError('crash')))
    with pytest.raises(OSError):
        migrate(base, apply=True)
    ref = store.reference(store.resolve('value'))
    monkeypatch.setattr(function_migration, 'project_references', real)
    assert migrate(base, apply=True)['references'] == 1
    assert store.reference(store.resolve('value')) == ref
    register('value', source(3), expected_revision=ref['revision'])
    assert migrate(base, apply=True)['references'] == 0


def test_install_update_does_not_overwrite_user_revision(base):
    idioms = base / 'data/idioms'
    idioms.mkdir()
    (idioms / 'installed.json').write_text(json.dumps({'value': 'value.ibl'}))
    (idioms / 'value.ibl').write_text(source(1))
    assert install(base)['updated'] == ['value']
    first = store.resolve('value')
    (idioms / 'value.ibl').write_text(source(2))
    assert install(base)['updated'] == ['value']
    assert store.resolve('value')['function_id'] == first['function_id']
    current = store.resolve('value')
    register('value', source(3), expected_revision=current['revision'])
    (idioms / 'value.ibl').write_text(source(4))
    assert install(base)['conflicts'] == ['value']
    assert store.resolve('value')['source'] == source(3)
    assert json.loads((base / 'data/workflows/install-conflicts.json').read_text())['proposals'][0]['source'] == source(4)


def test_fresh_install_with_empty_memory_and_legacy_yaml(base):
    sqlite3.connect(base / 'data/ibl_usage.db').close()
    idioms = base / 'data/idioms'
    idioms.mkdir()
    (idioms / 'installed.json').write_text(json.dumps({'value': 'value.ibl', 'old': 'old.yaml'}))
    (idioms / 'value.ibl').write_text(source(1))
    (idioms / 'old.yaml').write_text(yaml.safe_dump({'name': 'old', 'steps': '[self:time]{}'}))
    assert set(install(base)['updated']) == {'value', 'old'}
    assert install(base)['updated'] == []
    first = store.resolve('value')
    register('value', source(1), expected_revision=first['revision'], state='hold')
    (idioms / 'value.ibl').write_text(source(2))
    assert install(base)['updated'] == ['value']
    assert store.resolve('value', include_inactive=True)['state'] == 'hold'


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
