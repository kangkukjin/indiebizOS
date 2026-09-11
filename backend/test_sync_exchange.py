"""도메인별 동기화의 공개 URL/봉투/오류 계약. 실제 사용자 DB나 네트워크를 사용하지 않는다."""
import boot_paths  # noqa: F401
import importlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


@pytest.fixture(params=[("business", "business_sync"), ("health", "health_sync"), ("finance", "finance_ledger_sync")])
def exchange(request, monkeypatch):
    domain, owner = request.param
    api = importlib.import_module("api_" + domain)
    store = importlib.import_module(owner)
    calls = []
    state = {"export": {"rows": [{"id": "a", "deleted": True}], "images": {"x": "fake-base64"}}, "failure": None}
    manager = object()
    if domain == "business":
        monkeypatch.setattr(api, "business_manager", manager)

    def export(*args):
        assert args == ((manager,) if domain == "business" else ())
        calls.append("export")
        if state["failure"] == "export":
            raise RuntimeError("export unavailable")
        return state["export"]

    def merge(*args):
        assert args[:-1] == ((manager,) if domain == "business" else ())
        calls.append(("merge", args[-1]))
        if state["failure"] == "merge":
            raise RuntimeError("merge unavailable")
        return {"merged": 2, "skipped": 1}

    monkeypatch.setattr(store, "export_" + domain + "_db", export)
    monkeypatch.setattr(store, "merge_" + domain + "_db", merge)
    app = FastAPI()
    app.include_router(api.router)
    with TestClient(app) as client:
        yield client, "/" + domain + "/sync", calls, state


@pytest.mark.parametrize("wrapped", [False, True])
def test_sync_round_trip_preserves_domain_snapshot_and_call_order(exchange, wrapped):
    client, prefix, calls, state = exchange
    assert client.get(prefix + "/export").json() == {"success": True, "data": state["export"]}
    calls.clear()
    remote = {"rows": [{"id": "b", "deleted": True}], "images": {"b": "encoded"}}
    result = client.post(prefix + "/merge", json={"data": remote} if wrapped else remote)
    assert result.status_code == 200
    assert result.json() == {"success": True, "stats": {"merged": 2, "skipped": 1}, "data": state["export"]}
    assert calls == [("merge", remote), "export"]


def test_sync_rejects_invalid_envelope_before_domain_effects(exchange):
    client, prefix, calls, _ = exchange
    result = client.post(prefix + "/merge", json={"data": []})
    assert result.status_code == 400 and "dict" in result.json()["detail"]
    assert calls == []
    assert client.post(prefix + "/merge", json=["bad"]).status_code == 422


@pytest.mark.parametrize("failure", ["merge", "export"])
def test_sync_failure_never_becomes_success_and_failed_merge_does_not_export(exchange, failure):
    client, prefix, calls, state = exchange
    state["failure"] = failure
    result = client.post(prefix + "/merge", json={"rows": []})
    assert result.status_code == 500 and result.json() == {"detail": failure + " unavailable"}
    assert calls == [("merge", {"rows": []})] + (["export"] if failure == "export" else [])


def test_sync_urls_remain_behind_remote_session_gate(exchange):
    from api_launcher_web import is_public_remote_path
    _, prefix, _, _ = exchange
    assert not is_public_remote_path("GET", prefix + "/export")
    assert not is_public_remote_path("POST", prefix + "/merge")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
