"""Phone execution preserves rehearsal provenance without activating hardware."""
import importlib.util
from pathlib import Path

import boot_paths  # noqa: F401
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
import system_tools
from thread_context import get_task_origin, get_current_surface


@pytest.fixture
def phone_routes(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[1] / "phone-companion/app/src/main/python/phone_execution_routes.py"
    spec = importlib.util.spec_from_file_location("phone_routes_origin_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    app = FastAPI()
    module.install(app, lambda: str(tmp_path), lambda value: value)
    return app


@pytest.mark.parametrize("origin", ["training", "test"])
def test_execution_sets_and_restores_isolated_origin(phone_routes, monkeypatch, origin):
    seen = []
    def execute(request, project_path, agent_id):
        seen.append((get_task_origin(), get_current_surface(), agent_id))
        return {"success": True, "value": 3}
    monkeypatch.setattr(system_tools, "_execute_ibl_unified", execute)
    with TestClient(phone_routes) as client:
        assert client.post("/ibl/execute", json={"code": "return 3", "origin": origin, "surface": "web", "agent_id": "limb"}).json()["success"]
        assert client.post("/ibl/execute", json={"code": "return 3"}).json()["success"]
    assert seen == [(origin, "web", "limb"), (None, None, "phone")]


def test_execution_restores_origin_after_exception(phone_routes, monkeypatch):
    seen = []
    def execute(request, project_path, agent_id):
        seen.append(get_task_origin())
        if len(seen) == 1:
            raise RuntimeError("test failure")
        return {"success": True}
    monkeypatch.setattr(system_tools, "_execute_ibl_unified", execute)
    with TestClient(phone_routes, raise_server_exceptions=False) as client:
        assert client.post("/ibl/execute", json={"code": "return 3", "origin": "training"}).status_code == 500
        assert client.post("/ibl/execute", json={"code": "return 3"}).status_code == 200
    assert seen == ["training", None]


@pytest.mark.parametrize("origin", ["user", {}, ["training"]])
def test_untrusted_metadata_does_not_grant_user_origin(phone_routes, monkeypatch, origin):
    seen = []
    def execute(request, project_path, agent_id):
        seen.append(get_task_origin())
        return {"success": True}
    monkeypatch.setattr(system_tools, "_execute_ibl_unified", execute)
    assert TestClient(phone_routes).post("/ibl/execute", json={"code": "return 3", "origin": origin}).status_code == 200
    assert seen == [None]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, *(__import__("sys").argv[1:])]))
