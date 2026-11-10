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
    'backend/base/principal.py', 'backend/cognition/agent_pipeline.py', 'scripts/iblbuild_derive.py', 'data/vocabulary_policy.yaml',
    'backend/base/program_boundary.py', 'backend/datastore/red_apply.py',
    'data/common_prompts/fragments/13_repair.md',
    'data/packages/installed/tools/system_essentials/program_apply.py',
    'data/ibl_nodes_src/self.yaml',
    'backend/base/../base/not_core.py'])
def test_program_scope_cannot_grant_itself_governance(path):
    assert not eligible(path)


@pytest.mark.parametrize('path', [
    'backend/ibl/ibl_v2_parser.py', 'backend/cognition/final_evaluator.py',
    'backend/cognition/prompt_builder.py', 'backend/cognition/repair_resume.py',
    'backend/cognition/repair_policy.py', 'backend/services/restart_controller.py',
    'data/packages/installed/tools/system_essentials/repair_outcomes.py',
])
def test_host_is_repairable_through_generation_not_hot_imports(path):
    from program_boundary import host_bound, requires_restart, generation_candidate, candidate_plan
    from test_repair_workspace_completion import module
    assert eligible(path)
    assert host_bound(path) and requires_restart(path)
    assert describe(path)['activation'] == 'generation-restart'
    session = {'baseline': {path: {'sha': 'old'}},
               'files': {'/repo/' + path: {'rel': path}}}
    decision = candidate_plan(session, {path: {'sha': 'new'}})
    assert not decision['protected'] and not decision['unmanaged']
    assert decision['programs'][0]['kind'] == 'host'
    assert generation_candidate(session)
    # No live publication side effects: hand off to the existing restart owner.
    assert module('program_apply').apply(None, '/repo', session) is None


def test_one_policy_update_changes_admission_publication_and_loader(monkeypatch):
    import program_boundary as policy
    import task_repair
    import program_modules
    from test_repair_workspace_completion import module
    path = 'backend/services/new_algorithm.py'
    assert not program_modules.host_bound(path)
    monkeypatch.setitem(policy.RESTART_MODULES, 'new_algorithm', 'process lifetime')
    assert task_repair.eligible(path)  # repair admission stays open
    assert program_modules.host_bound(path)
    assert policy.path_status(path, '/repo')['items'][0]['activation'] == 'generation-restart'
    session = {'files': {'/repo/' + path: {'rel': path}}}
    assert module('program_apply').apply(None, '/repo', session) is None
    monkeypatch.setitem(policy.CORE_MODULES, 'new_algorithm', 'request authority')
    assert not task_repair.eligible(path)
    assert not policy.change(path, None, {'sha': 'new'})['mutable']


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


@pytest.mark.parametrize('path', [
    'data/guides/ai_trend_report.md', 'outputs/reports/_methodology_rules.md',
    'outputs/reports/candidates.json', 'data/outputs/research/draft.md',
    'docs/design.md', 'data/system_docs/technical.md',
    '공유창고/0/게임들/1942.html', '공유창고/4/private/report.json'])
def test_document_route_is_not_program_admission_or_publication(path):
    from program_boundary import path_status, candidate_plan
    import task_repair
    item = path_status(path, '/repo')['items'][0]
    assert item['mutable'] and item['route'] == 'file'
    assert item['completion'] == 'readback'
    assert not eligible(path) and task_repair.implementation_unit(path) is None
    assert candidate_plan({'baseline': {}}, {path: {'sha': 'new'}})['unmanaged'] == [path]


@pytest.mark.parametrize('path', ['docs/AGENTS.md', 'docs/generated_templates/anatomy.md',
                                'outputs/.env', '공유창고/0/.env', '공유창고/0/AGENTS.md',
                                'data/common_prompts/fragments/13_repair.md',
                                'data/system_ai_state/repair_sessions/a.json'])
def test_content_route_cannot_shadow_protected_ownership(path):
    from program_boundary import artifact_path
    assert describe(path)['route'] == 'deny'
    assert not artifact_path(path)


