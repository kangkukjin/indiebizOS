"""웹 동영상 정책의 독립 계약과 실제 FFmpeg 소비 경계."""
import json
import subprocess
from pathlib import Path

import boot_paths  # noqa: F401
import pytest
import thumbnails
import component_runtime

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('width,height,audio,copy,convert', [
    (3840, 1608, 'aac', False, True), (2160, 3840, 'aac', False, True),
    (1920, 1080, 'aac', True, False), (640, 360, 'aac', True, False),
    (1920, 1080, 'eac3', True, True), (None, None, 'aac', False, True)])
def test_web_playability_uses_size_as_well_as_codec(monkeypatch, width, height, audio, copy, convert):
    def probe(*a, **kw):
        data = {'streams': [{'codec_type':'video', 'codec_name':'h264', 'width':width, 'height':height},
                            {'codec_type':'audio', 'codec_name':audio}]}
        return subprocess.CompletedProcess(a[0], 0, json.dumps(data).encode(), b'')
    monkeypatch.setattr(thumbnails.subprocess, 'run', probe)
    assert thumbnails.video_codec_web_playable('movie.mkv') is copy
    assert thumbnails.needs_video_transcode('movie.mkv') is convert


def test_video_component_contract_runs_in_restricted_runtime():
    spec = component_runtime.registry(ROOT)['media.web_video_policy']
    assert component_runtime.verify(spec, (ROOT / spec['source']).read_bytes())['cases'] == 9


def test_full_stream_and_offset_use_same_policy(monkeypatch, tmp_path):
    commands = []
    monkeypatch.setattr(thumbnails.subprocess, 'Popen', lambda cmd, **kw: commands.append(cmd))
    thumbnails.start_stream_transcode('movie.mkv', str(tmp_path/'cache.mp4'))
    thumbnails.start_offset_stream('movie.mkv', 30)
    for cmd in commands:
        assert '1920' in cmd[cmd.index('-vf')+1]
        assert cmd[cmd.index('-crf')+1] == '24'


def test_policy_revision_changes_video_cache_key_without_deleting_files(tmp_path, monkeypatch):
    import api_showcase
    path = tmp_path / 'movie.mkv'; path.write_bytes(b'video')
    monkeypatch.setattr(thumbnails, 'video_policy_version', lambda: 'first')
    before = api_showcase._video_cache_key('folder', 'movie.mkv', path)
    monkeypatch.setattr(thumbnails, 'video_policy_version', lambda: 'second')
    assert api_showcase._video_cache_key('folder', 'movie.mkv', path) != before
    assert path.read_bytes() == b'video'


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
