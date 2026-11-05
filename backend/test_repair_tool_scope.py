"""Owner registration, new regression tests and publication share one candidate."""
import json
import shlex
import subprocess
import sys
from pathlib import Path

import boot_paths  # noqa: F401
import api_repair_continuation  # noqa: F401 — bind real path accessor before fixture patches
import pytest
from test_repair_staging import _load_handler, _make_repo
from test_conscious_supervisor import supervisor  # noqa: F401


@pytest.fixture
def repair(tmp_path, monkeypatch, supervisor):
    import repair_policy
    import workflow_store
    from thread_context import repair_workspace_scope
    repo = _make_repo(tmp_path / 'repo')
    (repo / 'frontend').mkdir()
    (repo / 'frontend/index.html').write_text('<html>fixture</html>')
    scripts = repo / 'data/scripts'
    scripts.mkdir(parents=True)
    (scripts / 'registry.yaml').write_text('{}\n')
    functions = repo / 'data/workflows'
    functions.mkdir()
    (repo / 'backend/test_existing.py').write_text('def test_existing(): assert True\n')
    for relative, content in {'data/guides/report.md': 'OLD GUIDE',
                              'outputs/reports/rules.md': 'OLD RULES',
                              'outputs/reports/ledger.json': '[]'}.items():
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    (repo / '.gitignore').write_text('.worktrees/\ndata/system_ai_state/\ndata/restart_control/\ndata/workflows/\ndata/scripts/registry.yaml.lock\n')
    for args in (['config', 'user.name', 'Test'], ['config', 'user.email', 'test@example.test'],
                 ['add', '.'], ['commit', '-qm', 'script fixture']):
        subprocess.run(['git', *args], cwd=repo, check=True)
    handler = _load_handler()
    st = handler._staging_mod()
    monkeypatch.setattr(handler, '_REPO_ROOT', repo)
    monkeypatch.setattr(handler, '_red_grant_active', lambda: True)
    monkeypatch.setattr(handler, '_staging_key', lambda: 'script-repair')
    monkeypatch.setattr(st, '_repair_owner', lambda: 'owner')
    for name in ('get_base_path', 'get_source_root', 'get_code_root'):
        monkeypatch.setattr('runtime_utils.' + name, lambda: repo)
    monkeypatch.setattr(workflow_store, '_get_workflows_path', lambda: functions)
    monkeypatch.setenv('INDIEBIZ_FUNCTION_STORE_ROOT', str(functions))
    monkeypatch.setattr('repair_context.active', lambda: True)
    monkeypatch.setattr('red_report.current_owner', lambda: 'owner')
    monkeypatch.setattr('supervision_bus.current', lambda *args: supervisor)
    monkeypatch.setattr('red_apply._load_handler', lambda job: handler)
    from red_apply import _run_post_verify
    monkeypatch.setattr('red_apply._run_post_verify',
                        lambda root, command, **kw: _run_post_verify(root, command, live_read=False, **kw))
    supervisor.configure(repair_policy.direct_framing('Register a working calculator'), repair=True)
    supervisor.task = 'script-repair'
    session = st.ensure_session(str(repo), 'script-repair')
    session.update(program_policy=1, repair_policy=2)
    st._save_session(str(repo), session)
    wt = repo / session['worktree']
    ops = handler._load_sibling('script_ops')
    for name, value in {'_ROOT': repo, '_SCRIPT_DIR': scripts, '_REGISTRY': scripts / 'registry.yaml',
                        '_STATE': repo / 'data/system_ai_state/script_state.json',
                        '_RUN_DIR': repo / 'data/system_ai_state/script_runs',
                        '_JOB_DIR': repo / 'data/system_ai_state/script_jobs'}.items():
        monkeypatch.setattr(ops, name, value)
    from tool_context import ToolContext
    def call(name, args):
        result = handler.execute(args, ToolContext(str(repo), name, agent_id='system_ai'))
        return result if name in {'read_file', 'edit_file'} else json.loads(result)
    call.handler = handler
    with repair_workspace_scope(str(wt)):
        yield repo, wt, st, supervisor, call


