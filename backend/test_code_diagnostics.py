"""Real post-edit diagnostics and bounded delivery, independent of model choice."""
import json
import subprocess
import time
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest
from code_analysis import shutdown
from code_diagnostics import Feedback, command_changes, feedback, revision
from coding_store import CodingStore
from situation_delivery import prepare
from situation_evidence import file_written
from test_situation_evidence import active  # noqa: F401


@pytest.fixture(autouse=True)
def cleanup(monkeypatch):
    from code_diagnostics import observe
    monkeypatch.setattr('execution_situation._feedback', observe)
    yield
    shutdown()


def finished(state):
    rows = []
    for _ in range(4):
        rows = state.flush(wait=10)
        if rows and all(r['status'] != 'pending' for r in rows):
            return rows
    return rows


@pytest.mark.parametrize('language', ['python', 'typescript'])
def test_committed_edit_reaches_api_and_mcp_then_clears(active, tmp_path, language):
    root = tmp_path / 'project'; root.mkdir()
    suffix = 'py' if language == 'python' else 'ts'
    path = root / ('a.' + suffix)
    if language == 'typescript':
        (root / 'tsconfig.json').write_text('{"compilerOptions":{"strict":true},"include":["*.ts"]}')
    broken = 'answer: int = "wrong"\n' if language == 'python' else 'const answer: number = "wrong";\n'
    path.write_text(broken)
    file_written(path, broken.encode())
    state = feedback(active.situation)
    state.store = CodingStore(tmp_path / 'coding')
    rows = finished(state)
    assert rows and rows[0]['server'] == language, rows
    assert rows[0]['items'] and rows[0]['document_hash'] == revision(path), rows
    messages = []
    prepare(messages, SimpleNamespace(agent_role='execution'))
    assert 'lsp_after_edit' in messages[-1]['content'] and 'assign' in messages[-1]['content']
    from api_supervision import situation_context
    assert 'lsp_after_edit' in situation_context('executor', 'situation-test')['context']
    fixed = 'answer: int = 1\n' if language == 'python' else 'const answer: number = 1;\n'
    path.write_text(fixed)
    file_written(path, fixed.encode())
    rows = finished(state)
    assert rows and not rows[0]['items'], rows
    assert rows[0]['document_hash'] == revision(path)
    pending = dict(state.pending)
    file_written(path, fixed.encode())
    assert state.pending == pending and not state.jobs


def test_common_apply_without_explicit_analysis_triggers_feedback(active, tmp_path):
    from file_changes import apply, prepare as proposal, state, encoded
    root = tmp_path / 'files'; root.mkdir()
    path = root / 'a.py'; path.write_text('x = 1\n')
    store = CodingStore(tmp_path / 'coding')
    row = {'id': 'files-test', 'path': str(root)}
    item = {'path': 'a.py', 'before': state(path), 'after': {'bytes': encoded(b'x: int = "oops"\n'), 'mode': 0o644}}
    p = proposal(store, row, [item])
    assert apply(store, row, p['proposal'])['applied']
    auto = feedback(active.situation)
    auto.store = store
    assert finished(auto)[0]['items']


def test_shell_changes_include_failed_command_and_ignore_readonly(active, tmp_path):
    root = tmp_path / 'source'; root.mkdir()
    path = root / 'a.py'; path.write_text('x = 1\n')
    auto = Feedback(store=CodingStore(tmp_path / 'coding'))
    try:
        with command_changes(root, auto):
            path.read_text()
        assert not auto.pending
        with command_changes(root, auto):
            proc = subprocess.run(['sh', '-c', 'printf \'x: int = "oops"\\n\' > a.py; exit 7'], cwd=root)
        assert proc.returncode == 7
        assert finished(auto)[0]['items']
    finally:
        auto.close()


