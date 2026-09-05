"""api_music.py — 로컬 음악 스트리밍 + 앨범아트 서빙 (music-player 패키지의 서빙 면).

[self:music] 통화의 stream/image 필드가 여기를 문다:
  GET /music/stream?path=…          — HTTP Range 스트리밍 (<audio> seek 지원, api_nas get_file 선례)
  GET /music/cover?path=…&size=300  — 내장 앨범아트(mutagen) → 캐시, 폴더 아트 폴백, 없으면 SVG

보안: 등록된 소스 폴더(data/music/sources.json) 아래의 실존 파일만 서빙 —
music_core.path_allowed 화이트리스트 (api_photo 의 무제한 서빙보다 좁게).
인증: 로컬 신뢰(remote_access_guard 가 외부 요청을 세션으로 거름) — photo 와 동일.
로직 공유: music_core 를 sys.modules 공유 키로 로드(bulletin_core 선례 — 핸들러와 같은 인스턴스).
"""

import asyncio
import hashlib
import importlib.util
import os
import re
import sys
import uuid
from pathlib import Path

import anyio
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

router = APIRouter(prefix="/music", tags=["music"])

_PKG_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "packages" / "installed" / "tools" / "music-player"
_CORE = None

AUDIO_MIME = {
    "mp3": "audio/mpeg", "m4a": "audio/mp4", "aac": "audio/aac",
    "flac": "audio/flac", "ogg": "audio/ogg", "oga": "audio/ogg", "opus": "audio/ogg",
    "wav": "audio/wav", "aiff": "audio/aiff", "aif": "audio/aiff", "wma": "audio/x-ms-wma",
}

_FOLDER_ART = ("cover.jpg", "cover.png", "folder.jpg", "folder.png", "front.jpg", "albumart.jpg")

# 앨범아트 없는 곡의 플레이스홀더 (그리드가 빈 칸 대신 음표를 보이게)
_PLACEHOLDER_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 96 96">'
    '<rect width="96" height="96" rx="12" fill="#292524"/>'
    '<text x="48" y="60" font-size="40" text-anchor="middle" fill="#a8a29e">&#9834;</text></svg>'
)


def _core():
    """music_core 로드 — 핸들러와 sys.modules 공유 키로 같은 인스턴스(락·경로 검증 공유)."""
    global _CORE
    if _CORE is not None:
        return _CORE
    key = "indiebiz_music_core"
    if key in sys.modules:
        _CORE = sys.modules[key]
        return _CORE
    p = _PKG_DIR / "music_core.py"
    if not p.exists():
        raise HTTPException(status_code=503, detail="music-player 패키지가 없습니다")
    spec = importlib.util.spec_from_file_location(key, str(p))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules[key] = mod
    _CORE = mod
    return mod


def _resolve(path: str) -> str:
    core = _core()
    p = core.norm_path(path)
    if not core.path_allowed(p) or not os.path.isfile(p):
        raise HTTPException(status_code=404, detail="서빙할 수 없는 경로 (등록된 음악 폴더 밖이거나 없는 파일)")
    return p


# 브라우저(Chromium)가 직접 무는 형식. 그 밖(wma·ape 등)이거나 '큰 파일의 한 구간'(cue 앨범)이면
# ffmpeg 으로 mp3 로 바꿔 캐시해 둔다 — 캐시 파일은 일반 파일이라 Range·seek 가 그대로 산다
# (공개파일 동영상 트랜스코드 선례. 거기선 생방송 파이프였지만 음악은 곡 하나가 짧아 캐시가 낫다).
_BROWSER_OK = {"mp3", "m4a", "aac", "flac", "ogg", "oga", "opus", "wav"}
_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "music" / "transcoded"
_CACHE_CAP_BYTES = 4 * 1024 * 1024 * 1024      # 4GB 넘으면 오래된 것부터 버린다(파생물)
_TRANSCODE_TIMEOUT = 180

# ffmpeg 은 **전용** 스레드 한도에서만 돈다. 기본 스레드풀(anyio 40)에 실으면 변환이 몰릴 때
# 그 풀을 통째로 채워, 변환과 무관한 요청(FileResponse·앨범아트, 무엇보다 **재생 중인 곡의
# Range 버퍼 보충**)까지 같이 굶는다 — 2026-09-05 실측: 동시 60건 변환 중 같은 mp3 Range 보충이
# 2.4ms → 13.8s(=곡이 끊긴다). 한도를 따로 두면 대기는 async 쪽에서 일어나 공용 풀이 빈다.
_FFMPEG_LIMITER = anyio.CapacityLimiter(2)

