"""Safari 실제 스크립트 프로세스 → 등록 실행기 → IBL. Apple Events 끝단만 모의한다."""
import boot_paths  # noqa: F401
import json
import copy
import importlib.util
import subprocess
from pathlib import Path
import sys
from unittest.mock import patch

import pytest
import yaml

from test_script_operation_outcomes import ops  # noqa: F401
from test_control_driver import safari  # noqa: F401 — native Apple Event stand-in

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def safari_process(ops, monkeypatch, tmp_path):
    from tool_loader import load_tool_handler
    entry = yaml.safe_load((ROOT / "data/scripts/registry.yaml").read_text())["Safari제어"]
    monkeypatch.setattr(ops, "_read_registry", lambda: {"Safari제어": {**entry, "file": "check.py"}})
    monkeypatch.setattr(ops, "_resolve_interpreter", lambda *args: (sys.executable, None))
    handler = load_tool_handler("script_op")
    monkeypatch.setitem(handler._SIBLING_MODS, "script_ops", ops)
    log = tmp_path / "apple-events.json"
    wrapper = '''
import json, re, runpy, subprocess, sys
from pathlib import Path
from unittest.mock import patch
state_path = Path(LOG + ".state")
state = json.loads(state_path.read_text()) if state_path.exists() else {"tabs": ["same", "same", "different"], "current": 1}
tabs = state["tabs"]
calls = json.loads(Path(LOG).read_text()) if Path(LOG).exists() else []
def fmt(value):
    if isinstance(value, list):
        return "{" + ", ".join(fmt(v) for v in value) + "}"
    return json.dumps(value)
def native(argv, **kwargs):
    script = argv[-1]
    calls.append(script)
    Path(LOG).write_text(json.dumps(calls))
    if "is running" in script:
        value = True
    elif "safari_snapshot_v2" in script:
        value = [[7, "A", state["current"], [list(range(1, len(tabs) + 1)), ["about:blank" if t == "blank" else "https://example.test/" + t for t in tabs], tabs]]]
    elif "make new tab" in script:
        tabs.append("blank")
        value = [7, len(tabs)]
    elif "set current tab" in script:
        if MODE != "workflow":
            raise subprocess.TimeoutExpired(argv, kwargs.get("timeout"))
        state["current"] = int(re.search(r"set current tab of w to tab (\\d+)", script)[1])
        value = None
    elif "close tab" in script:
        index = int(re.search(r"close tab (\\d+)", script)[1]) - 1
        tabs.pop(-1 if MODE == "wrong-tab" else index)
        value = None
    else:
        raise AssertionError(script)
    state_path.write_text(json.dumps(state))
    return subprocess.CompletedProcess(argv, 0, fmt(value) if value is not None else "", "")
with patch.object(sys, "platform", "darwin"), patch.object(subprocess, "run", native):
    runpy.run_path(SOURCE, run_name="__main__")
'''

    def prepare(mode="normal"):
        (ops._SCRIPT_DIR / "check.py").write_text(
            "SOURCE = " + repr(str(ROOT / "data/scripts/safari_control.py"))
            + "\nLOG = " + repr(str(log)) + "\nMODE = " + repr(mode) + "\n" + wrapper)
        return log
    return prepare


