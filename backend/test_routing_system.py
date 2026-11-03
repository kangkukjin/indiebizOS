"""Agent inspection preserves project identity across public identifier forms."""
import sys

import boot_paths  # noqa: F401
import pytest


@pytest.fixture
def agents(tmp_path, monkeypatch):
    import yaml
    import node_registry
    import ibl_registry
    from agent_lifecycle import agent_info
    monkeypatch.setenv("INDIEBIZ_BASE_PATH", str(tmp_path))
    for project in ("P1", "P2"):
        path = tmp_path / "projects" / project
        path.mkdir(parents=True)
        (path / "agents.yaml").write_text(yaml.safe_dump({"agents": [{"id": "agent_a", "name": "조사"}]}))
    monkeypatch.setattr(ibl_registry, "load_nodes_installed", lambda: {"nodes": {"sense": {}, "self": {}}})
    monkeypatch.setattr(node_registry, "list_nodes", lambda **kw: pytest.fail("단건 조회에서 전체 목록 생성"))
    return [agent_info(project, "agent_a") for project in ("P1", "P2")]


@pytest.mark.parametrize("params", [
    {"project_id": "P1", "agent_id": "agent_a"},
    {"agent_id": "P1/agent_a"},
    {"agent_id": "P1/조사"},
    {"project_id": "P1", "agent_id": "P1/agent_a"},
])
@pytest.mark.parametrize("op", [None, "info"])
def test_agent_info_public_identifier_forms(agents, monkeypatch, params, op):
    import ibl_routing
    import routing_system
    monkeypatch.setattr(ibl_routing, "system_capability", lambda name: routing_system._agent_info)
    result = ibl_routing._route_system("agents", {**params, "op": op}, "/unused")
    assert result == agents[0]


def test_agent_info_does_not_cross_project_or_guess(agents):
    from routing_system import _agent_info
    assert "error" in _agent_info("agent_a")
    assert "error" in _agent_info("P3/agent_a")
    assert "error" in _agent_info("P2/agent_a", project_id="P1")
    assert _agent_info("agent_a", project_id="P2") == agents[1]


def test_agent_info_prefers_stable_id_to_display_name(agents, tmp_path):
    from routing_system import _agent_info
    import yaml
    path = tmp_path / "projects/P1/agents.yaml"
    data = yaml.safe_load(path.read_text())
    data["agents"].append({"id": "agent_b", "name": "agent_a"})
    path.write_text(yaml.safe_dump(data))
    assert _agent_info("P1/agent_a") == agents[0]


def test_info_reads_only_target_and_observes_mutations(agents, tmp_path, monkeypatch):
    import yaml
    from pathlib import Path
    from routing_system import _agent_info
    import agent_lifecycle as life
    (tmp_path / "projects/P2/agents.yaml").write_text("[")
    reads = []
    original = Path.read_text
    def read(path, *args, **kwargs):
        if path.name == "agents.yaml":
            reads.append(path)
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", read)
    assert _agent_info("P1/agent_a")["agent_name"] == "조사"
    assert reads == [tmp_path / "projects/P1/agents.yaml"]
    life.update_agent("P1", "agent_a", name="변경")
    assert _agent_info("P1/agent_a")["agent_name"] == "변경"
    life.delete_agent("P1", "agent_a")
    assert "error" in _agent_info("P1/agent_a")
    agent = life.create_agent("P1", "새 에이전트")
    assert _agent_info(agent["id"], project_id="P1")["agent_name"] == "새 에이전트"


@pytest.mark.parametrize("allowed", [None, [], ["sense"]])
def test_info_capabilities_share_access_resolver(agents, tmp_path, monkeypatch, allowed):
    import yaml
    import ibl_access
    import ibl_registry
    from routing_system import _agent_info
    nodes = {"sense": {}, "limbs": {}, "self": {"always_on": True}, "others": {"always_on": True}}
    monkeypatch.setattr(ibl_registry, "load_nodes_installed", lambda: {"nodes": nodes})
    monkeypatch.setattr(ibl_access, "load_nodes_raw", lambda: {"nodes": nodes})
    path = tmp_path / "projects/P1/agents.yaml"
    path.write_text(yaml.safe_dump({"agents": [{"id": "agent_a", "name": "조사", "allowed_nodes": allowed}]}))
    expected = set(nodes) if not allowed else {"sense", "self", "others"}
    assert set(_agent_info("P1/agent_a")["capabilities"]) == expected


def test_info_errors_and_running_are_current(agents, tmp_path, monkeypatch):
    import yaml
    import ibl_registry
    import agent_registry
    from types import SimpleNamespace
    from routing_system import _agent_info
    monkeypatch.setattr(agent_registry, "runner_registry", {"P1:agent_a": SimpleNamespace(running=True)})
    assert _agent_info("P1/agent_a")["running"] is True
    agent_registry.runner_registry.clear()
    assert _agent_info("P1/agent_a")["running"] is False
    path = tmp_path / "projects/P1/agents.yaml"
    path.write_text(yaml.safe_dump({"agents": [{"id": "agent_a"}, {"id": "agent_a"}]}))
    assert "중복" in _agent_info("P1/agent_a")["error"]
    path.write_text("[")
    assert "error" in _agent_info("P1/agent_a")


def test_info_rejects_escape_without_creating_project(agents, tmp_path):
    from routing_system import _agent_info
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "projects/link").symlink_to(outside, target_is_directory=True)
    for project in ("..", str(outside), "link"):
        assert "error" in _agent_info("agent_a", project_id=project)
    assert "error" in _agent_info("agent_a", project_id="missing")
    assert not (tmp_path / "projects/missing").exists()


def test_info_preserves_public_descriptor_and_legacy_capability(agents, tmp_path):
    import yaml
    from routing_system import _agent_info
    path = tmp_path / 'projects/P1/agents.yaml'
    path.write_text(yaml.safe_dump({'agents': [{'id': 'agent_a', 'name': '조사', 'active': True,
                     'role_description': 'sources', 'allowed_tools': ['ibl_limbs']}]}))
    value = _agent_info('P1/agent_a')
    assert set(value) == {'id', 'type', 'protocol', 'description', 'actions', 'action_count', 'tags',
                          'project_id', 'agent_id', 'agent_name', 'capabilities', 'active', 'running'}
    assert value['id'] == 'P1/조사' and value['agent_id'] == 'agent_a'
    assert value['description'] == 'sources' and value['active'] is True
    assert value['capabilities'] == ['limbs']
    assert value['action_count'] == 1 and value['actions'][0]['name'] == 'ask'


def test_info_dictionary_failure_is_not_empty_capability(agents, monkeypatch):
    import ibl_registry
    from routing_system import _agent_info
    def fail():
        raise RuntimeError('dictionary unreadable')
    monkeypatch.setattr(ibl_registry, 'load_nodes_installed', fail)
    assert _agent_info('P1/agent_a') == {'error': 'dictionary unreadable'}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
