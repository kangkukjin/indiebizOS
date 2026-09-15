"""11~20위 중 each를 제외한 어휘 감사의 12개 결함 회귀. 외부 I/O는 대역으로 격리."""
import importlib.util
import json
import os
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest
from tool_context import ToolContext

PKG = Path(__file__).resolve().parents[1] / "data/packages/installed/tools"


def load(package, name="handler"):
    spec = importlib.util.spec_from_file_location(
        f"rank_repairs_{package.replace('-', '_')}_{name}", PKG / package / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def ops():
    return load("data-ops")


@pytest.mark.parametrize("rows", [[{"v": 2}, "lost", {"v": 1}], [3, 1, 2]])
def test_sort_refuses_loss_of_nonobject_rows(ops, rows):
    out = ops.execute({"items": rows, "by": "v"}, SimpleNamespace(tool_name="data_sort"))
    assert out["success"] is False
    assert "객체" in out["error"]
    assert len(rows) == 3


@pytest.mark.parametrize("by,agg", [("count", None), ("city", {"city": ["sum", "v"]})])
def test_groupby_refuses_overwriting_group_keys(ops, by, agg):
    out = ops._op_groupby({"items": [{by: "A", "v": 7}]}, {"by": by, "agg": agg})
    assert out["success"] is False and "이름" in out["error"]
    valid = ops._op_groupby({"items": [{by: "A", "v": 7}]},
                           {"by": by, "agg": {"건수": ["count"]}})
    assert valid["items"] == [{by: "A", "건수": 1}]


def test_union_preserves_original_branch_numbers(ops):
    out = ops._op_union([
        {"success": False, "error": "dead"},
        {"success": True, "path": "two.txt", "warning": "branch two warning"},
        {"items": [{"v": 3}]}], {})
    assert out["effect_rows"] == [2]
    assert out["branches_skipped"][0]["branch"] == 1
    assert "분기 1" in out["warning"]


@pytest.mark.parametrize("op", ["union", "merge"])
def test_partial_failure_warning_keeps_original_branch_number(ops, op):
    out = getattr(ops, "_op_" + op)([
        {"success": False, "error": "dead"},
        {"success": False, "error": "partial", "items": []},
        {"items": [{"v": 3}]}], {})
    assert "분기 2" in out["warning"]


def test_merge_error_keeps_original_branch_number(ops):
    out = ops._op_merge([{"success": False, "error": "dead"},
                         {"table": {"columns": ["v"], "rows": [[1]]}}], {})
    assert out["success"] is False and "분기 2" in out["error"]


@pytest.fixture
def indexed_files(tmp_path, monkeypatch):
    import file_index
    large, small = tmp_path / "old_large.png", tmp_path / "new_small.png"
    large.write_bytes(b"a" * 100)
    small.write_bytes(b"a")
    os.utime(large, (1000000000, 1000000000))
    os.utime(small, (1700000000, 1700000000))

    def meta(path, facets):
        path = Path(path)
        return {"path": str(path), "name": path.name, "size": path.stat().st_size,
                "mtime": path.stat().st_mtime, "kind": "image", "ext": "png"}

    monkeypatch.setattr(file_index, "_item_from_meta", meta)
    monkeypatch.setattr(file_index, "_IS_MAC", True)
    monkeypatch.setattr(file_index, "detect_body", lambda: {"profile": "pc"})
    monkeypatch.setattr(file_index, "_run_mdfind", lambda *a: [])
    return file_index, large, small


@pytest.mark.parametrize("filters", [{"q": "not-present"}, {"ext": "pdf"},
                                     {"min_size": 101}, {"kind": "video"}])
def test_empty_index_fallback_preserves_each_filter(indexed_files, tmp_path, filters):
    fi, _, _ = indexed_files
    out = fi.query(path=str(tmp_path), **filters)
    assert out["success"] and out["items"] == []


@pytest.mark.parametrize("filters", [{"start": "2020-01-01"}, {"end": "2020-01-31"},
                                     {"has_gps": True}])
def test_fallback_does_not_invent_unavailable_metadata(indexed_files, tmp_path, filters):
    fi, _, _ = indexed_files
    out = fi.query(path=str(tmp_path), **filters)
    assert out["success"] is False
    assert "검증" in out["error"]


@pytest.mark.parametrize("engine", ["spotlight", "fallback", "walk"])
def test_size_sort_before_limit(indexed_files, tmp_path, monkeypatch, engine):
    fi, large, small = indexed_files
    if engine == "spotlight":
        monkeypatch.setattr(fi, "_run_mdfind", lambda *a: [str(small), str(large)])
    elif engine == "walk":
        monkeypatch.setattr(fi, "_IS_MAC", False)
    out = fi.query(path=str(tmp_path), sort="size", limit=1)
    assert out["items"][0]["path"] == str(large)
    assert out["total"] == 2 and out["truncated"]


def test_index_failure_reported_with_filtered_fallback(indexed_files, tmp_path, monkeypatch):
    fi, _, _ = indexed_files
    def fail(*a):
        raise RuntimeError("index unavailable")
    monkeypatch.setattr(fi, "_run_mdfind", fail)
    out = fi.query(path=str(tmp_path), q="not-present")
    assert out["items"] == [] and out["index_error"] == "index unavailable"


def test_metadata_uses_project_root_and_common_file_fields(indexed_files, tmp_path):
    _, large, _ = indexed_files
    fs = load("system_essentials")
    out = json.loads(fs.execute({"path": ".", "sort": "size", "limit": 1},
                               ToolContext(str(tmp_path), "glob_files", agent_id="test")))
    row = out["items"][0]
    assert row["path"] == str(large)
    assert row["name"] == large.name and row["is_dir"] is False
    assert row["dir"] == str(tmp_path) and row["size"] == 100
    assert out["total"] == 2 and out["truncated"]


def test_list_and_find_share_unicode_matching(tmp_path):
    fs = load("system_essentials")
    name = unicodedata.normalize("NFD", "보고서.TXT")
    path = tmp_path / name
    path.write_text("sample")
    for tool in ("list_directory", "glob_files"):
        out = json.loads(fs.execute({"path": str(tmp_path), "pattern": "*보고서*.txt"},
                                    ToolContext(str(tmp_path), tool, agent_id="test")))
        assert len(out["items"]) == 1
        assert out["items"][0]["path"] == str(path)


@pytest.mark.parametrize("ticker", ["^KS11", "AAPL"])
def test_history_routes_absolute_dates_through_index_and_402(ticker, monkeypatch):
    investment = load("investment")
    captured = []
    def yahoo(**kw):
        captured.append(kw)
        return {"success": True, "data": {"prices": [{"date": "2020-01-03", "close": 10}]}}
    modules = {"tool_yfinance": SimpleNamespace(get_stock_price=yahoo),
               "tool_fmp": SimpleNamespace(get_stock_price=lambda **kw: {"success": False, "error": "HTTP 402"})}
    monkeypatch.setattr(investment, "load_module", modules.__getitem__)
    out = investment.execute({"op": "history", "ticker": ticker,
                              "start_date": "2020-01-01", "end_date": "2020-01-31"},
                             SimpleNamespace(tool_name="stock_op"))
    assert out["success"]
    assert captured[0]["start_date"] == "2020-01-01"
    assert captured[0]["end_date"] == "2020-01-31"


def test_yahoo_absolute_dates_use_inclusive_end(monkeypatch):
    yf = load("investment", "tool_yfinance")
    calls = []
    def get(url, **kw):
        calls.append(kw["params"])
        return SimpleNamespace(json=lambda: {"chart": {"result": []}})
    monkeypatch.setattr(yf.requests, "get", get)
    yf._yahoo_chart("AAPL", start_date="2020-01-01", end_date="2020-01-31")
    assert "range" not in calls[0]
    assert calls[0]["period1"] == int(datetime(2020, 1, 1, tzinfo=timezone.utc).timestamp())
    assert calls[0]["period2"] == int(datetime(2020, 2, 1, tzinfo=timezone.utc).timestamp())
    yf._yahoo_chart("AAPL", period="5d")
    assert calls[1] == {"range": "5d", "interval": "1d"}


def test_naver_index_dates_are_forwarded(monkeypatch):
    yf = load("investment", "tool_yfinance")
    calls = []
    def get(url, **kw):
        calls.append(kw["params"])
        return SimpleNamespace(status_code=200, text='["20200103", 1, 2, 1, 2, 5]')
    monkeypatch.setattr(yf.requests, "get", get)
    assert yf._naver_index_daily("^KS11", start_date="2020-01-01", end_date="2020-01-31")
    assert calls[0]["startTime"] == "20200101" and calls[0]["endTime"] == "20200131"


def test_history_filters_before_sampling_and_does_not_overlay_today(monkeypatch):
    yf = load("investment", "tool_yfinance")
    monkeypatch.setattr(yf, "_naver_index_daily", lambda *a, **kw: [])
    bars = [{"date": d, "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}
            for d in ("2019-12-31", "2020-01-02", "2020-01-03", "2026-09-15")]
    monkeypatch.setattr(yf, "_yahoo_chart", lambda *a, **kw: bars)
    monkeypatch.setattr(yf, "_naver_realtime", lambda *a: pytest.fail("historical quote must not fetch today"))
    out = yf.get_stock_price("AAPL", start_date="2020-01-01", end_date="2020-01-31")
    assert out["success"], out
    assert [r["date"] for r in out["data"]["prices"]] == ["2020-01-02", "2020-01-03"]
    assert out["data"]["as_of"] == "2020-01-03"


def test_summarize_accepts_video_id(monkeypatch):
    handler = load("youtube")
    monkeypatch.setattr(handler, "load_tool_youtube", lambda: SimpleNamespace(
        summarize_youtube=lambda **kw: {"success": True, **kw}))
    out = handler.execute({"op": "summarize", "video_id": "jNQXAC9IVRw"},
                          SimpleNamespace(tool_name="video_op"))
    assert out["success"] and "jNQXAC9IVRw" in out["url"]


def test_long_summary_reads_last_chunk_and_merges_in_order():
    transcript = load("youtube", "tool_transcript")
    calls = []
    def model(prompt):
        calls.append(prompt)
        return f"구간 요약 {len(calls)}"
    content, coverage = transcript._summarize_complete_transcript(
        "a" * 50000 + "TAIL_IMPORTANT_CONCLUSION", "final", model)
    assert "TAIL_IMPORTANT_CONCLUSION" in calls[1]
    assert calls[2].index("구간 요약 1") < calls[2].index("구간 요약 2")
    assert coverage == {"transcript_chars": 50025, "transcript_chunks": 2, "summary_calls": 3}
    assert content == "구간 요약 3"


def test_summary_reduces_all_chunks_without_unbounded_prompt():
    transcript = load("youtube", "tool_transcript")
    calls = []
    def model(prompt):
        calls.append(prompt)
        return "summary " * 2000
    _, coverage = transcript._summarize_complete_transcript("a" * 300000, "final", model)
    assert coverage["transcript_chunks"] == 6
    assert coverage["summary_calls"] > 7
    assert max(map(len, calls)) < 51000


@pytest.mark.parametrize("bad", ["", "x" * 20001])
def test_summary_refuses_failed_or_oversized_intermediate(bad):
    transcript = load("youtube", "tool_transcript")
    with pytest.raises(RuntimeError):
        transcript._summarize_complete_transcript("a" * 50001, "final", lambda p: bad)


def test_music_skip_failure_preserves_unattempted_queue_and_can_continue(monkeypatch):
    yt = load("youtube", "tool_youtube")
    yt._player_video_id = "current"
    yt._player_process = None
    yt._player_queue = [{"video_id": v, "title": v, "channel": "c", "duration": 20}
                        for v in ("bad", "good")]
    monkeypatch.setattr(yt, "_get_audio_url", lambda v: None)
    out = yt.skip_youtube()
    assert out["success"] is False and out["failed_video_id"] == "bad"
    assert out["queue_remaining"] == 1 and yt._player_queue[0]["video_id"] == "good"
    monkeypatch.setattr(yt, "_get_audio_url", lambda v: "fake-audio")
    monkeypatch.setattr(yt, "_start_ffplay", lambda *a: None)
    monkeypatch.setattr(yt.threading, "Thread", lambda **kw: SimpleNamespace(start=lambda: None))
    out = yt.skip_youtube()
    assert out["success"] and out["now_playing"]["video_id"] == "good"


def test_shared_photo_date_mode_keeps_metadata_cost_bounded(indexed_files, tmp_path, monkeypatch):
    fi, large, small = indexed_files
    monkeypatch.setattr(fi, "_run_mdfind", lambda *a: [str(large), str(small)])
    calls = []
    original = fi._item_from_meta
    def meta(path, facets):
        calls.append(path)
        return original(path, facets)
    monkeypatch.setattr(fi, "_item_from_meta", meta)
    out = fi.query(path=str(tmp_path), sort="date", limit=1)
    assert calls == [str(small)]
    assert "전체 촬영일 순위가 아닙니다" in out["warning"]


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
