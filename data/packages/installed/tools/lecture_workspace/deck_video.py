"""deck_video.py - 덱(슬라이드 PNG + 나레이션) → MP4 렌더

handler.py 의 `[self:deck]{op:"video"}` 가 쓰는 렌더 층. 조립(덱→씬/나레이션),
상태 파일, 그리고 **별도 프로세스 기동**이 여기 모여 있다.

★왜 별도 프로세스인가 (2026-08-17 실사고):
렌더는 워커 안의 데몬 스레드로 돌았다. 그런데 다른 세션이 `backend/*.py` 를 건드리면
uvicorn 이 리로드하면서 그 스레드를 통째로 죽인다. 12장 덱이 씬 4에서 끊겼고,
상태 파일은 `building` 인 채 멈춰 있어서 **20분 동안 아무도 죽은 줄 몰랐다**.
결국 사람이 손으로 ffmpeg 를 다시 돌려 영상을 만들었다.
- 프로세스를 분리하면(start_new_session) 리로드가 렌더를 못 건드린다.
- pid 를 상태 파일에 적어두면 죽었는지가 **추측이 아니라 확인**이 된다.
- 하트비트(씬마다 상태 파일 갱신)가 있으면 어디까지 갔는지 밖에서 보인다.

자식 진입점: `python deck_video.py` (stdin 으로 {"lecture_id","opts"} JSON).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_BACKEND_DIR = str(Path(__file__).resolve().parents[5] / "backend")
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)

import lecture_store  # noqa: E402

# 하트비트가 이만큼 멎으면 죽은 것으로 본다. pid 확인이 우선이고, 이건 pid 를 못 믿을 때의 바닥.
# 가장 느린 단계(TTS 한 장·나레이션 긴 씬 인코딩)보다 넉넉해야 산 렌더를 죽었다고 오판하지 않는다.
HEARTBEAT_STALE_SEC = 300


def state_path(lecture_id: str) -> Path:
    return lecture_store.lecture_dir(lecture_id) / "video_state.json"


def write_state(lecture_id: str, state: dict) -> None:
    try:
        state = {**state, "updated_at": datetime.now().isoformat(timespec="seconds")}
        sp = state_path(lecture_id)
        tmp = sp.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(sp)     # 원자 교체 — 폴링하는 쪽이 반쪽 JSON 을 읽지 않게
    except Exception as e:
        print(f"[deck_video] 상태 저장 실패(무시): {e}")


def read_state(lecture_id: str) -> dict:
    try:
        return json.loads(state_path(lecture_id).read_text(encoding="utf-8"))
    except Exception:
        return {}


def _pid_alive(pid) -> bool | None:
    """True=살아있음 / False=없음 / None=판정 불가(pid 를 안 적은 옛 상태 파일)."""
    if not pid:
        return None
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:      # 남의 프로세스 = 살아는 있음
        return True
    except Exception:
        return None


def status(lecture_id: str) -> dict:
    """상태 파일 + 살아있는지 판정. 죽었으면 `interrupted` 로 확정해 다시 적는다.

    ★'building' 을 그대로 돌려주지 않는 게 핵심이다 — 죽은 렌더와 도는 렌더가
    구별되지 않으면 부르는 쪽은 영원히 기다린다.
    """
    st = read_state(lecture_id)
    if st.get("status") != "building":
        return st

    alive = _pid_alive(st.get("pid"))
    age = None
    try:
        age = (datetime.now() - datetime.fromisoformat(st["updated_at"])).total_seconds()
    except Exception:
        pass

    dead = (alive is False) or (alive is None and age is not None and age > HEARTBEAT_STALE_SEC)
    if not dead:
        return {**st, "alive": True, "age_sec": round(age) if age is not None else None}

    why = ("렌더 프로세스가 사라졌습니다(pid %s)" % st.get("pid")) if alive is False else \
          f"하트비트가 {round(age or 0)}초 멈췄습니다"
    st = {**st, "status": "interrupted", "error": f"{why} — 렌더가 끝나기 전에 끊겼습니다."}
    write_state(lecture_id, st)
    return st


def _load_media_handler():
    """media_producer/handler.py 차용 — create_html_video 파이프라인."""
    import importlib.util
    path = Path(__file__).resolve().parent.parent / "media_producer" / "handler.py"
    key = "_media_handler_for_lecture"
    if key in sys.modules:
        return sys.modules[key]
    spec = importlib.util.spec_from_file_location(key, str(path))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[key] = mod
    spec.loader.exec_module(mod)
    return mod


def _scene_html_from_png(png_path: Path, width: int, height: int) -> str:
    """슬라이드 PNG 한 장 → 풀블리드 HTML 씬. base64 임베드 — 파일 경로 의존 없음."""
    import base64 as _b64
    b64 = _b64.b64encode(png_path.read_bytes()).decode("ascii")
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8"></head>'
        '<body style="margin:0;background:#000">'
        f'<img src="data:image/png;base64,{b64}" '
        f'style="width:{width}px;height:{height}px;object-fit:contain;display:block">'
        "</body></html>"
    )


# ── 실강 녹음(narration_live) — 나레이션의 셋째 원천 ─────────────────────
# 우선순위: 실강 녹음 > narration/<sid>.wav(목소리 복제) > 스피커 노트 TTS.
# ★TTS 경로와 인과가 반대다: TTS 는 "글이 길면 씬도 길어진다"인데,
#   실강은 **사람이 그 슬라이드를 띄워 둔 시간이 이미 정답**이고 씬이 거기 맞춘다.
#   그래서 순서도 덱 순서가 아니라 **녹음 타임라인**을 따른다 — 발표 중 되돌아간
#   장은 영상에서도 그 자리에 다시 나온다(그게 실제로 일어난 일이다).
LIVE_DIR_NAME = "narration_live"
MIN_SEGMENT_SEC = 0.05      # 스치듯 지나간 장 — 오디오 구간이 없는 것으로 본다


def live_recording(lecture_id: str) -> dict | None:
    """narration_live/timeline.json 을 읽어 돌려준다. 없거나 깨졌으면 None(=TTS 경로)."""
    d = lecture_store.lecture_dir(lecture_id) / LIVE_DIR_NAME
    tj = d / "timeline.json"
    if not tj.exists():
        return None
    try:
        tl = json.loads(tj.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[deck_video] 녹음 타임라인 읽기 실패 — TTS 경로로 진행: {e}")
        return None
    audio = d / (tl.get("audio_file") or "")
    if not tl.get("audio_file") or not audio.exists():
        print(f"[deck_video] 녹음 오디오 없음 — TTS 경로로 진행: {audio}")
        return None
    marks = [m for m in (tl.get("marks") or []) if m.get("slide_id")]
    if not marks:
        print("[deck_video] 녹음 타임라인에 전환 기록이 없음 — TTS 경로로 진행")
        return None
    tl["_dir"], tl["_audio"], tl["marks"] = d, audio, marks
    return tl


def audio_seconds(path: Path) -> float:
    """ffprobe 로 실제 길이(초). 실패하면 0 — 부르는 쪽이 판단한다."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, timeout=120)
        return float((out.stdout or "").strip())
    except Exception:
        return 0.0


