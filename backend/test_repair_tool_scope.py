"""Owner registration, new regression tests and publication share one candidate."""
import json
import shlex
import subprocess
import sys
from pathlib import Path

import boot_paths  # noqa: F401
import pytest
from test_repair_staging import _load_handler, _make_repo
from test_conscious_supervisor import supervisor  # noqa: F401


@pytest.fixture
def repair(tmp_path, monkeypatch, supervisor):
    import repair_policy
    import workflow_store
    from thread_context import repair_workspace_scope
    repo = _make_repo(tmp_path / 'repo')
    scripts = repo / 'data/scripts'
    scripts.mkdir(parents=True)
    (scripts / 'registry.yaml').write_text('{}\n')
    functions = repo / 'data/workflows'
    functions.mkdir()
    (repo / 'backend/test_existing.py').write_text('def test_existing(): assert True\n')
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
    monkeypatch.setattr('supervision_bus.current', lambda: supervisor)
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
        return json.loads(handler.execute(args, ToolContext(str(repo), name, agent_id='system_ai')))
    with repair_workspace_scope(str(wt)):
        yield repo, wt, st, supervisor, call


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


@pytest.mark.parametrize('path', ['backend/test_existing.py', 'backend/conftest.py', 'data/scripts/registry.yaml'])
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


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
