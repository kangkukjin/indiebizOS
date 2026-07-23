"""api_music.py — 로컬 음악 스트리밍 + 앨범아트 서빙 (music-player 패키지의 서빙 면).

[self:music] 통화의 stream/image 필드가 여기를 문다:
  GET /music/stream?path=…          — HTTP Range 스트리밍 (<audio> seek 지원, api_nas get_file 선례)
  GET /music/cover?path=…&size=300  — 내장 앨범아트(mutagen) → 캐시, 폴더 아트 폴백, 없으면 SVG

보안: 등록된 소스 폴더(data/music/sources.json) 아래의 실존 파일만 서빙 —
music_core.path_allowed 화이트리스트 (api_photo 의 무제한 서빙보다 좁게).
인증: 로컬 신뢰(remote_access_guard 가 외부 요청을 세션으로 거름) — photo 와 동일.
로직 공유: music_core 를 sys.modules 공유 키로 로드(bulletin_core 선례 — 핸들러와 같은 인스턴스).
"""

import hashlib
import importlib.util
import os
import re
import sys
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

router = APIRouter(prefix="/music", tags=["music"])

_PKG_DIR = Path(__file__).resolve().parent.parent / "data" / "packages" / "installed" / "tools" / "music-player"
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


@router.get("/stream")
async def stream_audio(request: Request, path: str = Query(...)):
    """음악 파일 Range 스트리밍 — <audio> 진행바 드래그(seek) 지원."""
    p = _resolve(path)
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
