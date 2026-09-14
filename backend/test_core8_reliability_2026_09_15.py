"""상위 IBL 감사 재현: 임시 파일/DB만 사용하고 모델·네트워크는 호출하지 않는다."""
import boot_paths  # noqa: F401
import builtins
import concurrent.futures
import importlib.util
import json
from pathlib import Path
import sqlite3
import struct
import sys
import threading
from contextlib import contextmanager
from types import SimpleNamespace

import pytest
from tool_context import ToolContext

PKG = Path(__file__).resolve().parents[1] / 'data/packages/installed/tools'


def load(package, module):
    spec = importlib.util.spec_from_file_location('core8_' + module, PKG / package / (module + '.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def files(tmp_path):
    h = load('system_essentials', 'handler')
    path = tmp_path / 'sample.txt'

    def call(tool, **params):
        return h.execute({'path': str(path), **params}, ToolContext(str(tmp_path), tool, agent_id='core8'))

    return h, path, call


@pytest.mark.parametrize('op', ['write_file', 'edit_file'])
@pytest.mark.parametrize('failure', ['partial_write', 'fsync', 'replace'])
def test_failed_save_preserves_original(files, monkeypatch, op, failure):
    h, path, call = files
    path.write_text('original full content\n')
    real_open = builtins.open

    def fail(*a, **kw):
        raise OSError('simulated storage failure')

    class PartialWriter:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.stream.close()

        def write(self, text):
            self.stream.write(text[:3])
            self.stream.flush()
            fail()

    def broken_open(file, mode='r', *args, **kw):
        stream = real_open(file, mode, *args, **kw)
        return PartialWriter(stream) if mode == 'x' else stream

    if failure == 'partial_write':
        monkeypatch.setattr(builtins, 'open', broken_open)
    else:
        monkeypatch.setattr(h._file_io.os, failure, fail)
    result = call(op, content='replacement', old_string='original', new_string='replacement')
    assert 'simulated storage failure' in result
    assert path.read_bytes() == b'original full content\n'
    assert list(path.parent.glob('.*.tmp')) == []


def test_concurrent_edits_keep_both_changes(files, monkeypatch):
    h, path, call = files
    path.write_text('alpha=old\nbeta=old\n')
    first_prepared = threading.Event()
    second_lock_attempt = threading.Event()
    real_lock = h._file_io.file_lock

    @contextmanager
    def lock(target):
        if first_prepared.is_set():
            second_lock_attempt.set()
        with real_lock(target):
            yield

    def prepare(*args):
        if not first_prepared.is_set():
            first_prepared.set()
            assert second_lock_attempt.wait(5)

    monkeypatch.setattr(h._file_io, 'file_lock', lock)
    monkeypatch.setattr(h, '_red_write_prepare', prepare)
    with concurrent.futures.ThreadPoolExecutor(2) as executor:
        first = executor.submit(call, 'edit_file', old_string='alpha=old', new_string='alpha=new')
        assert first_prepared.wait(5)
        second = executor.submit(call, 'edit_file', old_string='beta=old', new_string='beta=new')
        assert 'Successfully edited' in first.result(timeout=5)
        assert 'Successfully edited' in second.result(timeout=5)
    assert path.read_text() == 'alpha=new\nbeta=new\n'


def test_edit_keeps_crlf_mode_and_symlink(files):
    h, path, call = files
    target = path.with_name('real.txt')
    target.write_bytes(b'first\r\nsecond\r\n')
    target.chmod(0o640)
    path.symlink_to(target)
    assert 'Successfully edited' in call('edit_file', old_string='first', new_string='FIRST')
    assert path.is_symlink()
    assert target.read_bytes() == b'FIRST\r\nsecond\r\n'
    assert target.stat().st_mode & 0o777 == 0o640
    assert 'Successfully edited' in call('edit_file', start_line=2, end_line=2, new_string='SECOND')
    assert target.read_bytes() == b'FIRST\r\nSECOND\r\n'
    assert 'Successfully edited' in call('edit_file', old_string='FIRST\nSECOND', new_string='one\ntwo')
    assert target.read_bytes() == b'one\r\ntwo\r\n'



@pytest.mark.parametrize('params,expected', [({'limit': 0}, ''), ({'offset': 1, 'limit': 1}, 'b\n'),
                                            ({'tail': 1}, 'c\n')])
def test_range_reader_streams_without_readlines(files, monkeypatch, params, expected):
    h, path, call = files
    path.write_text('a\nb\nc\n')
    real_open = builtins.open

    class IterOnly:
        def __init__(self, stream):
            self.stream = stream

        def __enter__(self):
            return iter(self.stream)

        def __exit__(self, *args):
            self.stream.close()

    def streamed(file, mode='r', **kw):
        stream = real_open(file, mode, **kw)
        return IterOnly(stream) if str(file) == str(path) and mode == 'r' else stream

    monkeypatch.setattr(builtins, 'open', streamed)
    result = call('read_op', **params)
    assert result.split('\n', 1)[1] == expected
    assert '전체 3줄' in result


def test_full_read_cap_and_blocks_disclose_truncation(files):
    h, path, call = files
    path.write_text('abc\n' * 300_000)
    plain = call('read_op')
    assert plain.startswith('abc\n') and '처음 1MB' in plain
    blocks = json.loads(call('read_op', blocks=True))
    assert blocks['truncated'] is True and blocks['total_lines'] == 300_000
    assert len(blocks['message']) == 1_000_000


def test_pdf_pages_through_ibl(tmp_path):
    import fitz
    from ibl_engine import execute_ibl
    path = tmp_path / 'pages.pdf'
    with fitz.open() as doc:
        for i in range(1, 4):
            doc.new_page().insert_text((72, 72), f'ONLY_PAGE_{i}')
        doc.save(path)
    for pages, expected in [('2', [2]), ('1-2,2,3', [1, 2, 3])]:
        result = json.loads(execute_ibl({'_node': 'self', 'action': 'read',
                                      'params': {'path': str(path), 'pages': pages}}, str(tmp_path)))
        assert result['extracted_pages_count'] == len(expected)
        for i in range(1, 4):
            assert (f'ONLY_PAGE_{i}' in result['text']) == (i in expected)
    for pages in ['0', '4', '3-1', '', 'one', '1,,2']:
        result = json.loads(execute_ibl({'_node': 'self', 'action': 'read',
                                      'params': {'path': str(path), 'pages': pages}}, str(tmp_path)))
        assert result['success'] is False, (pages, result)


@pytest.mark.parametrize('action', ['select', 'filter'])
def test_invalid_item_rows_fail_at_ibl_boundary(tmp_path, action):
    from ibl_engine import execute_ibl
    for items in [['Seoul', 'Busan'], [{'name': 'kept'}, 'LOST']]:
        params = {'items': items}
        params.update({'columns': ['name']} if action == 'select' else {'where': 'name == kept'})
        result = execute_ibl({'_node': 'table', 'action': action, 'params': params}, str(tmp_path))
        result = json.loads(result) if isinstance(result, str) else result
        assert result['success'] is False and '객체' in result['error']


@pytest.mark.parametrize('currency', [{'items': []}, {'items': [{'id': 'partial'}]},
                                    {'table': {'columns': ['id'], 'rows': []}}])
def test_union_stop_and_all_failed(currency, tmp_path):
    from ibl_parser import parse
    from workflow_engine import execute_pipeline
    failed = {'success': False, 'error': 'failed', **currency}
    for branches, param in [([{'success': True, 'items': [{'id': 'ok'}]}, failed], 'on_error:"stop"'),
                            ([failed, failed], '')]:
        result = execute_pipeline(parse('[table:union]{' + param + '}'), str(tmp_path),
                                  context={'_prev_result': json.dumps(branches)})
        assert result['success'] is False, result


@pytest.fixture
def memory(tmp_path, monkeypatch):
    h = load('memory', 'handler')
    import memory_db as db
    monkeypatch.setattr(db, '_get_model', lambda: None)
    monkeypatch.setattr(db, '_delete_vec', lambda *a, **kw: None)
    conn = db.get_db(str(tmp_path), 'core8')
    conn.executemany('INSERT INTO memories(id,category,keywords,content,node) VALUES(?,?,?,?,?)', [
        (1, '기타', 'TOPIC', 'UNRELATED_DURABLE_MEMORY TOPIC', 'outside'),
        (2, '사용자선호', 'TOPIC', 'wanted TOPIC', 'wanted/child'),
        (3, '기타', 'TOPIC', 'nearby TOPIC', 'wanted_other')])
    conn.commit()
    conn.close()
    return h, db, str(tmp_path), ToolContext(str(tmp_path), 'memory_op', agent_id='core8')


def test_conversation_identity_cannot_delete_deep_memory(memory):
    h, db, project, context = memory
    with sqlite3.connect(str(Path(project) / 'conversations.db')) as conn:
        conn.executescript("CREATE TABLE agents(id TEXT,name TEXT); CREATE TABLE messages(id INTEGER,"
                           "from_agent_id TEXT,to_agent_id TEXT,content TEXT,message_time TEXT);"
                           "INSERT INTO messages VALUES(1,NULL,NULL,'CONVERSATION_NEEDLE','2026-09-15');")
    found = json.loads(h.execute({'op': 'search', 'query': 'CONVERSATION_NEEDLE'}, context))
    item = found['items'][0]
    assert item['conversation_id'] == 1 and 'memory_id' not in item
    assert 'id' not in found['memories'][0]
    for op in ['read', 'delete', 'move']:
        rejected = json.loads(h.execute({'op': op, **item, 'memory_id': 1, 'node': 'x'}, context))
        assert rejected['success'] is False
    assert db.read(project, 'core8', 1, touch=False)['content'].startswith('UNRELATED')
    found = json.loads(h.execute({'op': 'search', 'query': 'UNRELATED'}, context))
    assert found['items'][0]['memory_id'] == 1
    assert 'UNRELATED' in h.execute({'op': 'read', 'memory_id': 1}, context)
    assert json.loads(h.execute({'op': 'delete', 'memory_id': 1}, context))['deleted'] is True


def test_like_filters_before_limit(memory):
    h, db, project, context = memory
    for params in [{'node': 'wanted'}, {'category': '사용자선호'},
                   {'node': 'wanted', 'category': '사용자선호'}]:
        result = json.loads(h.execute({'op': 'search', 'query': 'TOPIC', 'top_k': 1, **params}, context))
        assert result['count'] == 1 and result['items'][0]['memory_id'] == 2


def test_semantic_filters_inside_knn_candidate_set(memory, monkeypatch):
    h, db, project, context = memory
    sqlite_vec = pytest.importorskip('sqlite_vec')
    db_path = db._get_db_path(project, 'core8')

    def connection(path):
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.enable_load_extension(True)
        sqlite_vec.load(conn)
        return conn

    with connection(db_path) as conn:
        conn.execute('CREATE VIRTUAL TABLE memories_vec USING vec0(embedding float[2])')
        for i, vector in [(1, [1., 0.]), (2, [.99, .01]), (3, [1., 0.])]:
            conn.execute('INSERT INTO memories_vec(rowid,embedding) VALUES (?,?)',
                         (i, struct.pack('2f', *vector)))
    model = SimpleNamespace(encode=lambda *a, **kw: SimpleNamespace(tolist=lambda: [1., 0.]))
    monkeypatch.setattr(db, '_get_model', lambda: model)
    monkeypatch.setattr(db, '_get_vec_conn', connection)
    monkeypatch.setattr(db, 'EMBEDDING_DIM', 2)
    for filters in [{'node': 'wanted'}, {'category': '사용자선호'}]:
        result = db.search(project, 'core8', 'TOPIC', limit=1, semantic_only=True, **filters)
        assert [r['id'] for r in result] == [2]


@pytest.mark.parametrize('cached_tool', [True, False])
def test_handler_cache_clear_during_read_keeps_current_module(monkeypatch, cached_tool):
    import tool_loader as loader
    module = SimpleNamespace(name='already loaded')
    monkeypatch.setattr(loader, '_tool_handlers_cache', {'read_op': module} if cached_tool else {})
    monkeypatch.setattr(loader, '_package_handlers_cache', {'system_essentials': module})
    monkeypatch.setattr(loader, '_tool_to_package_map', {'read_op': 'system_essentials'})
    monkeypatch.setattr(loader, 'require_tool_active', lambda *a: None)
    monkeypatch.setattr(loader, 'build_tool_package_map', lambda: None)

    def concurrent_clear(package):
        loader._tool_handlers_cache.clear()
        loader._package_handlers_cache.clear()
        return False

    monkeypatch.setattr(loader, '_invalidate_stale_handler', concurrent_clear)
    assert loader.load_tool_handler('read_op') is module


if __name__ == '__main__':
    sys.exit(pytest.main([__file__] + sys.argv[1:]))
