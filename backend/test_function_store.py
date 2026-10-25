"""Atomic publication and identity boundaries of reusable functions."""
import json
from pathlib import Path
import uuid

import pytest

import function_store as store
from function_library import register, retire
from ibl_v2_store import definitions
from ibl_v2_entry import handle_request


def source(name='value', value=1):
    return f'#!ibl edition=2\n[def:{name}](){{return {value}}}'


def run(code):
    return handle_request({'edition': 2, 'code': code})


def test_registration_and_execution_without_memory():
    ref = register('value', source())
    assert ref['function_id'] and len(ref['revision']) == 64
    assert run('[fn:value]{}')['value'] == 1
    assert definitions().references['value'] == ref


def test_compare_and_swap_and_old_revision():
    first = register('value', source())
    second = register('value', source(value=2), expected_revision=first['revision'])
    assert first['function_id'] == second['function_id']
    assert store.revision(first['function_id'], first['revision'])['source'] == source()
    with pytest.raises(ValueError, match='판본 충돌'):
        register('value', source(value=3), expected_revision=first['revision'])
    assert run('[fn:value]{}')['value'] == 2


def test_seed_does_not_overwrite_changed_function():
    first = register('value', source())
    assert register('value', source()) == first
    with pytest.raises(ValueError, match='명시적으로'):
        register('value', source(value=2))


def test_transitive_caller_blocks_breaking_change():
    a = register('a', '#!ibl edition=2\n[def:a]($x){return $x}')
    register('b', '#!ibl edition=2\n[def:b](){return [fn:a]{x:1}}')
    register('c', '#!ibl edition=2\n[def:c](){return [fn:b]{}}')
    with pytest.raises(ValueError, match='호출자'):
        register('a', '#!ibl edition=2\n[def:a]($y){return $y}', expected_revision=a['revision'])
    with pytest.raises(ValueError, match='호출자'):
        retire('a')
    assert run('[fn:c]{}')['value'] == 1


def test_retirement_preserves_history_but_stops_new_calls():
    ref = register('value', source())
    assert retire('value')
    assert 'value' not in definitions()
    assert store.revision(ref['function_id'], ref['revision'])['source'] == source()
    from function_library import reference_library
    with pytest.raises(ValueError, match='retired'):
        reference_library([ref])


def test_corrupt_one_revision_does_not_hide_other_functions():
    ref = register('a', source('a'))
    register('b', source('b', 2))
    path = store.storage_root() / 'revisions' / ref['function_id'] / (ref['revision'] + '.yaml')
    path.write_text('source: corrupted')
    assert 'a' in definitions().conflicts
    assert run('[fn:b]{}')['value'] == 2
    assert not run('[fn:a]{}')['success']


def test_catalog_corruption_never_falls_back_to_legacy_files():
    register('value', source())
    (store.storage_root() / 'catalog.json').write_text('{')
    with pytest.raises(ValueError):
        definitions()


def test_interrupted_publication_keeps_old_catalog(monkeypatch):
    first = register('value', source())
    original = store._atomic

    def fail_catalog(path, content):
        if path.name == 'catalog.json':
            raise OSError('interrupted before publication')
        return original(path, content)

    monkeypatch.setattr(store, '_atomic', fail_catalog)
    with pytest.raises(OSError):
        register('value', source(value=2), expected_revision=first['revision'])
    assert store.resolve('value')['revision'] == first['revision']


def test_exact_request_retry_after_response_loss():
    record = {'schema': 1, 'function_id': uuid.uuid4().hex, 'name': 'value',
              'edition': 2, 'source': source(), 'description': '', 'origin': 'user'}
    changes = [{'record': record, 'expected_revision': None}]
    result = store.publish(changes, request_id='a')
    assert store.publish(changes, request_id='a') == result
    changes[0]['record']['source'] = source(value=3)
    with pytest.raises(ValueError, match='요청 ID'):
        store.publish(changes, request_id='a')


