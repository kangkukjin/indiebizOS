"""강의 영상 자막 생성·합성 — libass 없는 ffmpeg에서도 동작하는 결정론 경로.

스피커 노트를 짧은 자막 구간으로 나누고, ffmpeg rawvideo 스트림을 Pillow로
합성한다. ffmpeg의 subtitles/ass 필터나 OpenCV에는 의존하지 않는다.
"""

from __future__ import annotations

import os
import re
import subprocess
from fractions import Fraction
from pathlib import Path


_FONT_CANDIDATES = (
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/System/Library/Fonts/AppleGothic.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
    "C:/Windows/Fonts/malgun.ttf",
)


def _split_sentences(text: str) -> list[str]:
    parts = re.findall(r"[^.!?。！？…]+[.!?。！？…]?", (text or "").replace("\n", " "))
    return [part.strip() for part in parts if part.strip()]


def _split_phrase(text: str, limit: int = 34) -> list[str]:
    if len(text) <= limit:
        return [text]
    pieces = re.split(r"(?<=[,，:;])\s*|\s+", text)
    result: list[str] = []
    current = ""
    for piece in pieces:
        if not piece:
            continue
        candidate = f"{current} {piece}".strip()
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            result.append(current)
        while len(piece) > limit:
            result.append(piece[:limit])
            piece = piece[limit:]
        current = piece
    if current:
        result.append(current)
    return result


def _chunks(text: str) -> list[str]:
    result: list[str] = []
    for sentence in _split_sentences(text):
        result.extend(_split_phrase(sentence))
    return result


def build_cues(
    texts: list[str],
    scene_durations: list[float],
    narration_durations: list[float],
    transition_duration: float = 0.0,
) -> list[dict]:
    """장별 원문과 실측 길이로 전역 자막 큐를 만든다."""
    cues: list[dict] = []
    scene_start = 0.0
    for index, scene_duration in enumerate(scene_durations):
        text = texts[index].strip() if index < len(texts) and texts[index] else ""
        narration_duration = (
            float(narration_durations[index])
            if index < len(narration_durations) and narration_durations[index]
            else 0.0
        )
        chunks = _chunks(text)
        if chunks:
            visible_duration = narration_duration or float(scene_duration)
            weights = [
                max(1, len(re.sub(r"\s", "", chunk)))
                + 2 * chunk.count(",")
                + 3 * int(chunk.endswith((".", "?", "!", "。", "！", "？", "…")))
                for chunk in chunks
            ]
            total_weight = sum(weights)
            local_start = 0.0
            for chunk_index, (chunk, weight) in enumerate(zip(chunks, weights)):
                local_end = (
                    visible_duration
                    if chunk_index == len(chunks) - 1
                    else local_start + visible_duration * weight / total_weight
                )
                cues.append({
                    "start": scene_start + max(0.0, local_start - 0.08),
                    "end": scene_start + min(visible_duration, local_end + 0.12),
                    "text": chunk,
                })
                local_start = local_end
        overlap = transition_duration if index < len(scene_durations) - 1 else 0.0
        scene_start += max(0.0, float(scene_duration) - overlap)
    return cues