def test_repository_root_has_no_single_mutable_owner():
    from program_boundary import path_status
    assert describe('.') is None and not eligible('.')
    status = path_status('.', '/repo')
    assert status['success'] and status['items'][0]['route'] == 'unmanaged'


def test_test_maintenance_and_managed_outputs_follow_their_owners():
    from program_boundary import change
    stamp = {'sha': 'exact', 'mode': 420}
    test = 'backend/test_new_behavior.py'
    assert change(test, None, stamp)['kind'] == 'test'
    assert change(test, stamp, {'sha': 'edited'})['mutable']
    assert change(test, stamp, None)['mutable']
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


def test_common_boundary_drives_task_admission_and_path_query(tmp_path, monkeypatch):
    import program_boundary as boundary
    import task_repair
    from test_repair_staging import _load_handler
    st = _load_handler()._staging_mod()
    path = 'backend/services/new_algorithm.py'
    assert task_repair.eligible(path)
    result = st.op_status({'_repo_root': str(tmp_path), 'path': path})
    assert result['items'][0]['mutable']
    monkeypatch.setitem(boundary.CORE_MODULES, 'new_algorithm', 'new authority contract')
    assert not task_repair.eligible(path)
    result = st.op_status({'_repo_root': str(tmp_path), 'path': path})
    assert result['items'][0]['reason'] == 'new authority contract'
    assert not result['items'][0]['mutable']
    assert not (tmp_path / 'data/system_ai_state').exists()
    assert not st.op_status({'_repo_root': str(tmp_path), 'path': '../outside.py'})['success']
    assert not st.op_status({'_repo_root': str(tmp_path), 'path': '/tmp/outside.py'})['success']
    assert boundary.describe('data/scripts/registry.yaml')['kind'] == 'managed'
    assert boundary.describe('backend/test_existing.py')['kind'] == 'test'


def test_task_scope_accepts_only_exact_managed_receipt(monkeypatch):
    import task_repair
    monkeypatch.setattr('repair_continuation.current', lambda: None)
    path = 'data/scripts/registry.yaml'
    after = {'sha': 'official', 'mode': 420}
    session = {'baseline': {}, 'task_scope': {'paths': ['data/scripts/calculator.py']},
               'managed_files': {path: {'owner': 'script-registry', 'fingerprint': after}}}
    task_repair.check_delta(session, [path], current={path: after})
    with pytest.raises(PermissionError, match='범위 밖'):
        task_repair.check_delta(session, [path])
    with pytest.raises(PermissionError, match='범위 밖'):
        task_repair.check_delta(session, [path], current={path: {'sha': 'manual'}})


def test_planner_and_executor_receive_the_same_boundary_guidance(tmp_path, monkeypatch):
    import program_boundary
    from consciousness_agent import ConsciousnessAgent
    from prompt_builder import _repair_turn_block
    from types import SimpleNamespace
    monkeypatch.setattr(program_boundary, 'guidance', lambda: 'CURRENT_BOUNDARY_CONTRACT')
    monkeypatch.setattr('runtime_utils.get_base_path', lambda: tmp_path)
    monkeypatch.setattr('prompt_builder.get_system_structure_core', lambda: '')
    monkeypatch.setattr('red_grant.active_grant', lambda **kw: {'task_id': 'test'})
    agent = object.__new__(ConsciousnessAgent)
    agent._load_prompt()
    executor = _repair_turn_block(SimpleNamespace(_load_file=lambda p: 'execution doctrine'))
    assert 'CURRENT_BOUNDARY_CONTRACT' in agent._supervisor_prompt
    assert 'CURRENT_BOUNDARY_CONTRACT' in executor


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))


@pytest.mark.parametrize('path', ['backend/test_existing.py', 'frontend/tests/ui.test.js',
                                 'scripts/tests/test_build.py'])
def test_test_sources_can_be_added_edited_and_removed(path):
    from program_boundary import change
    for before, after in [(None, {'sha': 'new'}), ({'sha': 'old'}, {'sha': 'new'}), ({'sha': 'old'}, None)]:
        result = change(path, before, after)
        assert result['route'] == 'workspace' and result['kind'] == 'test'
