"""Atomic module/catalog pointers, source verification and watcher ownership."""
from pathlib import Path
import shutil
import types

import boot_paths  # noqa: F401
import pytest
import program_publication as pub
import program_modules as modules
from test_repair_staging import _load_handler, _make_repo


def session_for(repo, code, changes):
    from test_repair_workspace_completion import module
    candidate = module('repair_candidate')
    work = repo / 'candidate'
    work.mkdir(exist_ok=True)
    sealed = {}
    for relative, content in changes.items():
        target = work / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if content is not None:
            target.write_text(content)
        sealed[relative] = {'before': candidate.fingerprint(code / relative), 'after': candidate.fingerprint(target)}
    return {'worktree': 'candidate', 'key': 'example', 'sealed': sealed,
            'derived_files': {p: row['after'] for p, row in sealed.items() if p == 'data/ibl_nodes.yaml'}}


def test_prepared_catalog_is_invisible_then_both_loaders_see_publication(tmp_path, monkeypatch):
    import runtime_utils
    import ibl_access
    import ibl_registry
    repo, code = tmp_path / 'repo', tmp_path / 'sealed'
    (repo / 'data').mkdir(parents=True)
    old = 'nodes:\n  sense:\n    actions:\n      example: {description: old}\n'
    new = old.replace('old', 'new')
    (repo / 'data/ibl_nodes.yaml').write_text(old)
    shutil.copytree(repo, code)
    monkeypatch.setattr(runtime_utils, 'get_code_root', lambda: code)
    monkeypatch.setattr(runtime_utils, 'get_source_root', lambda: repo)
    monkeypatch.setattr(runtime_utils, 'get_base_path', lambda: repo)
    monkeypatch.setattr(ibl_registry, '_nodes_path', None)
    monkeypatch.setattr(ibl_registry, '_prune_foreign_vocabulary', lambda data: None)
    ibl_access.invalidate_nodes_cache()
    ibl_registry.invalidate_nodes()
    session = session_for(repo, code, {'data/ibl_nodes.yaml': new})
    row = pub.snapshot(repo, code, session)
    pub.publish(repo, row)
    (repo / 'data/ibl_nodes.yaml').write_text(new)
    assert runtime_utils.get_vocabulary_path() == code / 'data/ibl_nodes.yaml'
    assert ibl_access.load_nodes_raw()['nodes']['sense']['actions']['example']['description'] == 'old'
    row['activation'] = 'active'
    pub.publish(repo, row)
    assert ibl_access.load_nodes_raw()['nodes']['sense']['actions']['example']['description'] == 'new'
    assert ibl_registry.load_nodes_installed()['nodes']['sense']['actions']['example']['description'] == 'new'
    session['module_publication'] = row
    assert pub.activation_matches(repo, code, session)
    sha = pub.file_hash(repo / 'data/ibl_nodes.yaml')
    assert pub.covers_changes(repo, code, {'data/ibl_nodes.yaml', 'backend/other.py'}, {'data/ibl_nodes.yaml': sha}) == {'data/ibl_nodes.yaml'}
    (pub.object_root(repo, row) / 'data/ibl_nodes.yaml').write_text(old)
    with pytest.raises(ValueError, match='corrupt'):
        pub.selected(repo, code)
    ibl_access.invalidate_nodes_cache()
    ibl_registry.invalidate_nodes()


def test_core_publication_rejected_and_unrelated_files_stay_sealed(tmp_path):
    repo, code = tmp_path / 'repo', tmp_path / 'sealed'
    repo.mkdir()
    code.mkdir()
    (code / 'unrelated.txt').write_text('old')
    session = session_for(repo, code, {'backend/base/runtime_utils.py': 'pass\n'})
    with pytest.raises(PermissionError, match='Protected'):
        pub.snapshot(repo, code, session)
    session = session_for(repo, code, {'backend/services/new_feature.py': 'VALUE = 2\n'})
    row = pub.snapshot(repo, code, session)
    assert (pub.object_root(repo, row) / 'unrelated.txt').read_text() == 'old'