def test_document_and_ledger_edits_reach_live_owner_without_code_completion(repair, monkeypatch):
    from repair_readiness import requires_code_receipts
    from thread_context import get_repair_workspace
    repo, wt, st, controller, call = repair
    # A code workspace already exists, as in a resumed REPAIR turn. Its tracked
    # guide must not hide the newly edited live guide from subsequent reads.
    monkeypatch.setattr(st, 'ensure_session', lambda *a: pytest.fail('document needs no code workspace'))
    for path in ('data/guides/report.md', str(repo / 'outputs/reports/rules.md')):
        result = call('write_file', {'path': path, 'content': 'NEW CONTENT'})
        assert result['success'] and not result.get('staged'), result
        assert call('read_file', {'path': path}) == 'NEW CONTENT'
    result = call('edit_file', {'path': '~workspace/data/guides/report.md',
                                'old_string': 'NEW CONTENT', 'new_string': 'FINAL GUIDE'})
    assert 'Successfully edited' in result, result
    assert (repo / 'data/guides/report.md').read_text() == 'FINAL GUIDE'
    assert (wt / 'data/guides/report.md').read_text() == 'OLD GUIDE'
    result = call('ledger_op', {'op': 'append', 'path': '~workspace/outputs/reports/ledger.json',
                                'item': {'id': 'new', 'decision': 'keep'}})
    assert result['success'], result
    rows = call('ledger_op', {'op': 'select', 'path': 'outputs/reports/ledger.json'})
    assert rows['items'][0]['id'] == 'new'
    assert (wt / 'outputs/reports/ledger.json').read_text() == '[]'
    assert get_repair_workspace() == str(wt)  # restore caller's code scope
    assert not requires_code_receipts(controller)


def test_single_boundary_change_controls_query_write_and_restoration(repair, monkeypatch):
    import program_boundary as policy
    from thread_context import get_repair_workspace
    repo, wt, st, controller, call = repair
    path = 'data/guides/report.md'
    assert call('patch_op', {'op': 'status', 'path': path})['items'][0]['route'] == 'file'
    with monkeypatch.context() as patch:
        patch.setitem(policy.CORE_PREFIXES, path, 'new protected contract')
        assert call('patch_op', {'op': 'status', 'path': path})['items'][0]['route'] == 'deny'
        result = call('write_file', {'path': path, 'content': 'FORBIDDEN'})
        assert not result['success'], result
        assert (repo / path).read_text() == (wt / path).read_text() == 'OLD GUIDE'
    assert get_repair_workspace() == str(wt)
    result = call('write_file', {'path': path, 'content': 'ALLOWED'})
    assert result['success'], result
    result = call('write_file', {'path': 'data/scripts/later.py', 'content': 'VALUE = 1'})
    assert result['success'] and result['staged'], result
    assert not (repo / 'data/scripts/later.py').exists()


@pytest.mark.parametrize('path', ['docs/AGENTS.md', 'outputs/.env',
                                'data/scripts/registry.yaml',
                                'data/system_ai_state/install_approvals.json'])
def test_file_owner_route_never_opens_protected_or_managed_ledger(repair, path):
    repo, wt, st, controller, call = repair
    result = call('ledger_op', {'op': 'append', 'path': path, 'item': {'id': 'forged'}})
    assert not result['success'], result
    assert not (repo / path).exists() or (repo / path).read_text() == '{}\n'


