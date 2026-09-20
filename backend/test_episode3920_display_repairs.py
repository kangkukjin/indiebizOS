"""문단 수집·묶음 검색의 모델 표시 경계. 원문·순위·오류는 그대로 보존한다."""
import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import boot_paths  # noqa: F401

from ibl_envelope import preview_envelope
from ibl_exec_each import _execute_table_each


ROOT = Path(__file__).resolve().parent.parent
TOOLS = ROOT / "data/packages/installed/tools"


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def dataops():
    return _load("episode3920_dataops", TOOLS / "data-ops/handler.py")


def _paragraphs(url, cap=16000):
    return {"success": True, "items": [
        {"url": url, "text": f"근거 {i}: " + "본문 " * 100} for i in range(12)],
        "_display": {"limit_rows": False, "max_chars": cap, "mirror_fields": ["text"]}}


def _collect(monkeypatch, results, parallel=1):
    import workflow_engine
    iterator = iter(results)
    monkeypatch.setattr(workflow_engine, "execute_pipeline", lambda *a, **kw: {
        "success": True, "final_result": json.dumps(next(iterator), ensure_ascii=False)})
    return _execute_table_each({"items": [{"url": f"https://test/{i}"} for i in range(len(results))],
                               "do": "[sense:crawl]{url:$it.url}", "keep": ["url"],
                               "on_error": "keep", "parallel": parallel}, ".")


@pytest.mark.parametrize("parallel", [1, 2])
def test_collected_paragraphs_survive_filter_select_and_model_delivery(monkeypatch, tmp_path, dataops, parallel):
    from model_result_view import project_result, read_result
    from supervision_store import TurnStore
    import model_result_view
    store = TurnStore(tmp_path / "evidence")
    monkeypatch.setattr(model_result_view, "evidence_store", lambda: store)
    out = _collect(monkeypatch, [_paragraphs("https://test/a"), _paragraphs("https://test/b")], parallel)
    filtered = dataops._op_filter(out, {"where": 'text contains "근거"'})
    selected = dataops._op_select(filtered, {"fields": ["text", "url"]})
    before = copy.deepcopy(selected)
    model = project_result({"success": True, "final_result": selected})
    # 종전에는 8문단만 보여 재조회를 강제했다. 24문단·약 1만 자는 한 번에 전달된다.
    assert len(model["final_result"]["items"]) == 24
    assert "_preview" not in model["final_result"]
    assert selected == before
    page = read_result({"id": model["result_ref"]["id"], "path": ["final_result", "items"]})
    assert json.loads(page["text"]) == selected["items"]


def test_collection_uses_one_budget_and_nested_collection_keeps_it(monkeypatch):
    first = _collect(monkeypatch, [_paragraphs("https://test/a", 2000), _paragraphs("https://test/b", 4000)])
    nested = _collect(monkeypatch, [first, _paragraphs("https://test/c", 3000)])
    assert nested["_display"] == {"limit_rows": False, "max_chars": 2000}
    before = copy.deepcopy(nested)
    model = preview_envelope(nested)
    assert sum(len(row["text"]) for row in model["items"]) <= 2000
    assert model["_preview"]["total"] == 36
    assert nested == before and len(nested["items"]) == 36


@pytest.mark.parametrize("other", [
    {"items": [{"n": 1}]}, {"message": "완료"},
    {"items": [{"text": "표"}], "_display": {"limit_rows": True, "max_chars": 2000}},
])
def test_mixed_collection_does_not_claim_all_rows_are_paragraphs(monkeypatch, other):
    out = _collect(monkeypatch, [_paragraphs("https://test/a"), other])
    assert "_display" not in out


def test_partial_failure_remains_visible_with_paragraph_policy(monkeypatch):
    import workflow_engine
    results = iter([
        {"success": False, "error": "접근 제한"},
        {"success": True, "final_result": _paragraphs("https://test/b")},
    ])
    monkeypatch.setattr(workflow_engine, "execute_pipeline", lambda *a, **kw: next(results))
    out = _execute_table_each({"items": [{"url": "a"}, {"url": "b"}],
                               "do": "[sense:crawl]{url:$it.url}", "on_error": "keep",
                               "parallel": 1}, ".")
    model = preview_envelope(out)
    assert model["error_count"] == 1 and model["errors"][0]["_error"] == "접근 제한"
    assert model["items"][0]["_error"] == "접근 제한"
    assert model["_display"]["limit_rows"] is False


