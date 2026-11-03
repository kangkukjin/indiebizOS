"""프로젝트 에이전트 신원·파일 보존 계약."""
import boot_paths  # noqa: F401
from pathlib import Path

import pytest
import yaml
import agent_lifecycle as lifecycle


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(lifecycle, "_project_path", lambda _: tmp_path)
    (tmp_path / "agents.yaml").write_text(yaml.safe_dump({"agents": [{"id": "a", "name": "old"}]}))
    for kind in ("role", "note"):
        (tmp_path / f"agent_old_{kind}.txt").write_text(kind)
    return tmp_path


def snapshot(path):
    return {p.name: p.read_bytes() for p in path.iterdir() if p.is_file()}


@pytest.mark.parametrize("kind", ["role", "note"])
@pytest.mark.parametrize("content", ["other", "role", "note"])
@pytest.mark.parametrize("role", [None, "updated"])
def test_rename_conflict_preserves_every_byte(project, kind, content, role):
    (project / f"agent_new_{kind}.txt").write_text(content)
    before = snapshot(project)
    with pytest.raises(lifecycle.AgentConflictError):
        lifecycle.update_agent("p", "a", name="new", role=role)
    assert snapshot(project) == before


def test_rename_and_same_name_edit(project):
    lifecycle.update_agent("p", "a", name="new", role="new role")
    assert (project / "agent_new_role.txt").read_text() == "new role"
    assert (project / "agent_new_note.txt").read_text() == "note"
    assert not (project / "agent_old_note.txt").exists()
    lifecycle.update_agent("p", "a", name="new", role="edited")
    assert (project / "agent_new_role.txt").read_text() == "edited"


@pytest.mark.parametrize("name", ["old", "new"])
def test_save_failure_restores_text(project, monkeypatch, name):
    before = snapshot(project)
    def fail(*args):
        raise OSError("disk full")
    monkeypatch.setattr(lifecycle, "_save", fail)
    with pytest.raises(OSError):
        lifecycle.update_agent("p", "a", name=name, role="edited")
    assert snapshot(project) == before


def test_destination_race_preserves_racing_writer(project, monkeypatch):
    before = snapshot(project)
    original = Path.open
    def race(path, mode="r", *args, **kwargs):
        if path.name == "agent_new_note.txt" and mode == "xb":
            with original(path, "wb") as stream:
                stream.write(b"racer")
        return original(path, mode, *args, **kwargs)
    monkeypatch.setattr(Path, "open", race)
    with pytest.raises(lifecycle.AgentConflictError):
        lifecycle.update_agent("p", "a", name="new")
    after = snapshot(project)
    assert after.pop("agent_new_note.txt") == b"racer"
    assert after == before


def test_duplicate_name_rejected_even_without_files(project):
    data = lifecycle._load(project)
    data["agents"].append({"id": "b", "name": "new"})
    lifecycle._save(project, data)
    before = snapshot(project)
    result = lifecycle.agents_op("update", {"project_id": "p", "agent_id": "a", "name": "new"})
    assert result["success"] is False
    assert snapshot(project) == before


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
