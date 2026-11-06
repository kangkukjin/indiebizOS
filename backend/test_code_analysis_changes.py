import boot_paths  # noqa: F401
import pytest
from coding_store import CodingStore
from coding_git import CodingConflict
import code_analysis_changes as changes


def test_multifile_preflight_recovery_external_edits_and_retry(tmp_path, monkeypatch):
    root = tmp_path / 'src'; root.mkdir()
    store = CodingStore(tmp_path / 'state'); row = {'id': 'coding_test', 'path': str(root)}
    edits = []
    for name in ('a.py', 'b.py'):
        path = root / name; path.write_bytes(b'before\r\n'); path.chmod(0o755)
        before = changes.state(path)
        edits.append({'path': name, 'before': before, 'after': {'bytes': changes.encoded(b'after\r\n'), 'mode': 0o755}})
    p = changes.prepare(store, row, edits)['proposal']
    (root / 'b.py').write_bytes(b'external')
    with pytest.raises(CodingConflict): changes.apply(store, row, p)
    assert (root / 'a.py').read_bytes() == b'before\r\n'
    (root / 'b.py').write_bytes(b'before\r\n')
    real = changes._replace
    def fail_second(path, value):
        if path.name == 'b.py': raise OSError('simulated process interruption')
        real(path, value)
    monkeypatch.setattr(changes, '_replace', fail_second)
    with pytest.raises(OSError): changes.apply(store, row, p)
    assert store.get('workspace_proposal', p)['state'] == 'recovery_required'
    monkeypatch.setattr(changes, '_replace', real)
    (root / 'a.py').write_bytes(b'external after partial apply')
    assert changes.recover(store, row)['items'][0]['state'] == 'recovery_required'
    (root / 'a.py').write_bytes(b'after\r\n')
    assert changes.recover(store, row)['items'][0]['applied']
    assert changes.apply(store, row, p)['cached']
    assert (root / 'b.py').read_bytes() == b'after\r\n' and (root / 'b.py').stat().st_mode & 0o777 == 0o755


def test_parent_symlink_swap_after_preflight_cannot_escape_root(tmp_path, monkeypatch):
    root = tmp_path / 'src'; (root / 'folder').mkdir(parents=True)
    outside = tmp_path / 'outside'; outside.mkdir()
    (root / 'folder/a.py').write_bytes(b'before')
    store = CodingStore(tmp_path / 'state'); row = {'id': 'coding_test', 'path': str(root)}
    p = changes.prepare(store, row, [{'path': 'folder/a.py', 'before': changes.state(root / 'folder/a.py'),
         'after': {'bytes': changes.encoded(b'after'), 'mode': 0o644}}])['proposal']
    real = changes._replace
    def swap(path, value):
        (root / 'folder').rename(root / 'old-folder')
        (root / 'folder').symlink_to(outside, target_is_directory=True)
        real(path, value)
    monkeypatch.setattr(changes, '_replace', swap)
    with pytest.raises(OSError):changes.apply(store, row, p)
    assert not (outside / 'a.py').exists()
