"""
nas_music.py - NAS 음악 스트리밍 모듈
YouTube 검색 및 오디오 스트리밍

api_nas.py에서 분리됨
"""

import asyncio
import re
import time
import threading

from fastapi import HTTPException, Request, Query
from fastapi.responses import StreamingResponse


# ============ 오디오 URL 캐시 (구간 탐색용 Range 프록시) ============
# 예전엔 yt-dlp stdout 을 그대로 파이프해서 스트리밍했는데, 그러면 Content-Length·
# Accept-Ranges 가 없어 브라우저가 곡 duration 을 모르고 중간 지점으로 seek 도 못 한다.
# 대신 direct 오디오 URL(googlevideo)을 해소해두고 Range 헤더를 그대로 중계하면
# 206 Partial + Content-Range 가 흘러 <audio> 진행바 드래그(중간 건너뛰기)가 동작한다.
# (포털 tune 프록시와 같은 방식.)
_AUDIO_URL_CACHE: dict = {}      # video_id -> (googlevideo_url, expire_ts)
_AUDIO_URL_LOCK = threading.Lock()


def _audio_cache_put(vid: str, url: str) -> None:
    m = re.search(r"[?&]expire=(\d{10})", url)
    exp = int(m.group(1)) if m else time.time() + 3600
    with _AUDIO_URL_LOCK:
        _AUDIO_URL_CACHE[vid] = (url, min(exp, time.time() + 5 * 3600))
        if len(_AUDIO_URL_CACHE) > 200:
            now = time.time()
            for k in [k for k, (_, e) in _AUDIO_URL_CACHE.items() if e < now]:
                _AUDIO_URL_CACHE.pop(k, None)


def _audio_cache_get(vid: str):
    with _AUDIO_URL_LOCK:
        v = _AUDIO_URL_CACHE.get(vid)
    if v and v[1] > time.time() + 60:
        return v[0]
    return None


def _resolve_audio_url(vid: str) -> str:
    """video_id → direct 오디오 스트림 URL. m4a 우선(iOS 사파리 호환 + moov 로 duration 확정)."""
    import yt_dlp
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True,
                           "format": "bestaudio[ext=m4a]/bestaudio/best"}) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
        return info.get("url", "") or ""


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
    """YouTube 오디오 스트리밍 (direct URL Range 프록시)

    direct 오디오 URL 을 해소(캐시)한 뒤, 클라이언트의 Range 헤더를 googlevideo 로
    그대로 중계한다. 응답이 Content-Length·Accept-Ranges·(부분요청 시)206 Content-Range 를
    실어 오므로 브라우저 <audio> 가 곡 길이를 알고 중간 지점으로 seek(구간 건너뛰기)할 수 있다.
    """
    if not re.match(r'^[a-zA-Z0-9_-]{11}$', video_id):
        raise HTTPException(status_code=400, detail="잘못된 video_id")

    loop = asyncio.get_event_loop()

    # direct 오디오 URL 해소 (blocking → executor)
    audio_url = _audio_cache_get(video_id)
    if not audio_url:
        try:
            audio_url = await loop.run_in_executor(None, _resolve_audio_url, video_id)
        except Exception:
            audio_url = ""
        if not audio_url:
            raise HTTPException(status_code=502, detail="오디오를 가져오지 못했어요")
        _audio_cache_put(video_id, audio_url)

    import requests as _rq

    fwd = {}
    rng = request.headers.get("range")
    if rng:
        fwd["Range"] = rng

    def _open(url: str):
        return _rq.get(url, headers=fwd, stream=True, timeout=(10, 30))

    try:
        r = await loop.run_in_executor(None, _open, audio_url)
        if r.status_code in (403, 410):     # URL 만료/IP 불일치 — 1회 재해소
            r.close()
            audio_url = await loop.run_in_executor(None, _resolve_audio_url, video_id)
            _audio_cache_put(video_id, audio_url)
            r = await loop.run_in_executor(None, _open, audio_url)
    except Exception:
        raise HTTPException(status_code=502, detail="스트림 연결 실패")

    if r.status_code not in (200, 206):
        r.close()
        raise HTTPException(status_code=502, detail="스트림 오류")

    headers = {k: r.headers[k] for k in ("Content-Type", "Content-Length", "Content-Range")
               if k in r.headers}
    headers.setdefault("Content-Type", "audio/mp4")
    headers["Accept-Ranges"] = "bytes"
    headers["Cache-Control"] = "no-cache"

    def audio_gen():
        try:
            for chunk in r.iter_content(STREAM_CHUNK_SIZE):
                if chunk:
                    yield chunk
        finally:
            r.close()

    return StreamingResponse(
        audio_gen(),
        status_code=r.status_code,
        headers=headers,
    )