def test_document_route_checks_scope_links_and_mixed_moves_before_writing(repair, monkeypatch):
    repo, wt, st, controller, call = repair
    path = 'data/guides/report.md'
    session = st.read_session(str(repo), 'script-repair')
    session['task_scope'] = {'paths': ['data/scripts/calculator.py']}
    st._save_session(str(repo), session)
    result = call('write_file', {'path': path, 'content': 'OUTSIDE SCOPE'})
    assert not result['success'] and '범위 밖' in result['error'], result
    session.pop('task_scope')
    st._save_session(str(repo), session)
    (repo / 'outputs/link.md').symlink_to(repo / 'backend/test_existing.py')
    result = call('write_file', {'path': 'outputs/link.md', 'content': 'BROKEN'})
    assert not result['success'], result
    result = call('move_path', {'src': path, 'dest': 'backend/moved.py'})
    assert not result['success'], result
    assert (repo / path).read_text() == 'OLD GUIDE'
    assert not (repo / 'backend/moved.py').exists()


def test_explicit_candidate_artifact_stays_staged(repair):
    repo, wt, st, controller, call = repair
    # Only ignored candidate artifacts can be registered for code delivery.
    with (repo / '.git/info/exclude').open('a') as stream:
        stream.write('outputs/delivery/\n')
    path = 'outputs/delivery/readme.txt'
    result = call('write_file', {'path': str(wt / path), 'content': 'WITH CODE'})
    assert result['success'] and result['staged'], result
    assert not (repo / path).exists()
    session = st.read_session(str(repo), 'script-repair')
    st._candidate.register_artifacts(str(repo), session, [path])
    st._candidate.collect(str(repo), session)
    assert path in session['artifact_paths']


def test_resumed_document_work_preserves_criteria_without_repeating_code_apply(repair):
    import copy
    import repair_continuation as journal
    from repair_readiness import completion_error
    repo, wt, st, controller, call = repair
    row = {'task_id': 'script-repair', 'root_task_id': 'script-repair',
           'staging_task_id': 'script-repair', 'phase': 'execution',
           'worktree': str(wt), 'authorized_origin': 'user',
           'criteria_contract': {'criteria': [{'id': 'C1', 'text': '개정 가이드의 운영 조회'}]},
           'next_instruction': '기존 조사와 기준을 보존해 문서 개정을 완료한다'}
    before = copy.deepcopy(row)
    with journal.resuming(row):
        result = call('write_file', {'path': 'data/guides/report.md', 'content': 'RESUMED GUIDE'})
        assert result['success'] and not result.get('staged'), result
        assert call('read_file', {'path': 'data/guides/report.md'}) == 'RESUMED GUIDE'
        assert completion_error(controller) is None
    assert row == before


def test_document_only_turn_does_not_create_repair_session(repair, monkeypatch):
    import system_tools
    from thread_context import repair_workspace_scope
    repo, wt, st, controller, call = repair
    record = repo / 'data/system_ai_state/repair_sessions/script-repair.json'
    record.unlink()
    monkeypatch.setattr(st, 'ensure_session', lambda *a: pytest.fail('unexpected code session'))
    result = call('write_file', {'path': 'data/guides/report.md', 'content': 'NO CODE SESSION'})
    assert result['success'], result
    assert call('read_file', {'path': 'data/guides/report.md'}) == 'NO CODE SESSION'
    assert not record.exists()
    # Exercise the real outer dispatcher, whose lazy scope used to create a
    # candidate before the file owner had seen any target path.
    monkeypatch.setattr(system_tools, 'load_tool_handler', lambda name: call.handler)
    monkeypatch.setattr('tool_loader.load_tool_handler', lambda name: call.handler)
    monkeypatch.setattr('repair_execution_scope.active', lambda: True)
    with repair_workspace_scope(None):
        result = system_tools.execute_tool('write_file',
            {'path': 'data/guides/report.md', 'content': 'DISPATCHED CONTENT'},
            str(repo), agent_id='worker')
    assert json.loads(result)['success'], result
    assert (repo / 'data/guides/report.md').read_text() == 'DISPATCHED CONTENT'
    assert not record.exists()


