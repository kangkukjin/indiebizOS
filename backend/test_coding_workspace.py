"""실제 Git 저장소로 기존 변경 보호·검토 신선도·커밋 재시도를 확인한다."""
from pathlib import Path

import pytest

from coding_git import CodingConflict, current_tree, git, text_git
from coding_store import CodingStore, identifier
from coding_workspace import CodingWorkspace


@pytest.fixture
def workspace(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.name", "Coding Test")
    git(repo, "config", "user.email", "coding-test@example.invalid")
    (repo / "a.txt").write_text("before\n")
    (repo / "other.txt").write_text("untouched\n")
    git(repo, "add", ".")
    git(repo, "commit", "-m", "seed")
    service = CodingWorkspace(CodingStore(tmp_path / "state"))
    record = service.open_repository(str(repo))
    return service, record, repo


def prepare(service, record):
    task = service.create_task(record["id"], "작은 변경")
    root = Path(task["workspace"])
    (root / "a.txt").write_text("after\n")
    return task, root


def approved(service, task, selected=None):
    tree = current_tree(task["workspace"])
    service.store.save("verification", {"id": identifier("verify"), "task_id": task["id"],
                                        "fingerprint": tree, "state": "passed", "exit_code": 0})
    review = service.review(task["id"], selected or [])
    service.approve(task["id"], review["id"], review["fingerprint"])
    return review


def apply(service, task, review, key="once"):
    return service.apply(task["id"], review["id"], review["fingerprint"], key, "small change")


def test_preserves_dirty_staged_untracked_and_intermediate_commit(workspace):
    service, record, repo = workspace
    (repo / "other.txt").write_text("staged\n")
    git(repo, "add", "other.txt")
    (repo / "other.txt").write_text("unstaged\n")
    (repo / "personal.txt").write_text("mine\n")
    staged = git(repo, "show", ":other.txt")
    task, root = prepare(service, record)
    git(root, "add", "a.txt")
    git(root, "commit", "-m", "executor intermediate")
    (root / "new.bin").write_bytes(b"\0\x01\xff")
    review = approved(service, task, ["new.bin"])
    assert set(review["paths"]) == {"a.txt", "new.bin"}
    result = apply(service, task, review)
    assert result["state"] == "completed"
    assert git(repo, "show", ":other.txt") == staged
    assert (repo / "other.txt").read_text() == "unstaged\n"
    assert (repo / "personal.txt").read_text() == "mine\n"
    assert git(repo, "show", "HEAD:other.txt") == b"untouched\n"
    assert (repo / "new.bin").read_bytes() == b"\0\x01\xff"
    assert apply(service, task, review) == result


def test_same_file_existing_change_blocks(workspace):
    service, record, repo = workspace
    (repo / "a.txt").write_text("owner change\n")
    task, _ = prepare(service, record)
    review = approved(service, task)
    with pytest.raises(CodingConflict, match="기존 변경"):
        apply(service, task, review)
    assert (repo / "a.txt").read_text() == "owner change\n"


def test_stale_review_and_stale_verification(workspace):
    service, record, repo = workspace
    task, root = prepare(service, record)
    review = approved(service, task)
    (root / "a.txt").write_text("newer\n")
    with pytest.raises(CodingConflict, match="검토 뒤"):
        apply(service, task, review)
    review2 = service.review(task["id"], [])
    assert not review2["verifications"][0]["fresh"]
    service.approve(task["id"], review2["id"], review2["fingerprint"])
    with pytest.raises(CodingConflict, match="검증"):
        apply(service, task, review2)
    assert (repo / "a.txt").read_text() == "before\n"


def test_concurrent_head_requires_new_review(workspace):
    service, record, repo = workspace
    task, _ = prepare(service, record)
    review = approved(service, task)
    (repo / "other.txt").write_text("new head\n")
    git(repo, "add", "other.txt")
    git(repo, "commit", "-m", "someone else")
    with pytest.raises(CodingConflict, match="정본 상태"):
        apply(service, task, review)
    updated = approved(service, task)
    assert apply(service, task, updated)["state"] == "completed"


def test_commit_failure_recovers_without_reapplying(workspace):
    service, record, repo = workspace
    task, _ = prepare(service, record)
    review = approved(service, task)
    hook = repo / ".git/hooks/pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    failed = apply(service, task, review)
    assert failed["state"] == "commit_pending"
    assert (repo / "a.txt").read_text() == "after\n"
    hook.unlink()
    done = apply(service, task, review)
    assert done["state"] == "completed"
    assert text_git(repo, "rev-list", "--count", "HEAD") == "2"


def test_conditional_save_traversal_links_and_running(workspace, tmp_path):
    service, record, repo = workspace
    task, root = prepare(service, record)
    opened = service.read_file(task["id"], "a.txt")
    (root / "a.txt").write_text("external\n")
    with pytest.raises(CodingConflict):
        service.save_file(task["id"], "a.txt", "lost", opened["fingerprint"])
    (root / "escape").symlink_to(repo / "a.txt")
    for path in ("../repo/a.txt", ".git", "escape"):
        with pytest.raises(ValueError):
            service.read_file(task["id"], path)
    task["active_run"] = "running"
    service.store.save("task", task)
    with pytest.raises(CodingConflict):
        service.review(task["id"], [])


def test_events_resume_and_reopen(workspace):
    service, record, _ = workspace
    task, _ = prepare(service, record)
    first = service.store.events(task["id"])
    seq = service.store.event(task["id"], "run", "output", {"text": "hello"})
    reopened = CodingWorkspace(CodingStore(service.store.root))
    assert reopened.store.get("task", task["id"])["pursuit_id"] == task["pursuit_id"]
    assert [e["sequence"] for e in reopened.store.events(task["id"], first[-1]["sequence"])] == [seq]


def test_own_repository_is_refused_until_repair_link(tmp_path):
    from runtime_utils import get_base_path
    service = CodingWorkspace(CodingStore(tmp_path / "state"))
    record = service.open_repository(str(get_base_path()))
    assert record["kind"] == "repair"
    with pytest.raises(ValueError, match="자기수리 연동"):
        service.create_task(record["id"], "자기 저장소 변경")
    assert service.store.list("task") == []


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