def slice_recording(tl: dict, on_progress=None) -> list:
    """녹음 한 덩어리 → 전환 시각으로 자른 슬라이드별 wav 목록.

    반환: [{slide_id, start, duration, path}] — 타임라인 순서 그대로.
    같은 슬라이드를 두 번 띄웠으면 구간도 두 개다(파일명에 순번을 넣어 안 덮는다).
    """
    d, audio = tl["_dir"], tl["_audio"]
    total = float(tl.get("duration_sec") or 0) or audio_seconds(audio)
    marks = sorted(tl["marks"], key=lambda m: float(m.get("t") or 0))
    segs = []
    for i, m in enumerate(marks):
        sid = str(m.get("slide_id"))
        start = max(0.0, float(m.get("t") or 0))
        end = float(marks[i + 1].get("t") or 0) if i + 1 < len(marks) else total
        if end - start <= MIN_SEGMENT_SEC:
            continue
        out = d / f"seg_{i:03d}_{sid}.wav"
        if on_progress:
            on_progress("slice", i + 1, len(marks), f"녹음 분할 {sid}")
        # ★-i 뒤의 -ss = 출력 시킹(정확). 입력 시킹은 빠르지만 키프레임에 붙어 어긋난다.
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", str(audio), "-ss", f"{start:.3f}", "-to", f"{end:.3f}",
             "-vn", "-ac", "1", "-ar", "44100", str(out)],
            capture_output=True, text=True, timeout=1800)
        if r.returncode != 0 or not out.exists():
            raise RuntimeError(f"녹음 분할 실패({sid}): {(r.stderr or '')[-300:]}")
        segs.append({"slide_id": sid, "start": start,
                     "duration": audio_seconds(out) or (end - start), "path": str(out)})
    if not segs:
        raise RuntimeError("녹음 타임라인에서 쓸 수 있는 구간이 하나도 나오지 않았습니다.")
    return segs


