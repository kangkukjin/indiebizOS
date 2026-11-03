"""Verified ordinary package candidate -> live source, active module, exact commit."""
import subprocess
from pathlib import Path

import boot_paths  # noqa: F401
import pytest
from test_repair_staging import _load_handler, _make_repo
import program_runtime
import program_versions


@pytest.fixture
def setup(tmp_path, monkeypatch):
    repo = _make_repo(tmp_path / 'repo')
    relative = 'data/packages/installed/tools/new-feature'
    root = repo / relative
    root.mkdir(parents=True)
    (root / 'handler.py').write_text('import helper\ndef execute(value, context): return helper.value\n')
    (root / 'helper.py').write_text('value = 1\n')
    with (repo / '.gitignore').open('a') as output:
        output.write('\ndata/restart_control/\ndata/system_ai_state/\n')
    for command in (['config', 'user.name', 'Test'], ['config', 'user.email', 'test@example.test'],
                    ['add', '.'], ['commit', '-qm', 'program fixture']):
        subprocess.run(['git', *command], cwd=repo, check=True)
    handler = _load_handler()
    handler._REPO_ROOT = repo
    st = handler._staging_mod()
    monkeypatch.setattr(st, '_repair_owner', lambda: 'owner')
    monkeypatch.setattr('runtime_utils.get_code_root', lambda: repo)
    monkeypatch.setattr('runtime_utils.get_source_root', lambda: repo)
    monkeypatch.setattr('runtime_utils.get_base_path', lambda: repo)
    initial = program_runtime.Namespace(root, 'apply_test').load('handler')
    runtime = program_runtime.wrap('new-feature', root, repo, initial)
    candidate = st.stage_file(str(repo), 'program-test', str(root / 'helper.py'))
    Path(candidate).write_text('value = 2\n')
    session = st.read_session(str(repo), 'program-test')
    session.update(program_policy=1, repair_policy=2)
    st._candidate.seal(str(repo), session, [{'gate': 'fixture', 'passed': True}],
                       {'status': 'APPROVED'}, {'criteria': [{'id': 'C1', 'text': 'helper correction'}]})
    st._save_session(str(repo), session)
    return repo, root, st, session, handler._load_sibling('program_apply'), runtime


def test_package_apply_commits_and_activates_without_registration_or_worker_restart(setup, monkeypatch):
    repo, root, st, session, apply, runtime = setup
    monkeypatch.setattr(st, '_schedule_deferred_apply', lambda *a: pytest.fail('whole worker restart'))
    (repo / 'unrelated.txt').write_text('another task')
    result = apply.apply(st, str(repo), session)
    assert result['success'] and result['activated'] and not result['restart_required'], result
    assert runtime.execute({}, None) == 2
    assert (repo / 'unrelated.txt').read_text() == 'another task'
    assert subprocess.check_output(['git', 'show', result['commit']['commit'] + ':' +
                                   str(root.relative_to(repo) / 'helper.py')], cwd=repo) == b'value = 2\n'
    assert st._candidate.active_generation_bytes(repo, session)[0] == 'matched'
    from repair_readiness import program_published
    assert program_published(repo, session)
    assert apply.finish(st, str(repo), session)['commit']['commit'] == result['commit']['commit']


def test_import_failure_restores_source_and_publication_without_commit(setup, monkeypatch):
    repo, root, st, session, apply, runtime = setup
    old = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo)
    monkeypatch.setattr(program_runtime, 'load', lambda *a: (_ for _ in ()).throw(RuntimeError('boot failed')))
    with pytest.raises(RuntimeError, match='boot failed'):
        apply.apply(st, str(repo), session)
    assert (root / 'helper.py').read_text() == 'value = 1\n'
    assert session['status'] == 'staging'
    assert 'new-feature' not in program_versions.read(repo)
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo) == old


def test_partial_write_crash_restores_exact_previous_bytes(setup, monkeypatch):
    repo, root, st, session, apply, runtime = setup
    def fail(*args):
        (root / 'helper.py').write_text('value = 2\n')
        session['status'] = 'applying'
        raise OSError('disk write interrupted')
    monkeypatch.setattr(st, '_perform_apply_locked', fail)
    with pytest.raises(OSError, match='interrupted'):
        apply.apply(st, str(repo), session)
    assert (root / 'helper.py').read_text() == 'value = 1\n'
    assert session['status'] == 'staging'


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))


def test_busy_package_finishes_without_another_user_apply(setup):
    import time
    repo, root, st, session, apply, runtime = setup
    with runtime.lease():
        result = apply.apply(st, str(repo), session)
        assert result['applied'] and not result['activated']
        assert not result['restart_required']
    deadline = time.monotonic() + 15
    while not (session.get('commit') or {}).get('success') and time.monotonic() < deadline:
        time.sleep(0.1)
    assert session['commit']['success']
    assert runtime.execute({}, None) == 2


