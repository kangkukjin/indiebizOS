"""Function mutation validates and commits one post-edit namespace."""
import boot_paths  # noqa: F401
from concurrent.futures import ThreadPoolExecutor
import threading

import pytest
import ibl_v2_store
import workflow_store
from test_imagination_round71_repairs import store, save, run, PROJECT  # noqa: F401


def test_compiler_finds_spaced_transitive_calls(store):
    assert save('[def:base]($x){return $x}')['success']
    assert save('[def:middle]($x){return [fn : base]{x:$x}}')['success']
    assert save('[def:outer]($x){return [fn : middle]{x:$x}}')['success']
    result = save('[def:base]($y){return $y}')
    assert not result['success']
    assert {x['name'] for x in result['broken_callers']} == {'middle', 'outer'}
    from workflow_engine import execute_workflow_action
    assert not execute_workflow_action('delete', {'workflow_id': 'base'}, PROJECT)['success']


def test_call_strings_and_local_shadowing_are_not_dependencies(store):
    save('[def:base]($x){return $x}')
    save('[def:text](){return "[fn:base]{x:1}"}')
    save('[def:local](){[def:base]($x){return $x}; return [fn:base]{x:1}}')
    assert ibl_v2_store.callers(ibl_v2_store.library(), 'base') == []
    assert save('[def:base]($y){return $y}')['success']


def test_rename_validates_new_definition_against_final_namespace(store):
    save('[def:old]($x){return $x}')
    result = save('[def:new]($x){return [fn:old]{x:$x}}', workflow_id='old')
    assert not result['success']
    assert workflow_store.get_workflow('old')['name'] == 'old'
    assert run('return [fn:old]{x:4}')['value'] == 4
    assert save('[def:new]($x){return $x}', workflow_id='old')['success']


def test_same_name_concurrent_saves_commit_exactly_one(store):
    start = threading.Barrier(2)
    def create(wid):
        start.wait(timeout=10)
        return save('[def:shared]($x){return $x}', workflow_id=wid)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(create, ['one', 'two']))
    assert sorted(r['success'] for r in results) == [False, True]
    assert ibl_v2_store.library().conflicts == {}
    assert len(list(store.glob('*.yaml'))) == 1


def test_legacy_save_cannot_remove_a_current_function(store):
    from workflow_engine import execute_workflow_action
    assert save('[def:base]($x){return $x}')['success']
    assert save('[def:caller]($x){return [fn:base]{x:$x}}')['success']
    result = execute_workflow_action('save', {'workflow_id': 'base', 'name': 'base',
                                             'edition': 1, 'do': '[self:time]{}'}, PROJECT)
    assert result['success'] is False
    assert '덮어쓸 수 없습니다' in result['error']
    assert run('return [fn:caller]{x:4}')['value'] == 4


def test_concurrent_caller_save_and_callee_delete_preserve_namespace(store):
    from workflow_engine import execute_workflow_action
    save('[def:base]($x){return $x}')
    start = threading.Barrier(2)
    def mutate(which):
        start.wait(timeout=10)
        if which == 'save':
            return save('[def:caller]($x){return [fn:base]{x:$x}}')
        return execute_workflow_action('delete', {'workflow_id': 'base'}, PROJECT)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(mutate, ['save', 'delete']))
    assert sum(r['success'] for r in results) == 1
    if results[0]['success']:
        assert run('return [fn:caller]{x:4}')['value'] == 4
    else:
        assert workflow_store.get_workflow('caller') is None


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
