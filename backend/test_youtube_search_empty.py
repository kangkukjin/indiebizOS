"""검색 0건은 유효한 빈 통화이며 공급자·형식 오류와 구분한다."""
import sys
from pathlib import Path
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest
from common.pkg_utils import load_sibling

ROOT = Path(__file__).resolve().parents[1]
HANDLER = str(ROOT / "data/packages/installed/tools/youtube/handler.py")


@pytest.fixture
def search(monkeypatch):
    yt = load_sibling(HANDLER, "tool_youtube")
    response = {"entries": []}
    class Downloader:
        def __init__(self, options):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def extract_info(self, *args, **kwargs):
            if isinstance(response, Exception):
                raise response
            return response
    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=Downloader))
    def run(value, count=12):
        nonlocal response
        response = value
        return yt.search_youtube("a search", count)
    return run


@pytest.mark.parametrize("entries", [[], [{"id": "UCabcdefghijklmnopqrstuv"}]])
def test_empty_is_successful_and_keeps_clamp_metadata(search, entries):
    out = search({"entries": entries}, 100)
    assert out["success"] and out["status"] == "empty"
    assert out["results"] == [] and out["count"] == 0
    assert out["clamped"] and out["requested"] == 100


@pytest.mark.parametrize("value", [None, {}, {"entries": None}, {"entries": [None]}, RuntimeError("timeout")])
def test_errors_are_not_empty_success(search, value):
    out = search(value)
    assert not out["success"] and out["error"]


def test_lazy_provider_entries_are_materialized(search):
    out = search({"entries": iter([{"id": "abcdefghijk", "title": "fixture"}])})
    assert out["success"] and out["count"] == 1


def test_batch_empty_section_survives_and_network_failure_stays_failure():
    handler = load_sibling(HANDLER, "handler")
    def response(query, count):
        if query == "bad":
            return {"success": False, "error": "timeout"}
        return {"success": True, "results": [], "count": 0, "status": "empty"}
    yt = SimpleNamespace(search_youtube=response)
    out = handler._direct_search({"queries": ["zero", "empty"]}, yt)
    assert out["success"] and out["items"] == []
    assert all(s["status"] == "empty" and s["success"] for s in out["sections"])
    out = handler._direct_search({"queries": ["zero", "bad"]}, yt)
    assert not out["success"] and len(out["errors"]) == 1
    assert out["sections"][0]["status"] == "empty"


@pytest.mark.parametrize("provided", [False, True])
def test_video_info_preserves_publisher_metrics_in_single_request(monkeypatch, provided):
    handler = load_sibling(HANDLER, "handler")
    transcript = load_sibling(HANDLER, "tool_transcript")
    info = {"title": "Fixture", "duration": 120, "uploader": "Publisher", "upload_date": "20260924"}
    fields = {"view_count": 0, "like_count": 120, "comment_count": 9,
              "channel": "Named Channel", "channel_id": "UCfixture", "channel_url": "https://www.youtube.com/@fixture",
              "uploader_id": "@fixture", "uploader_url": "https://www.youtube.com/@fixture",
              "channel_follower_count": 4000, "channel_is_verified": False, "description": "Self-reported expertise"}
    if provided:
        info.update(fields)
    calls = []
    class Downloader:
        def __init__(self, options):
            pass
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def extract_info(self, url, download):
            calls.append((url, download))
            return info
    monkeypatch.setitem(sys.modules, "yt_dlp", SimpleNamespace(YoutubeDL=Downloader))
    result = handler._op_info({"video_id": "abcdefghijk"}, transcript)
    assert result["success"] and len(calls) == 1 and calls[0][1] is False
    row = result["items"][0]
    assert row["upload_date"] == "2026-09-24"
    for key, value in fields.items():
        assert row[key] == (value if provided else None)
    from datetime import datetime
    assert datetime.fromisoformat(row["observed_at"]).utcoffset().total_seconds() == 0


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, *sys.argv[1:]]))
