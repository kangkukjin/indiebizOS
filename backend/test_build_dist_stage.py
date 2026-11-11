"""Distribution staging must not share writable inodes with the live body."""
import importlib.util
import os
from pathlib import Path

import pytest

from test_repair_tool_scope import repair  # noqa: F401
from test_conscious_supervisor import supervisor  # noqa: F401


def stage_builder(repo, monkeypatch):
    script = Path(__file__).resolve().parents[1] / 'scripts/build_dist_stage.py'
    spec = importlib.util.spec_from_file_location('dist_stage_under_test', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name, value in {
        'REPO_ROOT': repo, 'DATA_DIR': repo / 'data',
        'STAGE_ROOT': repo / 'frontend/.dist_stage',
        'STAGE_DATA': repo / 'frontend/.dist_stage/data',
    }.items():
        monkeypatch.setattr(module, name, value)
    return module


@pytest.mark.parametrize('legacy_link', [False, True])
def test_staging_preserves_independent_bytes_and_permissions(tmp_path, monkeypatch, legacy_link):
    source = tmp_path / 'data/guides/example.md'
    source.parent.mkdir(parents=True)
    source.write_text('ORIGINAL', encoding='utf-8')
    source.chmod(0o640)
    builder = stage_builder(tmp_path, monkeypatch)
    monkeypatch.setattr(builder, 'tracked_data_files', lambda: ['guides/example.md'])
    target = builder.STAGE_DATA / 'guides/example.md'
    if legacy_link:
        target.parent.mkdir(parents=True)
        os.link(source, target)
    assert builder.build_stage() == 0
    assert source.read_bytes() == target.read_bytes() == b'ORIGINAL'
    assert target.stat().st_mode & 0o777 == 0o640
    assert not source.samefile(target)
    assert source.stat().st_nlink == target.stat().st_nlink == 1
    # In-place writes expose aliases that atomic editors can accidentally hide.
    source.write_text('LIVE EDIT', encoding='utf-8')
    assert target.read_text() == 'ORIGINAL'
    target.write_text('PACKAGING EDIT', encoding='utf-8')
    target.chmod(0o600)
    assert source.read_text() == 'LIVE EDIT'
    assert source.stat().st_mode & 0o777 == 0o640
    assert builder.build_stage() == 0
    assert target.read_text() == 'LIVE EDIT'
    assert not source.samefile(target)


def test_rebuilt_stage_allows_document_repair_without_changing_packaged_copy(repair, monkeypatch):
    repo, wt, st, controller, call = repair
    relative = 'data/guides/report.md'
    source = repo / relative
    builder = stage_builder(repo, monkeypatch)
    target = builder.STAGE_ROOT / relative
    target.parent.mkdir(parents=True)
    os.link(source, target)
    status = call('patch_op', {'op': 'status', 'path': relative})['items'][0]
    assert status['mutable'] and status['route'] == 'file'
    blocked = call('write_file', {'path': relative, 'content': 'NEW GUIDE'})
    assert not blocked['success'] and '하드 링크' in blocked['error']
    assert source.read_text() == target.read_text() == 'OLD GUIDE'
    assert builder.build_stage() == 0
    result = call('write_file', {'path': relative, 'content': 'NEW GUIDE'})
    assert result['success'] and not result.get('staged'), result
    assert call('read_file', {'path': relative}) == 'NEW GUIDE'
    assert target.read_text() == (wt / relative).read_text() == 'OLD GUIDE'
    result = call('edit_file', {'path': relative, 'old_string': 'NEW', 'new_string': 'FINAL'})
    assert 'Successfully edited' in result, result
    assert source.read_text() == 'FINAL GUIDE'
    assert target.read_text() == 'OLD GUIDE'
