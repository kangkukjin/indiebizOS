"""General AI boundaries: actual inputs, exact coverage, no paid model calls."""
import copy
import importlib.util
import json
from pathlib import Path

import boot_paths  # noqa: F401
import pytest
import oneshot_facade
from common.ai_input_inspection import indexed_payload, inspect_inputs
from common.item_contract import ContractError, check_inputs, check_outputs, validate_contract
from ibl_typecheck import typecheck_code

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "boundary_ai_handler", ROOT / "data/packages/installed/tools/ai-ops/handler.py")
AI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AI)

CONTRACT = {"covers": [{"input": "input.lines", "output": "result.lines", "key": "id",
                        "required": ["text"], "allowed": {"status": ["done"]}}]}
SOURCE = [{"input": {"lines": [{"id": "a", "text": "원문"}, {"id": "b", "text": "둘"}]}}]
OUTPUT = [{"_i": 0, "result": {"lines": [{"id": "b", "text": "two", "status": "done"},
                                         {"id": "a", "text": "one", "status": "done"}]}}]


@pytest.fixture
def transform(monkeypatch):
    calls = []

    def run(output=None, **params):
        def model(prompt, system):
            calls.append((prompt, system))
            return copy.deepcopy(OUTPUT if output is None else output), None
        monkeypatch.setattr(oneshot_facade, "oneshot_json", model)
        return json.loads(AI._transform({"instruction": "번역", "items": copy.deepcopy(SOURCE),
                                         "contract": copy.deepcopy(CONTRACT), **params}))
    run.calls = calls
    return run


def test_valid_contract_prompts_and_checks_one_response(transform):
    result = transform()
    assert result["success"] and result["rows_out"] == 1 and len(transform.calls) == 1
    assert '"covers"' in transform.calls[0][1]
    assert result["items"][0]["input"] == SOURCE[0]["input"]


@pytest.mark.parametrize("change,detail", [
    (lambda lines: lines.pop(), "missing_ids"),
    (lambda lines: lines.append(dict(lines[0])), "duplicate_ids"),
    (lambda lines: lines[0].update(id="c"), "extra_ids"),
    (lambda lines: lines[0].pop("text"), "path"),
    (lambda lines: lines[0].update(text=None), "path"),
    (lambda lines: lines[0].update(status="unknown"), "allowed"),
])
def test_partial_or_invalid_response_stops_at_boundary(transform, change, detail):
    output = copy.deepcopy(OUTPUT)
    change(output[0]["result"]["lines"])
    result = transform(output)
    assert not result["success"] and result["error_type"] == "contract"
    assert result["phase"] == "output" and detail in result and len(transform.calls) == 1
    assert "items" not in result  # No success-shaped partial result for downstream consumers.


@pytest.mark.parametrize("output", [[], [{"result": OUTPUT[0]["result"]}],
                                    OUTPUT + OUTPUT, [{"_i": 7}]])
def test_contract_enforces_outer_row_mapping(transform, output):
    result = transform(output)
    assert result["error_type"] == "contract" and result["phase"] == "output"


def test_model_cannot_redefine_expected_ids(transform):
    output = copy.deepcopy(OUTPUT)
    output[0]["input"] = {"lines": [{"id": "b"}]}
    output[0]["result"]["lines"] = output[0]["result"]["lines"][:1]
    assert transform(output)["missing_ids"] == ["a"]


def test_stale_result_cannot_satisfy_missing_new_result(transform):
    original = [{**SOURCE[0], "result": OUTPUT[0]["result"]}]
    assert transform([{"_i": 0}], items=original)["error_type"] == "contract"


def test_hidden_output_column_conflict_is_found_before_model(transform):
    original = [{**SOURCE[0], "result": OUTPUT[0]["result"]}]
    result = transform(items=original, input_fields=["input"])
    assert result["error_type"] == "contract" and result["phase"] == "input"
    assert not transform.calls


