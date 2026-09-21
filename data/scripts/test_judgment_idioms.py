"""판정 관용구의 입력 분할·원문 보존 계약 회귀."""
import importlib.util
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location("judgment_idioms", Path(__file__).with_name("judgment_idioms.py"))
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


def prepare(source, mode="body", limit=20, context=0):
    return helper.prepare(dict(source=source, mode=mode, question="질문", limit=limit, context=context))


def answers(prepared, values=None):
    return {"items": [dict(r, judgment_result_value=(values or {}).get(r["rid"], True),
                          judgment_result_status="unknown" if (values or {}).get(r["rid"], True) is None else "decided")
                      for b in prepared["items"] for r in b["items"]]}


def test_unknown_oversize_context_and_failures():
    source = {"items": [{"text": "앞", "url": "a"}, {"text": "관련", "url": "a"},
                        {"text": "다른 출처", "url": "b"}, {"_error": "접근 실패", "url": "a"},
                        {"text": "x" * 61000, "url": "a"}], "truncated": True}
    p = prepare(source, context=1)
    r = helper.select(dict(source=source, mode="body", prepared=p,
                           judged=answers(p, {0: False, 1: None, 2: False}),
                           limit=10, context=1))
    assert r["items"] == [source["items"][i] for i in (0, 1, 3, 4)]
    assert r["truncated"] and r["selection_info"]["unknown"] == 1
    assert r["selection_info"]["oversized"] == 1
    assert r["selection_info"]["source_error_rows"] == 1


def test_batches_and_zero_no_api():
    source = [{"text": str(i), "url": "a"} for i in range(205)]
    p = prepare(source)
    assert sum(len(b["items"]) for b in p["items"]) == 205
    assert all(len(b["items"]) <= 100 and helper.payload_size(b["items"], p["instruction"]) <= 48000 for b in p["items"])
    assert prepare(source, limit=0)["items"] == []
    assert prepare([])["items"] == []


def test_missing_or_failed_judgments_are_not_unknown():
    source = [{"text": "관련", "url": "a"}]
    p = prepare(source)
    for invalid in ({"items": []}, {"items": [], "error_count": 1},
                    {"success": False, "error": "timeout"}):
        with pytest.raises(ValueError):
            helper.select(dict(source=source, mode="body", prepared=p, judged=invalid, limit=1, context=0))


def test_search_preserves_source_errors_without_recrawling():
    source = [{"url": "a", "title": "제목"}, {"url": "bad", "_error": "upstream"}]
    p = prepare(source, mode="search")
    r = helper.select(dict(source=source, mode="search", prepared=p, judged=answers(p), limit=1))
    assert r["items"] == source[:1]
    out = helper.finish(dict(selection=r, result={"items": [{"url": "a", "_error": "crawl"}], "error_count": 1}))
    assert out["items"][-1] == source[-1]
    assert out["error_count"] == 1
    assert out["selection_info"]["source_error_rows"] == 1


def test_limits_missing_urls_and_source_boundaries():
    with pytest.raises(ValueError):
        prepare([{"title": "missing URL"}], mode="search")
    source = [{"text": "A"}, {"text": "B"}, {"text": "C", "url": "c"}]
    assert helper.neighbors(source, 0, 10) == [0]
    p = prepare(source)
    r = helper.select(dict(source=source, mode="body", prepared=p, judged=answers(p), limit=1))
    assert r["items"] == source[:1] and r["truncated"]
    assert r["selection_info"]["omitted_by_limit"] == 2


def test_explicit_envelopes_preserve_markers_and_empty_currency():
    origin = {"items": [], "truncated": True, "error_count": 2}
    p = prepare(origin)
    r = helper.select(dict(mode="body", prepared=p["plan"], judged={"items": []}, limit=0))
    assert r["selection"]["truncated"] and r["selection"]["error_count"] == 2
    out = helper.finish(dict(selection=r["selection"], result={"items": [], "error_count": 0}))
    assert out["items"] == []
    assert out["source_markers"]["error_count"] == 2
    assert out["selection_info"]["api_batches"] == 0
