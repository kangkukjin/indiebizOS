"""Health probes exercise current contracts and never turn failed execution green."""
import boot_paths  # noqa: F401
import importlib
import json
from pathlib import Path

import pytest
from ibl_v2_ir import Fault, pack
from ibl_v2_adapters import Adapter, load_registry
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime


@pytest.fixture
def health(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    return importlib.import_module("ibl_health_check")


def packet(value):
    return {"edition": 2, "executed": True, "success": True,
            "value_wire": {"protocol": "ibl-value/1", "data": pack(value)}}


def test_http_probe_declares_current_edition_and_preserves_parent(health, monkeypatch):
    seen = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def read(self):
            return json.dumps(packet({"items": [{"title": "test"}]})).encode()

    def open_request(request, **kwargs):
        seen.update(body=json.loads(request.data), headers=dict(request.header_items()))
        return Response()

    monkeypatch.setenv("INDIEBIZ_RUNTIME_PARENT", "parent-test")
    monkeypatch.setattr(health.urllib.request, "urlopen", open_request)
    result = health.execute('[sense:search]{query:"test"}')
    assert seen["body"]["edition"] == 2
    assert seen["body"]["agent_id"] == "__self_check__"
    assert seen["headers"]["X-runtime-parent"] == "parent-test"
    assert health.classify_currency(result, "items")[0] == "GREEN"


@pytest.mark.parametrize("paged", [False, True])
def test_actual_agent_projection_is_read_losslessly_without_reexecution(health, monkeypatch, tmp_path, paged):
    import model_result_view as view
    from supervision_store import TurnStore
    monkeypatch.setattr(view, "evidence_store", lambda: TurnStore(tmp_path / "evidence"))
    value = {"items": [{"title": "실제 투영 계약", "body": "본문" * 10000}]}
    original = {**packet(value), "value": value, "source_complete": True, "evidence": []}
    shown = view.project_result(original)
    assert "value_wire" not in shown and "result_ref" in shown
    calls = []

    def request(fields, pid):
        calls.append(fields)
        if fields["code"]:
            return shown
        read = dict(fields["read_result"])
        if paged:
            read["limit"] = 1000
        return view.read_result(read)

    monkeypatch.setattr(health, "_request", request)
    result = health.execute("return value")
    assert health.final_of(result) == value
    assert len([c for c in calls if c["code"]]) == 1
    assert health.classify_currency(result, "items")[0] == "GREEN"


def test_missing_reference_page_never_uses_preview_as_complete_value(health, monkeypatch):
    shown = {"success": True, "executed": True, "value": {"items": [{}]}, "result_ref": {"id": "id"}}
    monkeypatch.setattr(health, "_request", lambda fields, pid:
                        shown if fields["code"] else {"error": "reference unavailable"})
    assert health.classify_currency(health.execute("original"), "items")[0] == "RED"


@pytest.mark.parametrize("result", [
    {"success": False, "executed": False, "error": "compile", "items": [{}]},
    {"_transport_error": "503"},
    {"success": True, "items": [{}]},
    {"success": True, "value_wire": {"protocol": "unknown", "data": pack({"items": [{}]})}},
    {"success": True, "value_wire": {"protocol": "ibl-value/1", "data": ["bogus"]}},
])
def test_failed_or_malformed_execution_is_red_even_with_items(health, result):
    assert health.classify_currency(result, "items")[0] == "RED"


def test_success_is_not_confused_with_business_record(health):
    value = {"success": False, "error": "business record", "items": [{"title": "valid"}]}
    assert health.final_of(packet(value)) == value
    assert health.final_of(packet([1, 2])) == [1, 2]
    assert health.classify_currency({"success": False, "executed": True, "error": "offline"}, "items")[0] == "YELLOW"


def test_all_current_live_probes_compile_and_assert_their_values(health):
    programs = importlib.import_module("ibl_health_programs")
    registry = load_registry(".", "__self_check__")
    # Keep real contracts, substitute only external effects.
    for key in ("sense:search", "sense:world_bank", "sense:paper", "sense:legal", "sense:kosis"):
        registry[key] = Adapter(registry[key].contract, lambda rt, args: {"items": [{"title": "x"}]})
    for key in ("table:chart", "table:document"):
        registry[key] = Adapter(registry[key].contract, lambda rt, args: {"success": True, "path": "test-output"})

    def missing(rt, args):
        raise Fault("NOT_FOUND", "missing file", kind="runtime")

    registry["self:read"] = Adapter(registry["self:read"].contract, missing)
    for name, source, kind in programs.PIPES:
        result = Runtime(compile_program(source, registry)).run()
        assert programs.pipe_ok(health.final_of(result), kind), (name, result)
    for name, source, expected in programs.OPERATORS:
        result = Runtime(compile_program(source, registry)).run()
        assert programs.operator_result(result, expected)[0], (name, result)


def test_negative_probe_rejects_compile_failure_and_wrong_error(health):
    programs = importlib.import_module("ibl_health_programs")
    for result in ({"executed": False, "success": False},
                   {"executed": True, "success": False, "diagnostic": {"code": "TYPE"}}):
        assert not programs.operator_result(result, "runtime_failure")[0]
    assert not programs.pipe_ok({"success": True}, "doc")
    assert not programs.pipe_ok({"success": False, "path": "partial"}, "doc")


def test_runner_does_not_certify_all_failed_fixtures(health, monkeypatch):
    import subprocess
    import world_pulse_health
    summary = {"static_ok": True, "currency": {"green": 0, "yellow": 10, "red": 0},
               "golden_pipes": {"passed": 5, "total": 5}}
    monkeypatch.setattr(subprocess, "run", lambda *args, **kwargs:
                        subprocess.CompletedProcess(args, 0, "@@HEALTH_JSON@@ " + json.dumps(summary), ""))
    events = world_pulse_health.run_ibl_health_check()
    assert next(e for e in events if e["action"] == "currency")["success"] is False


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
