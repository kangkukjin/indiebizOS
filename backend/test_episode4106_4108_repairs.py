"""Contracts and recovery information reach callers without changing access rights."""
import importlib.util
from pathlib import Path

import boot_paths  # noqa: F401
import pytest

from ibl_v2_adapters import Adapter, decode_envelope, load_registry
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def registry():
    return load_registry()


def test_describe_preserves_leaf_usage_but_not_old_core_grammar():
    from model_result_view import describe_actions
    definitions = {row["action"]: row["definition"] for row in describe_actions(
        ["others:channel_read", "table:each"], {"others", "table"})["actions"]}
    read = definitions["others:channel_read"]
    assert 'channel_type:"email",max_results:5' in read["target_description"]
    assert read["callable_contract"]["params"]["channel_type"] == "Text"
    assert read["callable_contract"]["enums"]["channel_type"] == ["email", "nostr", "gmail"]
    assert "target_description" not in definitions["table:each"]


@pytest.mark.parametrize("code", [
    '[others:channel_read]{channel:"hanmail",limit:5}',
    '[others:channel_read]{channel_type:"hanmail",max_results:5}',
    '[others:channel_read]{max_results:5}',
    '[others:channel_read]{channel_type:"email",max_results:0}',
    '[others:channel_read]{channel_type:"email",max_results:1.5}',
    '[others:channel_read]{channel_type:"email",max_results:5,limit:5}',
])
def test_invalid_mail_arguments_never_reach_provider(code, registry):
    calls = []
    adapter = registry["others:channel_read"]
    plan = compile_program(code, {"others:channel_read": Adapter(
        adapter.contract, lambda *_: calls.append(1))})
    assert plan.issues
    assert not Runtime(plan).run()["executed"]
    assert not calls


@pytest.mark.parametrize("args", [
    'channel_type:"email",max_results:5',
    'channel_type:"gmail",query:"subject:hello",max_results:5',
    'channel_type:"nostr",limit:5,since:123',
    'channel_type:"nostr",query:"hello",max_results:5',
    'to:"person@example.net",max_results:5',
])
def test_existing_mail_and_nostr_forms_still_compile(args, registry):
    plan = compile_program('[others:channel_read]{' + args + '}', registry)
    assert not plan.issues, plan.report()


def test_error_help_survives_runtime_and_model_boundary(tmp_path, monkeypatch):
    import channel_engine
    import model_result_view
    from supervision_store import TurnStore
    monkeypatch.setattr(model_result_view, "evidence_store", lambda: TurnStore(tmp_path))
    raw = channel_engine.execute_channel_action("channel_read", {}, str(tmp_path))
    def run(*_):
        return decode_envelope(raw, {"protocol": "legacy-envelope"})[0]
    contract = {"version": 1, "params": {}, "required": [], "result": "Record",
                "effects": ["read_external"]}
    result = Runtime(compile_program('[test:read]{}', {"test:read": Adapter(contract, run)})).run()
    shown = model_result_view.project_result(result)
    details = shown["diagnostic"]["details"]
    assert details["supported_channels"] == ["email", "nostr"]
    assert 'channel_type: "email"' in details["usage"]["read"]
    assert not shown["success"]


def test_missing_account_preserves_gate_and_read_specific_guidance(tmp_path, monkeypatch):
    import channel_engine as channel
    (tmp_path / "agents.yaml").write_text("agents:\n  - id: reader\n    type: external\n")
    monkeypatch.setattr(channel, "_channel_read", lambda *_: pytest.fail("no account: no read"))
    out = channel.execute_channel_action("channel_read", {
        "channel_type": "email", "account": "another@example.net"}, str(tmp_path), "reader")
    assert not out["success"]
    assert "조회·발신" in out["error"]
    assert "신원은 바뀌지 않습니다" in out["hint"]


def test_legacy_error_hint_recognizes_declared_callable_arguments():
    from system_tools_ibl import _enrich_error_with_param_hint
    result = _enrich_error_with_param_hint({"success": False, "error": "계정 없음"},
        '[others:channel_read]{channel_type:"email",max_results:5}')
    assert "선언한 키가 아니라" not in result["_param_hint"]


@pytest.mark.parametrize("params", [{"limit": 5}, {"max_results": 5}])
def test_email_count_is_honored_with_either_existing_size_argument(params, monkeypatch):
    from types import SimpleNamespace
    import channel_engine
    import imap_reader
    calls = []
    client = SimpleNamespace(total=0, get_messages=lambda **kw: calls.append(kw) or [])
    monkeypatch.setattr(imap_reader, "configured_reader", lambda _: client)
    out = channel_engine._channel_read("email", params, {"email": "reader@example.net"})
    assert out["success"] and calls == [{"query": None, "max_results": 5}]


def test_list_filter_recovery_hint_and_both_recovery_forms(registry):
    plan = compile_program('enumerate(["a","b"]) >> [table:filter]{where:($r)=>$r[1]=="b"}', registry)
    issue = next(i for i in plan.report()["issues"] if i["code"] == "TYPE")
    assert 'mode:"flat_map"' in issue["hint"]
    sources = [
        ('enumerate(["a","b"]) >> [table:each]{mode:"flat_map"}'
         '{[if:$it[1]=="b"]{return [$it]}; return []}', [[1, "b"]]),
        ('["a","b"] >> [table:each]{return {번호:$i,내용:$it}} '
         '>> [table:filter]{where:($r)=>$r.내용=="b"}', [{"번호": 1, "내용": "b"}]),
    ]
    for source, expected in sources:
        plan = compile_program(source, registry)
        assert not plan.issues, plan.report()
        assert Runtime(plan).run()["value"] == expected


def test_browser_connection_keeps_nested_causes_and_masks_secrets():
    path = ROOT / "data/packages/installed/tools/browser-action/browser_chrome.py"
    spec = importlib.util.spec_from_file_location("repair_chrome_driver", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    error = ExceptionGroup("TaskGroup", [ExceptionGroup("transport", [
        ConnectionRefusedError("server unavailable"),
        ValueError("password=do-not-expose"),
    ])])
    detail = module._connection_error_detail(error)
    assert "ConnectionRefusedError: server unavailable" in detail
    assert "do-not-expose" not in detail
    assert len(module._connection_error_detail(ValueError("x" * 5000))) <= 2000


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
