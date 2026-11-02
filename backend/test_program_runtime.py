"""Independent program revision, submodule isolation, leases and durable state."""
import asyncio
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest
import program_runtime as runtime
import program_versions as versions


def program(tmp_path, name='new-program', source=None):
    repo = tmp_path / 'repo'
    relative = Path('data/packages/installed/tools') / name
    root = repo / relative
    root.mkdir(parents=True)
    (root / 'handler.py').write_text(source or 'import helper\ndef execute(value, context): return helper.value\n')
    (root / 'helper.py').write_text('value = 1\n')
    baseline = tmp_path / 'sealed' / relative
    shutil.copytree(root, baseline)
    deployed = runtime.Namespace(baseline, 'baseline_' + name.replace('-', '_')).load('handler')
    bound = runtime.wrap(name, baseline, repo, deployed)
    return repo, root, baseline, bound


def publish(repo, root, baseline, *, source=None, helper='value = 2\n'):
    if source:
        (root / 'handler.py').write_text(source)
    (root / 'helper.py').write_text(helper)
    manifest = versions.snapshot(repo, root.name, root, code_root=baseline.parents[4])
    versions.publish(repo, manifest, versions.source_inventory(baseline), {'test': True})
    return manifest


def test_unregistered_program_replaces_its_helper_without_worker_restart(tmp_path):
    repo, root, baseline, bound = program(tmp_path)
    assert bound.execute({}, None) == 1
    revision = publish(repo, root, baseline)
    assert bound.execute({}, None) == 2
    assert bound.version == revision['version']
    assert not (root / 'runtime_components.json').exists()
    changed = {str(root.relative_to(repo) / 'helper.py')}
    inv = {str(root.relative_to(repo) / p): h for p, h in revision['files'].items()}
    assert versions.covers_changes(repo, baseline.parents[4], changed, inv) == changed


def test_old_generator_keeps_old_revision_and_other_program_can_change(tmp_path):
    source = 'import helper\ndef execute(value, context):\n yield helper.value\n yield helper.value\n'
    repo, root, baseline, bound = program(tmp_path / 'a', source=source)
    other_repo, other_root, other_base, other = program(tmp_path / 'b')
    call = bound.execute({}, None)
    assert next(call) == 1
    publish(repo, root, baseline)
    assert runtime.load(root.name, baseline, repo).pending is not None
    publish(other_repo, other_root, other_base, helper='value = 9\n')
    assert other.execute({}, None) == 9
    assert next(call) == 1
    call.close()
    assert list(bound.execute({}, None)) == [2, 2]


def test_state_export_restore_and_close_are_program_local(tmp_path):
    source = ('state = 0\nclosed = False\n'
              'def execute(value, context):\n global state\n state += 1\n return state\n'
              'def __program_export__(): return state\n'
              'def __program_restore__(value):\n global state\n state = value\n'
              'def __program_close__():\n global closed\n closed = True\n')
    repo, root, baseline, bound = program(tmp_path, source=source)
    assert bound.execute({}, None) == 1
    old = bound.module
    publish(repo, root, baseline)
    assert bound.execute({}, None) == 2
    assert old.closed is True


def test_coroutine_pins_program_until_await_finishes(tmp_path):
    source = 'import helper\nasync def execute(value, context): return helper.value\n'
    repo, root, baseline, bound = program(tmp_path, source=source)
    call = bound.execute({}, None)
    publish(repo, root, baseline)
    assert not bound.select(root, 'another')
    assert asyncio.run(call) == 1
    assert asyncio.run(bound.execute({}, None)) == 2


def test_helper_names_and_sys_path_do_not_leak_between_namespaces(tmp_path):
    repo, root, baseline, bound = program(tmp_path)
    before = list(sys.path)
    publish(repo, root, baseline, source=('import sys\nsys.path.insert(0, "must-not-leak")\n'
            'from . import helper\ndef execute(value, context): return helper.value\n'))
    assert bound.execute({}, None) == 2
    assert sys.path == before
    assert 'helper' not in sys.modules or getattr(sys.modules['helper'], '__file__', None) != str(root / 'helper.py')


