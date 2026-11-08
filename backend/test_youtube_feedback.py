"""Track replacement and immediate native readback are one bounded operation."""
import sys
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest
from test_youtube_phone import phone, yt  # noqa: F401


@pytest.fixture
def ready(yt, phone, monkeypatch):
    class Downloader:
        def __init__(self, *a, **kw): pass
        def __enter__(self): return self
        def __exit__(self, *a): pass
        def extract_info(self, *a, **kw):
            return {'entries': [{'id': 'newtrack123', 'title': 'New', 'duration': 60},
                                {'id': 'candidate12', 'title': 'Candidate', 'duration': 40}]}
    monkeypatch.setitem(sys.modules, 'yt_dlp', SimpleNamespace(YoutubeDL=Downloader))
    monkeypatch.setattr(yt, '_get_audio_url', lambda vid: 'https://example.test/' + vid)
    monkeypatch.setattr(yt.threading, 'Thread', lambda **kw: SimpleNamespace(start=lambda: None))
    yt._start_ffplay('old')
    yt._player_video_id = 'oldtrack123'
    yt._player_title = 'Old'
    yt._player_queue[:] = [{'video_id': 'waiting1234', 'title': 'Waiting'}]
    # Native fake generates a fresh id and playing state for every start.
    module, state, calls = phone
    native = module.bridge()
    def play(url, volume):
        import json
        calls.append(('play', url, volume))
        state.update(playing=True, playback_id='music-' + str(len(calls)))
        return json.dumps(state)
    native.playStream = play
    return yt, state, calls


def test_default_play_enqueues_without_restart(ready):
    yt, _, calls = ready
    result = yt.play_youtube('song')
    assert result['queued'] and result['observation']['scope'] == 'queue_membership'
    assert result['observation']['status'] == 'confirmed'
    assert len([c for c in calls if c[0] == 'play']) == 1
    assert yt._player_video_id == 'oldtrack123'


def test_replace_prepares_then_switches_once_preserving_queue_order(ready):
    yt, _, calls = ready
    result = yt.play_youtube('song', if_playing='replace')
    obs = result['observation']
    assert obs['status'] == 'confirmed' and obs['scope'] == 'player_state'
    assert obs['actual']['video_id'] == 'newtrack123'
    assert obs['actual']['playback_id'] == yt._player_process.playback_id
    assert [q['video_id'] for q in yt._player_queue] == ['waiting1234', 'candidate12']
    assert len([c for c in calls if c[0] == 'play']) == 2
    assert len([c for c in calls if c[0] == 'stop']) == 1


def test_prepare_failure_keeps_old_playback_and_queue(ready, monkeypatch):
    yt, state, calls = ready
    monkeypatch.setattr(yt, '_get_audio_url', lambda vid: None)
    result = yt.play_youtube('song', if_playing='replace')
    assert result['success'] is False
    assert yt._player_video_id == 'oldtrack123' and state['playing']
    assert [q['video_id'] for q in yt._player_queue] == ['waiting1234']
    assert not [c for c in calls if c[0] == 'stop']


def test_conflicting_native_player_is_unknown_without_replay(ready, monkeypatch):
    yt, _, calls = ready
    monkeypatch.setattr(yt._phone, 'stream_status', lambda: {'playing': True, 'playback_id': 'other'})
    result = yt.play_youtube('song', if_playing='replace')
    assert result['observation']['status'] == 'unknown'
    assert result['observation']['reason'] == 'playback_ownership_changed'
    assert len([c for c in calls if c[0] == 'play']) == 2


def test_stop_reports_native_readback_and_empty_queue(ready):
    yt, _, _ = ready
    result = yt.stop_youtube()
    assert result['observation']['status'] == 'confirmed'
    assert result['observation']['actual']['playing'] is False
    assert result['observation']['actual']['queue_length'] == 0