def test_batch_change_validates_resulting_library():
    a = register('a', '#!ibl edition=2\n[def:a]($x){return $x}')
    b = register('b', '#!ibl edition=2\n[def:b](){return [fn:a]{x:1}}')
    changes = []
    for ref, code in [(a, '#!ibl edition=2\n[def:a]($y){return $y}'),
                      (b, '#!ibl edition=2\n[def:b](){return [fn:a]{y:2}}')]:
        row = store.revision(ref['function_id'], ref['revision'])
        row.pop('revision')
        row['source'] = code
        changes.append({'record': row, 'expected_revision': ref['revision']})
    store.publish(changes)
    assert run('[fn:b]{}')['value'] == 2


def test_stale_memory_is_a_reference_not_a_definition():
    ref = register('value', source())
    register('value', source(value=2), expected_revision=ref['revision'])
    row = store.project_memory({'ibl_code': 'obsolete', 'provenance': {'function_ref': ref}})
    assert row['evidence_stale']
    assert row['ibl_code'] == source(value=2)
    assert store.resolve('value')['source'] != 'obsolete'


def test_scope_is_not_selected_by_untrusted_reference(tmp_path, monkeypatch):
    ref = register('value', source())
    import workflow_store
    monkeypatch.setattr(workflow_store, '_get_workflows_path', lambda: tmp_path / 'other')
    from function_library import reference_library
    with pytest.raises(ValueError, match='찾을 수'):
        reference_library([ref])


def test_pinned_execution_and_resume_use_original_revision():
    first = register('value', source())
    result = run('[fn:value]{}')
    register('value', source(value=2), expected_revision=first['revision'])
    fixed = handle_request({'edition': 2, 'code': '[fn:value]{}', 'function_refs': [first]})
    assert fixed['value'] == 1
    resumed = handle_request({'edition': 2, 'code': '[fn:value]{}', 'resume': result['resume']})
    assert resumed['success'], resumed
    assert resumed['value'] == 1
    assert run('[fn:value]{}')['value'] == 2


def test_pinned_closure_does_not_use_current_missing_dependency():
    register('a', source('a'))
    b = register('b', '#!ibl edition=2\n[def:b](){return [fn:a]{}}')
    result = handle_request({'edition': 2, 'code': '[fn:b]{}', 'function_refs': [b]})
    assert not result['success']


def test_function_statistics_do_not_follow_body_strings():
    from capability_history import function_statistics
    first = register('value', source())
    result = run('[fn:value]{}')
    assert function_statistics(first)['success_count'] == 1
    resumed = handle_request({'edition': 2, 'code': '[fn:value]{}', 'resume': result['resume']})
    assert resumed['success']
    assert function_statistics(first)['success_count'] == 1
    second = register('value', source(value=2), expected_revision=first['revision'])
    assert function_statistics(second)['success_count'] == 0


def test_public_save_is_reentrant_and_request_retry_is_idempotent():
    from ibl_v2_store import action
    args = {'code': source(), 'request_id': 'public-create'}
    first = action('save', args, '.')
    assert first['success'], first
    assert action('save', args, '.')['function_ref'] == first['function_ref']
    different = action('save', {**args, 'code': source(value=2)}, '.')
    assert not different['success']


def test_concurrent_writers_cannot_both_publish_same_expected_revision():
    from concurrent.futures import ThreadPoolExecutor
    first = register('value', source())
    def change(value):
        try:
            register('value', source(value=value), expected_revision=first['revision'])
            return True
        except ValueError:
            return False
    with ThreadPoolExecutor(2) as pool:
        assert sum(pool.map(change, [2, 3])) == 1


def test_approval_digest_binds_exact_function_revision():
    from approval_tokens import request_digest
    first = register('value', source())
    second = register('value', source(value=2), expected_revision=first['revision'])
    assert request_digest('[fn:value]{}', function_refs=[first]) != request_digest('[fn:value]{}', function_refs=[second])