def invoke(args, tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api_ibl import router
    app = FastAPI()
    app.include_router(router)
    if args.get("op") in {"switch", "close"} and "expected" not in args:
        import hashlib
        payload = [7, 1, ["https://example.test/" + t for t in ["same", "same", "different"]]]
        args = {**args, "expected": hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()}
    code = "[self:script]" + json.dumps({"id": "Safari제어", "args": args}, ensure_ascii=False)
    with TestClient(app) as client:
        response = client.post("/ibl/execute", json={
            "edition": 2, "code": code, "project_path": str(tmp_path)})
    assert response.status_code == 200, response.text
    return response.json()


def test_unknown_survives_real_script_process_and_ibl_fault(safari_process, tmp_path):
    log = safari_process()
    result = invoke({"op": "switch", "window_id": 7, "tab": 2}, tmp_path)
    assert not result["success"], result
    details = result["diagnostic"]["details"]
    assert details["failure"]["code"] == "UNKNOWN"
    assert details["recovery"]["status"] == "unknown"
    assert details["recovery"]["retry_change"] is False
    assert details["error_type"] == "result_unknown"
    wire = json.dumps(result, ensure_ascii=False)
    assert "UNKNOWN" in wire and "result_unknown" in wire and "재전송하지 말고" in wire, result
    assert '"retry_change": false' in wire and '"status": "unknown"' in wire, result
    calls = json.loads(log.read_text())
    assert sum("set current tab" in c for c in calls) == 1
    assert sum("safari_snapshot_v2" in c for c in calls) == 2  # 변경 전과 불명확 뒤 재조회


@pytest.mark.parametrize("tab", [1, 2, 3])
def test_close_renumbered_duplicate_tabs_through_ibl(safari_process, tmp_path, tab):
    log = safari_process()
    result = invoke({"op": "close", "window_id": 7, "tab": tab}, tmp_path)
    assert result["success"], result
    assert result["value"]["verified"] is True and result["value"]["tab_count"] == 2
    assert result["value"]["closed_tab"]["index"] == tab
    assert sum("close tab" in c for c in json.loads(log.read_text())) == 1


def test_close_other_tab_is_not_verified_or_retried(safari_process, tmp_path):
    log = safari_process("wrong-tab")
    result = invoke({"op": "close", "window_id": 7, "tab": 1}, tmp_path)
    assert not result["success"], result
    assert result["diagnostic"]["details"]["failure"]["code"] == "POSTCONDITION_FAILED", result
    assert sum("close tab" in c for c in json.loads(log.read_text())) == 1


@pytest.fixture
def driver(monkeypatch):
    spec = importlib.util.spec_from_file_location("safari_regression", ROOT / "data/scripts/safari_control.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "precheck", lambda request: True)
    return module


def window(driver, urls, current=1, wid=7):
    item = {"window_id": wid, "name": "test", "current_tab": current, "tab_count": len(urls),
            "tabs": [{"index": i + 1, "url": url, "name": url} for i, url in enumerate(urls)]}
    item["revision"] = driver.revision(item)
    return item


def scenario(driver, op, before, after, *, native="", expected=None, tab=2, url="https://b.test"):
    request = {"op": op, "window_id": 7}
    if op == "open":
        request["url"] = url
    else:
        request.update(tab=tab, expected=expected or before[0]["revision"])
    with patch.object(driver, "windows", side_effect=[copy.deepcopy(before), copy.deepcopy(after)]), \
            patch.object(driver, "apple_event") as event:
        if isinstance(native, Exception):
            event.side_effect = native
        else:
            event.return_value = native
        return driver.run(request), event


def test_stale_selection_refuses_before_mutation(driver):
    observed = window(driver, ["A", "B", "C"])
    actual = window(driver, ["B", "C"])
    with patch.object(driver, "windows", return_value=[actual]), patch.object(driver, "apple_event") as event:
        with pytest.raises(driver.Failure, match="관측 이후") as exc:
            driver.run({"op": "close", "window_id": 7, "tab": 2, "expected": observed["revision"]})
        assert exc.value.code == "STATE_CHANGED"
        event.assert_not_called()


@pytest.mark.parametrize("op", ["switch", "close"])
def test_missing_observation_refuses_before_any_native_call(driver, op):
    with patch.object(driver, "apple_event") as event:
        with pytest.raises(driver.Failure) as exc:
            driver.run({"op": op, "window_id": 7, "tab": 2})
        assert exc.value.code == "INVALID_ARGUMENT"
        event.assert_not_called()


def test_background_open_must_preserve_current_tab(driver):
    out, _ = scenario(driver, "open", [window(driver, ["A"])],
                      [window(driver, ["A", "https://b.test"], current=2)], native="{7, 2}")
    assert not out["success"] and not out["verified"]
    assert out["current_tab_unchanged"] is False
    assert out["failure"]["code"] == "POSTCONDITION_FAILED"
    assert out["recovery"]["retry_change"] is False


def test_closing_one_tab_cannot_verify_loss_of_whole_window(driver):
    out, _ = scenario(driver, "close", [window(driver, ["A", "B", "C"])], [])
    assert not out["verified"] and out["window_closed"]
    assert out["failure"]["code"] == "POSTCONDITION_FAILED"


def test_last_tab_can_close_window(driver):
    out, _ = scenario(driver, "close", [window(driver, ["A"])], [], tab=1)
    assert out["verified"] and out["window_closed"] and out["state"] is None
    assert out["target"] is None


def test_redirect_uses_creation_receipt_without_claiming_page_load(driver):
    out, _ = scenario(driver, "open", [window(driver, ["A"])],
                      [window(driver, ["A", "https://example.test/"])],
                      native="{7, 2}", url="http://example.test")
    assert out["verified"] and not out["checks"]["requested_url_observed"]
    assert out["checks"]["creation_receipt"] and out["page_loaded"] is None
    assert out["target"] == {"window_id": 7, "tab": 2, "expected": out["state"]["revision"]}


def test_redirect_without_creation_receipt_stays_unknown(driver):
    out, event = scenario(driver, "open", [window(driver, ["A"])],
                          [window(driver, ["A", "https://example.test/"])],
                          native=subprocess.TimeoutExpired("simulated-event", 15), url="http://example.test")
    assert out["status"] == "unknown" and not out["verified"]
    assert event.call_count == 1 and out["recovery"]["retry_change"] is False


def test_new_window_creation_returns_followup_target(driver):
    created = window(driver, ["https://example.test/"], wid=8)
    with patch.object(driver, "windows", side_effect=[[], [created]]), \
            patch.object(driver, "apple_event", return_value="{8, 1}") as event:
        out = driver.run({"op": "open", "url": "http://example.test"})
    assert out["verified"] and out["window_created"] and event.call_count == 1
    assert out["before"] is None and out["target"]["window_id"] == 8
    assert out["current_tab_unchanged"] is None and out["page_loaded"] is None


def test_open_must_preserve_existing_tab_urls(driver):
    out, _ = scenario(driver, "open", [window(driver, ["A"])],
                      [window(driver, ["changed", "https://b.test"])], native="{7, 2}")
    assert not out["verified"] and not out["checks"]["existing_state_preserved"]


def test_switch_cannot_verify_reordered_target(driver):
    out, _ = scenario(driver, "switch", [window(driver, ["A", "B", "C"])],
                      [window(driver, ["A", "C", "B"], current=2)])
    assert not out["verified"] and not out["checks"]["tab_order_preserved"]


def test_timeout_then_window_disappears_stays_unknown(driver):
    out, event = scenario(driver, "switch", [window(driver, ["A", "B"])], [],
                          native=subprocess.TimeoutExpired("simulated-event", 10))
    assert out["status"] == "unknown" and out["failure"]["code"] == "UNKNOWN"
    assert out["state"] is None and event.call_count == 1


def test_readback_failure_after_effect_is_unknown(driver):
    before = window(driver, ["A", "B"])
    with patch.object(driver, "windows", side_effect=[[before], driver.Failure("PERMISSION_REQUIRED", "lost access")]), \
            patch.object(driver, "apple_event", return_value="") as event:
        out = driver.run({"op": "close", "window_id": 7, "tab": 2, "expected": before["revision"]})
    assert out["status"] == "unknown" and event.call_count == 1
    assert out["observation_error"]["code"] == "PERMISSION_REQUIRED"


def test_title_loading_does_not_invalidate_close(driver):
    before = window(driver, ["A", "B", "C"])
    after = window(driver, ["A", "C"])
    after["tabs"][0]["name"] = "Loaded title"
    out, _ = scenario(driver, "close", [before], [after])
    assert out["verified"]


def test_native_guard_checks_again_before_changing(driver):
    before = window(driver, ["A", "B"])
    with patch.object(driver, "windows", return_value=[before]), \
            patch.object(driver, "apple_event", side_effect=driver.Failure("STATE_CHANGED", "race")) as event:
        with pytest.raises(driver.Failure) as exc:
            driver.run({"op": "close", "window_id": 7, "tab": 2, "expected": before["revision"]})
    assert exc.value.code == "STATE_CHANGED" and event.call_count == 1
    script = event.call_args.args[0]
    assert script.index("SAFARI_STATE_CHANGED") < script.index("close tab")
    assert "URL of every tab of w" in script and "index of current tab of w" in script


def test_already_selected_tab_needs_no_mutation_or_second_read(driver):
    before = window(driver, ["A", "B"], current=2)
    out, event = scenario(driver, "switch", [before], [])
    assert out["verified"] and out["changed"] is False
    event.assert_not_called()


def test_snapshot_batches_windows_and_limits_target(driver):
    rows = [[7, "A", 1, [[1, 2], ["A", "B"], ["title A", "title B"]]],
            [8, "B", 1, [[1], ["C"], ["title C"]]]]
    def osa(value):
        return "{" + ", ".join(osa(v) for v in value) + "}" if isinstance(value, list) else json.dumps(value)
    with patch.object(driver, "apple_event", return_value=osa(rows)) as event:
        states = driver.windows()
        assert len(states) == 2 and event.call_count == 1
        assert "set selectedWindows to every window" in event.call_args.args[0]
    with patch.object(driver, "apple_event", return_value=osa(rows[:1])) as event:
        assert len(driver.windows(7)) == 1 and event.call_count == 1
        assert "set selectedWindows to {window id 7}" in event.call_args.args[0]


def test_incomplete_snapshot_is_not_verified(driver):
    with patch.object(driver, "apple_event", return_value='{{7, "A", 1, {{1, 2}, {"A"}, {"A", "B"}}}}'):
        with pytest.raises(driver.Failure, match="불완전"):
            driver.windows(7)


def test_targeted_change_has_four_native_calls_and_returns_reusable_state(safari):
    out = safari.run({"op": "open", "window_id": 223970, "url": "https://example.test"})
    calls = safari._state["calls"]
    assert out["verified"] and len(calls) == 4
    assert sum("safari_snapshot_v2" in c for c in calls) == 2
    assert all("set selectedWindows to {window id 223970}" in c
               for c in calls if "safari_snapshot_v2" in c)
    assert "windows" not in out
    switched = safari.run({"op": "switch", **out["target"]})
    assert switched["verified"] and switched["current_tab"] == 2
    assert len(calls) == 8  # No separate status between commands.


def test_unicode_url_uses_applescript_literal(driver):
    out, event = scenario(driver, "open", [window(driver, ["A"])],
                          [window(driver, ["A", "https://example.test/한글"])],
                          native="{7, 2}", url="https://example.test/한글")
    assert out["verified"]
    assert "한글" in event.call_args.args[0] and "\\u" not in event.call_args.args[0]


def test_deadline_leaves_room_to_return_unknown(driver):
    with patch.object(driver, "DEADLINE", driver.time.monotonic() - 1), \
            patch.object(driver.subprocess, "run") as native:
        with pytest.raises(subprocess.TimeoutExpired):
            driver.apple_event("read")
        native.assert_not_called()


def test_ibl_contract_requires_observed_revision():
    from ibl_v2_compile import compile_program
    from ibl_v2_adapters import load_registry
    from ibl_v2_store import definitions
    plan = compile_program(
        '[self:script]{id:"Safari제어",args:{op:"close",window_id:7,tab:2}}',
        load_registry(), definitions=definitions(), inputs={})
    assert plan.issues and "expected" in str(plan.report())


def test_missing_target_in_native_guard_is_conservatively_reconciled(driver):
    out, event = scenario(driver, "close", [window(driver, ["A", "B"])], [],
                          native=driver.Failure("TARGET_MISSING", "window disappeared"))
    assert out["status"] == "unknown" and event.call_count == 1


def test_guide_workflow_executes_as_one_ibl_program(safari_process, tmp_path):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from api_ibl import router
    import re
    log = safari_process("workflow")
    guide = (ROOT / "data/guides/safari_control.md").read_text()
    code = re.findall(r"```ibl\n(.*?)```", guide, re.S)[-1]
    app = FastAPI()
    app.include_router(router)
    with TestClient(app) as client:
        result = client.post("/ibl/execute", json={
            "edition": 2, "code": code, "project_path": str(tmp_path)}).json()
    assert result["success"], result
    assert result["value"]["verified"] and result["value"]["tab_count"] == 3
    state = json.loads(Path(str(log) + ".state").read_text())
    assert state == {"tabs": ["same", "same", "different"], "current": 1}
    calls = json.loads(log.read_text())
    assert sum("make new tab" in c for c in calls) == 1
    assert sum("set current tab of w" in c for c in calls) == 2
    assert sum("close tab" in c for c in calls) == 1
    # One initial status, then one before/after read per mutation; no model round-trips.
    assert sum("safari_snapshot_v2" in c for c in calls) == 9


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
