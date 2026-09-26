"""여섯 경계가 한 JSON 계약을 내는지 — 엄격 직렬화 행렬 (Codex r43 흡수)."""

import asyncio
import datetime
import decimal
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boot_paths  # noqa: F401,E402

import api_ibl  # noqa: E402
import ibl_engine  # noqa: E402
import system_tools  # noqa: E402
from common.response_formatter import format_json  # noqa: E402
from common.value_semantics import dumps_public_result  # noqa: E402


def _cycle_value():
    cycle = []
    cycle.append(cycle)
    return {"v": cycle}


_SHAPES = [
    ("normal", lambda: {"v": [1, "x", None]}, "normal"),
    ("tuple", lambda: {"v": (1, 2)}, "tuple"),
    ("key_collision", lambda: {1: "number", "1": "text"}, "pairs"),
    ("bytes", lambda: {"v": b"abc"}, "error"),
    ("datetime", lambda: {"v": datetime.datetime(2026, 8, 26, 1, 2, 3)}, "error"),
    ("decimal", lambda: {"v": decimal.Decimal("0.1")}, "error"),
    ("set", lambda: {"v": {1, 2}}, "error"),
    ("cycle", _cycle_value, "error"),
]


def _parsed(result):
    if isinstance(result, str):
        return json.loads(result, parse_constant=lambda token: pytest.fail(token))
    json.dumps(result, allow_nan=False)
    return result


def _boundary_results(value, monkeypatch, tmp_path):
    results = [
        dumps_public_result(value),
        format_json(value),
        system_tools._dict_to_json(value),
    ]

    original_inner = system_tools._execute_tool_inner
    monkeypatch.setattr(system_tools, "_execute_tool_inner", lambda *_args, **_kwargs: value)
    results.append(system_tools.execute_tool("round43", {}, str(tmp_path)))
    monkeypatch.setattr(system_tools, "_execute_tool_inner", original_inner)

    original_impl = ibl_engine._execute_ibl_impl
    monkeypatch.setattr(ibl_engine, "_execute_ibl_impl", lambda *_args, **_kwargs: value)
    results.append(ibl_engine.execute_ibl({"_node": "sense", "action": "round43"}, str(tmp_path)))
    monkeypatch.setattr(ibl_engine, "_execute_ibl_impl", original_impl)

    original_unified = system_tools._execute_ibl_unified
    monkeypatch.setattr(system_tools, "_execute_ibl_unified", lambda *_args, **_kwargs: value)
    request = api_ibl.IBLRequest(code="[sense:round43]", project_path=str(tmp_path))
    results.append(asyncio.run(api_ibl.execute_ibl_code(request)))
    monkeypatch.setattr(system_tools, "_execute_ibl_unified", original_unified)
    return [_parsed(result) for result in results]


@pytest.mark.parametrize("name,factory,expected", _SHAPES)
def test_round43_matrix_has_one_json_contract_across_six_boundaries(
        name, factory, expected, monkeypatch, tmp_path):
    """훈련 48칸(8값 모양×직렬화/포매터/직접/도구/IBL/HTTP)을 재생한다."""
    results = _boundary_results(factory(), monkeypatch, tmp_path)

    assert len(results) == 6
    if expected == "normal":
        assert all(result == {"v": [1, "x", None]} for result in results), name
    elif expected == "tuple":
        assert all(result == {"v": [1, 2]} for result in results), name
    elif expected == "pairs":
        assert all(result == {"$object_pairs": [[1, "number"], ["1", "text"]]}
                   for result in results), name
    else:
        assert all(result.get("success") is False and
                   result.get("error_code") == "NON_JSON_RESULT"
                   for result in results), (name, results)


@pytest.mark.parametrize("payload", [
    '{"a": 1, "a": 2}',
    '{"outer": {"x": 1, "x": 2}}',
])
def test_duplicate_keys_in_json_strings_fail_before_the_parser_loses_data(payload):
    result = _parsed(dumps_public_result({"result": payload}, producer="duplicate-test"))

    assert result["success"] is False
    assert result["error_code"] == "NON_JSON_RESULT"
    assert "중복 키" in result["error"]
    assert "$.result<json>" in result["error"]


def test_unsupported_value_error_reports_the_nested_path():
    result = _parsed(dumps_public_result(
        {"items": [{"metadata": {"created": datetime.date(2026, 8, 26)}}]}))

    assert result["error_code"] == "NON_JSON_RESULT"
    assert "$.items[0].metadata.created" in result["error"]
    assert "date" in result["error"]


