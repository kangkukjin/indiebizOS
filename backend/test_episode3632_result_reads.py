"""ep3632: ~workspace struct 실패와 조회 한도/본문 키 추측 왕복의 회귀."""
import asyncio
import importlib
import json

import boot_paths  # noqa: F401
import pytest

from test_struct_body_seam import aiops  # noqa: F401
from supervision_store import TurnStore


@pytest.mark.parametrize("entry", ["json", "text", "external"])
@pytest.mark.parametrize("prefix", ["~workspace", "~", "absolute", "relative"])
def test_struct_expands_file_paths(entry, prefix, aiops, tmp_path, monkeypatch):
    mod, seen = aiops
    monkeypatch.setattr("runtime_utils.get_base_path", lambda: tmp_path)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.chdir(tmp_path)
    body = "실제 원문 전체를 사용한다. 두 번째 팁도 읽어야 한다. " * 20
    filename = "한글 본문.json" if entry == "json" else "한글 본문.txt"
    saved = tmp_path / filename
    saved.write_text(json.dumps({"text": body}, ensure_ascii=False) if entry == "json" else body,
                     encoding="utf-8")
    path = (str(saved) if prefix == "absolute" else filename if prefix == "relative"
            else prefix + "/" + filename)
    params = ({"_prev_result": {"saved_to_file": True, "file_path": path, "preview": "일부만"}}
              if entry == "external" else {"file": path})
    out = json.loads(mod._struct({"schema": "tip", **params}))
    assert out["success"], out
    assert body.strip() in seen["prompt"]
    assert "일부만" not in seen["prompt"]


@pytest.fixture
def result_view(tmp_path, monkeypatch):
    import model_result_view as view
    store = TurnStore(tmp_path / "evidence")
    monkeypatch.setattr(view, "evidence_store", lambda: store)
    monkeypatch.setattr("episode_logger.record_trajectory_event", lambda *a, **k: None)
    return view


@pytest.mark.parametrize("pipeline", [False, True])
@pytest.mark.parametrize("field", ["text", "transcript", "content"])
def test_advertised_path_and_next_read_restore_actual_body(result_view, pipeline, field):
    body = "한글 원문🍀\n" * 8000
    source = {"success": True, field: body}
    raw = {"final_result": json.dumps(source, ensure_ascii=False)} if pipeline else source
    before = json.dumps(raw)
    projected = result_view.project_result(raw)
    ref = projected["result_ref"]
    expected_path = (["final_result"] if pipeline else []) + [field]
    assert ref["read_args"]["path"] == expected_path
    assert ref["paths"] == [{"path": expected_path,
                              "chars": len(json.dumps(body, ensure_ascii=False, indent=2))}]
    assert ref["max_limit"] == 60000
    assert ref["read_args"]["limit"] == 60000
    request, chunks = ref["read_args"], []
    while request is not None:
        assert request["path"] == expected_path
        page = result_view.read_result(request)
        assert len(page["text"]) <= 60000
        chunks.append(page["text"])
        request = page["next_read"]
    assert json.loads("".join(chunks)) == body
    assert json.dumps(raw) == before


def test_root_pagination_and_limits(result_view):
    raw = {"items": [{"text": "원문" * 20000}], "warning": "원문 경고"}
    ref = result_view.project_result(raw)["result_ref"]
    request = {"id": ref["id"], "limit": 24000}
    chunks = []
    while request is not None:
        assert "path" not in request
        page = result_view.read_result(request)
        chunks.append(page["text"])
        request = page["next_read"]
    assert json.loads("".join(chunks)) == raw
    for args in ({"limit": 60001}, {"limit": 0}, {"offset": -1}, {"path": ["transcript"]}):
        with pytest.raises(ValueError):
            result_view.read_result({"id": ref["id"], **args})


def test_mcp_and_native_advertise_the_same_read_contract():
    import mcp_server
    from tool_loader import build_execute_ibl_tool
    native = build_execute_ibl_tool()["input_schema"]["properties"]["read_result"]
    tool = next(tool for tool in asyncio.run(mcp_server.mcp.list_tools()) if tool.name == "execute_ibl")
    remote = next(option for option in tool.inputSchema["properties"]["read_result"]["anyOf"]
                  if option.get("type") == "object")
    assert remote["properties"] == native["properties"]
    assert remote["required"] == native["required"] == ["id"]
    assert remote["properties"]["limit"]["maximum"] == 60000
    assert remote["properties"]["limit"]["default"] == 60000
    assert remote["properties"]["offset"]["minimum"] == 0


@pytest.mark.parametrize("body", ["한" * 59000, ('한글🍀\n"\\' * 14000)])
def test_default_page_survives_real_mcp_and_provider_boundaries(result_view, body, monkeypatch):
    """원문 조회→프로바이더→MCP 실물 함수. 재스필 없이 모든 페이지가 이어진다."""
    import mcp_server
    from ibl_result_transport import provider_tool_result
    source = {"final_result": json.dumps({"text": body}, ensure_ascii=False)}
    ref = result_view.project_result(source)["result_ref"]
    calls = []

    def backend_read(path, payload, timeout):
        assert path == "/ibl/execute" and payload["code"] == ""
        calls.append(payload["read_result"])
        page = result_view.read_result(payload["read_result"])
        raw = json.dumps(page, ensure_ascii=False)
        assert provider_tool_result(raw) == raw
        for module, name in [("anthropic", "AnthropicProvider"), ("openai", "OpenAIProvider"),
                             ("ollama", "OllamaProvider")]:
            cls = getattr(importlib.import_module(f"providers.{module}"), name)
            assert cls._truncate_tool_result(object.__new__(cls), raw) == raw
        return raw

    monkeypatch.setattr(mcp_server, "_post_backend", backend_read)
    monkeypatch.setattr(mcp_server, "_repeat_advisory", lambda *a: "")
    monkeypatch.delenv("MAX_MCP_OUTPUT_TOKENS", raising=False)
    # limit 자체를 생략해도 60K가 기본값이어야 한다.
    request = {"id": ref["id"], "path": ["final_result", "text"]}
    chunks = []
    while request is not None:
        page = json.loads(asyncio.run(mcp_server.execute_ibl(code="", read_result=request)))
        assert "_trimmed" not in page and "ref" not in page
        assert page["offset"] == sum(map(len, chunks))
        chunks.append(page["text"])
        request = page["next_read"]
        if request is not None:
            assert len(page["text"]) == 60000 and request["limit"] == 60000
    assert json.loads("".join(chunks)) == body
    serialized_length = len(json.dumps(body, ensure_ascii=False))
    assert len(calls) == (serialized_length + 59999) // 60000
    if len(body) == 59000:
        assert len(calls) == 1


def test_explicit_smaller_page_and_host_limit_still_apply(result_view, monkeypatch, tmp_path):
    import mcp_server
    ref = result_view.project_result({"text": "원문" * 50000})["result_ref"]
    page = result_view.read_result({"id": ref["id"], "path": ["text"], "limit": 25000})
    assert len(page["text"]) == 25000 and page["next_read"]["limit"] == 25000
    raw = json.dumps(page, ensure_ascii=False)
    monkeypatch.setenv("MAX_MCP_OUTPUT_TOKENS", "10000")
    monkeypatch.setattr("common.spill.spill_dir", lambda: str(tmp_path))
    clipped = mcp_server._trim_for_agent(raw)
    assert len(clipped) <= 16000
    assert json.loads(clipped)["ref"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
