"""Restricted execution, contract discovery and truncated tool recovery regressions."""
import json
from types import SimpleNamespace as NS

import boot_paths  # noqa: F401
import pytest

from test_ibl_general_capabilities import boundary  # noqa: F401


def test_restricted_execution_resume_uses_permission_set_semantics(boundary, tmp_path, monkeypatch):
    import thread_context
    from ibl_v2_entry import handle_request
    allowed = {"self", "table"}
    monkeypatch.setattr(thread_context, "get_allowed_nodes", lambda: allowed)
    request = {"edition": 2, "code": "return 1"}
    first = handle_request(request, str(tmp_path), "restricted")
    assert first["success"] and first["value"] == 1, first
    allowed = ["table", "self", "table"]
    resumed = handle_request({**request, "resume": first["resume"]},
                             str(tmp_path), "restricted")
    assert resumed["success"], resumed
    allowed = {"table"}
    changed = handle_request({**request, "resume": first["resume"]},
                             str(tmp_path), "restricted")
    assert changed["diagnostic"]["code"] == "RESUME_CHANGED"


def test_unrestricted_and_empty_permissions_have_distinct_identity(monkeypatch):
    import thread_context
    from ibl_run_journal import identity
    from ibl_v2_ir import Fault, pack
    plan = NS(fingerprint="same")
    monkeypatch.setattr(thread_context, "get_allowed_nodes", lambda: None)
    unrestricted = identity(plan, {}, ".", "agent")
    monkeypatch.setattr(thread_context, "get_allowed_nodes", lambda: set())
    assert unrestricted != identity(plan, {}, ".", "agent")
    with pytest.raises(Fault, match="set"):
        pack({"business_value": {1, 2}})


@pytest.mark.parametrize("names", [["함수"], [None], [[]], ["self:"], ["fn:a:b"]])
def test_invalid_describe_names_have_actionable_diagnostic(names):
    from model_result_view import describe_actions
    with pytest.raises(ValueError, match="fn:"):
        describe_actions(names, None)


def test_default_function_discovery_uses_current_contract(boundary, monkeypatch):
    import ibl_v2_store
    from model_result_view import describe_actions
    monkeypatch.setattr(ibl_v2_store, "definitions",
                        lambda: {"배수": "[def:배수]($x){return $x*2}"})
    row = describe_actions(["fn:배수"], {"self", "table"})["actions"][0]
    assert row["definition"]["callable_contract"]["name"] == "배수"
    missing = describe_actions(["fn:없는함수"], None)["actions"][0]
    assert missing["error"]


def test_missing_function_description_prevents_accompanying_effect(boundary, monkeypatch):
    import ibl_v2_entry
    from system_tools_ibl import _execute_ibl_unified_impl
    monkeypatch.setattr(ibl_v2_entry, "handle_request",
                        lambda *a, **kw: pytest.fail("missing contract must stop before execution"))
    result = json.loads(_execute_ibl_unified_impl({"edition": 2, "describe": ["fn:missing"],
                                                  "code": "return 1"}, "."))
    assert result["success"] is False and result["executed"] is False


def test_list_field_and_protocol_diagnostics_do_not_teach_syntax_retries():
    from ibl_v2_compile import compile_program
    from ibl_v2_analysis import syntax_report
    from ibl_v2_ir import Fault
    report = compile_program("$rows=[{n:1}]; return $rows.items").report()
    assert ".items" in report["issues"][0]["hint"]
    hint = syntax_report(Fault("VALUE_PROTOCOL", "bad set", kind="protocol"), "return 1")["diagnostic"]["hint"]
    assert "실행 기반" in hint and "구문 경계" not in hint


def test_multiline_body_is_passed_as_data_without_source_retyping(boundary):
    from ibl_v2_entry import handle_request
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    bad = handle_request({"edition": 2, "code": 'return "a\nb"'})
    assert bad["diagnostic"]["code"] == "STRING_LITERAL"
    assert "inputs" in bad["diagnostic"]["hint"]
    assert bad["diagnostic"]["location"]["line"] == 1
    body = 'a\nb "quote" $literal'
    assert Runtime(compile_program("return $본문", inputs={"본문": body}),
                   {"본문": body}).run()["value"] == body
    assert Runtime(compile_program(r'return "a\nb"')).run()["value"] == "a\nb"


def chunk(reason, tool=None, content=None, usage=None):
    return NS(choices=[NS(delta=NS(content=content, tool_calls=[tool] if tool else None,
                                  reasoning_content=None), finish_reason=reason)], usage=usage)


