"""[sense:search] days 보장과 배치의 상한·경고 보존 — 2026-10-07 웹 검색 반성(ep4327·4333) 수리 가드.

결함 1: days 는 공통 인자로 선언돼 있었지만 hn 만 읽고 gnews 는 묵살했다(days:2 에 2022년 기사).
수리 = 라우터 출구 `_apply_days` 가 date 열로 기간 밖 행을 제외하고 기간 밖·게시일 미상을 따로 센다.
날짜를 못 싣는 소스(ddg·naver webkr 등)는 실행 전에 거절한다.
결함 2: 공통 배치 `_batch_search` 가 내부 결과의 clamped·requested·message 를 버렸다.
수리 = 섹션별로 보존하고 상위에 clamped·message 를 모은다.
"""
import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import boot_paths  # noqa: F401,E402

_WEB = Path(__file__).resolve().parent.parent / "data/packages/installed/tools/web"


@pytest.fixture(scope="module")
def web():
    spec = importlib.util.spec_from_file_location("days_guard_web_handler", _WEB / "handler.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _iso(days_ago, tz=True):
    d = datetime.now(timezone.utc) - timedelta(days=days_ago)
    return d.isoformat() if tz else d.strftime("%Y-%m-%d")


def test_days_filter_drops_out_of_range_keeps_undated_and_recounts_sections(web):
    value = {"success": True, "count": 5, "sections": [{"query": "a", "count": 3}, {"query": "b", "count": 2}],
             "items": [{"query": "a", "date": _iso(0)}, {"query": "a", "date": _iso(30)}, {"query": "a"},
                       {"query": "b", "date": _iso(1, tz=False)}, {"query": "b", "date": "2022-05-01T00:00:00+00:00"}],
             "pool": [{"query": "a", "date": _iso(400)}]}
    out = web._apply_days({"days": 2}, value)
    assert out["count"] == 3 and len(out["items"]) == 3
    assert out["days_filter"]["kept"] == 2 and out["days_filter"]["out_of_range"] == 2 and out["days_filter"]["undated"] == 1
    assert [s["count"] for s in out["sections"]] == [2, 1]
    assert out["pool"] == []
    assert "미상 1건" in out["message"]


def test_days_zero_or_missing_is_a_no_op(web):
    value = {"success": True, "items": [{"date": "2022-01-01T00:00:00+00:00"}], "count": 1}
    assert web._apply_days({}, dict(value)) == value
    assert web._apply_days({"days": 0}, dict(value)) == value
    assert "days_filter" not in web._apply_days({"days": "x"}, dict(value))


def test_days_is_refused_before_execution_on_undated_sources(web):
    assert web._days_unsupported({"days": 2}, "ddg")
    assert web._days_unsupported({"days": 2, "type": "webkr"}, "naver")
    assert web._days_unsupported({"days": 2, "type": "뉴스"}, "naver") is None
    assert web._days_unsupported({"days": 2, "type": "blog"}, "naver") is None
    for src in ("gnews", "hn", "guardian"):
        assert web._days_unsupported({"days": 2}, src) is None
    assert web._days_unsupported({}, "ddg") is None


def test_search_router_refuses_days_on_ddg_without_calling_the_engine(web, monkeypatch):
    real = web.load_module

    def guarded(name):
        assert name != "tool_ddgs_search", "거절돼야 할 호출이 엔진까지 갔다"
        return real(name)
    monkeypatch.setattr(web, "load_module", guarded)
    r = json.loads(web.execute({"source": "ddg", "query": "x", "days": 2}, SimpleNamespace(tool_name="search", project_path=".")))
    assert r["success"] is False and "days" in r["error"] and r["items"] == []


def test_search_router_applies_days_to_gnews_rows(web, monkeypatch):
    rows = [{"title": "new", "date": _iso(0)}, {"title": "old", "date": "2022-05-01T00:00:00+00:00"}]
    monkeypatch.setattr(web, "_execute", lambda ti, ctx: web.format_json({"success": True, "items": list(rows), "count": 2}))
    monkeypatch.setattr(web, "load_module", lambda name: SimpleNamespace(query_notes=lambda a: []))
    r = json.loads(web.execute({"source": "gnews", "query": "x", "days": 2}, SimpleNamespace(tool_name="search", project_path=".")))
    assert [it["title"] for it in r["items"]] == ["new"]
    assert r["days_filter"] == {**r["days_filter"], "kept": 1, "out_of_range": 1, "undated": 0}


def test_batch_keeps_clamp_and_message_per_section_and_on_top(web, monkeypatch):
    def fake_execute(tool_input, context):
        q = tool_input["query"]
        if q == "꽉":
            return web.format_json({"success": True, "items": [{"title": "t"}], "clamped": True, "requested": 20,
                                    "message": "요청 20건 → 상한 10건으로 조정되어 검색했습니다."})
        return web.format_json({"success": True, "items": [{"title": "u"}]})
    monkeypatch.setattr(web, "execute", fake_execute)
    r = web._batch_search({"queries": ["꽉", "보통"], "limit": 20}, "ddgs_search", "ddg", ".")
    assert r["success"] is True and r["clamped"] is True and "상한 10건" in r["message"]
    by = {s["query"]: s for s in r["sections"]}
    assert by["꽉"]["clamped"] is True and by["꽉"]["requested"] == 20 and "message" in by["꽉"]
    assert "clamped" not in by["보통"] and by["보통"]["count"] == 1


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
