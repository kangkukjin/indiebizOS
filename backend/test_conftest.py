"""Cached installation setup must keep every consumer's writable catalog isolated."""
import json

import boot_paths  # noqa: F401
import pytest


@pytest.mark.parametrize('mutation', ['catalog', 'revision'])
def test_installed_catalog_starts_pristine_after_other_test_mutation(
        installed_functions, _installed_function_seed, mutation):
    import function_store

    root = installed_functions
    # Both cases start with the exact certified seed, including after the
    # preceding case corrupts its private copy. No hardlinks or mutable cache.
    for relative, contents in _installed_function_seed:
        assert (root / relative).read_bytes() == contents
    view = function_store.snapshot()
    assert view['records'] and not any('problem' in r for r in view['records'].values())
    row = next(iter(view['records'].values()))
    if mutation == 'catalog':
        path = root / 'catalog.json'
        data = json.loads(path.read_text())
        data['functions'][row['function_id']]['state'] = 'hold'
        path.write_text(json.dumps(data))
        with pytest.raises(ValueError, match='hold'):
            function_store.resolve(row['name'])
    else:
        path = root / 'revisions' / row['function_id'] / (row['revision'] + '.yaml')
        path.write_text('corrupted: true\n')
        assert 'problem' in function_store.snapshot()['records'][row['function_id']]


def test_cloned_installation_accepts_real_publication(installed_functions):
    import function_store
    from function_library import register

    before = function_store.snapshot()
    result = register('fixture_added', '#!ibl edition=2\n[def:fixture_added](){return 7}', edition=2)
    assert result['name'] == 'fixture_added'
    after = function_store.snapshot()
    assert after['generation'] == before['generation'] + 1
    assert len(after['records']) == len(before['records']) + 1
    assert function_store.resolve('fixture_added')['scope_id'] == function_store.catalog()['scope_id']


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