def test_deadline_failure_and_superseded_result_do_not_certify_success(active, tmp_path, monkeypatch):
    path = tmp_path / 'a.py'; path.write_text('x = 1')
    auto = Feedback()
    def slow(path, entry):
        time.sleep(.12)
        return {'path': str(path), 'document_hash': entry[1], 'status': 'received', 'items': []}
    monkeypatch.setattr(auto, 'query', slow)
    try:
        auto.mark(path)
        started = time.monotonic()
        assert auto.flush(wait=.001)[0]['status'] == 'pending'
        assert time.monotonic() - started < .1
        path.write_text('x = 2')
        rows = auto.flush(wait=1)
        assert rows[0]['status'] == 'stale'
    finally:
        auto.close()


def test_scope_and_unsupported_files_do_not_start_servers(active, tmp_path):
    from code_analysis_scope import bind
    root = tmp_path / 'copy'; root.mkdir()
    text = root / 'notes.md'; text.write_text('hello')
    outside = tmp_path / 'outside.py'; outside.write_text('x = 1')
    auto = Feedback()
    with bind(root):
        auto.mark(text)
        with pytest.raises(PermissionError):
            auto.mark(outside)
    assert not auto.pending and auto.pool is None


def test_native_edit_is_observed_and_turn_close_cancels_pending(active, tmp_path):
    path = tmp_path / 'a.py'; path.write_text('x = 1')
    s = active.situation
    s.observe_native({'type': 'tool_start', 'id': 'native', 'name': 'Edit', 'input': {'file_path': str(path)}})
    path.write_text('x = 2')
    s.observe_native({'type': 'tool_result', 'id': 'native', 'name': 'Edit', 'result': 'saved'})
    assert str(path) in s.code_feedback.pending
    s.close()
    assert s.code_feedback.closed.is_set()


@pytest.mark.parametrize('relative', [False, True])
def test_codex_file_receipt_resolves_against_issued_project(active, tmp_path, relative):
    path = tmp_path / 'a.py'; path.write_text('x = 1')
    s = active.situation
    s.observe_native({'type': 'tool_start', 'id': 'patch', 'name': 'apply_patch',
                      'input': {'changes': [{'path': 'a.py' if relative else str(path), 'kind': 'update'}]}})
    path.write_text('x = 2')
    s.observe_native({'type': 'tool_result', 'id': 'patch', 'name': 'apply_patch', 'result': 'saved'})
    assert str(path) in s.code_feedback.pending


def test_missing_server_reports_unavailable_without_failing_edit(active, tmp_path, monkeypatch):
    import code_analysis_documents
    from lsp_transport import LspError
    def missing(*args):
        raise LspError('SERVER_UNAVAILABLE', 'missing server')
    monkeypatch.setattr(code_analysis_documents, 'launch', missing)
    path = tmp_path / 'a.py'
    path.write_text('x = 1')
    file_written(path, b'x = 1')
    state = feedback(active.situation)
    state.store = CodingStore(tmp_path / 'coding')
    rows = finished(state)
    assert rows[0]['status'] == 'unavailable' and rows[0]['error_code'] == 'SERVER_UNAVAILABLE'
    assert path.read_text() == 'x = 1'


def test_post_hook_registers_file_and_returns_automatic_diagnostics(active, tmp_path):
    from api_supervision import situation_context
    path = tmp_path / 'a.py'; path.write_text('x: int = "bad"\n')
    feedback(active.situation).store = CodingStore(tmp_path / 'coding')
    result = situation_context('executor', 'situation-test', 'claude_hook', 'edit-1', str(path))
    assert 'lsp_after_edit' in result['context']
    assert 'assign' in result['context'] or 'pending' in result['context']


def test_git_dirty_file_modified_again_is_observed(active, tmp_path):
    from code_diagnostics import snapshot_sources
    root = tmp_path / 'repo'; root.mkdir()
    subprocess.run(['git', 'init', '-q', str(root)], check=True)
    path = root / 'a.py'; path.write_text('x = 0')
    subprocess.run(['git', '-C', str(root), 'add', '.'], check=True)
    subprocess.run(['git', '-C', str(root), '-c', 'user.name=Test', '-c', 'user.email=test@localhost',
                    'commit', '-qm', 'initial'], check=True)
    path.write_text('x = 1')
    before = snapshot_sources(root)
    path.write_text('x = 2')
    after = snapshot_sources(root)
    assert before[str(path)] != after[str(path)]


