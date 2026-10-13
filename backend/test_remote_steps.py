"""Remote plans preserve process failures, identity and retry boundaries."""
import boot_paths  # noqa: F401
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


runner = module("remote_steps")
installer = module("remote_install")


def command(code):
    return [sys.executable, "-c", code]


def plan(tmp_path, steps):
    return {"version": 1, "run_id": "test", "cwd": str(tmp_path), "steps": steps}


def test_failed_command_stops_following_steps_and_retains_original_output(tmp_path):
    p = plan(tmp_path, [{"id": "install", "argv": command("print('install failed'); raise SystemExit(7)")},
                        {"id": "later", "argv": command("open('wrong','w').close()")}])
    out = runner.run(p)
    assert out["status"] == "failed" and not (tmp_path / "wrong").exists()
    attempt = out["steps"]["install"]["attempts"][0]
    assert attempt["exit"] == 7 and not attempt["command_ok"]
    assert "install failed" in Path(attempt["log"]).read_text()
    assert len(runner.run(p)["steps"]["install"]["attempts"]) == 1


def test_resume_rechecks_verification_without_repeating_successful_effect(tmp_path):
    p = plan(tmp_path, [{"id": "install", "argv": command("open('count','a').write('x')"),
                        "verify": command("from pathlib import Path; assert Path('ready').exists()")}])
    assert runner.run(p)["status"] == "failed"
    (tmp_path / "ready").touch()
    done = runner.run(p, retry="install")
    assert done["status"] == "succeeded"
    assert done["steps"]["install"]["attempts"][-1]["reused_command"]
    assert runner.run(p)["status"] == "succeeded"
    assert (tmp_path / "count").read_text() == "x"
    (tmp_path / "ready").unlink()
    assert runner.run(p)["status"] == "blocked"
    assert (tmp_path / "count").read_text() == "x"
    (tmp_path / "ready").touch()
    done = runner.run(p)
    assert done["status"] == "succeeded" and "blocked_step" not in done and "reason" not in done


def test_plan_change_and_interrupted_execution_never_replay(tmp_path):
    p = plan(tmp_path, [{"id": "once", "argv": command("open('count','a').write('x')")}])
    runner.run(p)
    with pytest.raises(ValueError, match="changed"):
        runner.run({**p, "env": {"CHANGED": "yes"}})
    journal = tmp_path / "data/runtime/remote_steps/test/state.json"
    state = json.loads(journal.read_text())
    state["steps"]["once"]["status"] = "running"
    runner.atomic_json(journal, state)
    assert runner.run(p, retry="once")["status"] == "blocked"
    assert (tmp_path / "count").read_text() == "x"


def test_timeout_and_lock_are_distinct_from_success(tmp_path):
    p = plan(tmp_path, [{"id": "sleep", "argv": command("import time; print('started',flush=True); time.sleep(30)"), "timeout": .2}])
    out = runner.run(p)
    assert out["status"] == "failed"
    attempt = out["steps"]["sleep"]["attempts"][0]
    assert attempt["timeout"] and "started" in Path(attempt["log"]).read_text()
    with runner.exclusive(tmp_path / "data/runtime/remote_steps/execution.lock"):
        with pytest.raises(OSError):
            runner.run(p, retry="sleep")


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], text=True).strip()


@pytest.fixture
def repos(tmp_path):
    origin, target = tmp_path / "origin", tmp_path / "target"
    origin.mkdir()
    git(origin, "init", "-b", "main")
    git(origin, "config", "user.name", "fixture")
    git(origin, "config", "user.email", "fixture@example.invalid")
    (origin / ".gitignore").write_text("ignored.txt\ndata/_backups/\n")
    git(origin, "add", ".gitignore")
    git(origin, "commit", "-m", "initial")
    subprocess.run(["git", "clone", str(origin), str(target)], check=True, capture_output=True)
    return origin, target


def test_update_preserves_ignored_collision_and_matches_origin(repos):
    origin, target = repos
    (target / "ignored.txt").write_text("local data")
    (origin / "ignored.txt").write_text("new tracked file")
    git(origin, "add", "-f", "ignored.txt")
    git(origin, "commit", "-m", "new")
    installer.update(target)
    assert git(target, "rev-parse", "HEAD") == git(target, "rev-parse", "origin/main")
    assert (target / "ignored.txt").read_text() == "new tracked file"
    assert next((target / "data/_backups").glob("*/ignored.txt")).read_text() == "local data"


