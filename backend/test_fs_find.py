"""File identity for incremental work: exact metadata, opt-in content and failures."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path

import boot_paths  # noqa: F401
import pytest
from tool_context import ToolContext

ROOT = Path(__file__).resolve().parents[1]
PKG = ROOT / 'data/packages/installed/tools/system_essentials'


def load(name):
    spec = importlib.util.spec_from_file_location(f'_fingerprint_{name}', PKG / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def fs():
    return load('handler')


@pytest.mark.parametrize('tool', ['list_directory', 'glob_files'])
def test_exact_mtime_and_opt_in_hash_detect_restored_timestamp(fs, tmp_path, tool):
    p = tmp_path / 'sales.json'
    p.write_bytes(b'{"amount":24000}')
    stamp = 1791450000123456789
    os.utime(p, ns=(stamp, stamp))
    args = {'path': str(tmp_path), 'pattern': '*.json', 'hash': True}
    ctx = ToolContext(str(tmp_path), tool)
    first = json.loads(fs.execute(args, ctx))['items'][0]
    assert first['mtime_ns'] == str(p.stat().st_mtime_ns)
    assert first['sha256'] == hashlib.sha256(p.read_bytes()).hexdigest()
    p.write_bytes(b'{"amount":42000}')
    os.utime(p, ns=(stamp, stamp))
    second = json.loads(fs.execute(args, ctx))['items'][0]
    assert (first['size'], first['mtime'], first['mtime_ns']) == (
        second['size'], second['mtime'], second['mtime_ns'])
    assert first['sha256'] != second['sha256']


def test_plain_list_never_opens_content_and_stats_each_match_once(fs, tmp_path, monkeypatch):
    p = tmp_path / 'one.txt'
    p.write_text('one')
    stat = os.stat
    seen = []
    def counted(path, *args, **kwargs):
        seen.append(str(path))
        return stat(path, *args, **kwargs)
    monkeypatch.setattr(fs._fs_find.os, 'stat', counted)
    monkeypatch.setattr(fs._fs_find, '_content_hash', lambda *a: pytest.fail('unrequested content read'))
    out = json.loads(fs.execute({'path': str(tmp_path)}, ToolContext(str(tmp_path), 'list_directory')))
    assert out['items'][0]['mtime_ns'] == str(stat(p).st_mtime_ns)
    assert 'sha256' not in out['items'][0]
    assert seen.count(str(p)) == 1


def test_meta_find_uses_live_stat_and_hashes_only_selected_results(tmp_path, monkeypatch):
    import file_index
    p = tmp_path / 'current.txt'
    p.write_bytes(b'current')
    mod = load('fs_meta')
    monkeypatch.setattr(file_index, 'query', lambda **kw: {
        'success': True, 'items': [{'path': str(p), 'name': p.name, 'size': 999, 'mtime': 1}],
        'count': 1, 'total': 9, 'truncated': True})
    result = json.loads(mod.meta_query_or_error({'path': str(tmp_path), 'hash': True}, str(tmp_path)))
    row = result['items'][0]
    assert row['size'] == 7 and row['mtime_ns'] == str(p.stat().st_mtime_ns)
    assert row['sha256'] == hashlib.sha256(b'current').hexdigest()
    assert result['table']['rows'][0][1] == row['size']
    assert result['truncated'] and result['total'] == 9


@pytest.mark.parametrize('tool', ['list_directory', 'glob_files'])
def test_unreadable_hash_is_failure_not_an_unchanged_file(fs, tmp_path, monkeypatch, tool):
    (tmp_path / 'one.txt').write_text('one')
    def denied(*args):
        raise PermissionError('fingerprint denied')
    monkeypatch.setattr(fs._fs_find, '_content_hash', denied)
    result = json.loads(fs.execute({'path': str(tmp_path), 'pattern': '*.txt', 'hash': True},
                                   ToolContext(str(tmp_path), tool)))
    assert result['success'] is False and 'fingerprint denied' in result['error']


def test_directory_has_no_content_hash_and_fifo_is_rejected(tmp_path):
    mod = load('fs_find')
    directory, _ = mod.file_views(str(tmp_path), hash_content=True)
    assert directory['is_dir'] and directory['sha256'] is None
    fifo = tmp_path / 'pipe'
    os.mkfifo(fifo)
    with pytest.raises(OSError, match='일반 파일'):
        mod.file_views(str(fifo), hash_content=True)


def test_concurrent_content_change_cannot_produce_a_trusted_hash(tmp_path, monkeypatch):
    mod = load('fs_find')
    p = tmp_path / 'source'
    p.write_bytes(b'before')
    original = hashlib.file_digest
    def changed(stream, algorithm):
        result = original(stream, algorithm)
        p.write_bytes(b'after!')
        return result
    monkeypatch.setattr(mod.hashlib, 'file_digest', changed)
    with pytest.raises(OSError, match='변경'):
        mod.file_views(str(p), hash_content=True)


@pytest.mark.parametrize('raw', ['false', 1, None])
def test_hash_flag_is_boolean_even_for_empty_directory(fs, tmp_path, raw):
    result = json.loads(fs.execute({'path': str(tmp_path), 'hash': raw},
                                   ToolContext(str(tmp_path), 'list_directory')))
    assert result['success'] is False and 'Bool' in result['error']


@pytest.mark.parametrize('tool', ['list_directory', 'glob_files'])
def test_hash_reads_only_matching_files(fs, tmp_path, monkeypatch, tool):
    (tmp_path / 'wanted.json').write_text('{}')
    (tmp_path / 'excluded.txt').write_text('must not read')
    original = fs._fs_find._content_hash
    hashed = []
    def track(path, info):
        hashed.append(Path(path).name)
        return original(path, info)
    monkeypatch.setattr(fs._fs_find, '_content_hash', track)
    result = json.loads(fs.execute({'path': str(tmp_path), 'pattern': '*.json', 'hash': True},
                                   ToolContext(str(tmp_path), tool)))
    assert len(result['items']) == 1 and hashed == ['wanted.json']


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