# 같은 곡을 동시에 여러 번 요청해도(메타데이터 탐색 + 재생) 변환은 한 번만 — 캐시 키별 잠금.
_INFLIGHT: dict = {}
_INFLIGHT_GUARD = asyncio.Lock()


def _track_row(core, path: str):
    """라이브러리에서 그 곡의 행 — cue 트랙은 여기에 media_path/start 가 실려 있다."""
    try:
        with core._conn() as conn:
            return conn.execute(
                "SELECT path, media_path, start, duration, ext FROM tracks WHERE path = ?",
                (core.norm_path(path),)).fetchone()
    except Exception:
        return None


def _prune_cache() -> None:
    try:
        files = [(f, f.stat()) for f in _CACHE_DIR.glob("*.mp3")]
    except OSError:
        return
    total = sum(s.st_size for _, s in files)
    if total <= _CACHE_CAP_BYTES:
        return
    for f, s in sorted(files, key=lambda x: x[1].st_atime):   # 오래 안 쓴 것부터
        try:
            f.unlink()
            total -= s.st_size
        except OSError:
            pass
        if total <= _CACHE_CAP_BYTES * 0.8:
            break


def _cache_target(media: str, start: float, dur: float):
    """이 구간의 캐시 키와 목적지 — 변환 전에 '누가 같은 것을 굽고 있나'를 알기 위해 분리."""
    st = os.stat(media)
    key = hashlib.sha1(
        f"{media}|{st.st_mtime_ns}|{st.st_size}|{start:.3f}|{dur:.3f}".encode()
    ).hexdigest()
    return key, _CACHE_DIR / f"{key}.mp3"


def _cache_hit(out: Path) -> bool:
    if out.exists() and out.stat().st_size > 0:
        os.utime(out, None)                     # LRU 표시
        return True
    return False


def _transcoded(media: str, start: float, dur: float) -> str:
    """구간을 mp3 로 변환해 캐시하고 그 경로를 준다 (이미 있으면 그대로)."""
    import subprocess
    _key, out = _cache_target(media, start, dur)
    if _cache_hit(out):
        return str(out)
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    # 임시 파일은 시도마다 고유해야 한다 — 같은 키를 둘이 동시에 구우면 고정 이름 '.mp3.part'
    # 하나에 두 ffmpeg 이 겹쳐 써서 반쪽이 캐시로 승격된다(os.replace 는 먼저 끝난 쪽을 덮는다).
    tmp = out.with_suffix(f".{os.getpid()}.{uuid.uuid4().hex[:8]}.part")
    cmd = ["ffmpeg", "-nostdin", "-v", "error", "-y"]
    if start > 0:
        cmd += ["-ss", f"{start:.3f}"]          # 입력 앞 -ss = 빠른 탐색
    cmd += ["-i", media]
    if dur > 0:
        cmd += ["-t", f"{dur:.3f}"]
    cmd += ["-vn", "-c:a", "libmp3lame", "-b:a", "192k", "-f", "mp3", str(tmp)]
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=_TRANSCODE_TIMEOUT)
    except (OSError, subprocess.SubprocessError) as e:
        tmp.unlink(missing_ok=True)
        raise HTTPException(status_code=503, detail=f"변환 실패(ffmpeg): {e}")
    if r.returncode != 0 or not tmp.exists() or tmp.stat().st_size == 0:
        tmp.unlink(missing_ok=True)
        raise HTTPException(status_code=503,
                            detail=f"변환 실패: {(r.stderr or b'')[:200].decode('utf-8', 'replace')}")
    os.replace(tmp, out)                        # 원자 교체 — 반쪽 파일이 캐시에 남지 않게
    _prune_cache()
    return str(out)


