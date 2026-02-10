"""
nas_music.py - NAS 음악 스트리밍 모듈
YouTube 검색 및 오디오 스트리밍

api_nas.py에서 분리됨
"""

import asyncio
import re

from fastapi import HTTPException, Request, Query
from fastapi.responses import StreamingResponse


# ============ 유틸리티 ============

def _search_youtube(query: str, count: int = 5) -> list:
    """yt-dlp로 YouTube 검색"""
    import yt_dlp
    results = []
    with yt_dlp.YoutubeDL({
        "quiet": True, "no_warnings": True,
        "extract_flat": True,
        "default_search": f"ytsearch{count}",
    }) as ydl:
        info = ydl.extract_info(f"ytsearch{count}:{query}", download=False)
        for entry in (info.get("entries") or []):
            vid = entry.get("id", "")
            if vid.startswith("UC") or entry.get("_type") == "playlist":
                continue
            dur = entry.get("duration") or 0
            dur_str = f"{int(dur)//60}:{int(dur)%60:02d}" if dur > 0 else ""
            results.append({
                "video_id": vid,
                "title": entry.get("title", ""),
                "channel": entry.get("uploader", entry.get("channel", "")),
                "duration": dur_str,
                "duration_seconds": int(dur),
                "thumbnail": f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
            })
    return results


def _detect_audio_mime(header: bytes) -> str:
    """스트림 첫 바이트의 매직 바이트로 오디오 포맷 감지"""
    if header[:4] == b'\x1a\x45\xdf\xa3':       # EBML header → WebM/MKV
        return "audio/webm"
    if len(header) >= 8 and header[4:8] == b'ftyp':  # MP4/M4A
        return "audio/mp4"
    if header[:4] == b'OggS':                     # Ogg (Opus/Vorbis)
        return "audio/ogg"
    if header[:3] == b'ID3' or header[:2] in (b'\xff\xfb', b'\xff\xf3', b'\xff\xf2'):
        return "audio/mpeg"                       # MP3
    return "audio/webm"  # fallback


# ============ API 핸들러 ============

async def api_music_search(request: Request, q: str, count: int, STREAM_CHUNK_SIZE: int):
    """YouTube 음악 검색"""
    try:
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, _search_youtube, q, min(count, 10))
        return {"results": results, "query": q}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"검색 실패: {str(e)}")


async def api_music_stream(request: Request, video_id: str, STREAM_CHUNK_SIZE: int):
    """YouTube 오디오 스트리밍 (yt-dlp → stdout → 클라이언트)

    yt-dlp를 1회만 호출하고, 첫 청크의 매직 바이트로 포맷을 감지하여
    올바른 MIME 타입으로 스트리밍. Windows/Mac 모두 동작.
    """
    if not re.match(r'^[a-zA-Z0-9_-]{11}$', video_id):
        raise HTTPException(status_code=400, detail="잘못된 video_id")

    url = f"https://www.youtube.com/watch?v={video_id}"
    cmd = [
        "yt-dlp",
        "-f", "bestaudio[ext=webm]/bestaudio",
        "-o", "-",
        "--no-playlist",
        "--no-warnings",
        url,
    ]
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )

        # 첫 청크를 읽어서 매직 바이트로 포맷 감지
        first_chunk = await process.stdout.read(STREAM_CHUNK_SIZE)
        if not first_chunk:
            if process.returncode is None:
                process.kill()
            raise HTTPException(status_code=502, detail="오디오 데이터 없음")

        content_type = _detect_audio_mime(first_chunk)

        async def audio_gen():
            try:
                yield first_chunk  # 이미 읽은 첫 청크 먼저 전송
                while True:
                    chunk = await process.stdout.read(STREAM_CHUNK_SIZE)
                    if not chunk:
                        break
                    yield chunk
            finally:
                if process.returncode is None:
                    process.kill()
                try:
                    await process.wait()
                except Exception:
                    pass

        return StreamingResponse(
            audio_gen(),
            media_type=content_type,
            headers={"Cache-Control": "no-cache"},
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"스트리밍 실패: {str(e)}")
