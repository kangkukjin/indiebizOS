"""수리 묶음의 바이너리 각인과 명시적 비추적 산출물 배치 계약."""
import subprocess
from pathlib import Path

import pytest
import boot_paths  # noqa: F401
from test_repair_workspace_completion import setup, ready  # noqa: F401


def test_binary_add_delete_and_quoted_paths_commit_without_touching_other_index(setup):
    root, wt, st, sess = setup
    old = 'old 한글.bin'
    (root / old).write_bytes(b'\x00old\xff')
    subprocess.run(['git', 'add', old], cwd=root, check=True)
    subprocess.run(['git', 'commit', '-qm', 'old binary'], cwd=root, check=True)
    st._candidate.refresh(str(root), sess)
    (wt / old).unlink()
    new = 'nested/new "한글".bin'
    (wt / new).parent.mkdir()
    (wt / new).write_bytes(b'\x00new\xfe' * 256)
    (wt / new).chmod(0o755)
    (root / 'b.txt').write_text('other staged edit')
    subprocess.run(['git', 'add', 'b.txt'], cwd=root, check=True)
    st._candidate.refresh(str(root), sess)
    ready(root, st, sess)
    assert st._perform_apply(str(root), sess, [], None, None)['applied']
    result = st.commit_applied(str(root), sess['key'])
    assert result['success'], result
    assert subprocess.check_output(['git', 'show', 'HEAD:' + new], cwd=root) == (root / new).read_bytes()
    assert subprocess.run(['git', 'cat-file', '-e', 'HEAD:' + old], cwd=root).returncode != 0
    assert subprocess.check_output(['git', 'diff', '--cached', '--name-only'], cwd=root).strip() == b'b.txt'
    assert subprocess.check_output(['git', 'ls-tree', 'HEAD', '--', new], cwd=root).startswith(b'100755')


def artifacts(setup):
    root, wt, st, sess = setup
    for where in (root, wt):
        with (where / '.gitignore').open('a') as f:
            f.write('outputs/\n')
    # Both edits are baseline data, not part of the repair.
    st._candidate.refresh(str(root), sess)
    live = root / 'outputs/device'
    live.mkdir(parents=True)
    (live / 'config.json').write_text('keep existing private key')
    (live / 'helper').write_bytes(b'old')
    draft = wt / 'outputs/device'
    draft.mkdir(parents=True)
    (draft / 'helper').write_bytes(b'\0new binary')
    (draft / 'helper').chmod(0o755)
    (draft / 'readme.txt').write_text('new instructions')
    (draft / 'unrequested.txt').write_text('must not publish')
    paths = ['outputs/device/helper', 'outputs/device/readme.txt']
    st._candidate.register_artifacts(str(root), sess, paths)
    return root, wt, st, sess, paths


def test_artifact_apply_preserves_config_and_never_commits_output(setup):
    root, wt, st, sess, paths = artifacts(setup)
    (wt / 'a.txt').write_text('fixed code')
    ready(root, st, sess)
    assert set(paths) <= set(sess['sealed'])
    assert all(sess['sealed'][p]['artifact'] for p in paths)
    assert st._perform_apply(str(root), sess, [], None, None)['applied']
    assert (root / paths[0]).read_bytes() == b'\0new binary'
    assert (root / paths[0]).stat().st_mode & 0o777 == 0o755
    assert (root / 'outputs/device/config.json').read_text() == 'keep existing private key'
    assert not (root / 'outputs/device/unrequested.txt').exists()
    assert st.commit_applied(str(root), sess['key'])['success']
    assert subprocess.check_output(['git', 'ls-tree', '-r', '--name-only', 'HEAD', '--', 'outputs'], cwd=root) == b''
    assert subprocess.check_output(['git', 'show', 'HEAD:a.txt'], cwd=root) == b'fixed code'


@pytest.mark.parametrize('where', ['live', 'draft'])
def test_artifact_changes_after_seal_block_all_application(setup, where):
    root, wt, st, sess, paths = artifacts(setup)
    (wt / 'a.txt').write_text('fixed')
    ready(root, st, sess)
    ((root if where == 'live' else wt) / paths[0]).write_bytes(b'concurrent change')
    result = st._perform_apply(str(root), sess, [], None, None)
    assert not result['applied']
    assert (root / 'a.txt').read_text() == 'before'
    assert not (root / paths[1]).exists()


@pytest.mark.parametrize('path', ['../outside', 'data/limb_keys.json', 'outputs/../.env', 'outputs/link/file'])
def test_artifact_scope_and_symlinks_rejected(setup, path):
    root, wt, st, sess = setup
    (wt / 'outputs').mkdir()
    (wt / 'outputs/link').symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError):
        st._candidate.register_artifacts(str(root), sess, [path])
    assert not sess.get('artifact_paths')


def test_artifact_only_receipt_checks_live_bytes_without_empty_git_commit(setup, monkeypatch):
    from types import SimpleNamespace
    from repair_policy import completion
    root, wt, st, sess, paths = artifacts(setup)
    sess['repair_policy'] = 2
    ready(root, st, sess)
    before = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root)
    assert st._perform_apply(str(root), sess, [], None, None)['applied']
    result = st.commit_applied(str(root), sess['key'])
    assert result['success'] and result['artifacts_only']
    assert subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root) == before
    monkeypatch.setattr('red_apply._load_handler', lambda job: SimpleNamespace(_staging_mod=lambda: st))
    saved = st.read_session(str(root), sess['key'])
    assert completion(saved, {}, root)[0]
    (root / paths[0]).write_bytes(b'tampered')
    assert not completion(saved, {}, root)[0]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
