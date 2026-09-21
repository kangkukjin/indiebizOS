"""Episode 3942: 검사만 초록이던 잘못된 필터를 실행 파서로 거절한다."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import boot_paths  # noqa: E402,F401
from ibl_typecheck import typecheck_code  # noqa: E402


@pytest.fixture(scope="module")
def handler():
    path = Path(__file__).resolve().parents[1] / "data/packages/installed/tools/data-ops/handler.py"
    spec = importlib.util.spec_from_file_location("_filter_precheck_handler", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def code_for(where, key="where"):
    return ('[table:filter]{items:[{title:"모닝 브리프",price:3}], '
            + key + ':' + json.dumps(where, ensure_ascii=False) + '}')


@pytest.mark.parametrize("where", [
    "title ~= '모닝 브리프|자사주 매입|30조 배당'",
    "title === x", "price <> 3", "price >=",
    {"field": "title", "op": "~=", "value": "뉴스"},
    {"field": "title", "op": "matches", "value": "["},
    "title matches [",
    ["price < 0", {"field": "title", "op": "matches", "value": "["}],
    "price > 0 or title matches [",
])
def test_invalid_condition_rejected_in_check_and_runtime_even_without_rows(handler, where):
    checked = typecheck_code(code_for(where))
    assert not checked["ok"] and not checked.get("abstained"), checked
    issue = next(i for i in checked["issues"] if i.get("expected") == "row condition")
    for rows in ([], [{"title": "모닝 브리프", "price": 3}]):
        for extra in ({}, {"context": {"before": 1}}):
            result = handler._op_filter({"items": rows}, {"where": where, **extra})
            assert result["success"] is False, result
            assert issue["message"].removeprefix("조건 오류 — ") in result["error"]


@pytest.mark.parametrize("where", [
    'title matches "모닝 브리프|자사주 매입"',
    {"field": "title", "op": "matches", "value": "브리프$"},
    'title matches "(?=모닝)모닝"',
    'title contains "a=b"',
    'title == "a=b"',
    'price >= 3 and price < 5',
    "브리프",  # 검색어는 열 이름이 아니다.
    {"col": "title", "op": "contains", "value": "모닝"},
])
def test_valid_forms_keep_check_execution_parity(handler, where):
    checked = typecheck_code(code_for(where))
    assert checked["ok"] and not checked["issues"] and not checked.get("abstained"), checked
    rows = [{"title": "모닝 브리프", "price": 3}, {"title": "a=b", "price": 9}]
    result = handler._op_filter({"items": rows}, {"where": where})
    assert result.get("success") is not False and len(result["items"]) == 1, result


def test_alias_and_all_boolean_fields_are_checked():
    assert not typecheck_code(code_for("title ~= 뉴스", key="condition"))["ok"]
    assert not typecheck_code(code_for("price > 0 or missing == 1"))["ok"]
    assert not typecheck_code(code_for({"column": "missing", "op": "eq", "value": 1}))["ok"]
    code = code_for("브리프")[:-1] + ',condition:"title ~= 뉴스"}'
    assert typecheck_code(code)["ok"]  # where가 있으면 별칭은 실행에서도 무시한다.


@pytest.mark.parametrize("where", ["반가워요!", "안녕~"])
def test_search_punctuation_is_not_an_operator(handler, where):
    assert typecheck_code(code_for(where))["ok"]
    result = handler._op_filter({"items": [{"title": where}]}, {"where": where})
    assert result.get("success") is not False and len(result["items"]) == 1


def test_dynamic_condition_defers_until_binding_and_regex_anchor_is_not_dynamic():
    from ibl_typecheck import typecheck
    step = {"node": "table", "action": "filter", "params": {
        "items": [{"title": "x"}], "where": "{{_step_0_result}}"}}
    assert typecheck([step])["ok"]
    assert not typecheck_code(code_for({"field": "title", "op": "matches", "value": "[$"}))["ok"]


def test_function_body_condition_errors_are_not_lost():
    code = '[def:검사]{' + code_for("title ~= 뉴스") + '}\n[fn:검사]{}'
    checked = typecheck_code(code)
    assert not checked["ok"] and any(i.get("expected") == "row condition"
                                     for i in checked["issues"]), checked


@pytest.mark.parametrize("check_only", [True, False])
def test_unified_rejects_episode_expression_before_any_search(monkeypatch, tmp_path, check_only):
    import ibl_engine
    import system_tools_ibl as unified
    import thread_context

    calls = []
    monkeypatch.setattr(ibl_engine, "execute_ibl", lambda *a, **kw: calls.append(a))
    monkeypatch.setattr(unified, "_ibl_debug_log", lambda *a: None)
    snapshot = thread_context.snapshot()
    thread_context.clear_all_context()
    try:
        code = ('[sense:search]{query:"한국 증시"} >> '
                '[table:filter]{where:"title ~= \'모닝 브리프|자사주 매입|30조 배당\'"}')
        result = json.loads(unified._execute_ibl_unified_impl(
            {"code": code, "check": check_only}, str(tmp_path)))
        assert (result.get("ok") is False or result.get("success") is False), result
        assert "matches" in str(result) and "~=" in str(result)
        assert calls == []
    finally:
        thread_context.restore(snapshot)


if __name__ == "__main__":
    sys.exit(pytest.main([__file__] + sys.argv[1:]))
