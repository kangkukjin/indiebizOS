"""Real management operations, caller protection and journal continuation."""
import importlib.util
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
import yaml

import capability_changes as changes
import function_store
from function_library import register as _register
from ibl_v2_entry import handle_request

REPO = Path(__file__).resolve().parents[1]


def register(name, source, **kwargs):
    return _register(name, source, edition=2, **kwargs)


@pytest.fixture
def body(tmp_path, monkeypatch):
    import runtime_utils
    import workflow_store
    import ibl_dependencies
    root = tmp_path / 'body'
    directory = root / 'data/scripts'
    directory.mkdir(parents=True)
    functions = root / 'data/workflows'
    functions.mkdir()
    for name in ('ibl_nodes.yaml', 'package_meta.json', 'vocabulary_policy.yaml', 'core_manifest.json',
                 'api_registry.yaml', 'packages', 'vocabulary'):
        origin = REPO / 'data' / name
        if origin.exists():
            (root / 'data' / name).symlink_to(origin, target_is_directory=origin.is_dir())
    monkeypatch.setattr(runtime_utils, 'get_base_path', lambda: root)
    monkeypatch.setattr(workflow_store, '_get_workflows_path', lambda: functions)
    monkeypatch.setenv('INDIEBIZ_FUNCTION_STORE_ROOT', str(functions))
    monkeypatch.setenv('INDIEBIZ_BASE_PATH', str(root))
    path = REPO / 'data/packages/installed/tools/system_essentials/script_ops.py'
    spec = importlib.util.spec_from_file_location('capability_script_ops_test', path)
    ops = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ops)
    for name, value in {'_ROOT': root, '_SCRIPT_DIR': directory,
                        '_REGISTRY': directory / 'registry.yaml', '_STATE': tmp_path / 'state/scripts.json',
                        '_RUN_DIR': tmp_path / 'state/script_runs', '_JOB_DIR': tmp_path / 'state/script_runs/jobs'}.items():
        monkeypatch.setattr(ops, name, value)
    (directory / 'registry.yaml').write_text('{}\n')
    # Real IBL routing uses the same package singleton; only its filesystem roots
    # differ. No management call or compiler result is mocked.
    from common.pkg_utils import load_singleton
    real_ops = load_singleton(str(path), 'script_ops')
    for name in ('_ROOT', '_SCRIPT_DIR', '_REGISTRY', '_STATE', '_RUN_DIR', '_JOB_DIR'):
        monkeypatch.setattr(real_ops, name, getattr(ops, name))
    # The planning script runs as a real child with the application's modules,
    # while its data and function catalogs remain in this temporary body.
    runner = directory / 'capability_change.py'
    runner.write_text((REPO / 'data/scripts/capability_change.py').read_text().replace(
        "str(Path(__file__).resolve().parents[2] / 'backend')", repr(str(REPO / 'backend'))))
    result = ops.op_register({'id': '능력변경', 'path': str(runner)})
    assert result['success'], result
    return root, ops


def execute(plan):
    result = handle_request({'edition': 2, 'code': plan['program']}, plan['plan']['root'])
    if not result.get('success'):
        print(json.dumps({k: result[k] for k in ('error', 'diagnostic', 'issues') if k in result},
                         ensure_ascii=False, default=str))
    return result


def test_idiom_add_update_remove_and_fresh_probes(body):
    root, _ = body
    for operation, value in [('add', 1), ('update', 2)]:
        plan = changes.plan({'kind': 'idiom', 'target': 'sample', 'operation': operation,
                             'code': f'[def:sample](){{return {value}}}',
                             'probes': [{'code': '[fn:sample]{}', 'expected': value}]})
        result = execute(plan)
        assert result['success'], result
        assert result['value']['behavior_verified'] is True
        assert result['value']['verified_probes'] == 1
        assert result['value']['applied']['function_ref']['name'] == 'sample'
        assert 'check' not in result['value']['applied']
    ref = function_store.resolve('sample')
    plan = changes.plan({'kind': 'idiom', 'target': 'sample', 'operation': 'remove'})
    result = execute(plan)
    assert result['success'], result
    assert function_store.resolve('sample', include_inactive=True)['state'] == 'retired'
    assert function_store.revision(ref['function_id'], ref['revision'])['source']