@pytest.mark.parametrize('restriction', ['cancelled', 'activation'])
def test_document_route_preserves_turn_lifetime_restrictions(repair, monkeypatch, restriction):
    repo, wt, st, controller, call = repair
    if restriction == 'cancelled':
        monkeypatch.setattr('repair_continuation.current', lambda: {'root_task_id': 'cancelled-task'})
        monkeypatch.setattr('repair_continuation.cancelled', lambda *a: True)
    else:
        monkeypatch.setattr('repair_context.activation_only', lambda: True)
    result = call('write_file', {'path': 'data/guides/report.md', 'content': 'MUST NOT WRITE'})
    assert not result['success'], result
    assert (repo / 'data/guides/report.md').read_text() == 'OLD GUIDE'


def test_document_folder_operation_cannot_remove_nested_protected_contract(repair):
    repo, wt, st, controller, call = repair
    protected = repo / 'outputs/reports/AGENTS.md'
    protected.write_text('KEEP CONTRACT')
    result = call('delete_path', {'path': 'outputs/reports', 'recursive': True})
    assert not result['success'], result
    assert protected.read_text() == 'KEEP CONTRACT'


def script_candidate(repair):
    repo, wt, st, controller, call = repair
    code = 'import json\nprint(json.dumps({"value": 42}))\n'
    assert call('write_file', {'path': 'data/scripts/fresh.py', 'content': code})['success']
    result = call('script_op', {'op': 'register', 'id': 'fresh',
                              'path': 'data/scripts/fresh.py', 'expected_revision': ''})
    assert result['success'] and result['staged'] and not result['applied'], result
    return result


def test_registered_candidate_accepts_new_test_checks_and_commits(repair, monkeypatch):
    repo, wt, st, controller, call = repair
    script_candidate(repair)
    assert (repo / 'data/scripts/registry.yaml').read_text() == '{}\n'
    source = ('import json,subprocess,sys\nfrom pathlib import Path\n'
              'def test_new_behavior():\n'
              ' result=subprocess.check_output([sys.executable,"data/scripts/fresh.py"],text=True)\n'
              ' assert json.loads(result)=={"value":42}\n')
    result = call('write_file', {'path': 'backend/test_fresh_script.py', 'content': source})
    assert result['success'], result
    monkeypatch.setattr(st, '_schedule_deferred_apply', lambda *a: pytest.fail('unnecessary worker restart'))
    # Use the actual apply entry point: plan, gates, owner publication, live
    # probe and exact commit. No preparation result or activation is mocked.
    result = st.op_apply({'_repo_root': str(repo), '_grant_key': 'script-repair',
        'verification_plan': [{'criterion_id': 'C1', 'command': shlex.quote(sys.executable) +
                               ' -m pytest backend/test_fresh_script.py'}],
        'active_verify_cmd': shlex.quote(sys.executable) + ' data/scripts/fresh.py'})
    session = st.read_session(str(repo), 'script-repair')
    assert result['success'] and result['activated'] and not result['restart_required'], json.dumps(result, ensure_ascii=False)
    assert session['activation_checks']['active_verify_cmd']['state'] == 'passed'
    assert st._candidate.active_generation_bytes(repo, session)[0] == 'matched'
    from repair_readiness import program_published
    assert program_published(repo, session)
    assert subprocess.check_output([sys.executable, str(repo / 'data/scripts/fresh.py')], text=True).strip() == '{"value": 42}'
    assert 'fresh' in (repo / 'data/scripts/registry.yaml').read_text()
    # The committed test is part of this exact repair, not a weakened old test.
    assert subprocess.check_output(['git', 'show', result['commit']['commit'] + ':backend/test_fresh_script.py'], cwd=repo).decode() == source