async def _transcode_shared(media: str, start: float, dur: float) -> str:
    """변환을 전용 한도에서 한 번만 — 공용 스레드풀을 굶기지 않고, 같은 곡은 겹쳐 굽지 않는다.

    ①캐시 적중이면 ffmpeg 없이 즉답 ②같은 키를 이미 굽고 있으면 그 끝을 기다렸다가 캐시를 쓴다
    ③실제 변환은 _FFMPEG_LIMITER(전용) 위에서만 — 대기는 스레드가 아니라 async 쪽에서 한다.
    """
    _key, out = _cache_target(media, start, dur)
    if _cache_hit(out):
        return str(out)
    async with _INFLIGHT_GUARD:
        lock = _INFLIGHT.get(_key)
        if lock is None:
            lock = _INFLIGHT[_key] = asyncio.Lock()
    try:
        async with lock:
            return await anyio.to_thread.run_sync(
                _transcoded, media, start, dur, limiter=_FFMPEG_LIMITER)
    finally:
        async with _INFLIGHT_GUARD:
            if not lock.locked():
                _INFLIGHT.pop(_key, None)


@router.get("/stream")
async def stream_audio(request: Request, path: str = Query(...)):
    """음악 파일 Range 스트리밍 — <audio> 진행바 드래그(seek) 지원.

    브라우저가 못 무는 형식(wma·ape…)이거나 cue 앨범의 한 구간이면 mp3 로 변환해 캐시한 뒤
    그 파일을 같은 방식으로 서빙한다(첫 재생만 잠깐 기다리고, 이후는 원본과 동일).
    """
    core = _core()
    row = _track_row(core, path)
    media = (row["media_path"] if row and row["media_path"] else path)
    p = _resolve(media)
    ext = Path(p).suffix.lower().lstrip(".")
    seg_start = float(row["start"] or 0) if row and row["start"] is not None else 0.0
    seg_dur = float(row["duration"] or 0) if row and row["duration"] else 0.0
    if seg_start > 0 or ext not in _BROWSER_OK:   # ★아래 Range 파싱의 start 와 다른 축(구간 vs 바이트)
        p = await _transcode_shared(p, seg_start, seg_dur if seg_start > 0 else 0.0)

    mime = AUDIO_MIME.get(Path(p).suffix.lower().lstrip("."), "application/octet-stream")
    file_size = os.path.getsize(p)
    range_header = request.headers.get("range", "")
    m = re.match(r"bytes=(\d*)-(\d*)", range_header)
    if m and (m.group(1) or m.group(2)):
        start = int(m.group(1)) if m.group(1) else 0
        end = int(m.group(2)) if m.group(2) else file_size - 1
        end = min(end, file_size - 1)
        if start > end:
            raise HTTPException(status_code=416, detail="Range out of bounds")
        length = end - start + 1

        def iter_range():
            with open(p, "rb") as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(256 * 1024, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        return StreamingResponse(iter_range(), status_code=206, media_type=mime, headers={
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(length),
        })
    return FileResponse(p, media_type=mime,
                        headers={"Accept-Ranges": "bytes", "Content-Length": str(file_size)})


@router.get("/cover")
def cover_art(path: str = Query(...), size: int = Query(300)):
    """앨범아트 — 내장 태그 우선, 폴더 아트 폴백, 없으면 SVG 플레이스홀더. 캐시=data/music/covers/."""
    core = _core()
    try:
        p = _resolve(path)
    except HTTPException:
        return Response(content=_PLACEHOLDER_SVG, media_type="image/svg+xml",
                        headers={"Cache-Control": "public, max-age=3600"})
    size = max(64, min(int(size or 300), 1024))
    key = hashlib.md5(f"{p}:{size}:{os.path.getmtime(p)}".encode()).hexdigest()
    core.COVERS_DIR.mkdir(parents=True, exist_ok=True)
    cached = core.COVERS_DIR / f"{key}.jpg"
    if cached.exists():
        return FileResponse(str(cached), media_type="image/jpeg",
                            headers={"Cache-Control": "public, max-age=86400"})
    data = core.extract_cover(p)
    if not data:
        parent = Path(p).parent
        for name in _FOLDER_ART:
            art = parent / name
            if art.exists():
                data = art.read_bytes()
                break
    if data:
        try:
            import io
            from PIL import Image
            img = Image.open(io.BytesIO(data))
            img = img.convert("RGB")
            img.thumbnail((size, size))
            img.save(str(cached), "JPEG", quality=85)
            return FileResponse(str(cached), media_type="image/jpeg",
                                headers={"Cache-Control": "public, max-age=86400"})
        except Exception:
            pass
    return Response(content=_PLACEHOLDER_SVG, media_type="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=3600"})
