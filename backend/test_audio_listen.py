"""파일 듣기: 실제 신호·구간·캐시·부분 재개·모델 실패·마이크 비활성 계약."""
import importlib.util
import json
import math
import struct
import sys
import wave
from pathlib import Path

import boot_paths  # noqa: F401
import pytest

PACKAGE = Path(__file__).resolve().parents[1] / "data/packages/installed/tools/android"


@pytest.fixture
def audio(monkeypatch, tmp_path):
    monkeypatch.syspath_prepend(str(PACKAGE))
    monkeypatch.setenv("INDIEBIZ_BASE_PATH", str(tmp_path))
    import android_audio
    from tool_context import ToolContext
    with wave.open(str(tmp_path / "tone.wav"), "wb") as f:
        f.setparams((2, 2, 8000, 0, "NONE", "not compressed"))
        f.writeframes(b"".join(struct.pack("<hh", int(5000 * math.sin(i * 2 * math.pi * 440 / 8000))
                                            if i >= 8000 else 0, 0) for i in range(8000 * 6)))
    return android_audio, ToolContext(str(tmp_path), "phone_listen"), tmp_path


def test_signal_real_channels_silence_and_range(audio):
    api, ctx, _ = audio
    result = api.listen_file({"path": "tone.wav", "start": 0, "end": 2}, ctx, "inspect")
    assert result["success"], result
    row = result["items"][0]
    assert row["channels"][0]["peak_dbfs"] == pytest.approx(-16.33, abs=.1)
    assert row["channels"][1]["peak_dbfs"] is None
    assert row["silences"][0]["end"] == pytest.approx(1, abs=.01)
    assert result["model_calls"] == 0
    # 앞의 무음 구간이 범위 밖이면 관측에 끼어들면 안 된다.
    later = api.listen_file({"path": "tone.wav", "start": 2, "end": 4}, ctx, "inspect")
    assert later["success"], later
    assert later["items"][0]["silences"] == []


@pytest.mark.parametrize("args", [{"path": ""}, {"path": []}, {"path": "missing.wav"},
    {"path": "tone.wav", "start": -1}, {"path": "tone.wav", "start": 3, "end": 2},
    {"path": "tone.wav", "end": 7}, {"path": "tone.wav", "start": float("nan")},
    {"path": "tone.wav", "ranges": [], "start": 0}])
def test_invalid_file_or_range_fails(audio, args):
    api, ctx, _ = audio
    assert api.listen_file(args, ctx, "inspect")["success"] is False


def _fake_value(text="안녕하세요"):
    return {"text": text, "answer": "", "events": [], "timing": "chunk", "uncertain": False,
            "usage": {"input": 10, "output": 4}, "model": "test"}


def test_cache_reuse_and_source_and_question_invalidation(audio, monkeypatch):
    api, ctx, directory = audio
    calls = []
    monkeypatch.setattr(api, "analyze_clip", lambda *a: calls.append(a) or _fake_value())
    args = {"path": "tone.wav", "question": "대화인가?"}
    first = api.listen_file(args, ctx, "analyze")
    second = api.listen_file(args, ctx, "analyze")
    assert first["success"] and second["success"]
    assert len(calls) == 1 and second["model_calls"] == 0 and second["cached_chunks"] == 1
    api.listen_file({**args, "question": "노래인가?"}, ctx, "analyze")
    with (directory / "tone.wav").open("ab") as f:
        f.write(b"extra")
    api.listen_file(args, ctx, "analyze")
    assert len(calls) == 3


def test_partial_failure_keeps_completed_chunks_and_resumes(audio, monkeypatch):
    api, ctx, directory = audio
    calls = []
    def once(*args):
        calls.append(args)
        if len(calls) == 2:
            raise ValueError("API failure")
        return _fake_value()
    monkeypatch.setattr(api, "analyze_clip", once)
    args = {"path": "tone.wav", "segment_seconds": 5}
    first = api.listen_file(args, ctx)
    assert first["success"] is False and first["status"] == "partial"
    assert "transcript_path" not in first
    second = api.listen_file(args, ctx)
    assert second["success"] and second["cached_chunks"] == 1
    assert len(calls) == 3
    assert Path(second["transcript_path"]).read_text() == "안녕하세요\n\n안녕하세요"


def test_large_text_is_saved_without_retyping_or_refetch(audio, monkeypatch):
    api, ctx, _ = audio
    monkeypatch.setattr(api, "analyze_clip", lambda *a: _fake_value("가" * 8000))
    result = api.listen_file({"path": "tone.wav"}, ctx)
    assert result["success"] and result["truncated"]
    assert len(result["items"][0]["text"]) == 1000
    assert len(Path(result["transcript_path"]).read_text()) == 8000
    assert len(json.loads(Path(result["result_path"]).read_text())["items"][0]["text"]) == 8000


