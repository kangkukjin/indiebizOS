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
