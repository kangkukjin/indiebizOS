#!/usr/bin/env python3
"""영상의 정적 게인만 조절한다. args: src, dst, target_lufs(-21), max_true_peak(-1), inspect.

비디오는 복사하고 오디오만 AAC로 인코딩한다. 재인코딩 후 true peak를 다시 측정해
상한을 넘으면 게인을 낮춰 재시도한다. 압축·리미터·재생속도 변경은 하지 않는다.
"""
import json
import math
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
import boot_paths  # noqa: E402,F401


def measure(path):
    probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration,size",
                            "-of", "json", str(path)], capture_output=True, text=True, check=True)
    result = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
                             "-af", "ebur128=peak=true", "-f", "null", "-"],
                            capture_output=True, text=True, check=True)
    levels = re.findall(r"I:\s+(-?[\d.]+) LUFS", result.stderr)
    peaks = re.findall(r"Peak:\s+(-?[\d.]+) dBFS", result.stderr)
    if not levels or not peaks:
        raise ValueError("유한한 음량·true peak를 측정할 수 없습니다")
    meta = json.loads(probe.stdout)["format"]
    return {"lufs": float(levels[-1]), "true_peak": float(peaks[-1]),
            "seconds": float(meta["duration"]), "bytes": int(meta["size"])}


def align(args):
    src = (ROOT / args["src"]).resolve()
    before = measure(src)
    if args.get("inspect"):
        return {"success": True, "items": [{"path": str(src), **before}]}
    dst = (ROOT / args["dst"]).resolve()
    if src == dst:
        raise ValueError("src와 dst는 달라야 합니다")
    target, ceiling = float(args.get("target_lufs", -21)), float(args.get("max_true_peak", -1))
    if not all(math.isfinite(x) for x in (target, ceiling)) or ceiling > 0:
        raise ValueError("목표 음량은 유한수, true peak 상한은 0 dBTP 이하여야 합니다")
    gain = min(target - before["lufs"], ceiling - before["true_peak"])
    dst.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="audio_gain_", dir=dst.parent) as tmp:
        candidate = Path(tmp) / "aligned.mp4"
        for _ in range(3):
            subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src),
                            "-map", "0:v:0", "-map", "0:a:0", "-c:v", "copy", "-af", f"volume={gain:.3f}dB",
                            "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(candidate)],
                           capture_output=True, text=True, check=True)
            after = measure(candidate)
            if after["true_peak"] <= ceiling:
                candidate.replace(dst)
                break
            gain -= after["true_peak"] - ceiling + 0.1
        else:
            raise ValueError("재인코딩 후 true peak 상한을 충족하지 못했습니다")
    result = {"success": True, "items": [{"path": str(dst), **after}], "before": before,
              "gain_db": round(gain, 3), "target_lufs": target,
              "target_shortfall_db": round(max(0, target - after["lufs"]), 1),
              "max_true_peak": ceiling, "method": "static_gain"}
    dst.with_suffix(".audio.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


if __name__ == "__main__":
    try:
        print(json.dumps(align(json.loads(sys.stdin.read() or "{}")), ensure_ascii=False))
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        print(json.dumps({"success": False, "error": str(exc)}, ensure_ascii=False))
        raise SystemExit(1)
