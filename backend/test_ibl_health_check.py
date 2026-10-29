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


def test_static_timeout_keeps_deadline_and_reports_failure(health, monkeypatch, capsys):
    import subprocess

    def timeout(*args, **kwargs):
        assert kwargs["timeout"] == 600
        raise subprocess.TimeoutExpired(args[0], kwargs["timeout"])

    monkeypatch.setattr(subprocess, "run", timeout)
    result, elapsed = health._run_static_check()
    assert elapsed >= 0
    assert health._report_static(result) is False
    assert "제한시간 초과 (600초)" in capsys.readouterr().out


@pytest.mark.parametrize("returncode", [0, 1])
def test_static_verdict_uses_exit_code_even_with_success_text(health, returncode, capsys):
    import subprocess
    result = subprocess.CompletedProcess([], returncode, "검증 통과", "✗ 파생물 불일치")
    assert health._report_static(result) is (returncode == 0)
    if returncode:
        assert "파생물 불일치" in capsys.readouterr().out


@pytest.mark.parametrize("abort", [False, True])
def test_static_overlaps_live_checks_and_is_joined_on_exit(health, monkeypatch, abort):
    from threading import Event
    static_started, live_started, static_finished = Event(), Event(), Event()

    def static():
        static_started.set()
        try:
            assert live_started.wait(5), "live checks must start before static finishes"
            return "static-result"
        finally:
            static_finished.set()

    def live(future):
        assert static_started.wait(5)
        assert not future.done()
        live_started.set()
        if abort:
            raise SystemExit(0)  # same unwind path as admission closure
        assert future.result(timeout=5) == "static-result"

    monkeypatch.setattr(health, "_run_static_check", static)
    monkeypatch.setattr(health, "_run_checks", live)
    monkeypatch.setattr(health.sys, "argv", ["ibl_health_check.py"])
    if abort:
        with pytest.raises(SystemExit):
            health.main()
    else:
        health.main()
    assert static_finished.is_set()


@pytest.mark.parametrize("static_ok", [False, True])
def test_summary_keeps_live_results_when_static_fails(health, monkeypatch, capsys, static_ok):
    import subprocess
    from concurrent.futures import Future
    # Keep the real aggregation path; replace effects and use one fixture.
    monkeypatch.setattr(health.json, "load", lambda stream:
                        {"fixtures": {"sense:search": "probe"}, "exempt": {}})
    monkeypatch.setattr(health, "_load_safety_map", lambda: {("sense", "search"): True})
    monkeypatch.setattr(health, "_load_op_safety_map", lambda: {})
    monkeypatch.setattr(health, "_first_op", lambda *args: None)
    monkeypatch.setattr(health, "_op_returns_of", lambda *args: "items")
    monkeypatch.setattr(health, "_is_safe", lambda *args: True)
    monkeypatch.setattr(health, "execute", lambda *args: packet({"items": [{"title": "ok"}]}))
    monkeypatch.setattr(health, "run_contract_drift", lambda: {"compared": 1})
    monkeypatch.setattr(health, "PIPES", [])
    monkeypatch.setattr(health, "OPERATORS", [])
    future = Future()
    future.set_result((subprocess.CompletedProcess([], 0 if static_ok else 1, "", "실패"), 12.5))
    health._run_checks(future)
    line = next(line for line in capsys.readouterr().out.splitlines()
                if line.startswith("@@HEALTH_JSON@@ "))
    summary = json.loads(line.split(" ", 1)[1])
    assert summary["static_ok"] is static_ok
    assert summary["static_error"] == (None if static_ok else "실패")
    assert summary["currency"]["green"] == 1
    assert summary["timings"]["static_s"] == 12.5
    assert summary["timings"]["live_s"] >= 0


def test_static_check_uses_complete_source_tree_with_matching_child_environment(health, monkeypatch, tmp_path):
    import subprocess
    source, generation = tmp_path / "source", tmp_path / "generation"
    source.mkdir()
    generation.mkdir()
    monkeypatch.chdir(generation)
    monkeypatch.setenv("INDIEBIZ_SOURCE_ROOT", str(source))
    monkeypatch.setenv("INDIEBIZ_CODE_ROOT", str(generation))
    monkeypatch.setenv("INDIEBIZ_RUNTIME_CONTROL", "private-worker-token")
    seen = {}

    def run(command, **kwargs):
        seen.update(command=command, **kwargs)
        return subprocess.CompletedProcess(command, 1, "", "실제 불일치")

    monkeypatch.setattr(subprocess, "run", run)
    result, _ = health._run_static_check()
    assert result.returncode == 1
    assert seen["command"][1] == str(source / "scripts/build_ibl_nodes.py")
    assert seen["cwd"] == str(source)
    assert seen["env"]["INDIEBIZ_CODE_ROOT"] == str(source)
    assert "INDIEBIZ_RUNTIME_CONTROL" not in seen["env"]


def test_progress_is_flushed_without_waiting_for_completion(health, monkeypatch):
    printed = []
    monkeypatch.setattr("builtins.print", lambda *args, **kwargs: printed.append((args, kwargs)))
    health.progress("fixture", "sense:search")
    args, kwargs = printed[0]
    assert kwargs["flush"] is True
    point = json.loads(args[0].split(" ", 1)[1])
    assert point["stage"] == "fixture" and point["item"] == "sense:search"
    assert point["elapsed_s"] >= 0


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
