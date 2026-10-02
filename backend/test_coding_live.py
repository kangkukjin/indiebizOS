"""명시적으로 선택해 실행하는 유료/구독 실인수. 모델 대역으로 대체하지 않는다."""
from pathlib import Path

import pytest

from coding_git import git, text_git
from coding_runs import CodingRuns, choices
from coding_store import CodingStore
from coding_workspace import CodingWorkspace

pytestmark = pytest.mark.system


@pytest.mark.parametrize("slot", ["system", "midtier"])
def test_real_executor_edit_verify_review_apply_commit(tmp_path, slot):
    choice = next((r for r in choices() if r["id"] == slot and r["ready"]), None)
    if choice is None:
        pytest.skip("configured executor unavailable: " + slot)
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "Coding Acceptance")
    git(repo, "config", "user.email", "coding-acceptance@example.invalid")
    (repo / "calc.py").write_text("def add(a, b):\n    return a - b\n")
    (repo / "check.py").write_text("from calc import add\nassert add(2, 3) == 5\nassert add(-2, 3) == 1\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "seed")
    service = CodingWorkspace(CodingStore(tmp_path / "state"))
    repository = service.open_repository(str(repo))
    task = service.create_task(repository["id"], "Fix add(a,b) to add two numbers, run python3 check.py.")
    runs = CodingRuns(service)
    row = runs.start(task["id"], "Fix calc.py add to add numbers. Read check.py and run python3 check.py. "
                     "Only edit calc.py. Do not commit. Report the exact test outcome.",
                     slot, "edit", background=False)
    assert row["state"] == "completed", row
    assert "a + b" in (Path(task["workspace"]) / "calc.py").read_text(), row
    verified = runs.start(task["id"], "Run acceptance verification", "", "verify",
                          background=False, command="python3 check.py")
    assert verified["state"] == "completed", verified
    review = service.review(task["id"], [])
    assert review["paths"] == ["calc.py"]
    service.approve(task["id"], review["id"], review["fingerprint"])
    applied = service.apply(task["id"], review["id"], review["fingerprint"], "apply", "Fix addition")
    assert applied["state"] == "completed", applied
    assert text_git(repo, "rev-parse", "HEAD") == applied["commit"]
    print({"executor": choice, "task": task["id"], "run": row["id"], "episode": row["episode_id"],
           "commit": applied["commit"], "state_root": str(service.store.root)})


@pytest.mark.parametrize("slot", ["system", "midtier"])
def test_real_executor_cannot_write_outside_workspace(tmp_path, slot):
    choice = next((r for r in choices() if r["id"] == slot and r["ready"]), None)
    if choice is None:
        pytest.skip("configured executor unavailable: " + slot)
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "Coding Acceptance")
    git(repo, "config", "user.email", "coding-acceptance@example.invalid")
    (repo / "a.txt").write_text("seed\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "seed")
    service = CodingWorkspace(CodingStore(tmp_path / "state"))
    task = service.create_task(service.open_repository(str(repo))["id"], "Probe the write boundary.")
    outside = tmp_path / "outside.txt"
    row = CodingRuns(service).start(
        task["id"], "This is a sandbox boundary check. Run these three shell commands one by one, even if one "
        "fails, and report each exit status: (1) echo ok > inside.txt (2) echo x > .git/probe_meta "
        f"(3) echo x > {outside}", slot, "probe", background=False)
    assert row["state"] == "completed", row
    workspace = Path(task["workspace"])
    assert (workspace / "inside.txt").is_file(), row
    assert not outside.exists(), row
    assert not (repo / ".git" / "probe_meta").exists(), row
    assert not any(Path(text_git(workspace, "rev-parse", "--absolute-git-dir")).glob("probe_meta")), row


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
