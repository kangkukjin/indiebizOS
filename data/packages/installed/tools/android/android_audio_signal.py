"""파일 경로·구간·FFmpeg 측정. 원본을 수정하지 않고 채널별 신호를 검사한다."""
import hashlib
import json
import math
import re
import shutil
import subprocess
from pathlib import Path


def run_media(args, timeout=60):
    binary = shutil.which(args[0])
    if not binary:
        raise ValueError(f"{args[0]}가 설치되어 있지 않습니다. 파일 오디오 처리에 필요합니다")
    try:
        result = subprocess.run([binary, *args[1:]], capture_output=True, timeout=max(1, timeout))
    except subprocess.TimeoutExpired:
        raise ValueError("오디오 파일 처리 시간 초과") from None
    if result.returncode:
        raise ValueError("오디오 디코딩/변환 실패: " + result.stderr.decode(errors="replace")[-500:])
    return result


def probe(path):
    result = run_media(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_streams",
                        "-show_format", "-of", "json", str(path)])
    data = json.loads(result.stdout)
    streams = data.get("streams") or []
    if not streams:
        raise ValueError("파일에 오디오 트랙이 없습니다")
    stream = streams[0]
    duration = number(stream.get("duration") or data.get("format", {}).get("duration"), "duration")
    if duration <= 0:
        raise ValueError("오디오 길이를 확인할 수 없습니다")
    return {"duration": duration, "sample_rate": int(stream["sample_rate"]),
            "channels": int(stream["channels"]), "codec": stream.get("codec_name")}


def number(value, name):
    if isinstance(value, bool):
        raise ValueError(f"{name}은 초 단위 수여야 합니다")
    try:
        result = float(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name}은 유한수여야 합니다") from None
    if not math.isfinite(result):
        raise ValueError(f"{name}은 유한수여야 합니다")
    return result


def ranges(args, duration):
    requested = args.get("ranges")
    if requested is not None and ("start" in args or "end" in args):
        raise ValueError("ranges와 start/end를 함께 지정할 수 없습니다")
    if requested is None:
        requested = [{"start": args.get("start", 0), "end": args.get("end", duration)}]
    if not isinstance(requested, list) or not requested or len(requested) > 100:
        raise ValueError("ranges는 1~100개 {start,end} 구간 배열이어야 합니다")
    result = []
    for row in requested:
        if not isinstance(row, dict):
            raise ValueError("각 구간은 {start,end}여야 합니다")
        start, end = number(row.get("start", 0), "start"), number(row.get("end", duration), "end")
        if not 0 <= start < end <= duration + 0.05:
            raise ValueError(f"구간은 0 <= start < end <= 파일 길이({duration:.3f}초)를 만족해야 합니다")
        result.append((start, min(end, duration)))
    # 겹친 구간을 중복 청취/과금하지 않는다.
    merged = []
    for start, end in sorted(result):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(end, merged[-1][1]))
        else:
            merged.append((start, end))
    return merged


def file_hash(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def clip(path, output, start, end, timeout):
    # 언어/내용 이해용 사본만 mono FLAC. 신호 검사는 아래에서 원본 채널을 직접 읽는다.
    run_media(["ffmpeg", "-v", "error", "-nostdin", "-y", "-ss", str(start), "-i", str(path),
               "-t", str(end - start), "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "24000",
               "-sample_fmt", "s16", "-c:a", "flac", str(output)], timeout)


def inspect_signal(path, start, end, metadata, timeout=90):
    result = run_media(["ffmpeg", "-hide_banner", "-nostdin", "-ss", str(start), "-i", str(path),
                        "-map", "0:a:0", "-vn",
                        "-af", f"atrim=duration={end - start},asetpts=PTS-STARTPTS,"
                        "silencedetect=noise=-50dB:d=0.3,astats=metadata=0:reset=0",
                        "-f", "null", "-"], timeout)
    text = result.stderr.decode(errors="replace")
    silences, opened = [], None
    for line in text.splitlines():
        match = re.search(r"silence_start: ([\d.e+-]+)", line)
        if match:
            opened = float(match[1])
        match = re.search(r"silence_end: ([\d.e+-]+)", line)
        if match and opened is not None:
            silences.append({"start": start + opened, "end": start + min(float(match[1]), end - start)})
            opened = None
    if opened is not None:
        silences.append({"start": start + opened, "end": end})
    channels, current = [], None
    for line in text.splitlines():
        channel = re.search(r"Channel: (\d+)", line)
        if channel:
            current = {"channel": int(channel[1])}
            channels.append(current)
        elif "Overall" in line:
            current = None
        elif current is not None:
            for label, key in (("Peak level dB", "peak_dbfs"), ("RMS level dB", "rms_dbfs"),
                               ("Max difference", "max_sample_difference")):
                match = re.search(re.escape(label) + r": (\S+)", line)
                if match:
                    value = float(match[1])
                    current[key] = value if math.isfinite(value) else None
    if len(channels) != metadata["channels"] or any("peak_dbfs" not in c for c in channels):
        raise ValueError("FFmpeg가 채널별 신호 측정값을 반환하지 않았습니다")
    return {"start": start, "end": end, "kind": "signal", "channels": channels,
            "silences": silences, "silence_threshold_dbfs": -50, "silence_min_s": 0.3,
            "note": "무음은 신호 임계값 판정입니다. 대화 유무·음악의 자연스러움은 판정하지 않습니다."}
