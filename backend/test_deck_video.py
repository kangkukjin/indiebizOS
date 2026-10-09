"""Deck render completion across sync results, stored status and task receipts."""
import importlib.util
import json
import sys
from pathlib import Path

import pytest
import boot_paths  # noqa: F401
from common.expression_ir import Fault
from ibl_v2_adapters import decode_envelope

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "data/packages/installed/tools/lecture_workspace"
sys.path.insert(0, str(PACKAGE))
import deck_video  # noqa: E402
import task_receipts as T  # noqa: E402

LEGACY = {"protocol": "legacy-envelope", "value_path": ""}


@pytest.fixture
def render_fixture(tmp_path, monkeypatch):
    slides = tmp_path / "slides"
    slides.mkdir()
    for sid in ("s001", "s002"):
        (slides / f"{sid}.png").write_bytes(b"fixture pixels")
    deck = {"slide_order": ["s001", "s002"], "slides": {
        sid: {"png_file": f"slides/{sid}.png", "speaker_note": ""}
        for sid in ("s001", "s002")}}
    monkeypatch.setattr(deck_video.lecture_store, "read_deck", lambda _: deck)
    monkeypatch.setattr(deck_video.lecture_store, "lecture_dir", lambda _: tmp_path)
    monkeypatch.setattr(deck_video.lecture_store, "lecture_exists", lambda _: True)

    class Renderer:
        def create_html_video(self, args, directory):
            output = Path(directory) / args["output_filename"]
            output.write_bytes(b"partial render is retained")
            return {"success": True, "path": str(output)}

    monkeypatch.setattr(deck_video, "_load_media_handler", Renderer)
    return tmp_path, deck


def handler():
    spec = importlib.util.spec_from_file_location("deck_video_test_handler", PACKAGE / "handler.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def assert_partial(raw, result_key=None):
    with pytest.raises(Fault) as info:
        decode_envelope(raw, LEGACY)
    assert info.value.code == "PARTIAL_SOURCE"
    partial = info.value.partial
    result = partial[result_key] if result_key else partial
    assert result["skipped"] == ["s002"]
    assert result["slides"] == 1
    assert Path(result["output"]).read_bytes() == b"partial render is retained"


def test_sync_missing_png_preserves_partial_artifact_and_propagates_incompleteness(render_fixture):
    directory, _ = render_fixture
    (directory / "slides/s002.png").unlink()
    raw = json.loads(handler()._deck_video({"lecture_id": "fixture", "wait": True}))
    assert raw["source_complete"] is False
    assert raw["expected_scenes"] == 2
    assert raw["rendered_slide_ids"] == ["s001"]
    assert raw["errors"][0]["slide_id"] == "s002"
    assert_partial(raw)
    # Persisted status/check must not re-render, or lose the partial marker.
    assert_partial(json.loads(handler()._deck_video({"lecture_id": "fixture", "check": True})))


@pytest.mark.parametrize("op", ["status", "wait", "cancel"])
def test_background_partial_result_reaches_task_envelope(render_fixture, monkeypatch, op):
    directory, _ = render_fixture
    (directory / "slides/s002.png").unlink()
    result = deck_video.build("fixture", {})
    deck_video.write_state("fixture", {"status": "done", **result})
    monkeypatch.setitem(T._STATUS, "lecture_video", deck_video.task_status)
    ref = T.ref("lecture_video", "fixture")
    raw = T.wait(ref, timeout=0) if op == "wait" else getattr(T, op)(ref)
    assert raw["terminal"] is True and raw["state"] == "succeeded"
    assert raw["source_complete"] is False
    assert_partial(raw, "result")


def test_legacy_done_with_skipped_png_is_also_partial(render_fixture):
    directory, _ = render_fixture
    output = directory / "old.mp4"
    output.write_bytes(b"partial render is retained")
    deck_video.write_state("fixture", {"status": "done", "slides": 1,
                                       "skipped": ["s002"], "output": str(output)})
    assert_partial(deck_video.status("fixture"))


def test_recovered_and_intentionally_noteless_deck_are_complete(render_fixture):
    result = deck_video.build("fixture", {})
    value, _ = decode_envelope(result, LEGACY)
    assert value["source_complete"] is True
    assert value["expected_scenes"] == value["slides"] == 2
    assert value["missing_notes"] == ["s001", "s002"]
    assert value["errors"] == []


def test_live_recording_unshown_slide_is_not_missing(render_fixture, monkeypatch):
    monkeypatch.setattr(deck_video, "live_recording", lambda _: {"duration_sec": 2})
    monkeypatch.setattr(deck_video, "slice_recording", lambda *a, **kw: [
        {"slide_id": "s001", "start": 0, "duration": 2, "path": "fixture.wav"}])
    result = deck_video.build("fixture", {})
    assert result["unrecorded"] == ["s002"]
    assert result["source_complete"] is True
    assert result["expected_scenes"] == 1


def test_live_missing_repeated_scene_keeps_each_failure(render_fixture, monkeypatch):
    directory, _ = render_fixture
    (directory / "slides/s002.png").unlink()
    monkeypatch.setattr(deck_video, "live_recording", lambda _: {"duration_sec": 3})
    monkeypatch.setattr(deck_video, "slice_recording", lambda *a, **kw: [
        {"slide_id": sid, "start": n, "duration": 1, "path": "fixture.wav"}
        for n, sid in enumerate(["s002", "s001", "s002"])])
    result = deck_video.build("fixture", {})
    assert result["source_complete"] is False
    assert result["skipped"] == ["s002", "s002"]
    assert result["expected_scenes"] == 3
    assert result["rendered_slide_ids"] == ["s001"]
    assert len(result["errors"]) == 2


def test_all_missing_does_not_replace_previous_video(render_fixture):
    directory, _ = render_fixture
    (directory / "video").mkdir()
    output = directory / "video/lecture_video.mp4"
    output.write_bytes(b"previous good video")
    for png in (directory / "slides").glob("*.png"):
        png.unlink()
    with pytest.raises(RuntimeError, match="PNG"):
        deck_video.build("fixture", {})
    assert output.read_bytes() == b"previous good video"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
