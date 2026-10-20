"""Phone playback ownership and standalone dispatch, without physical devices."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest
from common.pkg_utils import load_sibling

ROOT = Path(__file__).resolve().parents[1]
HANDLER = str(ROOT / 'data/packages/installed/tools/youtube/handler.py')


@pytest.fixture
def phone(monkeypatch):
    module = load_sibling(HANDLER, 'youtube_phone')
    monkeypatch.setenv('INDIEBIZ_PROFILE', 'phone')
    state = {'playing': True, 'playback_id': 'music-1'}
    calls = []

    def play(url, volume):
        calls.append(('play', url, volume))
        return json.dumps(state)

    def stop(pid):
        calls.append(('stop', pid))
        stopped = pid == state['playback_id']
        if stopped:
            state['playing'] = False
        return json.dumps({'stopped': stopped})

    native = SimpleNamespace(playStream=play, stopStreamIf=stop,
                             streamStatus=lambda: json.dumps(state),
                             seekStream=lambda pid, pos: json.dumps({'position': pos}),
                             openMediaUrl=lambda url: json.dumps({'opened': True}))
    monkeypatch.setattr(module, 'bridge', lambda: native)
    return module, state, calls


def test_playback_completion_and_stop_are_scoped_to_its_id(phone):
    module, state, calls = phone
    playback = module.Playback('https://example.test/music.m4a')
    assert playback.poll() is None
    state['playing'] = False
    assert playback.wait(timeout=1) == 0
    assert not playback.replaced
    playback.terminate()
    assert calls[-1] == ('stop', 'music-1')


def test_old_music_handle_cannot_stop_replacement_radio(phone):
    module, state, calls = phone
    playback = module.Playback('https://example.test/music.m4a')
    state['playback_id'] = 'radio-2'
    assert playback.poll() == -1 and playback.replaced
    playback.terminate()
    assert state['playing']
    assert calls[-1] == ('stop', 'music-1')


def test_native_failure_is_not_successful_completion(phone):
    module, state, _ = phone
    playback = module.Playback('https://example.test/music.m4a')
    state['error'] = 'network failure'
    assert playback.wait(timeout=1) == 1


def test_native_start_failure_is_not_a_playback_handle(phone):
    module, state, _ = phone
    state['error'] = 'decoder failure'
    with pytest.raises(RuntimeError, match='decoder failure'):
        module.Playback('https://example.test/music.m4a')


def test_video_open_is_not_playback_confirmation(phone):
    module, _, _ = phone
    result = module.open_video('https://www.youtube.com/watch?v=abcdefghijk')
    assert result['opened'] and result['playing'] is None
    assert result['control'] == 'external'


@pytest.fixture
def yt(phone, monkeypatch):
    module, state, calls = phone
    player = load_sibling(HANDLER, 'tool_youtube')
    monkeypatch.setattr(player, '_phone', module)
    monkeypatch.setattr(module, 'prepare', lambda: None)
    for name, value in {'_player_process': None, '_player_video_id': None,
                        '_player_title': None, '_player_queue': [],
                        '_player_audio_url': None, '_player_mode': 'audio'}.items():
        monkeypatch.setattr(player, name, value)
    monkeypatch.setattr(player, 'spawn_detached', lambda *a: pytest.fail('PC player invoked'))
    monkeypatch.setattr(player, 'kill_processes_by_marker', lambda *a: pytest.fail('PC cleanup invoked'))
    monkeypatch.setattr(player, 'open_url', lambda *a: pytest.fail('PC browser invoked'))
    return player


def test_shared_player_starts_and_stops_native_audio(yt, phone):
    _, state, calls = phone
    yt._start_ffplay('https://example.test/music.m4a', seek=5)
    assert yt._player_process is not None
    assert yt._player_seek_offset == 5
    yt._close_player()
    assert not state['playing'] and calls[-1] == ('stop', 'music-1')


def test_replacement_does_not_advance_music_queue(yt, phone):
    _, state, _ = phone
    yt._start_ffplay('https://example.test/music.m4a')
    yt._player_queue.append({'video_id': 'next'})
    state['playback_id'] = 'radio-2'
    yt._queue_monitor()
    assert yt._player_process is None and len(yt._player_queue) == 1


def test_phone_video_url_opens_without_stream_extraction(yt, monkeypatch):
    class ForbiddenDownloader:
        def __init__(self, *a, **kw):
            pytest.fail('video URL should go directly to the phone video app')
    monkeypatch.setitem(sys.modules, 'yt_dlp', SimpleNamespace(YoutubeDL=ForbiddenDownloader))
    result = yt.play_youtube('https://www.youtube.com/watch?v=abcdefghijk', mode='video')
    assert result['opened'] and result['playing'] is None
    assert not yt.stop_youtube()['success']
    assert yt.get_queue()['control'] == 'external'
    assert not yt.add_to_queue('another song')['success']
    assert not yt.skip_youtube()['success']


def test_phone_search_uses_local_extractor(yt, monkeypatch):
    calls = []
    class Downloader:
        def __init__(self, options):
            calls.append(options)
        def __enter__(self):
            return self
        def __exit__(self, *a):
            pass
        def extract_info(self, query, download=False):
            calls.append(query)
            return {'entries': [{'id': 'abcdefghijk', 'title': 'Song', 'duration': 60}]}
    monkeypatch.setitem(sys.modules, 'yt_dlp', SimpleNamespace(YoutubeDL=Downloader))
    result = yt.search_youtube('song', 1)
    assert result['success'] and result['count'] == 1
    assert calls[1] == 'ytsearch1:song'


@pytest.mark.parametrize('op', ['download', 'relay'])
def test_pc_only_operations_report_limitation_without_forwarding(yt, monkeypatch, op):
    handler = load_sibling(HANDLER, 'handler')
    monkeypatch.setattr(handler, 'load_tool_youtube', lambda: yt)
    result = handler.execute({'op': op}, SimpleNamespace(tool_name='youtube_op'))
    assert not result['success'] and 'PC' in result['error']


def test_phone_bundle_contains_standalone_actions():
    import yaml
    manifest = json.loads((ROOT / 'data/phone_manifest.json').read_text())
    assert {'youtube', 'music-player'} <= set(manifest['packages'])
    assert {'limbs:youtube', 'self:music'} <= set(manifest['runnable_actions'])
    nodes = yaml.safe_load((ROOT / 'data/bodies/android.nodes.yaml').read_text())['nodes']
    assert 'youtube' in nodes['limbs']['actions']


def test_music_stream_is_local_and_retains_source_path_checks(monkeypatch, tmp_path):
    import importlib.util
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    import api_music
    path = ROOT / 'phone-companion/app/src/main/python/phone_execution_routes.py'
    spec = importlib.util.spec_from_file_location('phone_media_routes_test', path)
    routes = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(routes)
    app = FastAPI()
    routes.install(app, lambda: str(tmp_path), lambda value: value)
    monkeypatch.setattr(api_music, '_core', lambda: SimpleNamespace(
        norm_path=lambda p: p, path_allowed=lambda p: False))
    response = TestClient(app).get('/music/stream', params={'path': '/outside.mp3'})
    assert response.status_code == 404


def test_android_ejs_provider_is_discovered_and_propagates_js_errors(monkeypatch):
    pytest.importorskip('yt_dlp')
    from yt_dlp import YoutubeDL
    from yt_dlp.extractor.youtube import YoutubeIE
    from yt_dlp.extractor.youtube.jsc._director import initialize_jsc_director
    from yt_dlp.extractor.youtube.jsc._registry import _jsc_preferences, _jsc_providers
    from yt_dlp.extractor.youtube.jsc.provider import JsChallengeProviderError
    module = load_sibling(HANDLER, 'youtube_phone')
    monkeypatch.setattr(_jsc_providers, 'value', dict(_jsc_providers.value))
    monkeypatch.setattr(_jsc_preferences, 'value', set(_jsc_preferences.value))
    monkeypatch.setattr(module, '_registered', False)
    monkeypatch.setenv('INDIEBIZ_PROFILE', 'phone')
    output = {'stdout': '{"responses":[]}'}
    scripts = []
    def evaluate(script):
        scripts.append(script)
        return json.dumps(output)
    native = SimpleNamespace(evaluate=evaluate)
    monkeypatch.setitem(sys.modules, 'java', SimpleNamespace(jclass=lambda name: native))
    module.prepare()
    module.prepare()  # registration must be idempotent
    with YoutubeDL({'quiet': True}) as downloader:
        director = initialize_jsc_director(YoutubeIE(downloader))
        provider = next(p for p in director.providers.values()
                        if p.PROVIDER_NAME == 'indiebiz-webview')
        assert provider.is_available()
        assert provider._run_js_runtime('console.log(1)') == '{"responses":[]}'
        assert scripts == ['console.log(1)']
        output.clear()
        output['error'] = 'JS timeout'
        with pytest.raises(JsChallengeProviderError, match='JS timeout'):
            provider._run_js_runtime('loop')


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))


def test_every_new_track_preserves_device_volume(phone):
    module, _, calls = phone
    module.Playback('https://example.test/first.m4a')
    module.Playback('https://example.test/second.m4a')
    assert [call[2] for call in calls if call[0] == 'play'] == [-1, -1]
