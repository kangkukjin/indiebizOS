"""media_ops.py — 미디어 파일의 탐침·변환·HLS 사다리·자막 낱말 `[self:media]` (2026-10-05, 설치 목록 ⑩).

NAS 라우트(api_nas)에만 살던 ffprobe 탐침·내장 자막 추출을 여기로 내려 HTTP 와 IBL 이 같은 함수를 부른다.
변환(transcode)과 HLS 사다리는 긴 작업이라 ③ 접수증(task_receipts, kind=media_transcode·media_hls)을 돌려준다.
외부 자막 변환은 nas_subtitle, 진행형 변환은 base.thumbnails, 사다리는 base.hls_ladder — 제공자는 종류별 그대로.
"""
import hashlib
import json
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Optional

from common.platform_utils import find_binary
from nas_subtitle import (LANG_NAMES, SUBTITLE_EXTENSIONS, ass_to_vtt, decode_subtitle_bytes, detect_subtitles,
                          smi_to_vtt, srt_to_vtt)

FFMPEG_PATH = find_binary("ffmpeg") or "ffmpeg"
FFPROBE_PATH = find_binary("ffprobe") or "ffprobe"
BROWSER_COMPATIBLE_VIDEO = {"h264", "av1", "vp8", "vp9"}
BROWSER_COMPATIBLE_AUDIO = {"aac", "mp3", "opus", "vorbis", "flac"}
BROWSER_COMPATIBLE_CONTAINERS = {"mp4", "webm", "ogg", "mov"}
_PROBE_CACHE: dict = {}
_PROBE_CACHE_MAX = 200
_JOBS: dict = {}      # 변환·사다리 접수증 관찰 저장소(프로세스 메모리)
TRANSCODE_KIND, HLS_KIND = "media_transcode", "media_hls"