@pytest.mark.parametrize("code,failed", [('return "traceback"', False), ('return 1 / 0', True)])
@pytest.mark.parametrize("provider_name", ["openai", "openrouter", "deepseek", "anthropic", "ollama", "gemini"])
def test_runtime_status_reaches_provider_tool_turn(code, failed, provider_name, monkeypatch):
    """실제 실행 결과 → content/details 분리 → 제공자의 결과 이벤트·모델 입력."""
    from types import SimpleNamespace
    from providers import get_provider
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime

    result = Runtime(compile_program(code, {})).run()
    raw = json.dumps(result, ensure_ascii=False)
    provider = get_provider(provider_name, api_key="test", model="test", system_prompt="")
    provider._last_tool_images = []
    monkeypatch.setattr(provider, "_execute_tool_to_completion", lambda *a, **kw: {
        "content": raw, "details": "UI용 별도 표시"})
    if provider_name != "gemini":
        monkeypatch.setattr(provider, "_agentic_loop", lambda *a, **kw: iter(()))
    messages = []
    if provider_name == "gemini":
        output, _, _, flag = provider._execute_single_tool(
            SimpleNamespace(name="execute_ibl", args={"code": code}), lambda: None, 0)
        assert flag is failed
        from ibl_result_transport import provider_tool_result
        provider._genai_types = SimpleNamespace(FunctionResponse=SimpleNamespace, Part=SimpleNamespace)
        part = provider._function_response_part(
            SimpleNamespace(name="execute_ibl", id="t"), provider_tool_result(output))
        delivered = part.function_response.response["output"]
    else:
        kwargs = dict(messages=messages, collected_text="", execute_tool=lambda: None, depth=0)
        if provider_name == "anthropic":
            kwargs["tool_uses"] = [{"id": "t", "name": "execute_ibl", "input": {"code": code}}]
        else:
            kwargs.update(tool_calls={"t": {"name": "execute_ibl", "arguments": json.dumps({"code": code})}}, openai_tools=[])
            if provider_name != "ollama":
                kwargs["collected_reasoning"] = ""
        events = list(provider._execute_tools_and_continue(**kwargs))
        assert next(e for e in events if e["type"] == "tool_result")["is_error"] is failed
        if provider_name == "anthropic":
            block = messages[-1]["content"][0]
            assert bool(block.get("is_error")) is failed
            delivered = block["content"]
        else:
            delivered = messages[-1]["content"]
    assert json.loads(delivered) == result


@pytest.mark.parametrize("payload,failed", [
    ({"success": True, "source_complete": False, "incomplete_steps": [{"error": "traceback"}]}, False),
    ({"success": True, "value": {"success": False, "error": "failed:"}}, False),
    ({"success": False, "error": "division by zero"}, True),
    ({"items": [{"error": "traceback"}]}, False),
    ({"error": "legacy failure"}, True),
    ("Error: plain failure", True), ("plain traceback", True), ("normal text", False),
])
def test_provider_status_does_not_scan_structured_business_values(payload, failed):
    from providers.base import BaseProvider
    raw = json.dumps(payload) if isinstance(payload, dict) else payload
    text, flag = BaseProvider._verify_tool_result(None, "execute_ibl", {}, raw)
    assert text == raw
    assert flag is failed


@pytest.mark.parametrize("code,failed", [('return "traceback"', False), ('return 1 / 0', True)])
def test_mcp_protocol_status_reaches_both_cli_providers(code, failed, monkeypatch):
    import time
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    import mcp_server as mcp_boundary
    from mcp.types import CallToolResult
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    from providers import get_provider

    result = Runtime(compile_program(code, {})).run()
    raw = json.dumps(result)
    monkeypatch.setattr(mcp_boundary, "_post_backend", lambda *a: raw)
    monkeypatch.setattr(mcp_boundary, "_repeat_advisory", lambda *a: "")
    monkeypatch.setattr(mcp_boundary.mcp, "get_context", lambda: None)
    wire = asyncio.run(mcp_boundary.mcp.call_tool("execute_ibl", {"code": code}))
    if not isinstance(wire, CallToolResult):
        wire = CallToolResult(content=wire)
    assert wire.isError is failed
    assert json.loads(wire.content[0].text) == result

    codex = get_provider("codex", api_key="", model="test", system_prompt="")
    events = codex._translate_stream_event({"type": "item.completed", "item": {
        "id": "t", "type": "mcp_tool_call", "status": "completed", "tool": "execute_ibl",
        "result": wire.model_dump()}}, "", time.time())
    assert next(e for e, _ in events if e["type"] == "tool_result")["is_error"] is failed

    claude = get_provider("claude_code", api_key="", model="test", system_prompt="")
    events = claude._translate_stream_event({"type": "user", "message": {"content": [{
        "type": "tool_result", "tool_use_id": "t", "is_error": wire.isError,
        "content": [b.model_dump() for b in wire.content]}]}}, "", time.time())
    assert next(e for e, _ in events if e["type"] == "tool_result")["is_error"] is failed