@pytest.mark.parametrize('path', ['backend/conftest.py', 'data/scripts/registry.yaml'])
def test_protected_write_is_rejected_before_mutation_and_does_not_poison_candidate(repair, path):
    repo, wt, st, controller, call = repair
    script_candidate(repair)
    before = (wt / path).read_bytes() if (wt / path).exists() else None
    result = call('write_file', {'path': path, 'content': 'broken'})
    assert not result['success'], result
    assert ((wt / path).read_bytes() if (wt / path).exists() else None) == before
    st._candidate.collect(str(repo), st.read_session(str(repo), 'script-repair'))


def test_manual_registry_edit_cannot_borrow_an_owner_receipt(repair):
    repo, wt, st, controller, call = repair
    script_candidate(repair)
    (wt / 'data/scripts/registry.yaml').write_text('forged: {}\n')
    with pytest.raises(PermissionError, match='직접 변경'):
        st._candidate.collect(str(repo), st.read_session(str(repo), 'script-repair'))


def test_failed_registration_preserves_receipt_and_candidate(repair):
    repo, wt, st, controller, call = repair
    script_candidate(repair)
    before = (wt / 'data/scripts/registry.yaml').read_bytes()
    original = st.read_session(str(repo), 'script-repair')['managed_files']
    result = call('script_op', {'op': 'register', 'id': 'fresh',
                              'path': 'data/scripts/fresh.py', 'expected_revision': 'stale'})
    assert not result['success'], result
    session = st.read_session(str(repo), 'script-repair')
    assert session['managed_files'] == original
    assert (wt / 'data/scripts/registry.yaml').read_bytes() == before
    st._candidate.collect(str(repo), session)
    # A second official change replaces the exact receipt, rather than creating
    # permission for arbitrary registry edits.
    result = call('script_op', {'op': 'register', 'id': 'fresh',
                              'path': 'data/scripts/fresh.py', 'description': 'revised'})
    assert result['success'], result
    session = st.read_session(str(repo), 'script-repair')
    st._candidate.collect(str(repo), session)
    assert session['managed_files'] != original


def test_failed_managed_operation_rolls_back_partial_resource_write(repair):
    from test_repair_workspace_completion import module
    repo, wt, st, controller, call = repair
    script_candidate(repair)
    path = wt / 'data/scripts/registry.yaml'
    before = path.read_bytes()
    def fail():
        path.write_text('partial: {}\n')
        raise OSError('publication interrupted')
    with pytest.raises(OSError, match='interrupted'):
        module('repair_tool_scope').managed_write(st, str(repo), 'script-repair', fail)
    assert path.read_bytes() == before
    st._candidate.collect(str(repo), st.read_session(str(repo), 'script-repair'))


def test_managed_write_rolls_back_out_of_scope_registry_change(repair):
    import yaml
    from test_repair_workspace_completion import module
    repo, wt, st, controller, call = repair
    script_candidate(repair)
    session = st.read_session(str(repo), 'script-repair')
    session['task_scope'] = {'paths': ['data/scripts/fresh.py']}
    st._save_session(str(repo), session)
    path = wt / 'data/scripts/registry.yaml'
    before = path.read_bytes()
    def change_outside():
        registry = yaml.safe_load(before)
        registry['outside'] = {'file': 'other.py'}
        path.write_text(yaml.safe_dump(registry))
        return {'success': True}
    with pytest.raises(PermissionError, match='범위 밖'):
        module('repair_tool_scope').managed_write(st, str(repo), 'script-repair', change_outside)
    assert path.read_bytes() == before
    assert st.read_session(str(repo), 'script-repair')['managed_files'] == session['managed_files']


def test_bound_execution_maintains_tests_in_the_same_candidate(repair):
    import execution_turn
    repo, wt, st, controller, call = repair
    token = execution_turn._current.set(execution_turn.Binding(controller.runner, 'worker', 'script-repair'))
    try:
        result = call('write_file', {'path': 'backend/test_bound_script.py',
                                    'content': 'def test_value(): assert 1 + 1 == 2\n'})
        assert result['success'], result
        assert not (repo / 'backend/test_bound_script.py').exists()
        original = (repo / 'backend/test_existing.py').read_bytes()
        changed = call('write_file', {'path': 'backend/test_existing.py',
                                      'content': 'def test_existing(): assert 2 == 2\n'})
        assert changed['success'], changed
        assert (repo / 'backend/test_existing.py').read_bytes() == original
        assert not call('write_file', {'path': 'backend/base/program_boundary.py', 'content': 'bypass'})['success']
    finally:
        execution_turn._current.reset(token)


