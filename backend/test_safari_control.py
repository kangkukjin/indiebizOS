"""Safari 실제 스크립트 프로세스 → 등록 실행기 → IBL. Apple Events 끝단만 모의한다."""
import boot_paths  # noqa: F401
import json
from pathlib import Path
import sys

import pytest
import yaml

from test_script_operation_outcomes import ops  # noqa: F401

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
import json, runpy, subprocess, sys
from pathlib import Path
from unittest.mock import patch
tabs = ["same", "same", "different"]
calls = []
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
    elif "of every window" in script:
        value = [[7], ["A"], [1]]
    elif "of every tab" in script:
        value = [list(range(1, len(tabs) + 1)), ["https://example.test/" + t for t in tabs], tabs]
    elif "set current tab" in script:
        raise subprocess.TimeoutExpired(argv, kwargs.get("timeout"))
    elif "close tab" in script:
        index = int(script.rsplit("tab ", 1)[1]) - 1
        tabs.pop(index if MODE == "normal" else -1)
        value = None
    else:
        raise AssertionError(script)
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
    assert sum("of every window" in c for c in calls) == 2  # 변경 전과 불명확 뒤 재조회


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
    assert result["diagnostic"]["details"]["failure"]["code"] == "NOT_APPLIED", result
    assert sum("close tab" in c for c in json.loads(log.read_text())) == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
