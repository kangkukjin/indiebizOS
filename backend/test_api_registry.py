"""API 사전 조회와 직접/선언 파이프 실행의 계약. 네트워크 호출 없음."""
import boot_paths  # noqa: F401
import json

import pytest


@pytest.fixture
def registry(monkeypatch, tmp_path):
    import ibl_registry
    path = tmp_path / "registry.json"
    data = {
        "services": {"probe": {"base_url": "https://example.invalid", "auth": {"type": "none"}}},
        "tools": {
            "single_probe": {"service": "probe", "endpoint": "/one"},
            "pipeline_probe": {"pipeline": [
                {"id": "one", "service": "probe", "endpoint": "/one"},
                {"id": "two", "service": "probe", "endpoint": "/two"},
            ], "merge": {"mode": "concat"}},
        },
    }
    path.write_text(json.dumps(data))
    monkeypatch.setattr(ibl_registry, "_registry_path", path)
    monkeypatch.setattr(ibl_registry, "_registry", None)
    return path, data


def test_registry_queries_share_loader_and_reload(registry):
    import ibl_registry as reg
    path, data = registry
    assert reg.is_registry_tool("single_probe")
    assert reg.list_registry_tools() == list(data["tools"])
    assert reg.get_tool_config("single_probe") == data["tools"]["single_probe"]
    assert reg.get_service_config("probe") == data["services"]["probe"]
    assert reg.get_tool_config("missing") is None
    data["tools"] = {"replacement": {"service": "probe"}}
    path.write_text(json.dumps(data))
    assert reg.is_registry_tool("single_probe")
    reg.reload_registry()
    assert not reg.is_registry_tool("single_probe")
    assert reg.is_registry_tool("replacement")


def test_unbound_registry_tools_keep_direct_and_pipeline_execution(registry, monkeypatch, tmp_path):
    import api_engine
    import system_tools

    def request(method, url, *args, **kwargs):
        return [{"endpoint": url.rsplit("/", 1)[-1]}]

    monkeypatch.setattr(api_engine, "_do_request", request)
    single = system_tools._execute_tool_inner("single_probe", {}, str(tmp_path), None)
    combined = system_tools._execute_tool_inner("pipeline_probe", {}, str(tmp_path), None)
    assert json.loads(single) == [{"endpoint": "one"}]
    assert sorted(json.loads(combined), key=lambda row: row["endpoint"]) == [
        {"endpoint": "one"}, {"endpoint": "two"}]
    assert "error" in api_engine.execute_tool("missing", {}, str(tmp_path))


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