def test_many_diagnostics_fit_compact_and_delta_context_with_full_evidence(active, tmp_path):
    s = active.situation
    auto = Feedback(s)
    path = str(tmp_path / 'many.py')
    value = {'path': path, 'document_hash': 'version-1', 'status': 'received', 'server': 'python',
             'total': 100, 'items': [{'message': 'type mismatch ' + '긴 오류 설명' * 100,
                                    'severity': 1, 'range': {'start': {'line': i + 1, 'column': 1},
                                                             'end': {'line': i + 1, 'column': 2}}} for i in range(100)]}
    auto.publish(value)
    initial = s.prepare('test', baseline=True, compact=True)
    encoded = json.dumps(initial, ensure_ascii=False)
    assert len(encoded.encode()) <= 4000 and 'type mismatch' in encoded and 'lsp_after_edit' in encoded
    s.acknowledge('test', initial)
    auto.publish({**value, 'document_hash': 'version-2', 'total': 0, 'items': []})
    delta = s.prepare('test', retained=[initial['delivery_id']])
    assert delta['mode'] == 'delta' and 'lsp_after_edit' in json.dumps(delta)
    row = next(r for r in delta['observations'] if r['latest'].get('source') == 'lsp_after_edit')
    assert row['latest']['value']['total'] == 0 and row['latest']['source_ref']['id']


@pytest.mark.parametrize('compact', [False, True])
def test_edit_diagnostics_survive_crowded_context_and_clear_without_old_errors(active, tmp_path, compact):
    from test_execution_situation import mixed_workload
    from situation_evidence import observe_result
    from situation_delivery import render
    s = active.situation
    mixed_workload(s)
    auto = Feedback(s)
    path = str(tmp_path / 'invoice.py')
    items = [
        {'message': 'Type "str" is not assignable to return type "int"', 'severity': 1,
         'code': 'reportReturnType', 'source': 'Pyright',
         'range': {'start': {'line': 5, 'column': 12}, 'end': {'line': 5, 'column': 33}}},
        {'message': 'Type "int" is not assignable to return type "str"', 'severity': 1,
         'code': 'reportReturnType', 'source': 'Pyright',
         'range': {'start': {'line': 9, 'column': 12}, 'end': {'line': 9, 'column': 17}}},
    ]
    value = {'path': path, 'document_hash': 'broken', 'status': 'received', 'server': 'python',
             'total': 2, 'items': items}
    auto.publish(value)
    # Subsequent read/tool receipts used to evict the diagnostic from every MCP baseline.
    for i in range(12):
        s.observe({'kind': 'file', 'path': f'/read-{i}'}, 'version', {'read': True}, source='file_io')
        observe_result(s, {'output': 'file body ' * 200}, {'id': f'read-{i}'}, f'read-{i}')
    first = s.prepare('test', baseline=True, compact=compact)
    diagnostic = next(r for r in first['observations'] if r['latest']['source'] == 'lsp_after_edit')
    assert diagnostic['latest']['value']['items'] == items
    assert len(json.dumps(first, ensure_ascii=False).encode()) <= (4000 if compact else 8000)
    # This is the exact opaque-client transport, not just the stored observation.
    from api_supervision import situation_context
    context = situation_context('executor', 'situation-test')['context']
    assert all(item['message'].replace('"', '\\"') in context for item in items)
    s.acknowledge('test', first)
    auto.publish({**value, 'document_hash': 'fixed', 'total': 0, 'items': []})
    cleared = s.prepare('test', retained=[first['delivery_id']], compact=compact)
    diagnostic = next(r for r in cleared['observations'] if r['latest']['source'] == 'lsp_after_edit')
    assert diagnostic['latest']['subject_revision'] == 'fixed'
    assert diagnostic['latest']['value']['total'] == 0
    assert 'first' not in diagnostic
    assert 'reportReturnType' not in render(cleared)
    assert len(json.dumps(cleared, ensure_ascii=False).encode()) <= (4000 if compact else 2400)