@pytest.mark.parametrize('host_program', [False, True])
def test_commit_rejection_recovers_same_candidate_then_finishes(setup, monkeypatch, host_program):
    repo, root, st, session, apply, runtime = setup
    if host_program:
        relative = 'data/scripts/commit_retry.py'
        target = repo / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text('VALUE = 1\n')
        subprocess.run(['git', 'add', relative], cwd=repo, check=True)
        subprocess.run(['git', 'commit', '-qm', 'script baseline'], cwd=repo, check=True)
        candidate = st.stage_file(str(repo), 'host-retry', str(target))
        Path(candidate).write_text('VALUE = 2\n')
        session = st.read_session(str(repo), 'host-retry')
        session.update(program_policy=1, repair_policy=2)
        st._candidate.seal(str(repo), session, [{'gate': 'fixture', 'passed': True}],
                           {'status': 'APPROVED'}, {'criteria': [{'id': 'C1', 'text': 'script correction'}]})
        st._save_session(str(repo), session)
    else:
        target = root / 'helper.py'
    old = target.read_bytes()
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo)
    hook = repo / '.git/hooks/pre-commit'
    hook.write_text('#!/bin/sh\necho "missing runner entrypoint"\nexit 1\n')
    hook.chmod(0o755)
    result = apply.apply(st, str(repo), session)
    assert result['rolled_back'] and not result['applied'], result
    assert session['status'] == 'staging' and not session['verified']
    assert target.read_bytes() == old
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=repo) == head
    assert 'missing runner entrypoint' in result['error']
    assert 'readiness' not in session and not session.get('activation_checks')
    candidate = repo / session['worktree'] / target.relative_to(repo)
    assert '2' in candidate.read_text()
    candidate.write_text(candidate.read_text().replace('2', '3'))
    hook.write_text('#!/bin/sh\nexit 0\n')
    st._candidate.seal(str(repo), session, [{'gate': 'fixture', 'passed': True}],
                       {'status': 'APPROVED'}, {'criteria': [{'id': 'C1', 'text': 'correction'}]})
    st._save_session(str(repo), session)
    result = apply.apply(st, str(repo), session)
    assert result['success'] and result['activated'], result
    assert '3' in target.read_text()
    assert subprocess.check_output(['git', 'show', result['commit']['commit'] + ':' +
                                   target.relative_to(repo).as_posix()], cwd=repo) == target.read_bytes()


def test_commit_uncertainty_and_concurrent_edits_never_trigger_recovery(setup):
    repo, root, st, session, apply, runtime = setup
    before = (root / 'helper.py').read_bytes()
    assert apply.recover_commit_failure(st, str(repo), session, {'success': False}) is None
    assert apply.recover_commit_failure(st, str(repo), session,
                                       {'success': False, 'commit_not_created': True}) is None
    assert (root / 'helper.py').read_bytes() == before


def test_restart_controller_uses_same_commit_recovery_before_worker_swap(setup, monkeypatch):
    from types import SimpleNamespace
    from restart_protocol import atomic_json
    from restart_red import apply_job, reservation
    repo, root, st, session, apply, runtime = setup
    target = repo / 'backend/base/runtime_utils.py'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text('VALUE = 1\n')
    subprocess.run(['git', 'add', str(target)], cwd=repo, check=True)
    subprocess.run(['git', 'commit', '-qm', 'restart baseline'], cwd=repo, check=True)
    candidate = st.stage_file(str(repo), 'restart-retry', str(target))
    Path(candidate).write_text('VALUE = 2\n')
    session = st.read_session(str(repo), 'restart-retry')
    session.update(program_policy=1, repair_policy=2)
    st._candidate.seal(str(repo), session, [{'gate': 'fixture', 'passed': True}],
                       {'status': 'APPROVED'}, {'criteria': [{'id': 'C1', 'text': 'restart correction'}]})
    session.update(status='apply_scheduled', scheduled_at='fixture')
    st._save_session(str(repo), session)
    handler = _load_handler()
    handler._REPO_ROOT = repo
    monkeypatch.setattr(handler, '_staging_mod', lambda: st)
    monkeypatch.setattr('red_apply._load_handler', lambda job: handler)
    # Process ownership is tested by the controller suite; exercise the real
    # shared write/commit/recovery against Git without a live restart here.
    monkeypatch.setattr(st, 'perform_scheduled_apply', lambda repo, key, **kw:
                        st._perform_apply(repo, session, [], None, None))
    job = {'repo': str(repo), 'key': session['key'], 'task_id': session['key'],
           'scheduled_at': 'fixture', 'readiness_hash': st._candidate.digest(session['readiness'])}
    job_path = repo / st.SESSION_DIRNAME / (session['key'] + '.apply.json')
    atomic_json(job_path, job)
    hook = repo / '.git/hooks/pre-commit'
    hook.write_text('#!/bin/sh\necho core-hook-rejected\nexit 1\n')
    hook.chmod(0o755)
    result = apply_job(repo, job_path, reservation(job))
    assert result['rolled_back'] and not result['applied'] and not result['verified']
    assert 'core-hook-rejected' in result['error']
    assert target.read_text() == 'VALUE = 1\n'
    restored = st.read_session(str(repo), session['key'])
    assert restored['status'] == 'staging' and restored['worktree'] == session['worktree']
    assert Path(candidate).read_text() == 'VALUE = 2\n'
    assert 'readiness' not in restored
