"""보유/활성 이관과 두 폴더 경로의 런타임 필터."""
import json
from pathlib import Path

import pytest
import vocabulary_state as state


@pytest.fixture
def box(tmp_path, monkeypatch):
    (tmp_path / "data").mkdir()
    (tmp_path / "data/vocabulary_policy.yaml").write_text(
        'version: 1\nstandard_nodes: [self, others, table]\nrequired_packages: {base: core}\n')
    for pid, loc in (("base", "installed"), ("awake", "installed"), ("asleep", "not_installed")):
        p = tmp_path / "data/packages" / loc / "tools" / pid
        p.mkdir(parents=True)
        (p / "tool.json").write_text(json.dumps({"tools": [{"name": pid}]}))
        (p / "ibl_actions.yaml").write_text(f'node: sense\nactions:\n  {pid}: {{tool: {pid}, router: handler}}\n')
        (p / "handler.py").write_text('raise AssertionError("잠든 핸들러를 import하면 안 됨")\n')
    monkeypatch.setattr(state, "get_base_path", lambda: tmp_path)
    state.invalidate_inventory()
    yield tmp_path
    state.invalidate_inventory()


def test_inventory_and_initial_selection(box):
    assert set(state.inventory()["packages"]) == {"base", "awake", "asleep"}
    assert state.is_active("awake", box)
    assert not state.is_active("asleep", box)
    assert state.package_path("asleep").parent.parent.name == "not_installed"
    assert "잠들어" in state.action_reason("sense", "asleep")
    with pytest.raises(ValueError, match="잠들어"):
        state.require_tool_active("asleep")


def test_folder_location_is_not_selection_after_migration(box):
    state.read_state()
    old = state.package_path("awake")
    old.rename(box / "data/packages/not_installed/tools/awake")
    assert state.is_active("awake")
    assert state.package_path("awake").exists()
    new = box / "data/packages/installed/tools/new"
    new.mkdir()
    assert not state.is_active("new")


def test_broken_state_does_not_wake_everything(box):
    state.read_state()
    state.state_path().write_text('{bad')
    with pytest.raises(ValueError, match="손상"):
        state.is_active("awake")


def test_cached_handler_is_also_blocked(box, monkeypatch):
    import tool_loader
    monkeypatch.setitem(tool_loader._tool_handlers_cache, "asleep", object())
    with pytest.raises(ValueError, match="잠들어"):
        tool_loader.load_tool_handler("asleep")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