def test_corrupt_object_and_protected_contract_are_not_activated(tmp_path):
    repo, root, baseline, bound = program(tmp_path)
    manifest = publish(repo, root, baseline)
    selected, _ = versions.selected(repo, root.name, baseline)
    (selected / 'helper.py').write_text('value = 99\n')
    with pytest.raises(ValueError, match='corrupt'):
        bound.execute({}, None)
    (root / 'runtime_components.json').write_text('[]')
    manifest = versions.snapshot(repo, root.name, root, code_root=baseline.parents[4])
    with pytest.raises(PermissionError, match='protected'):
        versions.publish(repo, manifest, versions.source_inventory(baseline), {})


def test_existing_tool_loader_uses_new_submodules_without_cache_reset(tmp_path, monkeypatch):
    import tool_loader
    source = ('import importlib.util\nfrom pathlib import Path\n'
              'def execute(value, context):\n'
              ' spec = importlib.util.spec_from_file_location("local_helper", Path(__file__).with_name("helper.py"))\n'
              ' module = importlib.util.module_from_spec(spec)\n'
              ' spec.loader.exec_module(module)\n return module.value\n')
    repo, root, baseline, _ = program(tmp_path, source=source)
    tool_loader.clear_cache()
    monkeypatch.setattr(tool_loader, '_tool_to_package_map', {'new_tool': root.name})
    monkeypatch.setattr(tool_loader, 'build_tool_package_map', lambda **kw: {'new_tool': root.name})
    monkeypatch.setattr(tool_loader, 'require_tool_active', lambda *a: None)
    monkeypatch.setattr(tool_loader, 'package_path', lambda *a: baseline)
    monkeypatch.setattr('runtime_utils.get_source_root', lambda: repo)
    loaded = tool_loader.load_tool_handler('new_tool')
    assert loaded.execute({}, None) == 1
    publish(repo, root, baseline)
    assert tool_loader.load_tool_handler('new_tool').execute({}, None) == 2
    assert tool_loader.load_tool_handler('new_tool') is loaded
    tool_loader.clear_cache()


def test_background_thread_requires_drain_without_blocking_other_programs(tmp_path):
    import threading
    repo, root, baseline, bound = program(tmp_path)
    stop = threading.Event()
    worker = threading.Thread(target=stop.wait, daemon=True)
    bound.module.worker = worker
    worker.start()
    try:
        publish(repo, root, baseline)
        assert runtime.load(root.name, baseline, repo).pending is not None
        assert bound.execute({}, None) == 1
    finally:
        stop.set()
        worker.join(2)
    assert bound.execute({}, None) == 2


def test_failed_program_import_cleans_only_its_new_namespace(tmp_path):
    repo, root, baseline, bound = program(tmp_path)
    before = {name for name in sys.modules if name.startswith('_indiebiz_program_')}
    publish(repo, root, baseline, source='import helper\nraise RuntimeError("broken candidate")\n')
    with pytest.raises(RuntimeError, match='broken candidate'):
        bound.execute({}, None)
    assert {name for name in sys.modules if name.startswith('_indiebiz_program_')} == before
    assert bound.module.execute({}, None) == 1

def test_handler_attribute_writes_reach_its_execution_globals(tmp_path, monkeypatch):
    repo, root, baseline, bound = program(tmp_path, source='value = 1\ndef execute(args, context): return value\n')
    with monkeypatch.context() as patch:
        patch.setattr(bound, 'value', 7)
        assert bound.execute({}, None) == 7
    assert bound.execute({}, None) == 1

@pytest.mark.parametrize('namespace_package', [False, True])
def test_dotted_local_import_preserves_each_parent_module(tmp_path, namespace_package):
    repo, root, baseline, bound = program(tmp_path)
    nested = root / 'nested/deep'
    nested.mkdir(parents=True)
    if not namespace_package:
        (root / 'nested/__init__.py').write_text('')
        (nested / '__init__.py').write_text('')
    (nested / 'leaf.py').write_text('value = 11')
    publish(repo, root, baseline, source='import nested.deep.leaf\ndef execute(args, context): return nested.deep.leaf.value\n')
    assert bound.execute({}, None) == 11

if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