@pytest.mark.parametrize("source", [[{"input": {"lines": [{"id": "a"}, {"id": "a"}]}}],
                                    [{"input": {"lines": [{"id": 1}]}}], [{"input": {}}]])
def test_bad_input_fails_before_any_call(transform, source):
    result = transform(items=source)
    assert result["error_type"] == "contract" and result["phase"] == "input"
    assert not transform.calls


@pytest.mark.parametrize("params", [
    {"contract": {}}, {"contract": {"covers": []}}, {"preserve_rows": False},
    {"input_fields": ["unused"]}, {"fields": ["input"]},
    {"contract": {"covers": [{"input": "input.lines", "output": "result.lines", "key": "id", "typo": 1}]}},
])
def test_invalid_declaration_on_empty_input_calls_no_model(transform, params):
    result = transform(items=[], **params)
    assert not result["success"] and not transform.calls


def test_other_task_and_different_output_key():
    contract = {"covers": [{"input": "invoice.positions", "output": "audit.entries", "key": "sku",
                            "output_key": "source_sku", "required": ["amount"]}]}
    source = [{"invoice": {"positions": [{"sku": "SKU-A"}]}}]
    validate_contract(contract)
    check_inputs(source, contract)
    check_outputs(source, [{"audit": {"entries": [{"source_sku": "SKU-A", "amount": 0}]}}], contract)
    with pytest.raises(ContractError):
        check_outputs(source, [{"audit": {"entries": [{"source_sku": "sku-a", "amount": 0}]}}], contract)


def test_multiple_relations_and_empty_sets():
    contract = {"covers": [{"input": "a", "output": "b", "key": "id"},
                            {"input": "c", "output": "d", "key": "id"}]}
    validate_contract(contract)
    check_outputs([{"a": [], "c": [{"id": "x"}]}], [{"b": [], "d": [{"id": "x"}]}], contract)
    with pytest.raises(ContractError):
        check_outputs([{"a": [], "c": [{"id": "x"}]}], [{"b": [], "d": []}], contract)


def test_inspection_sizes_match_actual_model_payload_and_do_not_edit(transform):
    source = SOURCE * 3
    before = copy.deepcopy(source)
    inspected = transform(items=source, input_fields=["input"], inspect="each")
    info = inspected["inspection"]
    assert inspected["items"] == source == before and not transform.calls
    assert info["planned_requests"] == 3 and info["model_calls"] == 0
    assert info["repeated_fields"][0]["path"] == "input.lines"
    assert info["repeated_fields"][0]["request_count"] == 3
    for row in source:
        assert transform(items=[row], input_fields=["input"])["success"]
    actual_payloads = [p.split("[items]\n", 1)[1].split("\n\n[지시]", 1)[0] for p, _ in transform.calls]
    assert info["total_payload_chars"] == sum(map(len, actual_payloads))
    assert info["total_payload_bytes"] == sum(len(p.encode("utf-8")) for p in actual_payloads)


def test_batch_empty_oversize_and_projection(transform):
    batch = transform(items=SOURCE * 2, inspect="batch")
    assert batch["inspection"]["planned_requests"] == 1
    assert batch["inspection"]["total_payload_chars"] == len(indexed_payload(SOURCE * 2))
    assert transform(items=[], inspect="each")["inspection"]["planned_requests"] == 0
    huge = [{**SOURCE[0], "raw": "가" * 61000}]
    failed = transform(items=huge, inspect="each")
    assert failed["error_type"] == "input_size" and failed["inspection"]["oversized_count"] == 1
    assert transform(items=huge, inspect="each", input_fields=["input"])["success"]
    assert not transform.calls


def test_bounded_repetition_scan_is_honest():
    deep = {"a": {"b": {"c": {"d": {"e": {"f": {"g": [1]}}}}}}}
    assert inspect_inputs([deep], mode="each", limit_chars=60000)["repetition_scan"] == "partial"


