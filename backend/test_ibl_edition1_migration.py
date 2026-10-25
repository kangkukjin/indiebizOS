"""Retirement migration: immutable history, crash recovery and owner CAS."""
import importlib.util
import json
from pathlib import Path
import sys
import uuid

import pytest
import function_store as store
from ibl_v2_entry import handle_request

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def migration(monkeypatch):
    monkeypatch.syspath_prepend(str(ROOT / 'scripts'))
    import migrate_ibl_edition1
    return migrate_ibl_edition1


@pytest.fixture
def asset(tmp_path, monkeypatch, migration):
    root = tmp_path / 'data' / 'workflows'
    monkeypatch.setattr(store, '_root_provider', lambda **kw: root)
    record = {'schema': 1, 'function_id': uuid.uuid4().hex, 'name': '최신파일읽기',
              'edition': 1, 'source': '[self:read]{}', 'origin': 'user'}
    # Fixture represents an existing historical catalog, not an authorized writer.
    with monkeypatch.context() as m:
        m.setattr(store, '_validator', lambda *a: None)
        ref = store.publish([{'record': record, 'expected_revision': None}])['functions'][0]
    control = tmp_path / 'data/restart_control/state.json'
    control.parent.mkdir(parents=True)
    control.write_text(json.dumps({'phase': 'STOPPED'}))
    return tmp_path, ref


def test_migration_preserves_revision_and_uses_new_identity(asset, migration):
    base, old = asset
    history = store.revision(old['function_id'], old['revision'])
    plan = migration.apply(base, base / 'data/_backups/retirement')
    current = store.resolve('최신파일읽기', edition=2)
    assert current['function_id'] != old['function_id']
    assert store.revision(old['function_id'], old['revision']) == history
    assert store.catalog()['functions'][old['function_id']]['state'] == 'retired'
    assert plan['stages'] == ['published', 'retired']
    generation = store.catalog()['generation']
    assert migration.apply(base, base / 'data/_backups/retirement') == plan
    assert store.catalog()['generation'] == generation
    out = handle_request({'code': 'return 1', 'edition': 2, 'function_refs': [old]})
    assert not out['executed'] and 'EDITION_RETIRED' in str(out)


def test_response_loss_after_catalog_publish_resumes_once(asset, migration, monkeypatch):
    base, old = asset
    atomic = store._atomic
    fail = [True]
    def save(path, content):
        if path.name == 'retirement-batch.json' and '"published"' in content and fail[0]:
            fail[0] = False
            raise OSError('response lost')
        return atomic(path, content)
    monkeypatch.setattr(store, '_atomic', save)
    with pytest.raises(OSError, match='response lost'):
        migration.apply(base, base / 'data/_backups/retirement')
    assert store.catalog()['migration']['edition1_retirement']['complete'] is False
    partial_generation = store.catalog()['generation']
    plan = migration.apply(base, base / 'data/_backups/retirement')
    assert plan['stages'][-1] == 'retired'
    assert store.catalog()['generation'] == partial_generation + 1


def test_migration_refuses_active_runtime(asset, migration):
    base, _ = asset
    (base / 'data/restart_control/state.json').write_text('{"phase":"ACTIVE"}')
    with pytest.raises(ValueError, match='정지'):
        migration.apply(base, base / 'data/_backups/retirement')
    assert len(store.snapshot()['records']) == 1


def test_consumer_cas_does_not_overwrite_newer_value(tmp_path, migration):
    path = tmp_path / 'data/calendar_events.json'
    path.parent.mkdir(parents=True)
    path.write_text('{"events":[{"id":"new"}]}')
    with pytest.raises(ValueError, match='소비자가 변경'):
        migration.save_owner(tmp_path, {'path':'data/calendar_events.json',
            'before_hash':store.digest({'events':[]}), 'after_hash':'other'})
    assert json.loads(path.read_text())['events'][0]['id'] == 'new'


def test_saved_leaf_conversion_rejects_dynamic_or_compound(migration):
    assert migration.migrated_source('[self:script]{id:"x",args:{text:"a"}}').startswith('#!ibl edition=2')
    for source in ('[self:script]{id:"x",args:{text:"$value"}}',
                   '[self:script]{id:"x"} >> [self:time]{}', '[self:read]{path:"x"}'):
        with pytest.raises(ValueError):
            migration.migrated_source(source)


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