def test_script_add_update_remove_and_history(body):
    root, ops = body
    source = root / 'data/scripts/sample.py'
    source.write_text('import json,sys\nx=json.load(sys.stdin)\nprint(json.dumps({"n":x["n"]+1}))\n')
    for operation, description in [('add', 'first'), ('update', 'second')]:
        plan = changes.plan({'kind': 'script', 'target': 'sample', 'operation': operation,
                             'source': str(source), 'description': description,
                             'probes': [{'code': '[self:script]{id:"sample",args:{n:2}}', 'expected': {'n': 3}}]})
        result = execute(plan)
        assert result['success'], result
    before = ops.op_list({'id': 'sample'})['items'][0]
    result = execute(changes.plan({'kind': 'script', 'target': 'sample', 'operation': 'remove'}))
    assert result['success'], result
    assert source.is_file()
    assert ops.op_list({'id': 'sample'})['items'] == []
    assert ops._read_state()['sample']['last_run']
    assert ops.op_remove({'id': 'sample', 'expected_revision': before['revision']})['success']


def test_stale_script_write_and_candidate_bytes_are_rejected(body):
    root, ops = body
    path = root / 'data/scripts/sample.py'
    path.write_text('print("{}")')
    first = ops.op_register({'id': 'sample', 'path': str(path)})
    changed = ops.op_register({'id': 'sample', 'path': str(path), 'description': 'new',
                               'expected_revision': first['revision']})
    assert changed['success']
    assert not ops.op_remove({'id': 'sample', 'expected_revision': first['revision']})['success']
    plan = changes.plan({'kind': 'script', 'target': 'sample', 'operation': 'update', 'description': 'next'})
    path.write_text('print("changed")')
    with pytest.raises(ValueError, match='후보가 바뀌'):
        changes.operate({'op': 'check', 'plan': plan['plan']})


def test_script_caller_blocks_removal_and_contract_break(body):
    root, ops = body
    path = root / 'data/scripts/sample.py'
    path.write_text('print("{}")')
    contract = {'version': 1, 'params': {'x': 'Number'}, 'required': ['x'], 'result': 'Record',
                'effects': ['pure'], 'adapter': {'protocol': 'registered-json/1'}}
    first = ops.op_register({'id': 'sample', 'path': str(path), 'callable_contract': contract})
    assert first['success'], first
    register('caller', '[def:caller](){return [self:script]{id:"sample",args:{x:1}}}')
    assert not ops.op_remove({'id': 'sample'})['success']
    broken = {**contract, 'params': {'y': 'Number'}, 'required': ['y']}
    result = ops.op_register({'id': 'sample', 'path': str(path), 'callable_contract': broken})
    assert not result['success'] and '호출자' in result['error'], result
    assert ops._read_registry()['sample']['callable_contract'] == contract


def test_corrupt_registry_is_never_replaced(body):
    root, ops = body
    path = root / 'data/scripts/sample.py'
    path.write_text('print("{}")')
    registry = root / 'data/scripts/registry.yaml'
    registry.write_text('bad: [')
    assert not ops.op_register({'id': 'sample', 'path': str(path)})['success']
    assert registry.read_text() == 'bad: ['


def test_parallel_script_registration_preserves_both_entries(body):
    root, ops = body
    for name in ('one', 'two'):
        (root / f'data/scripts/{name}.py').write_text('print("{}")')
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda name: ops.op_register({'id': name,
            'path': str(root / f'data/scripts/{name}.py'), 'expected_revision': ''}), ['one', 'two']))
    assert all(r['success'] for r in results), results
    assert {'one', 'two'}.issubset(ops._read_registry())


