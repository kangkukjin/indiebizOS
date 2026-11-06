"""Real pinned Python/TypeScript servers, provider-neutral workspace lifecycle."""
from pathlib import Path

import boot_paths  # noqa: F401
import pytest
from coding_store import CodingStore
from workspace_sessions import Workspace
from code_analysis import manager, shutdown
from code_analysis_drivers import TOOLCHAIN


@pytest.fixture
def code(tmp_path):
    root = tmp_path / 'src'; root.mkdir()
    ws = Workspace(coding_store=CodingStore(tmp_path / 'state'))
    yield ws, root
    shutdown()


@pytest.mark.parametrize('language', ['python', 'typescript'])
def test_real_definition_rename_and_persistent_generation(code, language):
    if not (TOOLCHAIN / 'node_modules').is_dir():
        pytest.skip('install pinned servers with npm ci --prefix data/code_analysis')
    ws, root = code
    if language == 'python':
        (root / 'a.py').write_text('def greet(name: str) -> str:\n    return name\n')
        (root / 'b.py').write_text('from a import greet\ngreet("한글😀")\n')
        selector = {'analysis': 'definition', 'path': 'b.py', 'line': 2, 'column': 2}
        expected_path = 'a.py'
    else:
        (root / 'tsconfig.json').write_text('{"compilerOptions":{"strict":true},"include":["*.ts"]}')
        (root / 'a.ts').write_text('export function greet(name: string): string { return name; }\n')
        (root / 'b.ts').write_text('import { greet } from "./a";\ngreet("한글😀");\n')
        selector = {'analysis': 'definition', 'path': 'b.ts', 'line': 2, 'column': 2}
        expected_path = 'a.ts'
    resource = ws.open(root, kind='code')['resource']
    first = ws.read(resource, selector)
    assert first['items'][0]['path'] == expected_path
    second = Workspace(coding_store=ws.code().store).read(resource, selector)
    assert first['analysis']['generation'] == second['analysis']['generation']
    proposal = ws.propose(resource, {'analysis': 'rename', 'target': first['items'][0]['target'], 'new_name': 'welcome'})
    result = ws.apply(resource, proposal['proposal'])
    assert result['applied'] and len(result['paths']) == 2
    assert 'welcome' in (root / expected_path).read_text()
    assert ws.apply(resource, proposal['proposal'])['cached']


def test_inspect_never_creates_git_or_grants_write(code):
    ws, root = code
    (root / 'a.py').write_text('answer = 42\n')
    r = ws.open(root, kind='code', mode='inspect')['resource']
    assert not (root / '.git').exists()
    p = ws.propose(r, {'path': 'a.py'}, 'changed\n')
    with pytest.raises(PermissionError):
        ws.apply(r, p['proposal'])
    assert (root / 'a.py').read_text() == 'answer = 42\n'


def test_scope_rejects_other_resource(code, tmp_path):
    from code_analysis_scope import bind
    ws, root = code
    other = tmp_path / 'other'; other.mkdir()
    resource = ws.open(other, kind='code', mode='inspect')['resource']
    with bind(root):
        with pytest.raises(PermissionError):
            ws.read(resource)


def test_draft_imports_are_isolated_saved_files_stay_unchanged_and_snapshot_is_fixed(code):
    ws, root = code
    (root / 'a.py').write_text('answer: int = 1\n')
    (root / 'b.py').write_text('from a import answer\nanswer\n')
    resource = ws.open(root, kind='code')['resource']
    app, row = ws.code().analysis, ws.code().project(resource)
    draft1 = app.draft(row, client='window-a', path='a.py', text='answer: str = "hello"\n')
    draft2 = app.draft(row, client='window-b', path='a.py', text='answer: float = 1.2\n')
    selector = {'analysis': 'hover', 'path': 'b.py', 'line': 2, 'column': 2}
    first = ws.read(resource, {**selector, 'view': draft1['view']})
    second = ws.read(resource, {**selector, 'view': draft2['view']})
    saved = ws.read(resource, selector)
    assert 'str' in str(first['items']) and 'float' in str(second['items']) and 'int' in str(saved['items'])
    assert len({r['analysis']['generation'] for r in (first, second, saved)}) == 3
    with pytest.raises(PermissionError):
        app.draft(row, client='window-b', view=draft1['view'], expected=1, action='save')
    snapshot = ws.snapshot(resource)['snapshot']
    (root / 'a.py').write_text('answer: bool = True\n')
    fixed = ws.read(resource, selector, snapshot=snapshot)
    assert 'int' in str(fixed['items'])
    with pytest.raises(PermissionError, match='스냅샷'):
        ws.propose(resource, {'analysis': 'rename', 'target': fixed['items'][0]['target'], 'new_name': 'changed'})
    with pytest.raises(Exception, match='파일이 그 사이'):
        app.draft(row, client='window-a', view=draft1['view'], expected=1, action='save')


