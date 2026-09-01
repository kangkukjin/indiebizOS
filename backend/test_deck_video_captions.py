"""deck video 선택적 자막 경로 회귀 테스트.

실행: .venv/bin/python3 -m pytest backend/test_deck_video_captions.py -q

★왜 이 파일이 다시 쓰였나 (2026-09-01): 08-31 ep2519 수리가 이 테스트를 격리
  워크트리에 세 번 적재하고 두 번 폐기한 뒤 백엔드 종료로 통째로 잃었다. 라이브에는
  구현만 남고 계약을 지키는 자리가 0이었다.

고정하는 계약 다섯:
  ①captions 미지정 = 종전 경로 무변경 (렌더러가 받는 output_filename 도 그대로)
  ②큐 타임코드는 씬 길이가 아니라 **실측 음성 길이**와 전환 겹침을 따른다
  ③libass 없는 ffmpeg 에서도 rawvideo+Pillow 로 **실제 픽셀**이 바뀐다
  ④오디오는 비트스트림 그대로 보존된다
  ⑤요청한 자막이 실패하면 무자막 영상을 성공으로 반환하지 않는다
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
LW_DIR = ROOT / "data/packages/installed/tools/lecture_workspace"
if str(LW_DIR) not in sys.path:
    sys.path.insert(0, str(LW_DIR))

pytest.importorskip("PIL", reason="Pillow 없음 — 자막 합성 경로 검사 불가")

if not (shutil.which("ffmpeg") and shutil.which("ffprobe")):
    pytest.skip("ffmpeg/ffprobe 없음 — 합성 경로 검사 불가", allow_module_level=True)

import deck_video  # noqa: E402
import lecture_video_captions as captions  # noqa: E402

FPS = 12


# ── ② 큐 타임코드 ────────────────────────────────────────────────────────

def test_cues_follow_measured_audio_not_scene_duration():
    """씬은 5·6초인데 실측 음성은 4.5·5.0초 — 큐는 음성을 따라야 한다.

    ★씬 길이를 따르면 나레이션이 끝난 뒤에도 자막이 남아 그림과 어긋난다.
    """
    cues = captions.build_cues(
        ["첫 문장입니다. 둘째 문장입니다.", "다음 장입니다."],
        [5.0, 6.0],
        [4.5, 5.0],
        transition_duration=0.5,
    )
    assert len(cues) == 3
    assert cues[0]["start"] == pytest.approx(0.0)
    # 1장의 마지막 큐는 실측 음성(4.5)에서 끝난다 — 씬 길이 5.0 이 아니다.
    assert cues[1]["end"] == pytest.approx(4.5)
    # 2장 시작 = 씬1 길이(5.0) - 전환 겹침(0.5). 전환을 안 빼면 자막이 한 장씩 밀린다.
    assert cues[2]["start"] == pytest.approx(4.5)
    assert "".join(c["text"] for c in cues).replace(" ", "") == (
        "첫문장입니다.둘째문장입니다.다음장입니다."
    )


def test_cues_are_ordered_and_skip_noteless_scenes():
    cues = captions.build_cues(
        ["노트 있는 장.", "", "마지막 장."],
        [4.0, 4.0, 4.0],
        [3.0, 0.0, 3.0],
        transition_duration=0.0,
    )
    assert [c["text"] for c in cues] == ["노트 있는 장.", "마지막 장."]
    assert cues[1]["start"] >= cues[0]["start"]
    assert all(c["end"] > c["start"] for c in cues)


def test_write_ass_keeps_one_dialogue_per_cue_and_escapes_braces(tmp_path):
    cues = captions.build_cues(["여는 중괄호 { 와 닫는 } 가 든 노트."], [4.0], [3.0])
    target = tmp_path / "out.captions.ass"
    captions.write_ass(target, cues, 1280, 720, title="회귀")
    text = target.read_text(encoding="utf-8")
    assert text.count("\nDialogue: ") == len(cues)
    # ASS 는 { } 를 오버라이드 태그로 먹는다 — 이스케이프가 풀리면 글자가 사라진다.
    assert r"\{" in text and r"\}" in text


def test_captions_path_does_not_depend_on_libass():
    """설계 계약: subtitles/ass 필터를 쓰지 않는다(사용자 ffmpeg 에 libass 가 없다)."""
    source = (LW_DIR / "lecture_video_captions.py").read_text(encoding="utf-8")
    assert "subtitles=" not in source
    assert '"ass="' not in source and "-vf" not in source


# ── ③④ 실제 합성 ────────────────────────────────────────────────────────

def _make_source(path: Path, seconds: float = 2.0) -> None:
    """단색 영상 + 사인파 오디오 — 자막 픽셀만이 유일한 변화가 되게."""
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", f"color=c=#203040:s=320x180:r={FPS}:d={seconds}",
        "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(path),
    ], check=True, capture_output=True)


def _ink_ratio(video: Path, at: float, tmp: Path) -> float:
    """그 시점 프레임에서 '배경이 아닌' 픽셀 비율.

    ★색 집합 비교로는 못 판정한다 — x264 재인코딩만으로도 (32,48,63)→(32,48,61)
      같은 이웃 색이 생긴다(2026-09-01 실측). 자막은 검은 칩+흰 글자라서 배경에서
      멀리 떨어진 픽셀로만 세야 한다.
    """
    from PIL import Image
    shot = tmp / f"f{at}.png"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-ss", str(at), "-i", str(video), "-frames:v", "1", str(shot),
    ], check=True, capture_output=True)
    pixels = list(Image.open(shot).convert("RGB").getdata())
    base = max(set(pixels), key=pixels.count)
    far = sum(1 for px in pixels if max(abs(a - b) for a, b in zip(px, base)) > 24)
    return far / len(pixels)


def _audio_streams(video: Path) -> list:
    out = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "a",
        "-show_entries", "stream=codec_name", "-of", "json", str(video),
    ], check=True, capture_output=True, text=True).stdout
    return json.loads(out or "{}").get("streams") or []


def test_burn_captions_paints_only_inside_the_cue_window(tmp_path):
    src, out = tmp_path / "src.mp4", tmp_path / "out.mp4"
    _make_source(src, seconds=2.0)
    assert _ink_ratio(src, 0.5, tmp_path) < 0.01, "원본이 이미 단색이 아니다"

    result = captions.burn_captions(
        src, [{"start": 0.0, "end": 1.0, "text": "한글 자막이 보인다."}], out
    )
    assert out.exists() and result["captions"] == 1
    assert result["frames"] > 0

    # 큐 안 = 자막 칩·글자가 실제로 그려졌다. 큐 밖 = 배경 그대로.
    assert _ink_ratio(out, 0.5, tmp_path) > 0.02
    assert _ink_ratio(out, 1.5, tmp_path) < 0.01


def test_burn_captions_preserves_the_audio_stream(tmp_path):
    src, out = tmp_path / "src.mp4", tmp_path / "out.mp4"
    _make_source(src, seconds=1.5)
    assert _audio_streams(src), "테스트 원본에 오디오가 없다 — 검사가 성립하지 않는다"
    captions.burn_captions(src, [{"start": 0.0, "end": 1.0, "text": "소리 보존"}], out)
    assert _audio_streams(out), "자막 합성이 오디오를 떨어뜨렸다"


def test_burn_captions_refuses_empty_cues(tmp_path):
    src = tmp_path / "src.mp4"
    _make_source(src, seconds=0.5)
    with pytest.raises(RuntimeError):
        captions.burn_captions(src, [], tmp_path / "out.mp4")


# ── ①⑤ deck video 배선 ─────────────────────────────────────────────────

def _fake_deck(tmp_path: Path, notes: list[str]):
    """PNG 만 실존하면 되는 최소 덱 — lecture_store 를 타지 않는다."""
    from PIL import Image
    lecture_dir = tmp_path / "lecture"
    (lecture_dir / "slides").mkdir(parents=True)
    order, slides = [], {}
    for i, note in enumerate(notes):
        sid = f"s{i}"
        png = Path("slides") / f"{sid}.png"
        Image.new("RGB", (320, 180), (32, 48, 64)).save(lecture_dir / png)
        order.append(sid)
        slides[sid] = {"png_file": str(png), "speaker_note": note}
    return lecture_dir, {"title": "회귀 덱", "slide_order": order, "slides": slides}


class _FakeMediaHandler:
    """create_html_video 대역 — 실제 MP4 를 남기고 실측 음성 길이를 씬에 되돌린다."""

    def __init__(self, narration_seconds: float = 1.0):
        self.narration_seconds = narration_seconds
        self.received: dict = {}

    def create_html_video(self, tool_input, output_base):
        self.received = dict(tool_input)
        for i, scene in enumerate(tool_input["scenes"]):
            has_note = bool((tool_input["narration_texts"][i] or "").strip())
            # ★media_producer 가 지키는 이음매 — 이게 끊기면 자막이 씬 길이로 어긋난다.
            scene["_narration_duration"] = self.narration_seconds if has_note else 0.0
        target = Path(output_base) / tool_input["output_filename"]
        _make_source(target, seconds=self.narration_seconds * len(tool_input["scenes"]))
        return f"HTML 동영상 제작 완료: {target} | 씬 전환: fade (0.5초)"


def _run_build(monkeypatch, tmp_path, notes, opts, narration_seconds=1.0):
    lecture_dir, deck = _fake_deck(tmp_path, notes)
    mh = _FakeMediaHandler(narration_seconds)
    monkeypatch.setattr(deck_video.lecture_store, "read_deck", lambda _id: deck)
    monkeypatch.setattr(deck_video.lecture_store, "lecture_dir", lambda _id: lecture_dir)
    monkeypatch.setattr(deck_video, "_load_media_handler", lambda: mh)
    return lecture_dir, mh


def test_captions_absent_keeps_the_previous_path_untouched(monkeypatch, tmp_path):
    """①기본값 호환 — captions 를 안 주면 렌더러가 받는 파일명도 결과도 종전 그대로."""
    lecture_dir, mh = _run_build(monkeypatch, tmp_path, ["한 장 노트."], {})
    result = deck_video.build("lec", {"width": 320, "height": 180})

    assert mh.received["output_filename"] == "lecture_video.mp4"   # 임시 파일명으로 안 바뀐다
    assert result["output"].endswith("lecture_video.mp4")
    assert "caption_burned" not in result and "caption_file" not in result
    assert not list((lecture_dir / "video").glob("*.ass"))


def test_captions_true_burns_and_keeps_editable_ass(monkeypatch, tmp_path):
    lecture_dir, mh = _run_build(monkeypatch, tmp_path, ["첫 장 노트.", "둘째 장 노트."], {})
    result = deck_video.build("lec", {"width": 320, "height": 180, "captions": True})

    final = Path(result["output"])
    assert final.name == "lecture_video.mp4" and final.exists()
    # 렌더러는 임시 이름으로 받았어야 한다 — 요청 파일명은 합성 결과의 몫.
    assert mh.received["output_filename"] != "lecture_video.mp4"
    assert result["caption_burned"] is True and result["captions"] >= 2
    sidecar = Path(result["caption_file"])
    assert sidecar.exists() and sidecar.suffix == ".ass"
    assert "Dialogue: " in sidecar.read_text(encoding="utf-8")
    assert _audio_streams(final), "자막본이 오디오를 잃었다"
    # 중간 산출물(임시 원본·합성 임시본)이 남지 않는다.
    leftovers = [p.name for p in (lecture_dir / "video").iterdir() if p.name.startswith(".")]
    assert leftovers == []


def test_captions_true_without_notes_fails_instead_of_returning_silent_video(
    monkeypatch, tmp_path
):
    """⑤요청한 자막을 못 만들면 무자막 영상을 성공으로 돌려주지 않는다."""
    lecture_dir, _ = _run_build(monkeypatch, tmp_path, ["", ""], {})
    with pytest.raises(RuntimeError, match="자막 원문"):
        deck_video.build("lec", {"width": 320, "height": 180, "captions": True})
    assert not list((lecture_dir / "video").glob("*.mp4"))


# ── ②의 뿌리: 렌더러가 실측 길이를 씬에 되돌리는 이음매 ────────────────────

def test_media_producer_returns_measured_narration_duration_on_the_scene(
    monkeypatch, tmp_path
):
    """자막 타임코드의 유일한 출처 — media_producer 가 scene['_narration_duration'] 을 심는다.

    ★위쪽 deck video 테스트는 이 이음매를 **대역으로** 흉내낸다. 진짜 렌더러가
      이 줄을 잃으면 그 테스트들은 여전히 초록이고 자막만 조용히 어긋난다.
      그래서 여기서 실제 handler 를 찌른다(플레이라이트 직전에서 멈춰 세운다).
    """
    pytest.importorskip("moviepy", reason="moviepy 없음 — 길이 측정 경로 검사 불가")
    playwright_api = pytest.importorskip(
        "playwright.sync_api", reason="playwright 없음 — 멈춤 지점을 만들 수 없다"
    )

    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "mp_handler_captions_seam",
        ROOT / "data/packages/installed/tools/media_producer/handler.py",
    )
    mp = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mp
    spec.loader.exec_module(mp)

    narration = tmp_path / "narration.wav"
    subprocess.run([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "lavfi", "-i", "sine=frequency=330:duration=1.4", str(narration),
    ], check=True, capture_output=True)

    class _Stop(Exception):
        """캡처 단계 진입 = 길이 측정·되돌림 단계를 지났다는 표식."""

    # ★create_html_video 는 본문 전체를 try 로 감싸 실패를 계약(dict/문자열)으로 바꾼다 —
    #   그래서 pytest.raises 로는 못 세운다. 멈춤은 신호일 뿐이고, 검사 대상은
    #   호출자가 넘긴 **바로 그 scene 객체**가 실측 길이를 되받았는지다.
    monkeypatch.setattr(
        playwright_api, "sync_playwright",
        lambda: (_ for _ in ()).throw(_Stop()),
    )

    scene = {"html": "<html><body>회귀</body></html>", "duration": 5.0, "static": True}
    mp.create_html_video({
        "scenes": [scene],
        "narration_texts": ["실측 길이를 되돌려야 한다."],
        "narration_audio_paths": [str(narration)],   # 미리 구운 오디오 = TTS 호출 0
        "output_filename": "seam.mp4",
        "width": 320, "height": 180,
    }, str(tmp_path))

    assert "_narration_duration" in scene, (
        "렌더러가 실측 음성 길이를 씬에 되돌리지 않았다 — 자막이 씬 길이로 어긋난다"
    )
    assert scene["_narration_duration"] == pytest.approx(1.4, abs=0.15)