def test_module_apply_changes_captured_reference_and_commits_without_restart(tmp_path, monkeypatch):
    import subprocess
    repo = _make_repo(tmp_path / 'repo')
    relative = 'backend/services/local_feature.py'
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('def run(): return 1\n')
    with (repo / '.gitignore').open('a') as output:
        output.write('\ndata/restart_control/\ndata/system_ai_state/\n')
    for command in (['config', 'user.name', 'Test'], ['config', 'user.email', 'test@example.test'],
                    ['add', '.'], ['commit', '-qm', 'module fixture']):
        subprocess.run(['git', *command], cwd=repo, check=True)
    old_tables = dict(modules._TABLE), dict(modules._OWNERS)
    module = types.ModuleType('local_feature')
    modules.initialize(relative, module, path.read_text(), path)
    reference = module.run
    handler = _load_handler()
    handler._REPO_ROOT = repo
    st = handler._staging_mod()
    monkeypatch.setattr(st, '_repair_owner', lambda: 'owner')
    for name in ('get_code_root', 'get_source_root', 'get_base_path'):
        monkeypatch.setattr('runtime_utils.' + name, lambda: repo)
    candidate = st.stage_file(str(repo), 'module-test', str(path))
    Path(candidate).write_text('def run(): return 2\n')
    session = st.read_session(str(repo), 'module-test')
    session.update(program_policy=1, repair_policy=2)
    st._candidate.seal(str(repo), session, [{'gate': 'fixture', 'passed': True}],
                       {'status': 'APPROVED'}, {'criteria': [{'id': 'C1', 'text': 'module correction'}]})
    st._save_session(str(repo), session)
    monkeypatch.setattr(st, '_schedule_deferred_apply', lambda *a: pytest.fail('whole worker restart'))
    try:
        result = handler._load_sibling('program_apply').apply(st, str(repo), session)
        assert result['success'] and result['activated'] and not result['restart_required'], result
        assert reference() == 2
        assert st._candidate.active_generation_bytes(repo, session)[0] == 'matched'
        from repair_readiness import program_published
        assert program_published(repo, session)
    finally:
        modules._TABLE, modules._OWNERS = old_tables


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))


def test_sparse_package_view_still_protects_unchanged_gate(tmp_path):
    import program_versions
    repo, code = tmp_path / 'repo', tmp_path / 'code'
    prefix = 'data/packages/installed/tools/system_essentials'
    (repo / prefix).mkdir(parents=True)
    (repo / prefix / 'handler.py').write_text('def execute(value, context): return 1\n')
    (repo / prefix / 'ordinary_helper.py').write_text('VALUE = 1\n')
    shutil.copytree(repo, code)
    relative = prefix + '/ordinary_helper.py'
    session = session_for(repo, code, {relative: 'VALUE = 2\n'})
    row = pub.snapshot(repo, code, session)
    assert (pub.object_root(repo, row) / prefix / 'handler.py').is_symlink()
    assert 'handler.py' in pub.package_files(repo, code, row, 'system_essentials')
    (repo / relative).write_text('VALUE = 2\n')
    row['activation'] = 'active'
    pub.publish(repo, row)
    selected, record = program_versions.selected(repo, 'system_essentials', code / prefix)
    assert selected == code / prefix and record is None


def test_module_first_import_uses_published_file_and_can_add_module(tmp_path, monkeypatch):
    import sys
    import importlib
    repo, code = tmp_path / 'repo', tmp_path / 'code'
    relative = 'backend/services/brand_new.py'
    (repo / 'backend/services').mkdir(parents=True)
    shutil.copytree(repo, code)
    source = 'from pathlib import Path\ndef value(): return Path(__file__).read_text().startswith("from")\n'
    session = session_for(repo, code, {relative: source})
    row = pub.snapshot(repo, code, session)
    (repo / relative).write_text(source)
    row['activation'] = 'active'
    pub.publish(repo, row)
    old = list(sys.meta_path), list(modules._FINDERS), dict(modules._OWNERS), modules._TABLE
    monkeypatch.syspath_prepend(str(code / 'backend/services'))
    try:
        modules.install(code, repo)
        loaded = importlib.import_module('brand_new')
        assert Path(loaded.__file__) == pub.object_root(repo, row) / relative
        assert loaded.value()
    finally:
        sys.modules.pop('brand_new', None)
        sys.meta_path[:], modules._FINDERS[:], modules._OWNERS, modules._TABLE = old