def _ass_time(seconds: float) -> str:
    centiseconds = max(0, round(float(seconds) * 100))
    hours, remainder = divmod(centiseconds, 360000)
    minutes, remainder = divmod(remainder, 6000)
    secs, cs = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def write_ass(
    path: str | Path,
    cues: list[dict],
    width: int,
    height: int,
    title: str = "Lecture captions",
) -> str:
    """편집 가능한 ASS 원본도 함께 남긴다."""
    font_size = max(28, round(height * 0.055))
    margin_v = max(28, round(height * 0.05))
    header = f"""[Script Info]
Title: {title}
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Caption,Noto Sans CJK KR,{font_size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H59000000,-1,0,0,0,100,100,0,0,3,1,0,2,120,120,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for cue in cues:
        safe = str(cue["text"]).replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}")
        safe = safe.replace("\n", r"\N")
        lines.append(
            f"Dialogue: 0,{_ass_time(cue['start'])},{_ass_time(cue['end'])},"
            f"Caption,,0,0,0,,{safe}\n"
        )
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("".join(lines), encoding="utf-8")
    return str(target)


def _probe_video(path: Path) -> dict:
    result = subprocess.run([
        "ffprobe", "-v", "error", "-select_streams", "v:0",
        "-show_entries", "stream=width,height,avg_frame_rate,r_frame_rate,nb_frames",
        "-of", "json", str(path),
    ], capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"자막 원본 영상 조사 실패: {(result.stderr or '')[-300:]}")
    import json
    streams = json.loads(result.stdout or "{}").get("streams") or []
    if not streams:
        raise RuntimeError("자막 원본 영상에 비디오 스트림이 없습니다.")
    stream = streams[0]
    rate = stream.get("avg_frame_rate") or stream.get("r_frame_rate") or "0/1"
    fps = float(Fraction(rate))
    width, height = int(stream.get("width") or 0), int(stream.get("height") or 0)
    if fps <= 0 or width <= 0 or height <= 0:
        raise RuntimeError(f"자막 원본 영상 규격이 유효하지 않습니다: {width}x{height} {rate}")
    return {
        "width": width,
        "height": height,
        "rate": rate,
        "fps": fps,
        "frames": int(stream.get("nb_frames") or 0),
    }


def _load_font(height: int, font_path: str | None = None):
    from PIL import ImageFont
    candidates = ([font_path] if font_path else []) + list(_FONT_CANDIDATES)
    size = max(24, round(height * 0.055))
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            try:
                return ImageFont.truetype(candidate, size)
            except OSError:
                continue
    raise RuntimeError("한글 자막 폰트를 찾지 못했습니다 (Apple SD Gothic/Noto Sans CJK/Nanum/Malgun).")


def _wrap_lines(text: str, font, max_width: int) -> list[str]:
    if font.getlength(text) <= max_width:
        return [text]
    positions = [i for i in range(1, len(text)) if text[i - 1].isspace()]
    if not positions:
        positions = list(range(1, len(text)))
    split = min(
        positions,
        key=lambda i: max(font.getlength(text[:i].rstrip()), font.getlength(text[i:].lstrip())),
    )
    return [text[:split].rstrip(), text[split:].lstrip()]


def _caption_image(text: str, font, max_width: int):
    from PIL import Image, ImageDraw
    lines = _wrap_lines(text, font, max_width)
    probe = Image.new("RGBA", (max_width + 80, 220), (0, 0, 0, 0))
    probe_draw = ImageDraw.Draw(probe)
    boxes = [probe_draw.textbbox((0, 0), line, font=font, stroke_width=1) for line in lines]
    widths = [box[2] - box[0] for box in boxes]
    heights = [box[3] - box[1] for box in boxes]
    spacing, pad_x, pad_y = 7, 22, 13
    image = Image.new(
        "RGBA",
        (int(max(widths)) + pad_x * 2, int(sum(heights)) + spacing * (len(lines) - 1) + pad_y * 2),
        (0, 0, 0, 0),
    )
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle(
        (0, 0, image.width - 1, image.height - 1),
        radius=10,
        fill=(0, 0, 0, 178),
    )
    y = pad_y
    for line, box, line_height in zip(lines, boxes, heights):
        x = (image.width - (box[2] - box[0])) / 2 - box[0]
        draw.text(
            (x, y - box[1]),
            line,
            font=font,
            fill=(255, 255, 255, 255),
            stroke_width=1,
            stroke_fill=(0, 0, 0, 255),
        )
        y += line_height + spacing
    return image


def _read_exact(stream, size: int) -> bytes | None:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            if not chunks:
                return None
            raise RuntimeError(f"자막 프레임이 중간에서 잘렸습니다 ({size - remaining}/{size} bytes).")
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)


def burn_captions(
    source: str | Path,
    cues: list[dict],
    output: str | Path,
    font_path: str | None = None,
    on_progress=None,
) -> dict:
    """MP4를 rawvideo로 흘려 Pillow 자막을 합성하고 오디오는 비트스트림 복사한다."""
    from PIL import Image

    source_path, output_path = Path(source), Path(output)
    if not source_path.exists():
        raise RuntimeError(f"자막 원본 영상이 없습니다: {source_path}")
    if not cues:
        raise RuntimeError("합성할 자막 구간이 없습니다.")

    meta = _probe_video(source_path)
    width, height, fps = meta["width"], meta["height"], meta["fps"]
    font = _load_font(height, font_path)
    overlays = [_caption_image(str(cue["text"]), font, int(width * 0.78)) for cue in cues]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temp_output = output_path.with_name(
        f".{output_path.stem}.captioning-{os.getpid()}{output_path.suffix or '.mp4'}"
    )
    decoder = subprocess.Popen([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(source_path),
        "-an", "-f", "rawvideo", "-pix_fmt", "rgb24", "-",
    ], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    encoder = subprocess.Popen([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s:v", f"{width}x{height}",
        "-r", meta["rate"], "-i", "-", "-i", str(source_path),
        "-map", "0:v:0", "-map", "1:a:0?", "-c:v", "libx264",
        "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
        "-c:a", "copy", "-shortest", "-movflags", "+faststart", str(temp_output),
    ], stdin=subprocess.PIPE, stderr=subprocess.PIPE)

    frame_size = width * height * 3
    cue_index = -1
    frames = 0
    try:
        while True:
            raw = _read_exact(decoder.stdout, frame_size)
            if raw is None:
                break
            timestamp = frames / fps
            while cue_index + 1 < len(cues) and float(cues[cue_index + 1]["start"]) <= timestamp:
                cue_index += 1
            image = Image.frombytes("RGB", (width, height), raw)
            if cue_index >= 0 and timestamp <= float(cues[cue_index]["end"]):
                overlay = overlays[cue_index]
                x = (width - overlay.width) // 2
                y = height - overlay.height - max(24, round(height * 0.05))
                image.paste(overlay, (x, y), overlay)
            encoder.stdin.write(image.tobytes())
            frames += 1
            if callable(on_progress) and frames % max(1, round(fps * 10)) == 0:
                on_progress("captions", frames, meta["frames"], f"자막 프레임 {frames}")
        encoder.stdin.close()
        decoder_error = decoder.stderr.read().decode("utf-8", errors="replace")
        encoder_error = encoder.stderr.read().decode("utf-8", errors="replace")
        decoder_code, encoder_code = decoder.wait(), encoder.wait()
        if decoder_code != 0 or encoder_code != 0 or not temp_output.exists():
            raise RuntimeError(
                f"자막 합성 실패: decode={decoder_code} {(decoder_error or '')[-200:]} "
                f"encode={encoder_code} {(encoder_error or '')[-300:]}"
            )
        temp_output.replace(output_path)
    except Exception:
        for process in (decoder, encoder):
            if process.poll() is None:
                process.terminate()
        try:
            temp_output.unlink()
        except OSError:
            pass
        raise
    finally:
        for stream in (decoder.stdout, decoder.stderr, encoder.stdin, encoder.stderr):
            try:
                if stream and not stream.closed:
                    stream.close()
            except OSError:
                pass

    return {
        "output": str(output_path),
        "frames": frames,
        "captions": len(cues),
        "fps": round(fps, 3),
        "width": width,
        "height": height,
    }
