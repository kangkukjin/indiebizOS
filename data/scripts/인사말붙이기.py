#!/usr/bin/env python3
"""굽은 본문 나레이션을 음량 정렬하고, 첫·끝 장에 실음성 인사말을 이어 붙인다.

배경(2026-09-01 확정): 인사말은 복제가 아니라 사용자가 직접 낭독한 실음성
(outputs/narration/bookends3/{intro,outro}.wav)을 쓴다. 굽은 본문은 그대로는 작아서
(실측 −33±5 LUFS) 인사말과 음량이 갈린다 — 본문을 목표 LUFS 로 정적 게인 정렬한 뒤
이음매 숨(기본 0.3초)을 두고 붙인다. 다이나믹은 건드리지 않는다(압축·리미팅 없음).

args (stdin JSON):
  lecture_id : 강의 id (필수)
  raw_dir    : 굽은 본문 wav 폴더 (기본 <강의>/narration_raw)
  out_dir    : 배치할 폴더 (기본 <강의>/narration — deck video 가 먼저 본다)
  bookends   : 인사말 폴더 (기본 outputs/narration/bookends3)
  target_lufs: 본문 정렬 목표 (기본 -27.8 — 인사말과 같은 자)
  gap        : 이음매 숨 초 (기본 0.3)

산출: {"items":[{"title","meta","summary"}], "message":...}
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path("/Users/kangkukjin/Desktop/AI/indiebizOS")
SR = 24000


def fail(msg):
    print(json.dumps({"error": msg}, ensure_ascii=False))
    sys.exit(1)


def ff(args):
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-y"] + args,
                       capture_output=True, text=True)
    if p.returncode != 0:
        fail(f"ffmpeg 실패: {' '.join(args[:6])}\n{p.stderr[-800:]}")
    return p.stderr


def measure_lufs(path):
    """통합 라우드니스(LUFS) 실측 — ebur128."""
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path),
                        "-af", "ebur128=peak=true", "-f", "null", "-"],
                       capture_output=True, text=True)
    m = re.findall(r"I:\s+(-?[\d.]+) LUFS", p.stderr)
    if not m:
        fail(f"음량 측정 실패: {path}")
    return float(m[-1])


def duration(path):
    p = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "csv=p=0", str(path)], capture_output=True, text=True)
    return float(p.stdout.strip() or 0)


def normalize(src, dst, target):
    """정적 게인만 — 다이나믹 무손상."""
    cur = measure_lufs(src)
    gain = target - cur
    ff(["-i", str(src), "-af", f"volume={gain:.2f}dB",
        "-ar", str(SR), "-ac", "1", "-c:a", "pcm_s16le", str(dst)])
    return cur, gain


def concat(parts, dst, gap, tmp):
    """사이에 숨을 두고 이어 붙인다."""
    silence = tmp / "gap.wav"
    if not silence.exists():
        ff(["-f", "lavfi", "-i", f"anullsrc=r={SR}:cl=mono", "-t", str(gap),
            "-c:a", "pcm_s16le", str(silence)])
    seq = []
    for i, p in enumerate(parts):
        if i:
            seq.append(silence)
        seq.append(p)
    listing = tmp / "concat.txt"
    listing.write_text("".join(f"file '{p}'\n" for p in seq), encoding="utf-8")
    ff(["-f", "concat", "-safe", "0", "-i", str(listing),
        "-ar", str(SR), "-ac", "1", "-c:a", "pcm_s16le", str(dst)])


def main():
    raw = sys.stdin.read().strip()
    args = json.loads(raw) if raw else {}

    lecture_id = args.get("lecture_id")
    if not lecture_id:
        fail("lecture_id 가 필요합니다.")
    lec = Path(args.get("lecture_dir") or (ROOT / "outputs" / "lectures" / lecture_id))
    deck_path = lec / "deck.json"
    if not deck_path.exists():
        fail(f"강의를 찾을 수 없습니다: {deck_path}")
    order = json.loads(deck_path.read_text(encoding="utf-8")).get("slide_order") or []

    raw_dir = Path(args.get("raw_dir") or (lec / "narration_raw"))
    out_dir = Path(args.get("out_dir") or (lec / "narration"))
    books = Path(args.get("bookends") or (ROOT / "outputs" / "narration" / "bookends3"))
    target = float(args.get("target_lufs", -27.8))
    gap = float(args.get("gap", 0.3))

    intro, outro = books / "intro.wav", books / "outro.wav"
    for p in (intro, outro):
        if not p.exists():
            fail(f"인사말 음성이 없습니다: {p}")

    missing = [sid for sid in order if not (raw_dir / f"{sid}.wav").exists()]
    if missing:
        fail(f"굽지 않은 장이 있습니다: {', '.join(missing)} (경로 {raw_dir})")

    out_dir.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="bookend_"))
    items = []
    try:
        for sid in order:
            src = raw_dir / f"{sid}.wav"
            body = tmp / f"{sid}_norm.wav"
            cur, gain = normalize(src, body, target)
            dst = out_dir / f"{sid}.wav"
            note = f"{cur:.1f}→{target} LUFS ({gain:+.1f} dB)"
            if sid == order[0] and sid == order[-1]:
                concat([intro, body, outro], dst, gap, tmp)
                note += " + 인트로·아웃트로"
            elif sid == order[0]:
                concat([intro, body], dst, gap, tmp)
                note += " + 인트로"
            elif sid == order[-1]:
                concat([body, outro], dst, gap, tmp)
                note += " + 아웃트로"
            else:
                shutil.copy2(body, dst)
            items.append({"title": sid, "meta": f"{duration(dst):.2f}초", "summary": note})
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    total = sum(float(i["meta"][:-1]) for i in items)
    print(json.dumps({
        "items": items,
        "out_dir": str(out_dir),
        "count": len(items),
        "total_sec": round(total, 2),
        "message": (f"{len(items)}장 정렬·접합 완료 (목표 {target} LUFS, 숨 {gap}초, "
                    f"나레이션 합 {total:.1f}초) → {out_dir}"),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
