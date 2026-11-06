"""Real file transactions, conflicts, encoding and recovery."""
import codecs
from pathlib import Path
import pytest
from coding_store import CodingStore, fingerprint
from file_workspace import FileWorkspace


def test_patch_files_preserves_encoding_and_preflights(tmp_path):
    root = tmp_path / 'work'; root.mkdir()
    app = FileWorkspace(CodingStore(tmp_path / 'state')); row = app.open(root)
    (root / 'old.txt').write_bytes(codecs.BOM_UTF8 + b'one\r\ntwo\r\n')
    (root / 'old.txt').chmod(0o755)
    patch = '*** Begin Patch\n*** Update File: old.txt\n*** Move to: new.txt\n@@\n one\n-two\n+three\n*** Add File: sub/new.txt\n+hello\n*** End Patch'
    p = app.patch(row, patch, request_id='1')
    assert not (root / 'new.txt').exists()
    app.apply(row, p['proposal'])
    assert (root / 'new.txt').read_bytes() == codecs.BOM_UTF8 + b'one\r\nthree\r\n'
    assert (root / 'new.txt').stat().st_mode & 0o777 == 0o755
    assert not (root / '.git').exists()
    assert app.apply(row, p['proposal'])['cached']
    assert app.patch(row, patch, request_id='1')['cached']
    with pytest.raises(ValueError): app.patch(row, '*** Begin Patch\n*** Delete File: new.txt\n*** End Patch')
    p = app.patch(row, '*** Begin Patch\n*** Delete File: new.txt\n*** Update File: sub/new.txt\n@@\n-hello\n+world\n*** End Patch', expected={'new.txt': fingerprint((root/'new.txt').read_bytes())})
    (root / 'sub/new.txt').write_text('external\n')
    with pytest.raises(Exception): app.apply(row, p['proposal'])
    assert (root / 'new.txt').exists()


def test_patch_rejects_traversal_and_ambiguous_context(tmp_path):
    app = FileWorkspace(CodingStore(tmp_path / 'state')); row = app.open(tmp_path)
    (tmp_path / 'a').write_text('x\nx\n')
    for patch in ['*** Add File: ../out\n+x', '*** Update File: a\n@@\n-x\n+y']:
        with pytest.raises((ValueError, PermissionError)):
            app.patch(row, '*** Begin Patch\n' + patch + '\n*** End Patch')


def test_ibl_patch_preview_and_apply(tmp_path):
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    from thread_context import actor_context
    inputs={'root':str(tmp_path),'patch':'*** Begin Patch\n*** Add File: a.txt\n+one\n*** Add File: b.txt\n+two\n*** End Patch'}
    code='$w=[self:workspace]{op:"open",kind:"files",path:$root}; $p=[self:edit]{resource:$w.resource,patch:$patch,preview:true}; [self:workspace]{op:"apply",resource:$w.resource,proposal:$p.proposal}'
    plan=compile_program(code,load_registry(str(Path(__file__).resolve().parents[1])),inputs)
    assert not plan.issues,plan.issues
    with actor_context(origin='training'):
        out=Runtime(plan,inputs).run()
    assert out['success'],out.get('diagnostic')
    assert (tmp_path/'a.txt').read_text()=='one\n'
    assert (tmp_path/'b.txt').read_text()=='two\n'
