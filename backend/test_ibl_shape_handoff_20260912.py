"""3565의 실패 부류와 실제 성공 경로를 함께 검증한다. 공급자/모델 호출 없음."""
import importlib.util
import json
from pathlib import Path

import boot_paths  # noqa: F401
import pytest

from ibl_parser import parse_with_vars, RESUME_SLOT_BASE
from ibl_typecheck import typecheck, typecheck_code
from ibl_value_types import T, infer_value
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


def check(code, values=None):
    values = values or {}
    steps, names = parse_with_vars(code, preset_vars={n: RESUME_SLOT_BASE + i for i, n in enumerate(values)})
    return typecheck(steps, names, given={n: infer_value(v) for n, v in values.items()})


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr("common.spill.spill_dir", lambda: str(tmp_path))
    with actor_context(agent_id="shape-test", task_id="shape-handoff"):
        yield tmp_path


def run(code, tmp_path, **extra):
    return json.loads(_execute_ibl_unified({"code": code, **extra}, str(tmp_path), agent_id="shape-test"))


@pytest.mark.parametrize("code,values,missing", [
    ('$뉴스 = [sense:search]{source:"gnews",queries:["A","B"]}\n'
     '$뉴스 >> [table:select]{fields:["source","published"]}', {}, "source"),
    ('$종목 >> [table:select]{fields:["symbol","current_price"]}',
     {"종목": [quote("A"), quote("B")]}, "symbol"),
    ('[table:compute]{items:[{x:1}],expr:"y = x + 1"}', {}, "expr"),
    ('$유가주 >> [table:flatten]{field:"items"} >> [table:filter]{where:"date >= 2026-09-03"}'
     ' >> [table:select]{fields:["symbol","date","close"]}',
     {"유가주": [history("A"), history("B")]}, "symbol"),
    ('[sense:stock]{op:"history",ticker:"A",period:"1mo"} >> [table:flatten]{field:"items"}', {}, "items"),
    ('[table:compute]{items:[{"변화%":1}],set:{결과:"변화% / 100"}}', {}, "결과"),
])
def test_six_failure_classes_are_rejected(code, values, missing):
    result = check(code, values)
    assert not result["ok"], result
    assert any(missing in i["message"] for i in result["issues"] if i["severity"] == "error")


def test_cross_call_value_and_type_survive_together(isolated):
    key = variables.turn_key("shape-test")
    variables.save(key, {"종목": json.dumps([quote("A"), quote("B")])})
    failed = run('$종목 >> [table:select]{fields:["symbol"]}', isolated)
    assert failed["error_type"] == "typecheck"
    good = run('$표 = $종목 >> [table:flatten]{field:"items"} >> [table:select]{fields:["symbol"]}', isolated)
    assert good.get("success"), good
    assert good["turn_vars"]["live"] == ["표"]
    assert good["turn_vars"]["types"]["표"]["columns"] == ["symbol"]
    assert run('$표 >> [table:select]{fields:["symbol"]}', isolated).get("success")


def test_reassignment_empty_heterogeneous_and_resume(isolated):
    key = variables.turn_key("shape-test")
    variables.save(key, {"a": {"items": [{"old": 1}]}})
    assert run('$a = [table:take]{items:[{new:2}],n:1}\n$a >> [table:select]{fields:["new"]}', isolated).get("success")
    assert variables.types_for(variables.load(key), key)["a"].cols == ["new"]
    variables.save(key, {"a": {"items": []}})
    assert run('$a >> [table:select]{fields:["absent"]}', isolated).get("success")
    variables.save(key, {"a": {"items": [{"x": 1}, {"y": 2}]}})
    assert run('$a >> [table:select]{fields:["y"]}', isolated).get("success")
    resume = isolated / "resume.json"
    resume.write_text(json.dumps({"a": json.dumps({"items": [{"override": 3}]})}))
    assert run('$a >> [table:select]{fields:["override"]}', isolated, resume={"vars_ref": str(resume)}).get("success")


def test_partial_success_and_old_store(isolated):
    output = run('$ok = [table:take]{items:[{x:1}],n:1}\n'
                 '$bad = [self:read]{path:"/nonexistent_shape_handoff/file"}', isolated)
    assert output.get("success") is False
    assert output["turn_vars"]["types"]["ok"]["columns"] == ["x"]
    assert "bad" not in output["turn_vars"]["types"]
    key = variables.turn_key("shape-test")
    Path(variables.store_path(key)).write_text(json.dumps({"old": json.dumps({"items": [{"v": 1}]})}))
    assert run('$old >> [table:select]{fields:["v"]}', isolated).get("success")


def test_structured_type_is_lossless_beyond_display_limit():
    value = {"items": [{f"col{i}": i for i in range(30)}]}
    original = infer_value(value)
    restored = T.from_data(json.loads(json.dumps(original.to_data())))
    assert restored.cols == original.cols and restored.closed
    assert check('$a >> [table:select]{fields:["col29"]}', {"a": value})["ok"]
    assert not check('$a >> [table:select]{fields:["col30"]}', {"a": value})["ok"]