@pytest.mark.parametrize("provider_name", ["gemini_http", "deepseek_http"])
@pytest.mark.parametrize("code", ['return "traceback"', 'return 1 / 0'])
def test_http_providers_preserve_execution_status(provider_name, code, monkeypatch):
    """별도 오류 플래그가 없는 REST 경로도 모델 입력의 실행 봉투를 보존한다."""
    from providers import get_provider
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    result = Runtime(compile_program(code, {})).run()
    raw = json.dumps(result)
    provider = get_provider(provider_name, api_key="test", model="test", system_prompt="")
    provider._client = object()
    monkeypatch.setattr(provider, "_execute_tool_to_completion", lambda *a, **kw: raw)
    seen = []

    def request(messages, *args):
        if not seen:
            seen.append(True)
            if provider_name == "gemini_http":
                return {"candidates": [{"content": {"parts": [{"functionCall": {
                    "name": "execute_ibl", "args": {"code": code}}}]}}]}
            return {"choices": [{"message": {"tool_calls": [{"id": "t", "function": {
                "name": "execute_ibl", "arguments": json.dumps({"code": code})}}]}}]}
        if provider_name == "gemini_http":
            delivered = messages[-1]["parts"][0]["functionResponse"]["response"]["result"]
            reply = {"candidates": [{"content": {"parts": [{"text": "done"}]}}]}
        else:
            delivered = messages[-1]["content"]
            reply = {"choices": [{"message": {"content": "done"}}]}
        seen.append(json.loads(delivered))
        return reply

    monkeypatch.setattr(provider, "_generate" if provider_name == "gemini_http" else "_chat", request)
    assert provider.process_message("probe", execute_tool=lambda: None) == "done"
    assert seen == [True, result]


@pytest.mark.parametrize("failed", [False, True])
def test_projection_and_mcp_trimming_preserve_status_and_images(failed, monkeypatch, tmp_path):
    import base64
    import mcp_server as mcp_boundary
    import model_result_view
    from supervision_store import TurnStore
    from ibl_result_transport import tool_result_is_error
    from mcp.types import CallToolResult

    monkeypatch.setattr(model_result_view, "evidence_store", lambda: TurnStore(tmp_path / "evidence"))
    result = {"edition": 2, "success": not failed, "source_complete": False,
              "value": {"error": "traceback", "text": "x" * 100000},
              "incomplete_steps": [{"error": "failed: missing source"}]}
    projected = model_result_view.project_result(result)
    assert tool_result_is_error(json.dumps(projected)) is failed
    projected["images"] = [{"base64": base64.b64encode(b"image").decode(), "media_type": "image/png"}]
    monkeypatch.setattr(mcp_boundary, "_post_backend", lambda *a: json.dumps(projected))
    monkeypatch.setattr(mcp_boundary, "_repeat_advisory", lambda *a: "")
    monkeypatch.setattr(mcp_boundary.mcp, "get_context", lambda: None)
    # 더 큰 진단도 실제 전송 축약을 거친다. 실패 판정은 미리보기 텍스트에 의존하지 않는다.
    projected["diagnostic_text"] = "traceback " * 10000
    wire = asyncio.run(mcp_boundary.mcp.call_tool("execute_ibl", {"code": "return 1"}))
    if not isinstance(wire, CallToolResult):
        wire = CallToolResult(content=wire)
    assert wire.isError is failed
    body = json.loads(wire.content[0].text)
    assert body["success"] is (not failed)
    assert body["source_complete"] is False
    assert body["result_ref"]["id"] == projected["result_ref"]["id"]
    assert wire.content[1].type == "image"


def test_codex_transport_failure_is_not_overridden_by_successful_payload():
    from providers.codex import CodexProvider
    for status in ("failed", "interrupted"):
        _, failed = CodexProvider._tool_result({"type": "mcp_tool_call", "status": status,
            "result": {"content": [{"type": "text", "text": '{"success":true}'}], "isError": False}})
        assert failed is True


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
