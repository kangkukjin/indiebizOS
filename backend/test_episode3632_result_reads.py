"""ep3632: ~workspace struct 실패와 조회 한도/본문 키 추측 왕복의 회귀."""
import asyncio
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
    assert ref["max_limit"] == 24000
    request, chunks = ref["read_args"], []
    while request is not None:
        assert request["path"] == expected_path
        page = result_view.read_result(request)
        assert len(page["text"]) <= 12000
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
    for args in ({"limit": 25000}, {"limit": 0}, {"offset": -1}, {"path": ["transcript"]}):
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
    assert remote["properties"]["limit"]["maximum"] == 24000
    assert remote["properties"]["offset"]["minimum"] == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
