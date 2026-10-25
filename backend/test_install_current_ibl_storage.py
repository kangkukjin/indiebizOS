"""Explicit transition preserves evidence and is not part of boot execution."""
import importlib.util
import json
import sqlite3
from pathlib import Path
import yaml
import pytest
import function_store as store

path = Path(__file__).resolve().parents[1] / 'scripts/install_current_ibl_storage.py'
spec = importlib.util.spec_from_file_location('install_current_ibl_storage', path)
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


def seed(root):
    folder = root / 'data/workflows'
    folder.mkdir(parents=True)
    index = {'schema':1, 'scope_id':'fixture', 'generation':4, 'functions':{}, 'requests':{}, 'migration':{'complete':True}}
    for n, edition, source in [(1, 1, 'unparseable historical source'), (2, 2, '#!ibl edition=2\n[def:current](){return 2}')]:
        fid = f'{n:032x}'
        record = {'schema':1,'function_id':fid,'scope_id':'fixture','name':f'function{n}','edition':edition,'source':source}
        rev = store.digest(record)
        target = folder / 'revisions' / fid / (rev+'.yaml')
        target.parent.mkdir(parents=True)
        target.write_text(yaml.safe_dump(record))
        index['functions'][fid] = {'name':record['name'],'edition':edition,'revision':rev,'state':'active'}
    (folder/'catalog.json').write_text(json.dumps(index))
    with sqlite3.connect(root/'data/ibl_usage.db') as db:
        db.execute('CREATE TABLE ibl_examples(id INTEGER PRIMARY KEY, alias TEXT, intent TEXT, ibl_code TEXT, provenance TEXT)')
        db.execute("INSERT INTO ibl_examples VALUES(1,'old','secret','unparseable','{}')")
        db.execute('INSERT INTO ibl_examples VALUES(2,?,?,?,?)',
                   ('current','searchable','#!ibl edition=2\nreturn 2','{}'))
    return folder, index


def test_migration_preserves_revisions_rows_and_has_explicit_history(tmp_path):
    folder, original = seed(tmp_path)
    before = {str(p):p.read_bytes() for p in folder.glob('revisions/*/*.yaml')}
    backup = tmp_path/'backup'
    result = installer.transition(tmp_path, backup)
    assert result['functions'] == result['historical_functions'] == result['examples'] == 1
    assert {str(p):p.read_bytes() for p in folder.glob('revisions/*/*.yaml')} == before
    assert store.catalog(folder)['schema'] == 2
    assert len(store.snapshot(folder)['records']) == 1
    assert next(iter(store.history_snapshot(folder)['records'].values()))['source'] == 'unparseable historical source'
    with sqlite3.connect(tmp_path/'data/ibl_usage.db') as db:
        assert db.execute('SELECT ibl_code FROM ibl_examples WHERE id=1').fetchone()[0] == 'unparseable'
        assert db.execute('SELECT id FROM ibl_current_examples').fetchall() == [(2,)]
        assert db.execute("SELECT rowid FROM ibl_current_fts WHERE ibl_current_fts MATCH 'secret'").fetchall() == []
    assert installer.transition(tmp_path, backup) == {'already_current':True}
    assert json.loads((backup/'catalog.json').read_text()) == original


def test_interruption_recovers_before_catalog_publication(tmp_path, monkeypatch):
    folder, original = seed(tmp_path)
    real = store._atomic
    def interrupt(path, content):
        if path.name == 'history.json':
            raise OSError('interrupted')
        return real(path, content)
    monkeypatch.setattr(store, '_atomic', interrupt)
    with pytest.raises(OSError):
        installer.transition(tmp_path, tmp_path/'backup')
    assert json.loads((folder/'catalog.json').read_text()) == original
    monkeypatch.setattr(store, '_atomic', real)
    assert installer.transition(tmp_path, tmp_path/'backup')['examples'] == 1


if __name__ == '__main__':
    import pytest
    raise SystemExit(pytest.main([__file__]))
