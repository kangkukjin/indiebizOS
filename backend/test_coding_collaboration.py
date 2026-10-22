import boot_paths  # noqa: F401
from pathlib import Path
import os
import sys

import pytest

from coding_collaboration import Collaboration
from coding_projects import CodingProjects
from coding_store import CodingStore
from coding_git import git
from coding_process import available


@pytest.fixture
def setup(tmp_path):
    folder = tmp_path / 'project'
    folder.mkdir()
    (folder / 'a.txt').write_text('base a')
    (folder / 'b.bin').write_bytes(b'\x00\x01')
    projects = CodingProjects(CodingStore(tmp_path / 'state'))
    row = projects.open(folder)
    collaboration = Collaboration(projects.store)
    prepared = collaboration.prepare(row, 'request', 2, 'controller')
    return collaboration, prepared, folder


@pytest.mark.skipif(not available(), reason='macOS coding sandbox')
def test_dirty_untracked_binary_mode_merge_validate_apply(setup):
    app, row, original = setup
    a, b = map(Path, row['copies'])
    assert (a / 'a.txt').read_text() == 'base a'
    (a / 'a.txt').write_text('modified a')
    (b / 'b.bin').write_bytes(b'\x00\xff\x02')
    (b / 'b.bin').chmod(0o755)
    (a / 'new.txt').write_text('new')
    row = app.merge(row)
    row = app.validate(row, [[sys.executable, '-c', "from pathlib import Path; assert Path('a.txt').read_text() == 'modified a'"]])
    assert row['state'] == 'validated', row.get('validation')
    row = app.apply(row)
    assert row['state'] == 'applied'
    assert (original / 'a.txt').read_text() == 'modified a'
    assert (original / 'b.bin').read_bytes() == b'\x00\xff\x02'
    assert os.stat(original / 'b.bin').st_mode & 0o111
    assert app.apply(row) == row


def test_conflicts_and_source_changes_never_overwrite(setup):
    app, row, original = setup
    a, b = map(Path, row['copies'])
    (a / 'a.txt').write_text('left')
    (b / 'a.txt').write_text('right')
    row = app.merge(row)
    assert row['state'] == 'conflict'
    assert (original / 'a.txt').read_text() == 'base a'
    (b / 'a.txt').write_text('base a')
    row = app.merge(row)
    row.update(state='validated', validation={'passed': True, 'candidate_hash': row['candidate_hash']})
    (original / 'external.txt').write_text('external')
    with pytest.raises(ValueError, match='원본'):
        app.apply(row)
    assert (original / 'a.txt').read_text() == 'base a'


def test_partial_apply_and_recovery_preserve_external_edits(setup, monkeypatch):
    app, row, original = setup
    a = Path(row['copies'][0])
    (a / 'a.txt').write_text('left')
    (a / 'b.bin').write_bytes(b'changed')
    row = app.merge(row)
    row.update(state='validated', validation={'passed': True, 'candidate_hash': row['candidate_hash']})
    write = app._write
    def broken(folder, name, entry):
        if name == 'b.bin':
            raise OSError('injected disk error')
        write(folder, name, entry)
    monkeypatch.setattr(app, '_write', broken)
    with pytest.raises(OSError):
        app.apply(row)
    row = app.store.get('collaboration', row['id'])
    assert row['state'] == 'partial'
    (original / 'a.txt').write_text('third party')
    monkeypatch.setattr(app, '_write', write)
    row = app.recover(row)
    assert row['unresolved'] == ['a.txt']
    assert (original / 'a.txt').read_text() == 'third party'


def test_mid_copy_commit_does_not_hide_change_and_symlink_is_rejected(setup):
    app, row, _ = setup
    a = Path(row['copies'][0])
    (a / 'a.txt').write_text('committed change')
    git(a, 'add', '.')
    git(a, '-c', 'user.name=Test', '-c', 'user.email=test@local', 'commit', '-qm', 'worker commit')
    merged = app.merge(row)
    assert 'a.txt' in merged['changed']
    (a / 'alias').symlink_to(a / 'a.txt')
    with pytest.raises(ValueError, match='링크'):
        app.merge(row)


def test_ignored_original_is_not_overwritten_by_new_tracked_file(tmp_path):
    source = tmp_path / 'project'
    source.mkdir()
    (source / '.gitignore').write_text('private.txt\n')
    (source / 'private.txt').write_text('original secret')
    projects = CodingProjects(CodingStore(tmp_path / 'state'))
    project = projects.open(source)
    app = Collaboration(projects.store)
    row = app.prepare(project, 'ignored', 2, 'controller')
    copy = Path(row['copies'][0])
    (copy / 'private.txt').write_text('worker output')
    git(copy, 'add', '--force', 'private.txt')
    row = app.merge(row)
    row.update(state='validated', validation={'passed': True, 'candidate_hash': row['candidate_hash']})
    with pytest.raises(ValueError, match='원본|제외된'):
        app.apply(row)
    assert (source / 'private.txt').read_text() == 'original secret'


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