@pytest.mark.parametrize("owner", [True, False])
def test_noncore_repair_pipeline_reaches_registration_apply_and_commit(repair, monkeypatch, owner):
    """The old needs_repair:false branch stranded this same executor at apply."""
    import associative_recall
    import red_grant
    import thread_context as tc
    from agent_pipeline import CognitivePipelineMixin
    from test_conscious_supervisor import verdict
    repo, wt, st, controller, call = repair
    handler = __import__('red_apply')._load_handler({'repo': str(repo)})
    monkeypatch.setattr(handler, '_red_grant_active',
                        lambda: red_grant.active_grant(task_id=tc.get_current_task_id()))
    monkeypatch.setattr('principal.is_owner', lambda: owner)
    framing = {**controller.framing, 'needs_repair': False}

    class Runner(CognitivePipelineMixin):
        config = {'name': 'worker', 'id': 'worker'}
        project_path = repo
        _associate = associative_recall.stub()
        _decide_request_type = lambda *a: ('REPAIR', None)
        _tag_override = lambda *a: None
        _run_consciousness_or_reuse = lambda *a, **kw: framing
        _consciousness_clarification = lambda *a: None
        _extract_achievement_criteria = lambda *a: ''
        _load_role = lambda self: ''
        _build_system_prompt_split = lambda *a: ('stable', '')
        _apply_consciousness_to_history = lambda self, history, co: history
        _after_response_async = lambda *a, **kw: None

    results = []
    def execute(**kwargs):
        if not owner:
            assert not red_grant.active_grant(task_id='script-repair')
            assert not controller.repair_granted
            assert not call('patch_op', {'op': 'apply'})['success']
            yield {'type': 'final', 'content': '소유자 실행 권한 없음'}
            return
        assert red_grant.active_grant(task_id='script-repair')
        assert controller.repair_granted
        script_candidate(repair)
        source = ('import json,subprocess,sys\n'
                  'def test_value():\n'
                  ' assert json.loads(subprocess.check_output([sys.executable,"data/scripts/fresh.py"])) == {"value":42}\n')
        assert call('write_file', {'path': 'backend/test_pipeline_script.py', 'content': source})['success']
        # A live grant must never open the core or the registry to file writes.
        for path in ('backend/base/program_boundary.py', 'backend/cognition/agent_pipeline.py',
                     'data/scripts/registry.yaml'):
            assert not call('write_file', {'path': path, 'content': 'bypass'})['success']
        result = call('patch_op', {'op': 'apply', 'verification_plan': [
            {'criterion_id': 'C1', 'command': shlex.quote(sys.executable) +
             ' -m pytest backend/test_pipeline_script.py'}],
             'active_verify_cmd': shlex.quote(sys.executable) + ' data/scripts/fresh.py'})
        assert result['success'] and result['activated'], result
        results.append(result)
        yield {'type': 'final', 'content': '프로그램 적용·활성·각인 완료'}

    runner = Runner()
    runner.ai = controller.runner.ai
    runner.ai._provider = None
    runner.ai.process_message_stream = execute
    controller.runner = runner
    monkeypatch.setattr('system_ai_core._switch_to_role', lambda *a: None)
    monkeypatch.setattr('final_evaluator.invoke', lambda c, *a, **kw: verdict(c))
    import execution_turn
    token = execution_turn._current.set(execution_turn.Binding(runner, 'worker', 'script-repair'))
    try:
        with tc.actor_context(agent_id='worker', task_id='script-repair', origin='user'):
            events = list(runner._cognitive_stream_body('코어 수정 없이 스크립트 수리를 완료해줘', []))
            assert not [e for e in events if e['type'] == 'error'], events
            assert red_grant.active_grant(task_id='script-repair') is None
    finally:
        execution_turn._current.reset(token)
    assert len(results) == int(owner)
    if not owner:
        assert (repo / 'data/scripts/registry.yaml').read_text() == '{}\n'
        return
    from repair_readiness import program_published
    assert program_published(repo, st.read_session(str(repo), 'script-repair'))