def test_wrong_scope_and_function_revision_conflict(body):
    first = register('sample', '[def:sample](){return 1}')
    plan = changes.plan({'kind': 'idiom', 'target': 'sample', 'operation': 'remove'})
    register('sample', '[def:sample](){return 2}', expected_revision=first['revision'])
    from workflow_engine import execute_workflow_action
    denied = execute_workflow_action('delete', {'workflow_id': 'sample', 'expected_revision': first['revision']}, '.')
    assert not denied['success']
    with pytest.raises(ValueError, match='판본'):
        changes.operate({'op': 'check', 'plan': plan['plan']})
    plan['plan']['root'] = '/another/body'
    with pytest.raises(ValueError, match='범위'):
        changes.status(plan['plan'])


def test_definition_commit_survives_probe_failure_and_journal_resume(body):
    plan = changes.plan({'kind': 'idiom', 'target': 'sample', 'operation': 'add',
                         'code': '[def:sample](){return 1}',
                         'probes': [{'code': '[fn:sample]{}', 'expected': 2}]})
    failed = execute(plan)
    assert not failed['success'], failed
    current = function_store.resolve('sample')
    assert current and current['state'] == 'active'
    observed = changes.status(plan['plan'])
    assert observed['matches'] and not observed['behavior_verified']
    again = handle_request({'edition': 2, 'code': plan['program'], 'resume': failed['resume']}, plan['plan']['root'])
    assert not again['success']
    assert function_store.resolve('sample')['revision'] == current['revision']
    continuation = changes.operate({'op': 'verify', 'plan': plan['plan'],
                                    'probes': [{'code': '[fn:sample]{}', 'expected': 1}]})
    verified = execute(continuation)
    assert verified['success'] and verified['value']['complete'], verified
    assert function_store.resolve('sample')['revision'] == current['revision']


def test_dynamic_script_references_are_reported_not_invented(body):
    root, _ = body
    register('dynamic', '[def:dynamic]($name){return [self:script]{id:$name}}')
    from capability_consumers import references
    impact = references('script', 'any', root)
    assert impact['callers'] == [] and impact['unknown']


def test_management_uses_owner_catalog_during_candidate_planning(body, monkeypatch):
    root, _ = body
    register('sample', '[def:sample](){return 1}')
    candidate = root / 'candidate'
    candidate.mkdir()
    import thread_context
    monkeypatch.setattr(thread_context, 'get_repair_workspace', lambda *a, **k: str(candidate))
    plan = changes.plan({'kind': 'idiom', 'target': 'sample', 'operation': 'update',
                         'code': '[def:sample](){return 2}'})
    assert plan['plan']['root'] == str(candidate)
    assert plan['plan']['functions'] == str(root / 'data/workflows')
    assert function_store.resolve('sample')['source'] == '[def:sample](){return 1}'


def test_candidate_script_keeps_owner_callers(body):
    from capability_consumers import validate_script_change
    root, ops = body
    path = root / 'data/scripts/sample.py'
    path.write_text('print("1")')
    assert ops.op_register({'id': 'sample', 'path': str(path)})['success']
    register('caller', '[def:caller](){return [self:script]{id:"sample"}}')
    candidate = root / 'candidate'
    candidate.mkdir()
    with pytest.raises(ValueError, match='호출자를 먼저'):
        validate_script_change(candidate, candidate / 'data/scripts/registry.yaml',
                               ops._read_registry(), {}, 'sample', root / 'data/workflows')


