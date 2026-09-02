"""공개파일 오프셋 재생의 영상·자막 시간축 회귀."""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: F401
import thumbnails


@pytest.mark.parametrize("quality", ["", "low", "lowh", "tiny", "nano"])
def test_offset_stream_uses_accurate_seek_transcode(monkeypatch, quality):
    """오프셋 영상은 키프레임 복사 없이 요청 시각부터 재인코딩해야 한다."""
    captured = {}

    def fake_popen(cmd, **kwargs):
        captured["cmd"] = cmd
        captured["kwargs"] = kwargs
        return object()

    monkeypatch.setattr(thumbnails.subprocess, "Popen", fake_popen)
    thumbnails.start_offset_stream("/tmp/movie.mkv", 2700, quality=quality)

    cmd = captured["cmd"]
    assert cmd.index("-ss") < cmd.index("-i")
    assert cmd[cmd.index("-ss") + 1] == "2700"
    assert ["-c", "copy"] != cmd[cmd.index("-i") + 2:cmd.index("-map")]
    assert not any(
        cmd[i:i + 2] == ["-c:v", "copy"]
        for i in range(len(cmd) - 1)
    )
    assert captured["kwargs"]["stdout"] is thumbnails.subprocess.PIPE


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
