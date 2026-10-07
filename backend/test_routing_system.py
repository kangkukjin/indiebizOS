"""Agent inspection preserves project identity across public identifier forms."""
import sys

import boot_paths  # noqa: F401
import pytest


@pytest.fixture
def agents(monkeypatch):
    import node_registry
    rows = [
        {"id": "P1/조사", "type": "agent", "project_id": "P1",
         "agent_id": "agent_a", "agent_name": "조사"},
        {"id": "P2/조사", "type": "agent", "project_id": "P2",
         "agent_id": "agent_a", "agent_name": "조사"},
    ]
    monkeypatch.setattr(node_registry, "list_nodes", lambda **kwargs: rows)
    return rows


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
    monkeypatch.setattr(ibl_routing, "_cap", lambda name: routing_system._agent_info)
    result = ibl_routing._route_system("agents", {**params, "op": op}, "/unused")
    assert result == agents[0]


def test_agent_info_does_not_cross_project_or_guess(agents):
    from routing_system import _agent_info
    assert "error" in _agent_info("agent_a")
    assert "error" in _agent_info("P3/agent_a")
    assert "error" in _agent_info("P2/agent_a", project_id="P1")
    assert _agent_info("agent_a", project_id="P2") == agents[1]


def test_agent_info_prefers_stable_id_to_display_name(agents):
    from routing_system import _agent_info
    agents.append({"id": "P1/agent_a", "type": "agent", "project_id": "P1",
                   "agent_id": "agent_b", "agent_name": "agent_a"})
    assert _agent_info("P1/agent_a") == agents[0]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
