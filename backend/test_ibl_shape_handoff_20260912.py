"""3565의 실패 부류와 실제 성공 경로를 함께 검증한다. 공급자/모델 호출 없음."""
import importlib.util
import json
from pathlib import Path

import boot_paths  # noqa: F401
import pytest

from ibl_typecheck import typecheck_code
import ibl_turn_vars as variables
from thread_context import actor_context
from system_tools import _execute_ibl_unified

ROOT = Path(__file__).resolve().parents[1]


def quote(symbol):
    row = {"symbol": symbol, "current_price": 101, "change_percent": 1, "previous_close": 100}
    return {"success": True, "data": {**row, "prices": [{"date": "2026-09-04", "close": 99}]},
            "items": [row]}


def history(symbol):
    rows = [{"date": "2026-09-04", "open": 99, "high": 102, "low": 98, "close": 101, "volume": 10}]
    return {"success": True, "data": {"symbol": symbol, "prices": rows}, "items": rows}




@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr("common.spill.spill_dir", lambda: str(tmp_path))
    with actor_context(agent_id="shape-test", task_id="shape-handoff"):
        yield tmp_path


def run(code, tmp_path, **extra):
    return json.loads(_execute_ibl_unified({"code": code, **extra}, str(tmp_path), agent_id="shape-test"))






















@pytest.fixture
def dataops():
    spec = importlib.util.spec_from_file_location("shape_dataops", ROOT / "data/packages/installed/tools/data-ops/handler.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module








def test_projection_deduplicates_only_the_copy_and_preserves_evidence(tmp_path, monkeypatch):
    import model_result_view as view
    from supervision_store import TurnStore
    store = TurnStore(tmp_path)
    monkeypatch.setattr(view, "evidence_store", lambda: store)
    a = quote("LONG-SYMBOL")
    a["data"].update({f"field{i}": "preserved scalar " * 4 for i in range(12)})
    a["items"][0].update({k: v for k, v in a["data"].items() if k != "prices"})
    a["data"]["truncated"] = True
    a["warning"] = "source unavailable"
    failure = {"success": False, "error": "upstream failed", "source": "provider"}
    from test_ibl_check_client import packet
    raw = packet([a, failure])
    before = json.dumps(raw)
    result = view.project_result(raw)
    assert isinstance(result["value"], list)
    shown = result["value"][0]
    assert shown["data"]["prices"] == a["data"]["prices"]
    assert shown["data"]["truncated"] is True and shown["warning"] == a["warning"]
    assert shown["items"][0] == a["items"][0]
    assert result["value"][1] == failure
    assert len(json.dumps(result, ensure_ascii=False)) < len(json.dumps(raw, ensure_ascii=False))
    assert json.dumps(raw) == before
    assert json.loads(store.read_evidence(result["result_ref"]["id"], limit=None)["text"]) == raw


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