def test_held_function_has_no_legacy_or_memory_escape():
    ref = register('value', source())
    register('value', source(), expected_revision=ref['revision'], state='hold')
    assert not run('[fn:value]{}')['success']
    assert not handle_request({'edition': 2, 'code': '[fn:value]{}', 'function_refs': [ref]})['success']
    row = store.project_memory({'ibl_code': source(), 'provenance': {'function_ref': ref}})
    assert row['function_problem']


def test_repair_workspace_does_not_read_owner_catalog(tmp_path):
    from thread_context import repair_workspace_scope
    register('value', source())
    with repair_workspace_scope(str(tmp_path / 'repair')):
        assert store.resolve('value') is None
    assert store.resolve('value')


def test_stored_app_inputs_do_not_hide_breaking_function_revision(tmp_path, monkeypatch):
    import workflow_store
    monkeypatch.setattr(workflow_store, '_get_workflows_path', lambda: tmp_path / 'data/workflows')
    first = register('value', '#!ibl edition=2\n[def:value]($x){return $x}')
    folder = tmp_path / 'data/instruments'
    folder.mkdir(parents=True)
    (folder / 'app.yaml').write_text('edition: 2\naction: "[fn:value]{x:$choice}"')
    with pytest.raises(ValueError, match='저장 소비자'):
        register('value', '#!ibl edition=2\n[def:value]($y){return $y}', expected_revision=first['revision'])


def test_memory_projection_keeps_new_revision_observations_separate():
    from capability_history import record_function_call
    first = register('value', source())
    second = register('value', source(value=2), expected_revision=first['revision'])
    record_function_call(second, 'actual', '1', success=True, dependency_revision='body',
                         observed={'kind': 'record', 'keys': ['current']})
    row = store.project_memory({'ibl_code': source(), 'returns_observed': 'old',
                                'provenance': {'function_ref': first}})
    assert row['evidence_stale'] and row['success_count'] == 1
    assert 'current' in row['returns_observed'] and 'old' not in row['returns_observed']


def test_legacy_registration_is_rejected_before_publication():
    before = store.catalog()
    with pytest.raises(ValueError, match='EDITION_UNSUPPORTED'):
        register('old', '$return = $x', edition=1)
    assert store.catalog() == before


def test_retired_identity_does_not_shadow_a_new_identity():
    first = register('value', source())
    retire('value')
    second = register('value', source(value=2), function_id=uuid.uuid4().hex)
    assert second['function_id'] != first['function_id']
    assert run('[fn:value]{}')['value'] == 2
    from function_library import reference_library
    with pytest.raises(ValueError, match='retired'):
        reference_library([first])


def test_memory_reference_cannot_cross_scope():
    ref = register('value', source())
    ref['scope_id'] = 'other-owner'
    row = store.project_memory({'ibl_code': 'historical', 'provenance': {'function_ref': ref}})
    assert row.get('function_problem')
    assert row['ibl_code'] == 'historical'


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))


def test_regular_snapshot_and_execution_do_not_read_history(tmp_path, monkeypatch):
    import function_store
    from function_library import register, compile_current
    from pathlib import Path
    ref=register('current', '#!ibl edition=2\n[def:current](){return 3}')
    root=function_store.storage_root()
    (root/'history.json').write_text('invalid historical index')
    original=Path.read_text
    def read(path,*args,**kwargs):
        assert path.name!='history.json', 'normal execution consulted history'
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'read_text',read)
    assert function_store.resolve('current')['function_id']==ref['function_id']
    assert compile_current('[fn:current]{}').report()['ok']


def test_history_detail_name_does_not_resolve_current_catalog(monkeypatch):
    import function_store
    import workflow_engine
    historical={'function_id':'old', 'name':'historic', 'source':'unparseable', 'legacy_ids':[]}
    monkeypatch.setattr(function_store,'history_snapshot',lambda: {'records':{'old':historical}})
    monkeypatch.setattr(function_store,'snapshot',lambda: pytest.fail('history looked up active catalog'))
    out=workflow_engine.execute_workflow_action('detail',{'name':'historic','history':True},'.')
    assert out['source']=='unparseable' and out['runnable'] is False