def build(lecture_id: str, opts: dict, on_progress=None) -> dict:
    """조립 + 렌더 본체 (동기). 자식 프로세스와 wait:true 양쪽에서 호출."""
    width, height = int(opts.get("width") or 1280), int(opts.get("height") or 720)
    deck = lecture_store.read_deck(lecture_id)
    lecture_dir_path = lecture_store.lecture_dir(lecture_id)
    order = deck.get("slide_order") or []
    slides = deck.get("slides") or {}

    scenes, narrations, missing_notes, skipped = [], [], [], []
    preset_audio = []
    live_info: dict = {}

    def _scene(png_path: Path, duration: float) -> None:
        scenes.append({
            "html": _scene_html_from_png(png_path, width, height),
            "duration": float(duration),
            # ★덱 슬라이드는 정지 PNG 한 장이다 — 렌더러가 재볼 필요가 없다(프로브 비용 0).
            "static": True,
        })

    live = live_recording(lecture_id)
    if live:
        # ── 실강 녹음 경로 — 씬 길이도 순서도 녹음 타임라인이 정한다 ──
        segs = slice_recording(live, on_progress=on_progress)
        for seg in segs:
            meta = slides.get(seg["slide_id"]) or {}
            png = lecture_dir_path / (meta.get("png_file") or "")
            if not meta.get("png_file") or not png.exists():
                skipped.append(seg["slide_id"])
                continue
            _scene(png, seg["duration"])
            narrations.append("")                    # TTS 를 타지 않는다
            preset_audio.append(seg["path"])
        shown = {s["slide_id"] for s in segs}
        live_info = {
            "live_recording": True,
            "recording_sec": round(float(live.get("duration_sec") or 0), 2),
            "segments": [{"slide_id": s["slide_id"], "start": round(s["start"], 2),
                          "duration": round(s["duration"], 2)} for s in segs],
            # 녹음 중 한 번도 안 띄운 장 — 영상에 안 나온다(빠뜨린 게 아니라 안 보여준 것).
            "unrecorded": [sid for sid in order if sid not in shown],
        }
    else:
        # narration/<slide_id>.wav 가 있으면 그 파일이 TTS 를 이긴다 — 목소리 복제로 구운
        # 내 목소리 나레이션을 넣는 자리(가이드 voice_narration.md, 스크립트 '나레이션생성').
        narration_dir = lecture_dir_path / "narration"
        for sid in order:
            meta = slides.get(sid) or {}
            png = lecture_dir_path / (meta.get("png_file") or "")
            if not meta.get("png_file") or not png.exists():
                skipped.append(sid)
                continue
            _scene(png, float(opts.get("duration_per_scene") or 5))
            note = (meta.get("speaker_note") or "").strip()
            narrations.append(note)      # 빈 노트 = 무나레이션 씬 (html_video 가 기본 길이로 처리)
            ready = narration_dir / f"{sid}.wav"
            preset_audio.append(str(ready) if ready.exists() else None)
            if not note and not ready.exists():
                missing_notes.append(sid)

    if not scenes:
        raise RuntimeError("렌더할 슬라이드가 없습니다 (PNG 미존재).")

    mh = _load_media_handler()
    video_dir = lecture_dir_path / "video"
    video_dir.mkdir(exist_ok=True)
    tool_input = {
        "scenes": scenes,
        "narration_texts": narrations,
        "narration_audio_paths": preset_audio,
        # 화자·엔진 기본값을 여기서 박지 않는다 — 미지정이면 media_producer 의 엔진 기본
        # (2026-08-10부터 Gemini/Charon)이 이긴다. 옛날엔 Edge 화자가 박혀 있어서
        # 기본 엔진을 바꿔도 강의 영상만 옛 목소리로 남았다.
        "rate": opts.get("rate") or "+0%",
        # ★실강 녹음일 때 전환·여백은 그대로 '어긋남'이 된다: xfade 는 씬을 겹치고
        #   NARRATION_PADDING 은 씬마다 0.5초를 더한다 — 둘 다 원래 발표의 타이밍을 깬다.
        #   그래서 기본을 뒤집는다(사용자가 transition 을 명시하면 그건 존중).
        "transition": opts.get("transition") or ("none" if live_info else "fade"),
        "narration_padding": 0.0 if live_info else None,
        "output_filename": opts.get("output_filename") or "lecture_video.mp4",
        "width": width, "height": height,
        "on_progress": on_progress,
    }
    for k in ("voice", "engine", "style"):   # 미지정이면 안 실어야 엔진 기본이 이긴다
        if opts.get(k):
            tool_input[k] = opts[k]
    if opts.get("bgm_path"):
        tool_input["bgm_path"] = opts["bgm_path"]
    result_msg = mh.create_html_video(tool_input, str(video_dir))
    if not str(result_msg).startswith("HTML 동영상 제작 완료"):
        raise RuntimeError(str(result_msg)[:500])
    # "HTML 동영상 제작 완료: <경로> | 씬 전환: fade (0.5초)" → 경로만.
    # ★" | " 를 안 자르면 output 이 경로가 아니게 된다(2026-08-17 실측 — 전환 정보가 붙어 왔다).
    output = str(result_msg).split(":", 1)[1].strip().split(" | ")[0].split(" (")[0]
    return {
        "output": output, "slides": len(scenes),
        "narrated": len(scenes) - len(missing_notes),
        "preset_narration": sum(1 for p in preset_audio if p),   # 미리 구운 오디오를 쓴 장 수
        "missing_notes": missing_notes, "skipped": skipped,
        **live_info,
    }


