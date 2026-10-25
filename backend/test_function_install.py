"""Cutover is explicit, repeatable and never silently chooses conflicting bodies."""
import json
import sqlite3
import yaml
import pytest

import function_store as store
from function_library import register
from function_install import install


@pytest.fixture
def base(tmp_path, monkeypatch):
    import workflow_store
    root = tmp_path / 'owner'
    (root / 'data/workflows').mkdir(parents=True)
    monkeypatch.setattr(workflow_store, '_get_workflows_path', lambda: root / 'data/workflows')
    return root


def source(value):
    return f'#!ibl edition=2\n[def:value](){{return {value}}}'










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
    (idioms / 'installed.json').write_text(json.dumps({'value': 'value.ibl'}))
    (idioms / 'value.ibl').write_text(source(1))
    (idioms / 'old.yaml').write_text(yaml.safe_dump({'name': 'old', 'steps': '[self:time]{}'}))
    assert set(install(base)['updated']) == {'value'}
    assert install(base)['updated'] == []
    first = store.resolve('value')
    register('value', source(1), expected_revision=first['revision'], state='hold')
    (idioms / 'value.ibl').write_text(source(2))
    assert install(base)['updated'] == ['value']
    assert store.resolve('value', include_inactive=True)['state'] == 'hold'


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
