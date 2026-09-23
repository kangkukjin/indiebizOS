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


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, *sys.argv[1:]]))