def test_static_contract_and_inspection_use_dictionary_metadata():
    params = json.dumps({"items": SOURCE, "instruction": "번역", "contract": CONTRACT, "inspect": "each"})
    result = typecheck_code("[table:ai]" + params)
    assert result["ok"], result
    assert result["preflight"]["declared_ai_visits_upper_bound"] == 0
    bad = json.dumps({"items": SOURCE, "instruction": "번역", "contract": CONTRACT, "fields": ["input"]})
    result = typecheck_code("[table:ai]" + bad)
    assert not result["ok"] and any("contract" in i["message"] for i in result["issues"])


def test_dynamic_contract_is_deferred_not_rejected():
    code = '$c=' + json.dumps(CONTRACT) + '\n[table:ai]{items:' + json.dumps(SOURCE)
    result = typecheck_code(code + ',instruction:"번역",contract:$c}')
    assert result["ok"], result


@pytest.mark.parametrize("path", ["a..b", "a.*", "a[0]", " a", ".a"])
def test_invalid_paths_rejected_by_shared_parser(path):
    with pytest.raises(ContractError):
        validate_contract({"covers": [{"input": path, "output": "result", "key": "id"}]})


def test_inspection_preserves_columns_and_still_rejects_wrong_currency():
    code = '[{source:"x"}] >> [table:ai]{instruction:"번역",inspect:"each",fields:["result"]}'
    assert typecheck_code(code + ' >> [table:select]{columns:["source"]}')["ok"]
    assert not typecheck_code(code + ' >> [table:select]{columns:["result"]}')["ok"]
    code = '[{source:"x"}] >> [table:brief]{instruction:"요약"} >> [table:ai]{instruction:"x",inspect:"each"}'
    assert not typecheck_code(code)["ok"]


def test_inspection_and_criteria_never_call_a_judge(monkeypatch, transform):
    import ibl_quality
    monkeypatch.setattr(ibl_quality, "_judge", lambda *a: pytest.fail("quality model called"))
    params = {"inspect": "each", "criteria": "정확한 번역", "instruction": "번역", "items": SOURCE}
    checked = typecheck_code("[table:ai]" + json.dumps(params))
    assert not checked["ok"]
    result = ibl_quality.apply_criteria("정확한 번역", transform(inspect="each"),
                                       {"params": params}, "table", "ai", ".", None,
                                       lambda *a: pytest.fail("inspection retried"))
    assert result["error_type"] == "input_inspection" and not transform.calls


def test_each_stops_before_remaining_requests_and_downstream_on_partial_response(tmp_path, monkeypatch):
    import ibl_engine
    import workflow_engine
    from ibl_parser import parse_with_vars

    calls = []
    def model(*args):
        calls.append(1)
        return [{"_i": 0, "result": {"lines": OUTPUT[0]["result"]["lines"][:1]}}], None
    monkeypatch.setattr(oneshot_facade, "oneshot_json", model)
    original = ibl_engine._execute_ibl_impl
    def leaf(ti, project, agent_id=None):
        if ti.get("_node") == "table" and ti.get("action") == "ai":
            return AI._transform(ti["params"])
        if ti.get("_node") == "self" and ti.get("action") == "script":
            pytest.fail("downstream consumer ran after incomplete response")
        return original(ti, project, agent_id)
    monkeypatch.setattr(ibl_engine, "_execute_ibl_impl", leaf)
    code = '[table:each]{items:' + json.dumps(SOURCE * 3) + ',limit:3,parallel:1,on_error:"stop"}{'
    code += '[table:ai]{items:[$it],instruction:"번역",contract:' + json.dumps(CONTRACT) + '}}'
    code += ' >> [self:script]{op:"run",id:"must_not_run"}'
    result = workflow_engine.execute_pipeline(parse_with_vars(code)[0], str(tmp_path))
    assert not result["success"], result
    assert len(calls) == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-v"]))