def _search_items(groups=4, count=5, chars=800):
    return [{"query": f"검색 {q}", "title": f"결과 {q}-{i}", "summary": "가" * chars,
             "url": f"https://test/{q}/{i}"} for q in range(groups) for i in range(count)]


def test_batch_preview_covers_queries_without_reordering_source(dataops):
    raw = {"items": _search_items(), "_display": {"group_by": "query"}}
    selected = dataops._op_select(raw, {"fields": ["title", "url", "summary", "query"]})
    before = copy.deepcopy(selected)
    model = preview_envelope(selected)
    assert [row["query"] for row in model["items"]] == [f"검색 {q}" for q in range(4)] * 2
    assert model["_preview"]["indices"] == [1, 6, 11, 16, 2, 7, 12, 17]
    assert model["_preview"]["groups_total"] == model["_preview"]["groups_shown"] == 4
    assert selected == before
    assert preview_envelope(selected, verbose=True) == before
    # 묶음 열을 지운 명시적 투영에서는 더 이상 묶음을 추측하지 않는다.
    without_query = dataops._op_select(raw, {"fields": ["title", "summary"]})
    assert "selection" not in preview_envelope(without_query)["_preview"]


def test_group_preview_shares_text_budget_and_reports_unshown_groups():
    raw = {"items": _search_items(groups=10, count=2, chars=15000),
           "_display": {"group_by": "query"}}
    model = preview_envelope(raw)
    assert len(model["items"]) == 8
    assert all(row["summary"] for row in model["items"])
    assert sum(len(r["title"]) + len(r["summary"]) for r in model["items"]) <= 12000
    assert model["_preview"]["groups_shown"] == 8
    assert model["_preview"]["groups_total"] == 10


def test_parallel_union_keeps_display_policy_and_original_order(dataops):
    sources = [{"success": True, "items": _search_items(groups=2), "_display": {"group_by": "query"}},
               {"success": True, "items": _search_items(groups=3), "_display": {"group_by": "query"}}]
    union = dataops._op_union(sources, {})
    assert union["items"] == sources[0]["items"] + sources[1]["items"]
    selected = dataops._op_select(dataops._op_dedup(union, {"by": "url"}),
                                  {"fields": ["query", "title", "summary", "url"]})
    model = preview_envelope(selected)
    assert {row["query"] for row in model["items"]} == {"검색 0", "검색 1", "검색 2"}
    paragraphs = dataops._op_union([_paragraphs("a", 2000), _paragraphs("b", 4000)], {})
    assert paragraphs["_display"] == {"limit_rows": False, "max_chars": 2000}


def test_group_preview_honors_shared_value_semantics():
    raw = {"items": [{"category": value, "text": "가" * 800} for value in
                     [1, "1", 1, "1", 1, "1", 1, "1", 2, "2"]],
           "_display": {"group_by": "category"}}
    model = preview_envelope(raw)
    # groupby의 계약은 숫자와 숫자 문자열을 구분한다.
    assert model["_preview"]["groups_total"] == 4
    assert [r["category"] for r in model["items"][:4]] == [1, "1", 2, "2"]


@pytest.mark.parametrize("source", ["ddg", "naver", "gnews", "hn"])
def test_search_producers_declare_group_preview_and_keep_errors(monkeypatch, source):
    web = _load("episode3920_web", TOOLS / "web/handler.py")
    sections = [{"items": _search_items(groups=1), "error": "일부 실패"}, {"items": []}]
    # 실제 네트워크 대신 배치 수신만 대역화한다. 검색 소스별 조립은 실코드다.
    monkeypatch.setattr(web, "_fetch_sections", lambda jobs: copy.deepcopy(sections))
    if source in ("ddg", "naver"):
        out = web._batch_search({"queries": ["가", "나"]}, "unused", source, ".")
    else:
        out = json.loads(web.execute({"queries": ["가", "나"]}, SimpleNamespace(
            tool_name="search_gnews" if source == "gnews" else "search_hn", project_path=".")))
    assert out["_display"] == {"group_by": "query"}
    assert not out["success"] and out["errors"][0]["error"] == "일부 실패"
    assert out["sections"][1]["count"] == 0


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__, "-q", *sys.argv[1:]]))