def test_report_read_keeps_original_source_and_candidate_code_stays_separate(repair):
    repo, wt, st, controller, call = repair
    report = repo / 'data/outputs/research/report.md'
    report.parent.mkdir(parents=True)
    report.write_text('Read the report and finish the repair.\n')
    for path in [str(report), 'data/outputs/research/report.md']:
        result = call('read_file', {'path': path})
        assert 'Read the report' in str(result), result
    assert not (wt / 'data/outputs/research/report.md').exists()
    (wt / 'backend/candidate.py').write_text('CANDIDATE = True\n')
    (repo / 'backend/candidate.py').write_text('LIVE = True\n')
    assert 'CANDIDATE' in str(call('read_file', {'path': 'backend/candidate.py'}))
    assert 'CANDIDATE' in str(call('read_file', {'path': str(repo / 'backend/candidate.py')}))
    # Deleted/missing candidate implementation cannot quietly read the live source.
    (wt / 'backend/candidate.py').unlink()
    assert 'LIVE' not in str(call('read_file', {'path': 'backend/candidate.py'}))


def test_prior_owned_candidate_is_readable_but_never_a_write_destination(repair):
    repo, wt, st, controller, call = repair
    old = repo / '.worktrees/repair-old'
    (old / 'data/scripts').mkdir(parents=True)
    (old / 'data/scripts/partial.py').write_text('PARTIAL = 42\n')
    st._save_session(str(repo), {'key': 'old', 'owner': 'owner', 'status': 'staging',
                                'worktree': '.worktrees/repair-old'})
    for path in [str(old / 'data/scripts/partial.py'), '.worktrees/repair-old/data/scripts/partial.py']:
        assert 'PARTIAL = 42' in str(call('read_file', {'path': path}))
        assert not call('write_file', {'path': path, 'content': 'changed'})['success']
    st._save_session(str(repo), {'key': 'old', 'owner': 'someone_else', 'status': 'staging',
                                'worktree': '.worktrees/repair-old'})
    assert 'PARTIAL = 42' not in str(call('read_file', {'path': str(old / 'data/scripts/partial.py')}))
    assert (old / 'data/scripts/partial.py').read_text() == 'PARTIAL = 42\n'


@pytest.mark.parametrize('relative', ['../outside.txt', '.git/config'])
def test_source_reads_cannot_open_private_state_or_escape(repair, relative):
    repo, wt, st, controller, call = repair
    from test_repair_workspace_completion import module
    with pytest.raises((ValueError, PermissionError)):
        module('repair_tool_scope').source_path(st, repo, wt, Path(relative))



def test_legacy_manual_registry_is_preserved_then_only_official_entry_is_registered(repair):
    import base64
    import yaml
    repo, wt, st, controller, call = repair
    (wt / 'data/scripts/fresh.py').write_text('import json\nprint(json.dumps({"value":42}))\n')
    path = wt / 'data/scripts/registry.yaml'
    draft = 'unapproved: {file: imaginary.py}\n'
    path.write_text(draft)
    result = call('script_op', {'op': 'register', 'id': 'fresh', 'path': 'data/scripts/fresh.py'})
    assert result['success'] and result['recovered_draft'], result
    assert set(yaml.safe_load(path.read_text())) == {'fresh'}
    assert (repo / 'data/scripts/registry.yaml').read_text() == '{}\n'
    session = st.read_session(str(repo), 'script-repair')
    assert base64.b64decode(session['managed_drafts'][0]['data']).decode() == draft
    st._candidate.collect(str(repo), session)