def probe(file_path: Path) -> dict:
    """ffprobe 로 코덱/컨테이너/길이/내장 자막 트랙 — mtime 캐시. 실패는 needs_transcode=True + error."""
    file_path = Path(file_path)
    key = (str(file_path), file_path.stat().st_mtime)
    if key in _PROBE_CACHE:
        return _PROBE_CACHE[key]
    try:
        r = subprocess.run([FFPROBE_PATH, "-v", "quiet", "-print_format", "json", "-show_streams", "-show_format", str(file_path)],
                           capture_output=True, text=True, timeout=15)
        if r.returncode != 0:
            return {"error": "ffprobe failed", "needs_transcode": True}
        info = json.loads(r.stdout)
    except Exception as e:  # noqa: BLE001
        return {"error": str(e), "needs_transcode": True}
    video_codec = audio_codec = None
    tracks = []
    for s in info.get("streams", []):
        kind, codec = s.get("codec_type"), (s.get("codec_name") or "").lower()
        if kind == "video" and video_codec is None:
            video_codec = codec
        elif kind == "audio" and audio_codec is None:
            audio_codec = codec
        elif kind == "subtitle":
            lang, title = s.get("tags", {}).get("language", ""), s.get("tags", {}).get("title", "")
            tracks.append({"index": len(tracks), "codec": codec, "language": lang,
                           "title": title or LANG_NAMES.get(lang, lang) or f"Track {len(tracks)}"})
    container = file_path.suffix.lower().lstrip(".")
    v_ok, a_ok, c_ok = video_codec in BROWSER_COMPATIBLE_VIDEO, (audio_codec in BROWSER_COMPATIBLE_AUDIO or audio_codec is None), container in BROWSER_COMPATIBLE_CONTAINERS
    out = {"video_codec": video_codec, "audio_codec": audio_codec, "container": container,
           "duration": float(info.get("format", {}).get("duration", 0) or 0),
           "needs_transcode": not (v_ok and a_ok and c_ok), "video_compatible": v_ok, "audio_compatible": a_ok,
           "container_compatible": c_ok, "subtitle_tracks": tracks}
    if len(_PROBE_CACHE) >= _PROBE_CACHE_MAX:
        for k in list(_PROBE_CACHE)[:_PROBE_CACHE_MAX // 2]:
            _PROBE_CACHE.pop(k, None)
    _PROBE_CACHE[key] = out
    return out


def embedded_subtitle_vtt(file_path: Path, track: int = 0) -> bytes:
    """내장 자막 트랙 → WebVTT 바이트. 없거나 실패면 LookupError."""
    r = subprocess.run([FFMPEG_PATH, "-i", str(file_path), "-map", f"0:s:{int(track)}", "-f", "webvtt", "-v", "quiet", "pipe:1"],
                       capture_output=True, timeout=30)
    if r.returncode != 0 or not r.stdout:
        raise LookupError("자막 트랙을 추출할 수 없습니다")
    return r.stdout


def external_subtitle_vtt(path: Path, smi_class: str = "KRCC") -> str:
    """외부 자막 파일(srt/vtt/ass/ssa/smi) → VTT 텍스트."""
    suffix = path.suffix.lower()
    if suffix not in SUBTITLE_EXTENSIONS:
        raise ValueError("지원하지 않는 자막 형식입니다")
    content = decode_subtitle_bytes(path.read_bytes())
    if content is None:
        raise ValueError("자막 파일 인코딩을 인식할 수 없습니다")
    if suffix == ".vtt":
        return content
    if suffix == ".srt":
        return srt_to_vtt(content)
    if suffix in (".ass", ".ssa"):
        return ass_to_vtt(content)
    return smi_to_vtt(content, lang_class=smi_class or "KRCC")


# ── 긴 작업: 변환·사다리 — ③ 접수증 ────────────────────────────────────────────

def _job_status(ref: dict) -> dict:
    import task_receipts as T
    row = _JOBS.get(ref["task_id"])
    if not row:
        return T.view(ref, T.UNKNOWN, error="모르는 미디어 작업(재기동으로 유실됐거나 다른 몸)")
    if row["state"] == T.RUNNING:
        return T.view(ref, T.RUNNING, progress={"kind": row["kind"], "src": row["src"], "started_at": row["started_at"]})
    if row["state"] == T.SUCCEEDED:
        return T.view(ref, T.SUCCEEDED, result=row.get("result"))
    return T.view(ref, T.FAILED, error=row.get("error") or "미디어 작업 실패")


def task_status(ref: dict) -> dict:
    return _job_status(ref)


def _start_job(kind: str, src: Path, fn, receipt_extra: dict) -> dict:
    import task_receipts as T
    job_id = f"{kind}_{hashlib.md5(f'{src}{time.time()}'.encode()).hexdigest()[:12]}"
    _JOBS[job_id] = {"kind": kind, "src": str(src), "state": T.RUNNING, "started_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    for old in list(_JOBS)[:-200]:
        _JOBS.pop(old, None)

    def _run():
        row = _JOBS.get(job_id)
        try:
            result = fn()
            if row is not None:
                row.update(state=T.SUCCEEDED, result=result)
        except Exception as e:  # noqa: BLE001
            if row is not None:
                row.update(state=T.FAILED, error=f"{type(e).__name__}: {e}")
    threading.Thread(target=_run, daemon=True, name=f"media-{job_id}").start()  # cc-ok: 접수증(task_receipts)으로 관측, 사멸 시 unknown
    T.register(kind, task_status)
    return T.receipt(kind, job_id, state=T.RUNNING, src=str(src), **receipt_extra,
                     message=f"{kind} 시작 — [self:task]{{op: \"wait\", ref: $r.task_ref, timeout: 240}} 로 결과 확인")


def transcode(src: Path, dst: Optional[Path] = None, timeout: int = 1800) -> dict:
    """브라우저 호환 mp4(H.264/AAC)로 변환 — base.thumbnails.transcode_video_to_mp4. 접수증 반환."""
    import thumbnails
    src = Path(src)
    dst = Path(dst) if dst else src.with_name(src.stem + ".web.mp4")

    def _do():
        ok = thumbnails.transcode_video_to_mp4(str(src), str(dst), timeout=timeout)
        if not ok:
            raise RuntimeError("ffmpeg 변환 실패")
        return {"path": str(dst), "bytes": dst.stat().st_size if dst.exists() else None}
    return _start_job(TRANSCODE_KIND, src, _do, {"dst": str(dst)})


def hls(src: Path) -> dict:
    """HLS 사다리(tiny/low/orig) 준비 — base.hls_ladder.ensure_ladder, NAS 스트림 캐시와 같은 자리. 접수증 반환."""
    import hls_ladder
    from runtime_utils import get_base_path
    src = Path(src)
    cache_dir = Path(get_base_path()) / "data" / "nas_stream_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    orig_cache = str(cache_dir / f"{hashlib.md5(str(src).encode('utf-8')).hexdigest()[:16]}.mp4")

    def _do():
        hls_ladder.ensure_ladder(str(src), orig_cache, prune_root=str(cache_dir), prune_cap=20 * 1024 * 1024 * 1024)
        return {"rungs": hls_ladder.available_rungs(orig_cache), "cache": orig_cache}
    return _start_job(HLS_KIND, src, _do, {"cache": orig_cache})


def media_op(params: dict) -> Any:
    """[self:media] — probe|transcode|hls|subtitles|subtitle."""
    op = (params.get("op") or "probe").strip()
    raw = params.get("path") or params.get("file") or ""
    if not raw:
        return {"success": False, "error": f"{op} 에는 path 가 필요합니다"}
    from runtime_utils import expand_body_path
    try:
        path = Path(expand_body_path(str(raw))).expanduser()
    except Exception:
        path = Path(str(raw)).expanduser()
    if not path.exists():
        return {"success": False, "error": f"파일 없음: {path}"}
    try:
        if op == "probe":
            return {"success": True, "path": str(path), **probe(path)}
        if op == "transcode":
            return transcode(path, params.get("dst") or None)
        if op == "hls":
            return hls(path)
        if op == "subtitles":
            rows = detect_subtitles(path)
            emb = probe(path).get("subtitle_tracks") or []
            return {"success": True, "path": str(path), "items": rows, "count": len(rows), "embedded": emb}
        if op == "subtitle":
            if params.get("track") is not None:
                return {"success": True, "path": str(path), "track": int(params["track"]),
                        "vtt": embedded_subtitle_vtt(path, int(params["track"])).decode("utf-8", errors="replace")}
            return {"success": True, "path": str(path), "vtt": external_subtitle_vtt(path, params.get("smi_class") or "KRCC")}
    except (ValueError, LookupError) as exc:
        return {"success": False, "error": str(exc)}
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "ffmpeg 시간 초과"}
    except FileNotFoundError:
        return {"success": False, "error": "ffmpeg/ffprobe 를 찾을 수 없습니다", "error_type": "capability"}
    return {"success": False, "error": f"알 수 없는 op: {op} (probe|transcode|hls|subtitles|subtitle)"}