def test_update_refuses_local_tracked_changes(repos):
    _, target = repos
    (target / ".gitignore").write_text("changed")
    with pytest.raises(ValueError, match="Tracked local"):
        installer.update(target)
    assert (target / ".gitignore").read_text() == "changed"


def test_package_duplicates_are_preserved_and_only_untracked_side_moves(repos):
    origin, target = repos
    name = "data/packages/installed/tools/example/tool.json"
    (origin / name).parent.mkdir(parents=True)
    (origin / name).write_text('{"id":"example"}')
    git(origin, "add", name)
    git(origin, "commit", "-m", "package")
    installer.update(target)
    stale = target / "data/packages/not_installed/tools/example"
    stale.mkdir(parents=True)
    (stale / "user.txt").write_text("preserve")
    installer.reconcile_packages(target)
    assert (target / name).exists() and not stale.exists()
    assert next((target / "data/_backups").glob("*/data/packages/not_installed/tools/example/user.txt")).read_text() == "preserve"


def test_recipe_has_explicit_install_and_verification_commands(tmp_path):
    p = installer.make_plan(tmp_path, "recipe", sys.executable, "/runtime/bin/npm")
    runner.validate(p)
    steps = {s["id"]: s for s in p["steps"]}
    assert steps["update"]["verify"]
    assert steps["pip-check"]["argv"][-3:] == ["-m", "pip", "check"]
    assert steps["imports"]["argv"][-1].endswith("check_import_coverage.py")
    assert steps["frontend-build"]["argv"][-2:] == ["run", "build"]


@pytest.mark.parametrize('step', [None, {"id": "bad", "argv": ["python", "\0"]},
                                {"id": "bad", "argv": [""]}])
def test_invalid_plans_fail_before_creating_state(tmp_path, step):
    with pytest.raises(ValueError):
        runner.run(plan(tmp_path, [step]))
    assert not (tmp_path / "data").exists()


def test_cli_returns_failure_and_accepts_literal_empty_argument(tmp_path):
    p = plan(tmp_path, [{"id": "failure", "argv": command("import sys; assert sys.argv[1] == ''; raise SystemExit(9)") + [""]}])
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(p))
    result = subprocess.run([sys.executable, str(ROOT / "scripts/remote_steps.py"), str(path)], capture_output=True, text=True)
    assert result.returncode == 1
    state = json.loads(result.stdout.splitlines()[-1])
    assert state["steps"]["failure"]["attempts"][0]["exit"] == 9
    assert runner.run(p, inspect=True)["process_liveness"] == "not_checked"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))


@pytest.mark.parametrize("locale", ["cp949", "cp1252"])
def test_unicode_journal_resumes_without_repeating_work(tmp_path, monkeypatch, locale):
    root = tmp_path / "한글 日本語 😀"
    root.mkdir()
    p = plan(root, [{"id": "once", "argv": command("open('count','a').write('x')")}])
    assert runner.run(p)["status"] == "succeeded"
    original = Path.read_text
    monkeypatch.setattr(Path, "read_text", lambda self, encoding=None, errors=None: original(self, encoding=encoding or locale, errors=errors))
    assert runner.run(p, inspect=True)["status"] == "succeeded"
    assert runner.run(p)["status"] == "succeeded"
    assert (root / "count").read_text(encoding="utf-8") == "x"

@pytest.mark.parametrize("locale", ["cp949", "cp1252"])
def test_unicode_plan_cli_uses_declared_utf8(tmp_path, monkeypatch, locale):
    root = tmp_path / "한글 日本語 😀"
    root.mkdir()
    p = plan(root, [{"id": "once", "argv": command("open('count','a').write('x')")}])
    path = root / "plan.json"
    path.write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")
    original = Path.read_text
    monkeypatch.setattr(Path, "read_text", lambda self, encoding=None, errors=None: original(self, encoding=encoding or locale, errors=errors))
    monkeypatch.setattr(sys, "argv", ["remote_steps.py", str(path)])
    assert runner.main() == 0
    assert (root / "count").read_text(encoding="utf-8") == "x"
