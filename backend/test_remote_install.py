"""Source updates preserve build output without discarding authored changes."""
import boot_paths  # noqa: F401
import subprocess

import pytest

from test_remote_steps import git, installer, repos  # noqa: F401


def tracked(origin, name, content):
    path = origin / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    git(origin, "add", name)
    git(origin, "commit", "-m", "fixture content")


def test_two_updates_preserve_rebuilt_outputs_and_original_bytes(repos):
    origin, target = repos
    name = "frontend/i18n/catalog.json"
    tracked(origin, name, '{"ko":"원문"}\n')
    installer.update(target)
    for index in range(2):
        built = ('{"ko":"빌드 %s"}\r\n' % index).encode("utf-8")
        (target / name).write_bytes(built)
        assert installer.generated_changes(target) == [name]
        assert (target / name).read_bytes() == built  # preflight is read-only
        tracked(origin, name, '{"ko":"새 판 %s"}\n' % index)
        installer.update(target)
        assert (target / name).read_bytes() == (origin / name).read_bytes()
        copies = list((target / "data/_backups").glob("*/" + name))
        assert any(p.read_bytes() == built for p in copies)
        assert git(target, "status", "--porcelain", "--untracked-files=no") == ""


@pytest.mark.parametrize("name", ["frontend/i18n/translations.json", "src/user.py"])
def test_authored_changes_block_before_generated_files_are_touched(repos, name):
    origin, target = repos
    generated = "frontend/i18n/catalog.json"
    tracked(origin, generated, "{}")
    tracked(origin, name, "original")
    installer.update(target)
    (target / generated).write_text("rebuilt")
    (target / name).write_text("user correction")
    with pytest.raises(ValueError, match="Tracked local"):
        installer.update(target)
    assert (target / name).read_text() == "user correction"
    assert (target / generated).read_text() == "rebuilt"
    assert not (target / "data/_backups").exists()


def test_staged_generated_changes_are_not_unstaged_or_restored(repos):
    origin, target = repos
    name = "frontend/i18n/catalog.json"
    tracked(origin, name, "{}")
    installer.update(target)
    (target / name).write_text("staged")
    git(target, "add", name)
    with pytest.raises(ValueError, match="staged"):
        installer.update(target)
    assert git(target, "show", ":" + name) == "staged"


def test_git_paths_decode_utf8_even_with_a_non_utf8_locale(repos, monkeypatch):
    origin, target = repos
    name = "한글/日本語🙂.txt"
    tracked(origin, name, "keep")
    installer.update(target)
    original = subprocess.check_output

    def locale_output(*args, **kwargs):
        kwargs.setdefault("encoding", "cp1252")
        return original(*args, **kwargs)

    monkeypatch.setattr(installer.subprocess, "check_output", locale_output)
    assert name in installer.git(target, "ls-files", "-z").split("\0")


def test_generated_change_during_backup_is_not_discarded(repos, monkeypatch):
    origin, target = repos
    name = "frontend/i18n/catalog.json"
    tracked(origin, name, "{}")
    installer.update(target)
    (target / name).write_text("first build")
    copy = installer.shutil.copy2

    def concurrent_write(source, destination):
        copy(source, destination)
        source.write_text("second build")

    monkeypatch.setattr(installer.shutil, "copy2", concurrent_write)
    with pytest.raises(ValueError, match="during backup"):
        installer.update(target)
    assert (target / name).read_text() == "second build"
    assert next((target / "data/_backups").glob("*/" + name)).read_text() == "first build"


if __name__ == "__main__":
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))


def test_plan_keeps_driver_when_target_script_is_replaced(repos, monkeypatch):
    import os
    import sys
    from pathlib import Path
    _, target = repos
    plan = installer.make_plan(target, 'source-change', sys.executable, '/runtime/bin/npm')
    steps = {row['id']: row for row in plan['steps']}
    assert list(steps).index('quiesce') < list(steps).index('update')
    assert list(steps)[-1] == 'resume-runtime'
    script = Path(steps['preflight']['argv'][1])
    assert target / 'data/_backups' in script.parents
    (target / 'scripts').mkdir()
    (target / 'scripts/remote_install.py').write_text('raise RuntimeError("replaced")')
    env = {**os.environ, **plan['env']}
    env.pop('PYTHONPATH', None)
    result = subprocess.run([sys.executable, str(script), 'verify-head', '--root', str(target)],
                            env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_staged_recipe_runs_without_hub_or_target_code_and_does_not_change_inventory(tmp_path):
    import os
    import sys
    import generation_store

    hub = tmp_path / 'hub'
    hub.mkdir()
    (hub / 'scripts').mkdir()
    (hub / 'scripts/live.py').write_text('LIVE = True\n')
    before = generation_store.execution_inventory(hub)
    workspace = hub / 'outputs/job/tools'
    installer.stage_tools(hub, workspace)
    script = workspace / 'scripts/remote_update_runtime.py'
    script.write_text(script.read_text() + '\n# remote-only correction\n')
    assert not any(p.is_symlink() for p in workspace.rglob('*'))
    assert generation_store.execution_inventory(hub) == before

    with pytest.raises(FileExistsError):
        installer.stage_tools(hub, workspace)
    with pytest.raises(ValueError, match='outputs'):
        installer.stage_tools(hub, hub / 'scripts/remote-job')
    (hub / 'outputs/link').symlink_to(hub / 'scripts', target_is_directory=True)
    with pytest.raises(ValueError, match='outputs'):
        installer.stage_tools(hub, hub / 'outputs/link/remote-job')

    # Copy the prepared folder as a transfer would. No original hub/target
    # modules or PYTHONPATH may be needed even for quiesce's actual imports.
    remote = tmp_path / 'remote tools'
    installer.shutil.copytree(workspace, remote)
    target = tmp_path / 'target'
    target.mkdir()
    env = {k: v for k, v in os.environ.items() if not k.startswith('INDIEBIZ') and k != 'PYTHONPATH'}
    for name in ('remote_install', 'remote_steps', 'remote_boot'):
        result = subprocess.run([sys.executable, str(remote / f'scripts/{name}.py'), '--help'],
                                cwd=target, env=env, text=True, capture_output=True)
        assert result.returncode == 0, result.stdout + result.stderr
    result = subprocess.run([sys.executable, str(remote / 'scripts/remote_update_runtime.py'),
                             'quiesce', '--root', str(target), '--run-id', 'remote-only'],
                            cwd=target, env=env, text=True, capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert generation_store.execution_inventory(hub) == before


def test_flat_driver_patch_keeps_existing_plan_import_contract(tmp_path):
    import os
    import sys
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    driver = tmp_path / 'old-driver'
    driver.mkdir()
    for name in ('remote_install.py', 'remote_update_runtime.py', 'remote_boot.py'):
        installer.shutil.copy2(root / 'scripts' / name, driver / name)
    env = {**os.environ, 'INDIEBIZ_UPDATE_ROOT': str(root)}
    env.pop('PYTHONPATH', None)
    for name in ('remote_install.py', 'remote_update_runtime.py'):
        result = subprocess.run([sys.executable, str(driver / name), '--help'],
                                cwd=tmp_path, env=env, text=True, capture_output=True)
        assert result.returncode == 0, result.stdout + result.stderr
