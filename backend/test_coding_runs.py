"""실제 OS 경계·자식 취소·명령 멱등과 provider 정책 분리."""
import os
import subprocess
import time
from pathlib import Path

import pytest

from coding_process import CodingProcesses, available
from coding_runs import CodingRuns
from coding_store import CodingStore
from coding_workspace import CodingWorkspace
from coding_git import git
from test_coding_workspace import workspace, prepare

pytestmark = pytest.mark.skipif(not available(), reason="macOS sandbox required")


def test_real_process_boundary_and_git_metadata(tmp_path):
    root = tmp_path / "workspace"
    root.mkdir()
    (root / ".git").write_text("metadata")
    outside = tmp_path / "outside"
    (root / "link").symlink_to(outside)
    controller = CodingProcesses(root, tmp_path / "runtime")
    commands = [("echo ok > inside", True), ("echo nope > ../outside", False),
                ("echo nope > .git", False), ("echo nope > link", False)]
    for command, ok in commands:
        proc = controller.spawn(["/bin/sh", "-c", command], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        proc.communicate(timeout=10)
        assert (proc.returncode == 0) == ok
    controller.close()
    assert not outside.exists()
    assert (root / ".git").read_text() == "metadata"


def test_command_verification_and_duplicate(workspace):
    service, record, repo = workspace
    task, root = prepare(service, record)
    runs = CodingRuns(service)
    first = runs.start(task["id"], "verify", "", "command1", background=False,
                       command="test \"$(cat a.txt)\" = after")
    assert first["state"] == "completed", first
    assert runs.start(task["id"], "verify", "", "command1", background=False,
                      command="test \"$(cat a.txt)\" = after") == first
    verification = service.store.list("verification")
    assert len(verification) == 1
    assert verification[0]["state"] == "passed"
    assert service.store.get("task", task["id"])["active_run"] is None


def test_cancellation_kills_child(workspace):
    service, record, repo = workspace
    task, root = prepare(service, record)
    runs = CodingRuns(service)
    row = runs.start(task["id"], "long", "", "slow", command="sleep 30 & echo $! > child.pid; wait")
    deadline = time.monotonic() + 10
    while not (root / "child.pid").exists() and time.monotonic() < deadline:
        time.sleep(.05)
    assert (root / "child.pid").exists()
    child = int((root / "child.pid").read_text())
    runs.cancel(task["id"])
    while service.store.get("task", task["id"])["active_run"] and time.monotonic() < deadline:
        time.sleep(.05)
    assert service.store.get("task", task["id"])["active_run"] is None
    import psutil
    assert not psutil.pid_exists(child) or psutil.Process(child).status() == psutil.STATUS_ZOMBIE


def test_coding_profile_does_not_change_default(tmp_path):
    from providers.codex import CodexProvider
    from providers.coding_profile import configure
    kwargs = dict(api_key="", model="gpt-6-astra:high", system_prompt="", agent_id="test")
    normal = CodexProvider(**kwargs)
    coding = CodexProvider(**kwargs)
    for provider in (normal, coding):
        provider._binary_path = "codex"
    task = {"id": "coding-test", "workspace": str(tmp_path)}
    controller = CodingProcesses(tmp_path, tmp_path / "runtime")
    configure(coding, task, controller)
    assert coding.TOOL_POLICY == ""
    assert normal.TOOL_POLICY
    cmd = coding._build_command()
    assert "--dangerously-bypass-approvals-and-sandbox" not in cmd
    assert "workspace-write" in cmd
    assert coding._get_session_key() != normal._get_session_key()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