def spawn(lecture_id: str, opts: dict) -> dict:
    """렌더를 별도 프로세스로 띄운다. 백엔드가 리로드돼도 이 프로세스는 살아남는다."""
    lecture_dir_path = lecture_store.lecture_dir(lecture_id)
    video_dir = lecture_dir_path / "video"
    video_dir.mkdir(exist_ok=True)
    log_path = video_dir / "render.log"

    env = dict(os.environ)
    # 부모의 import 경로를 그대로 물려준다 — 백엔드는 .venv 를 sys.path 로 붙여 쓰므로
    # PYTHONPATH 없이 띄우면 자식이 렌더·오디오 라이브러리를 못 찾는다.
    # (이 패키지 자체는 그 라이브러리를 직접 import 하지 않는다 — 차용은 media_producer 쪽.
    #  능력 메타의 light/heavy 는 파일 텍스트 스캔이라 여기 이름을 적으면 heavy 로 뒤집힌다.)
    env["PYTHONPATH"] = os.pathsep.join(p for p in sys.path if p)

    logf = open(log_path, "a", encoding="utf-8")
    logf.write(f"\n===== {datetime.now().isoformat(timespec='seconds')} 렌더 시작 ({lecture_id}) =====\n")
    logf.flush()
    proc = subprocess.Popen(
        [sys.executable, os.path.abspath(__file__)],
        stdin=subprocess.PIPE, stdout=logf, stderr=subprocess.STDOUT,
        env=env, cwd=str(lecture_dir_path),
        start_new_session=True,      # ★프로세스 그룹 분리 = 부모(워커)가 죽어도 안 딸려간다
    )
    proc.stdin.write(json.dumps({"lecture_id": lecture_id, "opts": opts},
                                ensure_ascii=False).encode("utf-8"))
    proc.stdin.close()
    write_state(lecture_id, {"status": "building", "stage": "start", "pid": proc.pid,
                             "log": str(log_path)})
    return {"pid": proc.pid, "log": str(log_path)}


def _child_main() -> int:
    payload = json.loads(sys.stdin.read() or "{}")
    lecture_id = payload.get("lecture_id") or ""
    opts = payload.get("opts") or {}
    pid = os.getpid()

    def _hb(stage, index=0, total=0, detail=""):
        write_state(lecture_id, {"status": "building", "pid": pid, "stage": stage,
                                 "index": index, "total": total, "detail": detail})
        print(f"[deck_video] {stage} {index}/{total} {detail}", flush=True)

    write_state(lecture_id, {"status": "building", "pid": pid, "stage": "start"})
    try:
        result = build(lecture_id, opts, on_progress=_hb)
    except Exception as e:
        import traceback
        traceback.print_exc()
        write_state(lecture_id, {"status": "error", "pid": pid, "error": str(e)[:500]})
        return 1
    write_state(lecture_id, {"status": "done", "pid": pid, **result})
    print(f"[deck_video] 완료: {result.get('output')}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(_child_main())
