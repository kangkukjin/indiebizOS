#!/usr/bin/env python3
"""훈련42 산출물 반출·실측 검증. 결과 JSON을 stdout과 work/verify_result.json에 남긴다."""
import json, re, shutil, subprocess, sys, hashlib
from pathlib import Path
from PIL import Image

AGENT = Path("/Users/kangkukjin/Desktop/AI/indiebizOS/outputs/long_sentence_imagination/2026-10-09_42회차/agent")
INPUT = AGENT.parent / "input" / "scenes.json"
LEC = Path("/Users/kangkukjin/Desktop/AI/indiebizOS/outputs/lectures/hunryeon42-dogribai-dongne-surigyosil")
SRC_MP4 = LEC / "video" / "suri_class_promo.mp4"
SRC_ASS = LEC / "video" / "suri_class_promo.captions.ass"
WORK = AGENT / "work"
FRAMES = AGENT / "frames"
MP4 = AGENT / "suri_class_promo.mp4"
ASS = AGENT / "suri_class_promo.captions.ass"
SRT = AGENT / "suri_class_promo.captions.srt"
W, H, SAFE_Y = 1280, 720, 540


def run(cmd):
    return subprocess.run(cmd, capture_output=True, text=True, check=True)


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def t2s(t):
    h, m, s = t.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def srt_time(sec):
    ms = round(sec * 1000)
    h, ms = divmod(ms, 3600000)
    m, ms = divmod(ms, 60000)
    s, ms = divmod(ms, 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def main():
    FRAMES.mkdir(parents=True, exist_ok=True)
    shutil.copy2(SRC_MP4, MP4)
    shutil.copy2(SRC_ASS, ASS)
    scenes = json.loads(INPUT.read_text())["scenes"]
    deck = json.loads((LEC / "deck.json").read_text())
    order = deck["slide_order"]
    deck_notes = [deck["slides"][sid].get("speaker_note", "") for sid in order]
    deck_titles = [deck["slides"][sid].get("title", "") for sid in order]

    # 1) ffprobe
    probe = json.loads(run(["ffprobe", "-v", "error", "-show_entries",
        "format=duration,format_name,size,bit_rate:stream=index,codec_type,codec_name,profile,width,height,pix_fmt,r_frame_rate,sample_rate,channels,channel_layout,duration,bit_rate",
        "-of", "json", str(MP4)]).stdout)
    streams = probe["streams"]
    v = [s for s in streams if s["codec_type"] == "video"]
    a = [s for s in streams if s["codec_type"] == "audio"]
    dur = float(probe["format"]["duration"])

    # 2) 무음 구간 (나레이션 사이 간격 — 배경음악이 있으면 무음이 거의 없다)
    sd = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(MP4), "-af", "silencedetect=noise=-45dB:d=0.25", "-f", "null", "-"], capture_output=True, text=True).stderr
    starts = [float(x) for x in re.findall(r"silence_start: ([0-9.]+)", sd)]
    ends = [float(x) for x in re.findall(r"silence_end: ([0-9.]+)", sd)]
    silences = [{"start": round(s, 3), "end": round(e, 3) if i < len(ends) else None} for i, (s, e) in enumerate(zip(starts, ends + [None] * (len(starts) - len(ends))))]
    vol = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(MP4), "-af", "volumedetect", "-f", "null", "-"], capture_output=True, text=True).stderr
    mean_db = re.search(r"mean_volume: (-?[0-9.]+) dB", vol)
    max_db = re.search(r"max_volume: (-?[0-9.]+) dB", vol)

    # 3) ASS 파싱 → SRT → note 대조(정규화 없음, 공백 1칸으로만 이음)
    cues = []
    for line in ASS.read_text(encoding="utf-8").splitlines():
        if line.startswith("Dialogue:"):
            parts = line.split(",", 9)
            cues.append({"start": t2s(parts[1]), "end": t2s(parts[2]), "text": parts[9].replace("\\N", "\n")})
    srt = []
    for i, c in enumerate(cues, 1):
        srt.append(f"{i}\n{srt_time(c['start'])} --> {srt_time(c['end'])}\n{c['text']}\n")
    SRT.write_text("\n".join(srt), encoding="utf-8")

    # 장면별로 큐를 순서대로 소비하며 note와 정확 일치 확인
    compare, ci = [], 0
    for idx, sc in enumerate(scenes):
        note = sc["note"]
        taken, joined = [], ""
        while ci < len(cues) and len(joined) < len(note):
            taken.append(ci)
            joined = " ".join(cues[k]["text"] for k in taken)
            ci += 1
        compare.append({
            "key": sc["key"], "cue_indices": [k + 1 for k in taken], "joined": joined,
            "equals_scene_note": joined == note,
            "deck_note_equals_scene_note": deck_notes[idx] == note if idx < len(deck_notes) else False,
            "deck_title_equals_scene_title": deck_titles[idx] == sc["title"] if idx < len(deck_titles) else False,
            "scene_start": round(cues[taken[0]]["start"], 2) if taken else None,
            "caption_end": round(cues[taken[-1]]["end"], 2) if taken else None,
        })
    leftover = len(cues) - ci
    # SRT 재독 대조
    srt_texts = re.findall(r"\d+\n[0-9:,]+ --> [0-9:,]+\n(.*?)\n(?:\n|$)", SRT.read_text(encoding="utf-8"), re.S)
    srt_match = srt_texts == [c["text"] for c in cues]

    # 장면 구간(다음 장면 시작까지, 마지막은 영상 끝)
    for i, c in enumerate(compare):
        nxt = compare[i + 1]["scene_start"] if i + 1 < len(compare) else dur
        c["scene_end"] = round(nxt, 2)
        c["scene_span_sec"] = round(nxt - c["scene_start"], 2)

    # 4) 슬라이드 PNG 하단 25% 검사(원본 렌더)
    slide_checks = []
    for sid in order:
        img = Image.open(LEC / "slides" / f"{sid}.png").convert("RGB")
        bg = img.getpixel((640, 700))
        band = img.crop((0, SAFE_Y, img.width, img.height))
        diff = sum(1 for px in band.getdata() if max(abs(px[j] - bg[j]) for j in range(3)) > 12)
        top = img.crop((0, 0, img.width, SAFE_Y))
        content = sum(1 for px in top.getdata() if max(abs(px[j] - bg[j]) for j in range(3)) > 40)
        slide_checks.append({"slide_id": sid, "size": list(img.size), "bg_rgb": list(bg), "bottom_nonbg_pixels": diff, "top_content_pixels": content})

    # 5) 큐마다 중간 프레임 추출 → 자막 영역 측정(해당 슬라이드 배경색과 다른 행/열)
    frames = []
    for i, c in enumerate(cues):
        t = (max(c["start"], cues[i - 1]["end"] if i else 0) + c["end"]) / 2
        scene_idx = next(k for k, s in enumerate(compare) if (i + 1) in s["cue_indices"])
        out = FRAMES / f"cue{i+1:02d}_{compare[scene_idx]['key']}_{t:.2f}s.png"
        run(["ffmpeg", "-y", "-v", "error", "-ss", f"{t:.3f}", "-i", str(MP4), "-frames:v", "1", str(out)])
        fr = Image.open(out).convert("RGB")
        bg = slide_checks[scene_idx]["bg_rgb"]
        rows = [y for y in range(fr.height) if y >= 400 and any(max(abs(fr.getpixel((x, y))[j] - bg[j]) for j in range(3)) > 40 for x in range(0, fr.width, 2))]
        # 자막 박스 = 하단 쪽 연속 행 덩어리
        cap_rows = [y for y in rows if y >= 500]
        cols = []
        if cap_rows:
            y0, y1 = min(cap_rows), max(cap_rows)
            cols = [x for x in range(fr.width) if any(max(abs(fr.getpixel((x, y))[j] - bg[j]) for j in range(3)) > 40 for y in range(y0, y1 + 1, 2))]
        frames.append({"cue": i + 1, "scene": compare[scene_idx]["key"], "time": round(t, 2), "frame": str(out),
                       "size": list(fr.size), "caption_top_y": min(cap_rows) if cap_rows else None,
                       "caption_bottom_y": max(cap_rows) if cap_rows else None,
                       "caption_left_x": min(cols) if cols else None, "caption_right_x": max(cols) if cols else None,
                       "caption_in_bottom_25pct": bool(cap_rows) and min(cap_rows) >= SAFE_Y,
                       "caption_inside_frame": bool(cols) and min(cols) > 0 and max(cols) < fr.width - 1 and max(cap_rows) < fr.height - 1})

    result = {
        "files": {"mp4": str(MP4), "mp4_sha256": sha(MP4), "mp4_bytes": MP4.stat().st_size,
                  "ass": str(ASS), "srt": str(SRT), "source_mp4_sha256": sha(SRC_MP4)},
        "probe": probe, "duration_sec": round(dur, 3), "video_streams": len(v), "audio_streams": len(a),
        "checks": {
            "res_1280x720": bool(v) and v[0]["width"] == W and v[0]["height"] == H,
            "h264": bool(v) and v[0]["codec_name"] == "h264", "aac": bool(a) and a[0]["codec_name"] == "aac",
            "one_video_one_audio": len(v) == 1 and len(a) == 1, "duration_20_70": 20 <= dur <= 70,
            "all_notes_match_captions": all(c["equals_scene_note"] for c in compare) and leftover == 0,
            "deck_notes_match": all(c["deck_note_equals_scene_note"] for c in compare),
            "deck_titles_match": all(c["deck_title_equals_scene_title"] for c in compare),
            "srt_matches_ass": srt_match,
            "slides_bottom_empty": all(s["bottom_nonbg_pixels"] == 0 for s in slide_checks),
            "captions_in_bottom_25pct": all(f["caption_in_bottom_25pct"] for f in frames),
            "captions_inside_frame": all(f["caption_inside_frame"] for f in frames),
        },
        "scene_order": [d for d in order], "compare": compare, "leftover_cues": leftover,
        "cues": [{"n": i + 1, "start": round(c["start"], 2), "end": round(c["end"], 2), "text": c["text"]} for i, c in enumerate(cues)],
        "silences": silences, "mean_volume_db": float(mean_db.group(1)) if mean_db else None, "max_volume_db": float(max_db.group(1)) if max_db else None,
        "slide_checks": slide_checks, "frames": frames,
    }
    (WORK / "verify_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