def test_failed_legacy_registration_keeps_exact_draft(repair):
    repo, wt, st, controller, call = repair
    path = wt / 'data/scripts/registry.yaml'
    draft = 'unapproved: {file: imaginary.py}\n'
    path.write_text(draft)
    result = call('script_op', {'op': 'register', 'id': 'missing', 'path': 'data/scripts/missing.py'})
    assert not result['success']
    assert path.read_text() == draft
    assert not st.read_session(str(repo), 'script-repair').get('managed_files')



def test_restartable_host_edit_reaches_deferred_apply_after_real_candidate_check(repair, monkeypatch):
    import program_boundary
    repo, wt, st, controller, call = repair
    monkeypatch.setitem(program_boundary.RESTART_MODULES, 'host_lifetime', 'process lifetime')
    relative = 'backend/host_lifetime.py'
    result = call('write_file', {'path': relative, 'content': 'VALUE = 42\n'})
    assert result['success'], result
    test = 'import runpy\ndef test_value(): assert runpy.run_path("backend/host_lifetime.py")["VALUE"] == 42\n'
    assert call('write_file', {'path': 'backend/test_host_lifetime.py', 'content': test})['success']
    scheduled = []
    def schedule(repo, session, checks, verify, active):
        assert session['readiness']['decision']['status'] == 'APPROVED'
        assert session['sealed'][relative]['after']
        scheduled.append(session['key'])
        return {'success': True, 'scheduled': True, 'worktree': session['worktree']}
    monkeypatch.setattr(st, '_schedule_deferred_apply', schedule)
    result = call('patch_op', {'op': 'apply', 'verification_plan': [
        {'criterion_id': 'C1', 'command': shlex.quote(sys.executable) +
         ' -m pytest backend/test_host_lifetime.py'}]})
    assert result['success'] and result['scheduled'], json.dumps(result, ensure_ascii=False)
    assert scheduled == ['script-repair']
    assert not (repo / relative).exists()



def test_runtime_diagnostics_can_be_read_without_opening_state_writes(repair):
    repo, wt, st, controller, call = repair
    state = repo / 'data/restart_control/state.json'
    state.parent.mkdir(parents=True, exist_ok=True)
    state.write_text('{"phase":"ACTIVE"}')
    for name in (str(state), 'data/restart_control/state.json', '~workspace/data/restart_control/state.json'):
        assert 'ACTIVE' in call('read_file', {'path': name})
        assert not call('write_file', {'path': name, 'content': '{"phase":"forged"}'})['success']
    assert state.read_text() == '{"phase":"ACTIVE"}'
    assert not (wt / 'data/restart_control/state.json').exists()

if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))


def test_host_indexes_new_candidate_for_builders_without_changing_canonical_index(repair):
    repo, wt, st, controller, call = repair
    index = (repo / '.git/index').read_bytes()
    result = call('write_file', {'path': 'data/scripts/new_build_input.py', 'content': 'VALUE = 1\n'})
    assert result['success'], result
    session = st.read_session(str(repo), 'script-repair')
    st._candidate.collect(str(repo), session)
    command = ['git', 'ls-files', '--', 'data/scripts/new_build_input.py']
    assert subprocess.check_output(command, cwd=wt, text=True).strip() == 'data/scripts/new_build_input.py'
    assert not subprocess.check_output(command, cwd=repo, text=True).strip()
    assert (repo / '.git/index').read_bytes() == index
    # Existing tests are maintained in the candidate, without touching the live index.
    (wt / 'backend/test_existing.py').write_text('def test_existing(): pass\n')
    st._candidate.collect(str(repo), session)
    assert any(row['rel'] == 'backend/test_existing.py' for row in session['files'].values())
    assert (repo / '.git/index').read_bytes() == index
