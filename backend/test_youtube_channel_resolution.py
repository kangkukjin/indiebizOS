"""YouTube @handle 해석과 IBL 경계 회귀 테스트."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import boot_paths  # noqa: F401

from common.pkg_utils import load_sibling
from ibl_parser import parse


ROOT = Path(__file__).resolve().parents[1]
YOUTUBE = ROOT / "data/packages/installed/tools/youtube"


def _module():
    return load_sibling(str(YOUTUBE / "handler.py"), "tool_youtube")


def test_at_handle_is_literal_inside_ibl_params():
    nodes = parse('[sense:video]{op: "channel", handle: "@zenandmotor"}')
    assert nodes[0]["params"]["handle"] == "@zenandmotor"
    assert nodes[0].get("target", "") == ""


def test_channel_reference_normalization():
    yt = _module()
    assert yt._normalize_channel_ref(handle="@zenandmotor") == {
        "handle": "@zenandmotor", "url": "https://www.youtube.com/@zenandmotor"}
    assert yt._normalize_channel_ref(handle="zenandmotor")["handle"] == "@zenandmotor"
    cid = "UC1234567890123456789012"
    assert yt._normalize_channel_ref(url=f"https://youtube.com/channel/{cid}")["channel_id"] == cid


def test_channel_resolution_falls_back_to_html_and_rss(monkeypatch):
    yt = _module()
    cid = "UC1234567890123456789012"
    monkeypatch.setattr(yt, "_extract_channel_with_ytdlp",
                        lambda url, limit: {"title": "", "items": []})
    monkeypatch.setattr(yt, "_extract_channel_from_html",
                        lambda url: {"channel_id": cid, "title": "채널", "items": []})
    monkeypatch.setattr(yt, "_fetch_channel_feed", lambda channel_id, name, limit: [{
        "video_id": "abcdefghijk", "title": "최신 영상", "channel": name}])

    result = yt.get_youtube_channel(handle="@zenandmotor", limit=3)
    assert result["success"] is True
    assert result["channel_id"] == cid
    assert result["uploads_playlist_id"] == f"UU{cid[2:]}"
    assert result["count"] == 1 and result["items"][0]["title"] == "최신 영상"


def test_channel_requires_a_reference():
    result = _module().get_youtube_channel()
    assert result["success"] is False
    assert "handle" in result["error"]


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