def test_offsets_are_relative_to_original_file(audio, monkeypatch):
    api, ctx, _ = audio
    monkeypatch.setattr(api, "analyze_clip", lambda *a: {**_fake_value(), "timing": "word",
        "events": [{"start": .1, "end": .4, "text": "말", "kind": "speech"}]})
    result = api.listen_file({"path": "tone.wav", "start": 2, "end": 4}, ctx)
    assert result["items"][0]["start"] == 2.1
    assert result["coverage"] == "selected_or_partial"


def test_path_dispatch_never_opens_microphone(audio, monkeypatch):
    api, ctx, _ = audio
    spec = importlib.util.spec_from_file_location("listen_handler_test", PACKAGE / "handler.py")
    handler = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(handler)
    calls = []
    monkeypatch.setattr(api, "listen_file", lambda args, c, op: calls.append(op) or {"success": True})
    monkeypatch.setattr(handler, "_listen_run", lambda *a: pytest.fail("microphone called"))
    handler.execute({"path": "tone.wav", "question": "들리는 소리는?"}, ctx)
    handler.execute({"path": "", "op": "transcribe"}, ctx)
    assert calls == ["analyze", "transcribe"]
    with pytest.raises(pytest.fail.Exception):
        handler.execute({"op": "transcribe"}, ctx)


def test_response_truncation_and_impossible_times_rejected(audio):
    import android_audio_provider as provider
    with pytest.raises(ValueError):
        provider._parse_generation({"candidates": [{"finishReason": "MAX_TOKENS"}]}, 3)
    with pytest.raises(ValueError):
        provider.validate_events([{"start": 0, "end": 8, "text": "말"}], 3)
    payload = {"status": "completed", "steps": [{"type": "model_output", "content": [{"type": "text", "text": "안녕"}]}]}
    with pytest.raises(ValueError):
        provider._parse_interaction(payload, 3, True)
    assert provider._parse_interaction(payload, 3, False)["text"] == "안녕"


def test_overlap_ranges_merge_without_double_cost(audio):
    from android_audio_signal import ranges
    assert ranges({"ranges": [{"start": 1, "end": 4}, {"start": 3, "end": 5}]}, 6) == [(1, 5)]


def test_worker_preserves_contextvars_for_tool_model_accounting():
    import contextvars
    from ibl_routing import _run_sync_with_timeout
    value = contextvars.ContextVar("audio_test", default=None)
    token = value.set({"calls": 0})
    try:
        def work():
            value.get()["calls"] += 1
            return value.get()
        assert _run_sync_with_timeout(work, (), 2, "test")["calls"] == 1
        assert value.get()["calls"] == 1
    finally:
        value.reset(token)


def test_worker_model_usage_reaches_turn_ledger():
    from ibl_routing import _run_sync_with_timeout
    from providers.base import begin_turn_token_ledger, read_turn_tokens, ProviderMetrics
    import contextvars
    def isolated():
        begin_turn_token_ledger()
        _run_sync_with_timeout(lambda: ProviderMetrics().record_usage(1, {
            "input_tokens": 11, "output_tokens": 7}), (), 2, "audio")
        assert read_turn_tokens() == 18
    contextvars.copy_context().run(isolated)


def test_cancelled_call_does_not_start_model(audio, monkeypatch):
    api, ctx, _ = audio
    monkeypatch.setattr(api, "_cancelled", lambda: True)
    monkeypatch.setattr(api, "analyze_clip", lambda *a: pytest.fail("model called"))
    result = api.listen_file({"path": "tone.wav"}, ctx)
    assert result["success"] is False and result["model_calls"] == 0


def test_concurrent_same_chunk_is_billed_once(audio, monkeypatch):
    api, ctx, _ = audio
    import threading
    from concurrent.futures import ThreadPoolExecutor
    entered, release = threading.Event(), threading.Event()
    calls = []
    def slow(*args):
        calls.append(args)
        entered.set()
        assert release.wait(3)
        return _fake_value()
    monkeypatch.setattr(api, "analyze_clip", slow)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(api.listen_file, {"path": "tone.wav"}, ctx)
        assert entered.wait(2)
        second = pool.submit(api.listen_file, {"path": "tone.wav"}, ctx)
        release.set()
        results = [first.result(), second.result()]
    assert all(r["success"] for r in results), results
    assert len(calls) == 1


def test_original_cannot_be_overwritten_with_transcript(audio, monkeypatch):
    api, ctx, directory = audio
    # 경로 guard 통과 이후에도 원본 동일성 검사를 한다.
    monkeypatch.setattr(ctx, "resolve_output_path", lambda *a, **k: {"path": str(directory / "tone.wav")})
    monkeypatch.setattr(api, "analyze_clip", lambda *a: pytest.fail("model called"))
    result = api.listen_file({"path": "tone.wav", "out": "tone.wav"}, ctx)
    assert result["success"] is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
