"""Dependency reuse requires a successful receipt and unchanged installed files."""
import boot_paths  # noqa: F401
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import remote_dependencies as dependencies


@pytest.fixture
def environment(tmp_path, monkeypatch):
    installed = tmp_path / 'environment'
    installed.mkdir()
    calls = []
    key = ['initial']
    monkeypatch.setattr(dependencies, 'configuration',
                        lambda *args: (key[0], [['install']], installed, True))

    def install(*args, **kwargs):
        calls.append(args)
        (installed / 'library.py').write_text('installed')

    monkeypatch.setattr(dependencies.subprocess, 'run', install)
    return tmp_path, installed, calls, key


def test_second_update_reuses_but_input_change_reinstalls(environment):
    root, installed, calls, key = environment
    dependencies.install(root, 'python')
    dependencies.install(root, 'python')
    assert len(calls) == 1
    key[0] = 'changed requirements'
    dependencies.install(root, 'python')
    assert len(calls) == 2
    (installed / 'library.py').unlink()
    dependencies.install(root, 'python')
    assert len(calls) == 3
    dependencies.install(root, 'python', refresh=True)
    assert len(calls) == 4


def test_failed_refresh_invalidates_success_receipt(environment, monkeypatch):
    root, _, calls, _ = environment
    dependencies.install(root, 'node')
    real = dependencies.subprocess.run
    monkeypatch.setattr(dependencies.subprocess, 'run',
                        lambda *a, **k: (_ for _ in ()).throw(subprocess.CalledProcessError(7, a[0])))
    with pytest.raises(subprocess.CalledProcessError):
        dependencies.install(root, 'node', refresh=True)
    assert not (root / 'data/runtime/remote_dependencies/node.json').exists()
    monkeypatch.setattr(dependencies.subprocess, 'run', real)
    dependencies.install(root, 'node')
    assert len(calls) == 2


def test_inputs_changed_during_install_are_not_certified(environment, monkeypatch):
    root, _, _, key = environment
    monkeypatch.setattr(dependencies.subprocess, 'run', lambda *a, **k: key.__setitem__(0, 'changed'))
    with pytest.raises(ValueError, match='changed during'):
        dependencies.install(root, 'python')
    assert not (root / 'data/runtime/remote_dependencies/python.json').exists()


def test_environment_cache_ignores_bytecode_but_detects_package_changes(tmp_path):
    (tmp_path / 'package.py').write_text('one')
    before = dependencies.environment_stamp(tmp_path)
    (tmp_path / '__pycache__').mkdir()
    (tmp_path / '__pycache__/package.pyc').write_bytes(b'cache')
    (tmp_path / '.tmp').mkdir()
    (tmp_path / '.tmp/tsconfig.app.tsbuildinfo').write_text('build cache')
    assert dependencies.environment_stamp(tmp_path) == before
    (tmp_path / 'package.py').write_text('different')
    assert dependencies.environment_stamp(tmp_path) != before


def test_external_editable_directory_disables_reuse(tmp_path):
    env, source = tmp_path / 'env', tmp_path / 'source'
    env.mkdir()
    source.mkdir()
    (env / 'editable').symlink_to(source, target_is_directory=True)
    assert dependencies.environment_stamp(env) is None


def test_python_requirements_includes_are_not_reused(tmp_path, monkeypatch):
    (tmp_path / 'backend').mkdir()
    req = tmp_path / 'backend/requirements-core.txt'
    req.write_text('fastapi==1.0\n-r extra.txt\n')
    monkeypatch.setattr(dependencies.subprocess, 'check_output', lambda *a, **k: 'python runtime')
    key, commands, _, reusable = dependencies.configuration(tmp_path, 'python', '')
    assert not reusable
    assert commands[-1][-2:] == ['pip', 'check']
    req.write_text('fastapi==2.0\n')
    new, _, _, reusable = dependencies.configuration(tmp_path, 'python', '')
    assert reusable and new != key


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