@pytest.mark.parametrize('catalog_kind', ['vocabulary', 'derived'])
def test_combined_catalog_and_package_waits_only_for_package_calls(tmp_path, monkeypatch, catalog_kind):
    import program_runtime as runtime
    from test_repair_workspace_completion import module
    from types import SimpleNamespace as NS
    repo, code = tmp_path / 'repo', tmp_path / 'code'
    prefix = 'data/packages/installed/tools/mixed-feature'
    (repo / prefix).mkdir(parents=True)
    (repo / prefix / 'handler.py').write_text('def execute(value, context): return 1\n')
    (repo / 'data/ibl_nodes.yaml').write_text('nodes: {}\n')
    shutil.copytree(repo, code)
    initial = runtime.Namespace(code / prefix, 'mixed_test').load('handler')
    program = runtime.wrap('mixed-feature', code / prefix, repo, initial)
    changes = {prefix + '/handler.py': 'def execute(value, context): return 2\n',
               'data/ibl_nodes.yaml': 'nodes: {sense: {actions: {}}}\n'}
    session = session_for(repo, code, changes)
    row = pub.snapshot(repo, code, session)
    for p, content in changes.items():
        (repo / p).write_text(content)
    pub.publish(repo, row)
    monkeypatch.setattr('runtime_utils.get_code_root', lambda: code)
    monkeypatch.setattr('runtime_utils.get_source_root', lambda: repo)
    monkeypatch.setattr('ibl_routing.invalidate_runtime_caches', lambda: [])
    pending = []
    monkeypatch.setattr(runtime, 'finish_later', lambda *args: pending.append(args))
    session.update(module_publication=row, readiness={},
                   program_scope={'programs': [{'kind': 'package', 'owner': 'package:mixed-feature', 'root': prefix, 'files': [prefix + '/handler.py']},
                                                {'kind': catalog_kind, 'owner': 'vocabulary:sense'}]},
                   program_activation=[{'activation': 'pending'}])
    st = NS(_candidate=NS(commit=lambda *a: {'success': True, 'commit': 'test-receipt'}), _save_session=lambda *a: None)
    old_table = modules._TABLE
    try:
        with program.lease():
            result = module('program_host_apply').finish(st, repo, session)
            assert not result['activated'] and pending
            assert pub.selected(repo, code)[0] == code
        result = module('program_host_apply').finish(st, repo, session)
        assert result['activated'] and not result['restart_required']
        assert program.execute({}, None) == 2
        assert pub.selected(repo, code)[0] == pub.object_root(repo, row)
    finally:
        modules._TABLE = old_table


def test_unrelated_live_edit_does_not_revoke_published_catalog(tmp_path):
    repo, code = tmp_path / 'repo', tmp_path / 'code'
    (repo / 'data').mkdir(parents=True)
    (repo / 'backend/services').mkdir(parents=True)
    (repo / 'data/ibl_nodes.yaml').write_text('nodes: {}\n')
    (repo / 'backend/services/first.py').write_text('VALUE = 1\n')
    shutil.copytree(repo, code)
    a = session_for(repo, code, {'backend/services/first.py': 'VALUE = 2\n'})
    a['key'] = 'first'
    first = pub.snapshot(repo, code, a)
    (repo / 'backend/services/first.py').write_text('VALUE = 2\n')
    first['activation'] = 'active'
    pub.publish(repo, first)
    b = session_for(repo, code, {'data/ibl_nodes.yaml': 'nodes: {sense: {}}\n'})
    b['key'] = 'catalog'
    catalog = pub.snapshot(repo, code, b)
    (repo / 'data/ibl_nodes.yaml').write_text('nodes: {sense: {}}\n')
    catalog['activation'] = 'active'
    pub.publish(repo, catalog)
    # A human's unrelated unvalidated edit cannot roll B back to the host catalog.
    (repo / 'backend/services/first.py').write_text('VALUE = 99\n')
    b['module_publication'] = catalog
    assert pub.activation_matches(repo, code, b)
    assert pub.selected(repo, code)[0] == pub.object_root(repo, catalog)
    assert pub.covers_changes(repo, code, {'backend/services/first.py'}, {'backend/services/first.py': pub.file_hash(repo / 'backend/services/first.py')}) == set()


def test_pending_program_does_not_publish_with_another_program_or_erase_it(tmp_path):
    repo, code = tmp_path / 'repo', tmp_path / 'code'
    (repo / 'backend/services').mkdir(parents=True)
    for name in ('first', 'second'):
        (repo / f'backend/services/{name}.py').write_text('VALUE = 1\n')
    shutil.copytree(repo, code)
    a = session_for(repo, code, {'backend/services/first.py': 'VALUE = 2\n'})
    a['key'] = 'first'
    first = pub.snapshot(repo, code, a)
    pub.publish(repo, first)  # still draining, not active
    b = session_for(repo, code, {'backend/services/second.py': 'VALUE = 3\n'})
    b['key'] = 'second'
    second = pub.snapshot(repo, code, b)
    assert 'backend/services/first.py' not in second['files']
    second['activation'] = 'active'
    pub.publish(repo, second)
    # Resume A against B's accepted object, keeping B's source and ownership.
    resumed = pub.snapshot(repo, code, a)
    assert resumed['files']['backend/services/second.py'] == second['files']['backend/services/second.py']
    assert resumed['owners']['backend/services/second.py'] == 'second'