def test_unknown_dynamic_and_large_inputs_are_not_closed():
    assert typecheck_code('[sense:stock]{op:"$dynamic"} >> [table:select]{fields:["anything"]}')["ok"]
    assert not infer_value({"items": [{"x": 1}] * 21000}).closed
    assert check('$a >> [table:select]{fields:["unknown"]}', {"a": {"items": [{"x": 1}] * 21000}})["ok"]


def test_source_rows_remain_available_and_oversize_reassignment_cannot_reuse_old_value(isolated, monkeypatch):
    key = variables.turn_key("shape-test")
    value = {"items": [{"title": "short"}], "data": [{"original": "full evidence"}]}
    variables.save(key, {"a": value})
    assert run('$a >> [table:select]{fields:["original"]}', isolated).get("success")
    monkeypatch.setattr(variables, "MAX_VALUE_CHARS", 10)
    replacement = {"items": [{"new_column": "new evidence"}]}
    kept, skipped = variables.save(key, {"a": replacement})
    assert kept == ["a"] and not skipped
    assert json.loads(variables.load(key)["a"]) == replacement
    assert not run('$a >> [table:select]{fields:["original"]}', isolated).get("success")
    assert run('$a >> [table:select]{fields:["new_column"]}', isolated).get("success")


def test_observed_catalog_and_other_search_modes_are_not_closed():
    assert typecheck_code('[sense:search]{source:"gnews",query:"A"} >> [table:select]{fields:["source"]}')["ok"]
    assert typecheck_code('[sense:search]{source:"gnews",queries:["A"],curate:3} >> [table:select]{fields:["extra"]}')["ok"]
    assert typecheck_code('[sense:search]{source:"gnews",queries:[],query:"A"} >> [table:select]{fields:["source"]}')["ok"]


def test_transform_replaces_old_items_type_but_preserves_source_evidence():
    code = '$a >> [table:select]{fields:["x"]} >> [table:select]{fields:["y"]}'
    assert not check(code, {"a": {"items": [{"x": 1, "y": 2}]}})["ok"]
    assert check(code, {"a": {"items": [{"x": 1, "y": 2}], "data": [{"y": 2}]}})["ok"]


def test_type_display_groups_identical_branches():
    from ibl_value_types import display_type
    shown = display_type(infer_value([quote(str(i)) for i in range(20)]))
    assert shown["branch_count"] == 20 and len(shown["branches"]) == 1
    assert shown["branches"][0]["count"] == 20
    assert len(json.dumps(shown)) < 1800


@pytest.fixture
def dataops():
    spec = importlib.util.spec_from_file_location("shape_dataops", ROOT / "data/packages/installed/tools/data-ops/handler.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_flatten_preserves_nested_identity_null_literal_and_collisions(dataops):
    branches = [history("A"), history("B")]
    result = dataops._op_flatten(branches, {"field": "items", "keep": ["data.symbol"]})
    assert [row["data.symbol"] for row in result["items"]] == ["A", "B"]
    values = [{"data.symbol": None, "data": {"symbol": "nested"}, "items": [{"data.symbol": "child"}]}]
    out = dataops._op_flatten(values, {"field": "items", "keep": ["data.symbol"]})
    assert out["items"][0] == {"data.symbol": "child", "data.symbol_2": None}
    assert dataops._op_flatten(branches, {"field": "items", "keep": ["data.missing"]})["success"] is False
    result = check('$a >> [table:flatten]{field:"items",keep:["data.symbol"]} >> '
                   '[table:select]{fields:["data.symbol","date"]}', {"a": branches})
    assert result["ok"], result


def test_normal_envelope_and_union_operations_remain_valid():
    values = {"a": [quote("A"), quote("B")]}
    for code in ('$a >> [table:select]{fields:["data"]}',
                 '$a >> [table:union] >> [table:select]{fields:["symbol"]}',
                 '$a >> [table:flatten]{field:"items"} >> [table:select]{fields:["symbol"]}'):
        assert check(code, values)["ok"], code


def test_compute_diagnostic_teaches_the_working_form():
    failed = typecheck_code('[table:compute]{items:[{x:1}],expr:"y=x+1"}')
    hint = failed["issues"][0]["hint"]
    assert "set:" in hint and "col(" in hint
    assert typecheck_code('''[table:compute]{items:[{"변화%":1}],set:{결과:'col("변화%") / 100'}}''')["ok"]


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
    raw = {"success": True, "final_result": json.dumps([json.dumps(a), json.dumps(failure)])}
    before = json.dumps(raw)
    result = view.project_result(raw)
    assert isinstance(result["final_result"], list)
    shown = result["final_result"][0]
    assert shown["data"]["prices"] == a["data"]["prices"]
    assert shown["data"]["truncated"] is True and shown["warning"] == a["warning"]
    assert shown["items"][0] == a["items"][0]
    assert result["final_result"][1] == failure
    assert len(json.dumps(result, ensure_ascii=False)) < len(json.dumps(raw, ensure_ascii=False))
    assert json.dumps(raw) == before
    assert json.loads(store.read_evidence(result["result_ref"]["id"], limit=None)["text"]) == raw


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q"]))