def test_draft_rename_updates_multiple_buffers_then_one_save(code):
    ws, root = code
    (root / 'a.ts').write_text('export const answer = 42;\n')
    (root / 'b.ts').write_text('import {answer} from "./a";\nanswer;\n')
    (root / 'tsconfig.json').write_text('{"include":["*.ts"]}')
    resource = ws.open(root, kind='code')['resource']
    app, row = ws.code().analysis, ws.code().project(resource)
    view = app.draft(row, client='editor', path='a.ts', text='export const answer = 43;\n')
    p = ws.propose(resource, {'analysis': 'rename', 'path': 'a.ts', 'line': 1, 'column': 15, 'new_name': 'result', 'view': view['view']})
    with pytest.raises(PermissionError): ws.apply(resource, p['proposal'], client='other')
    result = ws.apply(resource, p['proposal'], client='editor')
    assert 'result' in result['files']['a.ts'] and 'result' in result['files']['b.ts']
    assert 'answer' in (root / 'a.ts').read_text()
    app.draft(row, client='editor', view=view['view'], expected=result['revision'], action='save')
    assert 'result = 43' in (root / 'a.ts').read_text()
    assert 'result' in (root / 'b.ts').read_text()


def test_flat_boot_paths_are_derived_without_executing_project(code):
    ws, root = code
    (root / 'backend/services').mkdir(parents=True)
    (root / 'backend/boot_paths.py').write_text('LAYER_DIRS = ["services"]\nraise RuntimeError("must not execute")\n')
    (root / 'backend/services/example.py').write_text('def welcome() -> int:\n    return 42\n')
    (root / 'backend/main.py').write_text('from example import welcome\nwelcome()\n')
    r = ws.open(root, kind='code', mode='inspect')['resource']
    result = ws.read(r, {'analysis': 'definition', 'path': 'backend/main.py', 'line': 2, 'column': 2})
    assert result['items'][0]['path'] == 'backend/services/example.py'
    assert 'backend/boot_paths.py:LAYER_DIRS' in result['analysis']['environment']['sources']


def test_mixed_language_batch_and_unsupported_is_not_empty_success(code):
    ws, root = code
    (root / 'a.py').write_text('answer = 42\n')
    (root / 'b.ts').write_text('const greeting: string = "hello";\n')
    r = ws.open(root, kind='code', mode='inspect')['resource']
    result = ws.read(r, {'analysis': 'batch', 'requests': [
        {'analysis': 'hover', 'path': 'a.py', 'line': 1, 'column': 2},
        {'analysis': 'hover', 'path': 'b.ts', 'line': 1, 'column': 9}]})
    assert all(i['success'] for i in result['items'])
    assert {i['analysis']['server'] for i in result['items']} == {'python', 'typescript'}
    unsupported = ws.read(r, {'analysis': 'implementation', 'path': 'a.py', 'line': 1, 'column': 2})
    assert unsupported['success'] is False and unsupported['analysis']['status'] == 'unsupported'


def test_draft_save_recovers_crash_after_disk_commit(code, monkeypatch):
    import code_analysis_changes
    ws, root = code
    (root / 'a.py').write_text('answer = 1\n')
    resource = ws.open(root, kind='code')['resource']
    app, row = ws.code().analysis, ws.code().project(resource)
    view = app.draft(row, client='editor', path='a.py', text='answer = 2\n')
    original_apply = code_analysis_changes.apply

    def crash_after_commit(*args, **kwargs):
        original_apply(*args, **kwargs)
        raise RuntimeError('simulated process loss after disk commit')

    monkeypatch.setattr(code_analysis_changes, 'apply', crash_after_commit)
    with pytest.raises(RuntimeError, match='process loss'):
        app.draft(row, client='editor', view=view['view'], expected=1, action='save')
    assert (root / 'a.py').read_text() == 'answer = 2\n'
    monkeypatch.setattr(code_analysis_changes, 'apply', original_apply)
    result = app.draft(row, client='editor', view=view['view'], expected=1, action='save')
    assert result['saved'] and not result['files'] and result['revision'] == 2
    assert len(app.store.list('workspace_proposal')) == 1
