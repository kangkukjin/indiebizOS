"""Ordinary ownership is the default; governance is a separate, explicit boundary."""
import boot_paths  # noqa: F401
import pytest
from program_boundary import describe, eligible
from program_dependencies import analyse, watched_paths


@pytest.mark.parametrize('path', [
    'backend/base/future_image_codec.py', 'backend/services/new_report.py',
    'data/packages/installed/tools/not-previously-known/handler.py',
    'data/packages/installed/tools/system_essentials/fs_find.py',
    'data/scripts/new_script.py', 'data/ibl_nodes_src/new_dictionary.yaml',
    'frontend/surfaces/new-app/app.js', 'data/packages/installed/tools/new/unknown.resource',
    'data/packages/installed/tools/new/script.ps1'])
def test_new_programs_need_no_allow_list_entry(path):
    assert eligible(path)
    assert describe(path)['activation']


@pytest.mark.parametrize('path', [
    'backend/base/principal.py', 'backend/cognition/final_evaluator.py',
    'backend/ibl/ibl_v2_parser.py', 'scripts/iblbuild_derive.py', 'data/vocabulary_policy.yaml',
    'backend/base/program_boundary.py', 'backend/services/restart_controller.py',
    'data/common_prompts/fragments/13_repair.md',
    'data/packages/installed/tools/system_essentials/program_apply.py',
    'data/ibl_nodes_src/self.yaml', 'backend/test_existing.py',
    'backend/base/../base/not_core.py'])
def test_program_scope_cannot_grant_itself_governance(path):
    assert not eligible(path)


def test_inputs_follow_imports_and_new_package_files_not_unrelated_features(tmp_path):
    files = {
        'data/packages/installed/tools/new/handler.py': 'import helper\n',
        'data/packages/installed/tools/new/helper.py': 'from shared import value\n',
        'backend/base/shared.py': 'value = 1\n',
        'backend/base/unrelated.py': 'value = 2\n',
        'backend/test_shared.py': 'import shared\n',
        'frontend/src/unrelated.ts': 'const unrelated = 2;\n',
    }
    for name, source in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
    scope = analyse(tmp_path, ['data/packages/installed/tools/new/helper.py'])
    assert 'backend/base/shared.py' in scope['inputs']
    assert 'backend/base/unrelated.py' not in scope['inputs']
    assert 'frontend/src/unrelated.ts' not in scope['inputs']
    added = 'data/packages/installed/tools/new/another.py'
    (tmp_path / added).write_text('value = 3')
    assert added in watched_paths(tmp_path, scope)


@pytest.mark.parametrize('kind,owner', [('idiom', 'function-store'), ('script', 'script-registry'), ('action', 'vocabulary')])
def test_managed_definitions_keep_their_publication_owner(kind, owner):
    from program_boundary import managed
    result = managed(kind, 'new-definition')
    assert result['owner'] == owner
    if kind == 'action':
        assert result['activation'] == 'vocabulary-and-implementation'
        assert result['restart_required'] is None  # determined by the implementation owner
    else:
        assert result['activation'] == 'owner-revision'
        assert result['restart_required'] is False


def test_dynamic_change_keeps_old_tests_protected_and_binds_owner_output():
    from program_boundary import change
    stamp = {'sha': 'exact', 'mode': 420}
    test = 'backend/test_new_behavior.py'
    assert change(test, None, stamp)['kind'] == 'test'
    assert not change(test, stamp, {'sha': 'edited'})['mutable']
    assert not change(test, stamp, None)['mutable']
    assert not change('backend/conftest.py', None, stamp)['mutable']
    path = 'data/scripts/registry.yaml'
    receipts = {path: {'owner': 'script-registry', 'fingerprint': stamp}}
    assert change(path, None, stamp, managed=receipts)['kind'] == 'managed'
    assert not change(path, None, {'sha': 'forged'}, managed=receipts)['mutable']
    assert not change(path, None, stamp)['mutable']
    assert not change('backend/base/repair_process_bridge.py', None, stamp)['mutable']


def test_script_helpers_and_consumers_are_part_of_dependency_inputs(tmp_path):
    files = {'data/scripts/main.py': 'import helper\n',
             'data/scripts/helper.py': 'VALUE=1\n',
             'data/scripts/unrelated.py': 'VALUE=9\n',
             'backend/test_script.py': 'TARGET="data/scripts/main.py"\n'}
    for name, source in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(source)
    scope = analyse(tmp_path, ['data/scripts/main.py'])
    assert 'data/scripts/helper.py' in scope['inputs']
    assert 'backend/test_script.py' in scope['tests']
    assert 'data/scripts/unrelated.py' not in scope['inputs']


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