def provider_with_streams(monkeypatch, streams):
    from providers.deepseek import DeepSeekProvider
    provider = DeepSeekProvider(api_key="test", model="deepseek-flash", system_prompt="s", tools=[])
    calls = []
    iterator = iter(streams)

    def create(params):
        calls.append(params)
        return iter(next(iterator))

    monkeypatch.setattr(provider, "_create_stream_with_retry", create)
    return provider, calls


def test_truncated_tool_retries_once_without_executing_partial_arguments(monkeypatch):
    partial = NS(id="broken", function=NS(name="demo", arguments='{"x":'))
    complete = NS(id="whole", function=NS(name="demo", arguments='{"x":1}'))
    provider, calls = provider_with_streams(monkeypatch, [
        [chunk("length", partial)], [chunk("tool_calls", complete)], [chunk("stop", content="done")]])
    executed = []
    events = list(provider._agentic_loop([{"role": "user", "content": "work"}],
                                       [{"type": "function"}], lambda *a: executed.append(a) or "ok"))
    assert len(executed) == 1 and executed[0][1] == {"x": 1}
    assert calls[1]["extra_body"] == {"thinking": {"type": "disabled"}}
    assert "extra_body" not in calls[2]  # 복구 후에는 기존 모델 추론 설정을 복원한다.
    assert not any(m.get("tool_calls", [{}])[0].get("id") == "broken"
                   for call in calls for m in call["messages"] if m.get("tool_calls"))
    assert events[-1] == {"type": "final", "content": "done"}


def test_repeated_truncated_tool_is_error_and_never_final(monkeypatch):
    partial = NS(id="broken", function=NS(name="demo", arguments='{"x":'))
    provider, calls = provider_with_streams(monkeypatch, [[chunk("length", partial)]] * 2)
    events = list(provider._agentic_loop([{"role": "user", "content": "work"}],
                                       [{"type": "function"}], lambda *a: pytest.fail("partial tool executed")))
    assert len(calls) == 2
    assert events[-1]["type"] == "error" and events[-1]["code"] == "tool_call_truncated"
    assert not any(e["type"] == "final" for e in events)


def test_usage_only_stream_chunk_is_counted(monkeypatch):
    usage = NS(prompt_tokens=20, completion_tokens=5, total_tokens=25)
    provider, _ = provider_with_streams(monkeypatch, [[chunk("stop", content="done"), NS(choices=[], usage=usage)]])
    measured = []
    monkeypatch.setattr(provider.metrics, "record_usage", lambda ms, value, **kw: measured.append(value))
    list(provider._agentic_loop([{"role": "user", "content": "work"}], [], None))
    assert measured == [usage]


def test_synchronous_caller_cannot_accept_truncation_as_success(monkeypatch):
    from providers.deepseek import DeepSeekProvider
    provider = DeepSeekProvider(api_key="test", model="deepseek-flash", system_prompt="s", tools=[])
    provider._client = True
    monkeypatch.setattr(provider, "process_message_stream", lambda *a: iter([
        {"type": "text", "content": "partial"},
        {"type": "error", "code": "tool_call_truncated", "content": "incomplete"}]))
    with pytest.raises(RuntimeError, match="incomplete"):
        provider.process_message("work")
    assert provider.last_failure_kind == "provider_error"


def test_missing_directory_keeps_path_context_through_adapter(tmp_path):
    from ibl_v2_entry import handle_request
    result = handle_request({"edition": 2, "code": '[self:list]{path:"data/missing"}'}, str(tmp_path))
    fault = result["diagnostic"]
    assert fault["code"] == "NOT_FOUND" and fault["details"]["error_type"] == "not_found"
    assert fault["details"]["path"] == str(tmp_path / "data/missing")
    assert fault["details"]["base_path"] == str(tmp_path)
    assert "상대경로" in fault["details"]["hint"]


def test_region_address_delimiters_do_not_change_matching_or_ambiguity(monkeypatch):
    from test_episode_audit_2026_09_09 import _package_module
    naver = _package_module("tool_naver.py")
    monkeypatch.setattr(naver, "_api_get", lambda *a: {"regions": [
        {"cortarNo": "1", "cortarName": "경상남도,진주시,성북동"},
        {"cortarNo": "2", "cortarName": "다른시 성북동"}]})
    assert naver._resolve_keyword("진주시 성북동")["cortarNo"] == "1"
    assert not naver._region_matches("장동", "전주시,색장동")
    with pytest.raises(ValueError, match="여러 지역"):
        naver._resolve_keyword("성북동")


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