def test_mixed_changes_are_ordered_and_share_real_management(body):
    root, ops = body
    script = root / 'data/scripts/sample.py'
    script.write_text('print("7")')
    plan = changes.plan({'changes': [
        {'kind': 'idiom', 'target': 'caller', 'operation': 'add',
         'code': '[def:caller](){return [self:script]{id:"sample"}}'},
        {'kind': 'script', 'target': 'sample', 'operation': 'add', 'source': str(script)}]})
    assert plan['plan']['order'] == [('script', 'sample'), ('idiom', 'caller')]
    result = execute(plan)
    assert result['success'], result
    removed = changes.plan({'changes': [
        {'kind': 'script', 'target': 'sample', 'operation': 'remove'},
        {'kind': 'idiom', 'target': 'caller', 'operation': 'remove'}]})
    assert removed['plan']['order'] == [('idiom', 'caller'), ('script', 'sample')]
    assert execute(removed)['success']


@pytest.mark.parametrize('operation', ['add', 'update', 'remove'])
def test_action_changes_keep_existing_apply_authority_and_scope(body, operation):
    root, _ = body
    path = root / 'data/ibl_nodes_src/test.yaml'
    path.parent.mkdir()
    path.write_text('nodes: {}\n')
    target = 'self:workflow' if operation == 'update' else 'sense:change_fixture'
    plan = changes.plan({'kind': 'action', 'target': target,
                         'operation': operation, 'files': [str(path)]})
    assert '[self:patch]' in plan['program'] and 'verification_plan' not in plan['program']
    assert '[self:package]' not in plan['program']  # no automatic activation selection
    assert list(plan['plan']['files']) == ['data/ibl_nodes_src/test.yaml']
    from ibl_v2_parser import parse
    parse(plan['program'])


def test_scheduled_apply_is_pending_and_not_completion():
    pending = changes.operate({'op': 'completion', 'receipt': {
        'success': True, 'scheduled': True, 'applied': False, 'do_not_wait': True}})
    assert not pending['complete'] and pending['receipt']['do_not_wait']
    done = changes.operate({'op': 'completion', 'receipt': {'success': True, 'complete': True}})
    assert done['complete']


def test_script_imprint_has_exact_paths_and_rejects_foreign_registry_changes(body):
    import subprocess
    root, ops = body
    def git(*args):
        return subprocess.run(['git', *args], cwd=root, check=True, capture_output=True, text=True).stdout
    git('init', '-q')
    git('config', 'user.email', 'test@example.test')
    git('config', 'user.name', 'Test')
    git('add', 'data/scripts/registry.yaml', 'data/scripts/capability_change.py')
    git('commit', '-qm', 'fixture')
    script = root / 'data/scripts/sample.py'
    script.write_text('print("1")')
    plan = changes.plan({'kind': 'script', 'target': 'sample', 'operation': 'add', 'source': str(script)})
    assert ops.op_register({'id': 'sample', 'path': str(script)})['success']
    (root / 'unrelated.txt').write_text('keep staged')
    git('add', 'unrelated.txt')
    program = changes.finish_plan(plan['plan'])['program']
    from capability_consumers import nodes
    call = next(n for n in nodes(program) if n.kind == 'call' and n.data['action'] == 'body')
    fields = call.data['params'].data['fields']
    paths = [n.data['value'] for n in fields['paths'].data['values']]
    assert set(paths) == {'data/scripts/registry.yaml', 'data/scripts/sample.py'}
    # Exercise the existing commit owner, only binding its repository to the fixture.
    spec = importlib.util.spec_from_file_location('change_body_test', REPO / 'data/packages/installed/tools/system_essentials/body_ops.py')
    owner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(owner)
    committed = owner.op_commit({'paths': paths, 'message': 'sample add'}, trusted_root=str(root))
    assert committed['success'], committed
    assert 'unrelated.txt' in git('diff', '--cached', '--name-only')
    assert 'sample.py' in git('show', '--pretty=', '--name-only', 'HEAD')
    assert ops.op_register({'id': 'other', 'path': str(script)})['success']
    with pytest.raises(ValueError, match='다른 등록 변경'):
        changes.finish_plan(plan['plan'])


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
