"""api_ytrelay.py — 유튜브 릴레이 스트리밍 (ytmusic 계기 '전송' 탭의 서빙 면).

브라우저가 유튜브(googlevideo)에 직접 접속하지 않고 유튜브를 보는 길:
맥이 yt-dlp 로 스트림 URL 을 해소하고, ffmpeg 이 그 URL 에서 받으면서(-c copy
리먹스, 재인코딩 0) 첫 바이트부터 fMP4 생방송으로 흘린다 — 같은 바이트를 파이썬
tee 로 캐시(.part)에 쓰고 완주 시 faststart 리먹스(공개파일 스트리밍 트랜스코드
선례 그대로, thumbnails.finish/detach 재사용). 두 번째 재생부터는 캐시 직행
(Range·seek 완전).

왜 릴레이인가: googlevideo URL 은 해소한 쪽(맥) IP 에 잠기므로 클라이언트에 그대로
주면 외부망(LTE)에서 죽는다 — mode:client 의 한계이자 포털 tune 프록시(/h/…/tune/)와
같은 부류. 여기서는 받는 쪽이 항상 맥 자신이라 원격 표면이 어디에 있든 재생된다.

GET /yt/relay/{video_id}?kind=audio|video
인증: 로컬 신뢰(remote_access_guard 가 외부 요청을 런처 세션으로 거름) — /music 동일,
is_public_remote_path 등록 금지.
"""

import json
import os
import re
import time
import uuid
import subprocess
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response, StreamingResponse
from starlette.concurrency import run_in_threadpool

import thumbnails

router = APIRouter(prefix="/yt", tags=["yt-relay"])

_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "youtube_cache"
_CACHE_CAP_BYTES = 5 * 1024 * 1024 * 1024   # 5GB 넘으면 오래 안 쓴 것부터 버린다(파생물)

_VID_RE = re.compile(r"^[A-Za-z0-9_-]{6,20}$")

# 해소 결과 캐시 — googlevideo URL 은 수 시간 유효하지만 여유 있게 45분만 신뢰.
# (재생 중 일시정지 후 재요청·같은 곡 재클릭이 매번 yt-dlp 왕복(수 초)을 물지 않게.)
_RESOLVE_TTL = 45 * 60
_resolve_cache: dict = {}   # (video_id, kind) -> (ts, dict)


def _resolve_streams(video_id: str, kind: str, q: str = "") -> dict:
    """yt-dlp 로 스트림 URL 해소 (다운로드 없음 — 메타만, 수 초).

    video: avc1(h264)+m4a(aac) 분리 스트림 우선 — 둘 다 -c copy 리먹스 가능한 조합.
    audio: m4a(aac) 우선 — copy, 없으면(드묾) AAC 재인코딩 폴백(오디오라 실시간보다 훨씬 빠름).
    q="low": 유튜브가 이미 만들어 둔 저해상도 판(≤480p, ~0.5-0.8Mbps)을 고른다 —
      로컬 재인코딩 없이 같은 -c copy 리먹스로 느린 회선(테슬라 1.4Mbps 실측)에 들어간다.
      원본 1080p(3-5Mbps)는 그 회선에서 비디오 버퍼만 굶어 '소리는 나오고 화면 정지'.
    """
    import yt_dlp
    url = f"https://www.youtube.com/watch?v={video_id}"
    # 마지막 /best 폴백: 옛 영상(2005년대)은 결합 포맷 하나뿐이라 audio-only 매칭이
    # 실패한다 — 결합 입력이어도 오디오 경로는 -vn 으로 소리만 뽑으므로 무해.
    if kind == "video":
        cap = 480 if q == "low" else 1080
        fmt = (f"bestvideo[vcodec^=avc1][height<={cap}]+bestaudio[ext=m4a]"
               f"/best[ext=mp4][height<={cap}]/best[height<={cap}]/best")
    else:
        fmt = "bestaudio[ext=m4a]/bestaudio/best"
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True,
                           "format": fmt, "noplaylist": True}) as ydl:
        info = ydl.extract_info(url, download=False)
    reqs = info.get("requested_formats") or [info]   # 병합 포맷=[비디오,오디오] / 단일=자기 자신
    urls = [f.get("url") for f in reqs if f.get("url")]
    if not urls:
        raise RuntimeError("스트림 URL 해소 실패")
    acodec = next((f.get("acodec") for f in reqs
                   if f.get("acodec") not in (None, "none")), "") or ""
    ua = ((reqs[0].get("http_headers") or {}).get("User-Agent", "")
          or (info.get("http_headers") or {}).get("User-Agent", ""))
    return {
        "urls": urls,
        "duration": float(info.get("duration") or 0),
        "acodec": acodec,
        "ua": ua,
        # 시청 기록·피드용 메타 — 어차피 해소가 물어온 정보라 공짜
        "title": info.get("title") or "",
        "channel": info.get("channel") or info.get("uploader") or "",
        "channel_id": info.get("channel_id") or "",
    }


def _resolve_cached(video_id: str, kind: str, q: str = "") -> dict:
    key = (video_id, kind, q)
    hit = _resolve_cache.get(key)
    if hit and time.time() - hit[0] < _RESOLVE_TTL:
        return hit[1]
    try:
        r = _resolve_streams(video_id, kind, q)
    except Exception:
        r = _resolve_streams(video_id, kind, q)   # 1회 재시도 — yt-dlp 일시 실패(실측)가 502→플레이어 err4 로 번지지 않게
    _resolve_cache[key] = (time.time(), r)
    # 만료 항목 청소(무한 성장 방지 — 항목이 작아 크기보다 위생 목적)
    for k in [k for k, (ts, _) in _resolve_cache.items()
              if time.time() - ts > _RESOLVE_TTL]:
        _resolve_cache.pop(k, None)
    return r


def _start_relay(res: dict, kind: str):
    """ffmpeg 릴레이 시작 — googlevideo 에서 받으며 fMP4 를 stdout 에 흘린다.
    (proc, tmp, errf) 반환. 완주=thumbnails.finish_stream_transcode / 중단=detach_….
    errf = ffmpeg 오류문 보관 임시파일 — DEVNULL 이면 실패 이유(403·포맷 없음)가
    통째로 사라져 502 가 "릴레이 시작 실패" 한 줄로만 남는다(2026-08-26 무음 사건:
    낡은 yt-dlp 가 물어온 URL 이 403 이었는데 그 사실이 어디에도 안 보였다).
    PIPE 가 아니라 파일인 이유: 아무도 안 읽는 PIPE 는 64KB 에서 ffmpeg 을 세운다.

    ★tee 머서 금지·단일 fMP4 출력 + 파이썬 tee (thumbnails.start_stream_transcode 의
    교훈 그대로 — 여기선 입력이 파일이 아니라 URL 2개라 커맨드만 자작한다)."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = str(_CACHE_DIR / f".{uuid.uuid4().hex[:12]}.part.mp4")
    cmd = ["ffmpeg", "-v", "error"]
    for u in res["urls"]:
        if res["ua"]:
            cmd += ["-user_agent", res["ua"]]   # 입력 옵션이라 각 -i 앞에 붙어야 한다
        cmd += ["-i", u]
    if kind == "video":
        cmd += ["-map", "0:v:0", "-map", f"{len(res['urls']) - 1}:a:0?", "-c:v", "copy"]
    else:
        cmd += ["-map", "0:a:0", "-vn"]
    # aac(mp4a)면 copy=리먹스 — 아니면(옛 영상 opus 단독 등 드묾) AAC 재인코딩
    cmd += (["-c:a", "copy"] if res["acodec"].startswith("mp4a")
            else ["-c:a", "aac", "-b:a", "160k", "-ac", "2"])
    cmd += ["-f", "mp4", "-movflags", "frag_keyframe+empty_moov+default_base_moof",
            "pipe:1"]
    errf = tempfile.TemporaryFile()
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=errf)
    return proc, tmp, errf


def _err_tail(errf, limit: int = 300) -> str:
    """ffmpeg 오류문의 마지막 줄 — 무음/502 의 진짜 이유를 표면까지 나른다.
    마지막 줄만 쓰는 이유: 그 앞 줄엔 서명 붙은 googlevideo URL 이 통째로 실린다."""
    try:
        errf.seek(0)
        txt = errf.read().decode("utf-8", "replace").strip()
    except Exception:
        txt = ""
    finally:
        try:
            errf.close()
        except Exception:
            pass
    line = txt.splitlines()[-1] if txt else ""
    return line[:limit] or "(오류문 없음)"


_WATCH_LOG = Path(__file__).resolve().parent.parent.parent / "data" / "youtube_watch.json"
_WATCH_LOG_CAP = 500


def _log_watch(video_id: str, kind: str, meta: dict | None) -> None:
    """시청 기록 — 재생(릴레이 요청)마다 한 줄. yttv 피드('본 채널·주제')의 원료.
    같은 영상 10분 내 재요청(seek·일시정지 후 재개)은 한 번으로 친다.
    캐시 직행이라 meta 가 없으면 지난 기록에서 제목을 물려받는다."""
    from datetime import datetime
    try:
        log = []
        if _WATCH_LOG.exists():
            log = json.loads(_WATCH_LOG.read_text(encoding="utf-8"))
            if not isinstance(log, list):
                log = []
        now = time.time()
        for e in reversed(log):
            if e.get("video_id") == video_id and e.get("kind") == kind:
                try:
                    prev = datetime.fromisoformat(e.get("ts", "")).timestamp()
                except ValueError:
                    prev = 0
                if now - prev < 600:
                    return
                if not meta:   # 캐시 직행 — 지난 기록의 메타 승계
                    meta = e
                break
        meta = meta or {}
        log.append({
            "ts": datetime.now().isoformat(timespec="seconds"),
            "video_id": video_id, "kind": kind,
            "title": meta.get("title", ""), "channel": meta.get("channel", ""),
            "channel_id": meta.get("channel_id", ""),
        })
        log = log[-_WATCH_LOG_CAP:]
        tmp = _WATCH_LOG.with_suffix(".tmp")
        tmp.write_text(json.dumps(log, ensure_ascii=False, indent=0), encoding="utf-8")
        os.replace(tmp, _WATCH_LOG)
    except Exception:
        pass   # 기록 실패가 재생을 막아선 안 된다


def _prune_cache() -> None:
    try:
        files = [(f, f.stat()) for f in _CACHE_DIR.glob("*.mp4")
                 if not f.name.startswith(".")]
    except OSError:
        return
    total = sum(s.st_size for _, s in files)
    if total <= _CACHE_CAP_BYTES:
        return
    for f, s in sorted(files, key=lambda x: x[1].st_mtime):   # 오래 안 쓴 것부터
        try:
            f.unlink()
            total -= s.st_size
        except OSError:
            pass
        if total <= _CACHE_CAP_BYTES * 0.8:
            break


async def _read_init_segment(proc) -> bytes:
    """fMP4 init 세그먼트(ftyp+moov)가 통째로 잡힐 때까지 모은다(duration 패치용)."""
    head = b""
    while len(head) < (1 << 18):
        chunk = await run_in_threadpool(proc.stdout.read, 1 << 16)
        if not chunk:
            break
        head += chunk
        if b"moof" in head:
            break
    return head


async def _live_body(first: bytes, proc, tmp: str, cache_dst: str):
    """생방송 본문 — stdout 을 흘리면서 같은 바이트를 tmp 에 쓴다(파이썬 tee).
    완주 시 faststart 리먹스로 캐시 완성, 시청 중단 시엔 백그라운드 완주."""
    import asyncio
    f = open(tmp, "wb")
    try:
        f.write(first)
        yield first
        while True:
            chunk = await run_in_threadpool(proc.stdout.read, 1 << 16)
            if not chunk:
                break
            f.write(chunk)
            yield chunk
        f.close()
        await run_in_threadpool(thumbnails.finish_stream_transcode, proc, tmp, cache_dst)
        await run_in_threadpool(_prune_cache)
    except (asyncio.CancelledError, GeneratorExit):
        f.close()
        thumbnails.detach_stream_transcode(proc, tmp, cache_dst)
        raise


# ── HLS 적응형 (넷플릭스식 화질 자동 전환) ─────────────────────────────────
# 유튜브가 이미 만들어 둔 화질 사다리(avc1 144~1080p, DASH fMP4)를 재인코딩 없이
# byterange HLS 로 묶는다: 각 스트림은 ftyp+moov(init)+sidx(조각 색인)+moof… 구조
# (실측)라, sidx 만 파싱하면 조각 경계를 알 수 있다 → EXT-X-MAP + EXT-X-BYTERANGE
# 플레이리스트를 만들고 세그먼트는 googlevideo 로 Range 그대로 중계. hls.js 가
# 회선을 재서 조각마다 화질을 갈아탄다(소리는 나오는데 화면 정지=버퍼 기아의 근본 해소).
# ★yt-dlp 가 낡으면 사다리 자체가 안 온다(2026.02 판=360p 하나뿐 실측 — 최신 유지 필수).

_LADDER_TTL = 45 * 60
_ladder_cache: dict = {}   # video_id -> (ts, ladder)
_segidx_cache: dict = {}   # (video_id, itag) -> {"init_end", "segments":[(offset,size,dur)], ...}


def _resolve_ladder(video_id: str) -> dict:
    """화질 사다리 해소 — avc1 video-only 렁(높이별 1개) + m4a 오디오 1개."""
    hit = _ladder_cache.get(video_id)
    if hit and time.time() - hit[0] < _LADDER_TTL:
        return hit[1]
    import yt_dlp
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True, "noplaylist": True}) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={video_id}", download=False)
    by_height = {}
    # ★protocol="https"(DASH 직행 URL)만 — 2026.08 판 yt-dlp 는 같은 높이에
    # m3u8_native 렁(itag 269·270…)도 함께 물어온다. 그 url 은 파일이 아니라
    # 재생목록(.m3u8 텍스트)이라 sidx 파싱이 "sidx 없음" 으로 죽는다(실측).
    for f in info.get("formats") or []:
        if (not f.get("url") or f.get("protocol") != "https"
                or not (f.get("vcodec") or "").startswith("avc1")
                or (f.get("acodec") or "none") != "none" or f.get("ext") != "mp4"):
            continue
        h = f.get("height") or 0
        if h and (h not in by_height or (f.get("tbr") or 0) > (by_height[h].get("tbr") or 0)):
            by_height[h] = f
    auds = [f for f in (info.get("formats") or [])
            if f.get("url") and f.get("protocol") == "https"
            and (f.get("acodec") or "").startswith("mp4a")
            and (f.get("vcodec") or "none") == "none" and f.get("ext") == "m4a"]
    if not by_height or not auds:
        raise RuntimeError("화질 사다리 없음 (DASH 포맷 미제공 영상)")
    aud = max(auds, key=lambda f: f.get("abr") or 0)
    ladder = {
        "video": [{"itag": f["format_id"], "url": f["url"], "height": f["height"],
                   "width": f.get("width") or 0, "tbr": f.get("tbr") or 0,
                   "codec": f.get("vcodec") or "avc1"}
                  for _, f in sorted(by_height.items())],
        "audio": {"itag": aud["format_id"], "url": aud["url"],
                  "tbr": aud.get("abr") or aud.get("tbr") or 128,
                  "codec": aud.get("acodec") or "mp4a.40.2"},
        "ua": (info.get("http_headers") or {}).get("User-Agent", "") or
              ((by_height[max(by_height)].get("http_headers") or {}).get("User-Agent", "")),
        "title": info.get("title") or "",
        "channel": info.get("channel") or info.get("uploader") or "",
        "channel_id": info.get("channel_id") or "",
        "duration": float(info.get("duration") or 0),
    }
    _ladder_cache[video_id] = (time.time(), ladder)
    return ladder


def _ladder_stream(ladder: dict, itag: str) -> dict | None:
    if ladder["audio"]["itag"] == itag:
        return ladder["audio"]
    return next((v for v in ladder["video"] if v["itag"] == itag), None)


def _fetch_range(url: str, ua: str, start: int, end: int | None) -> bytes:
    import urllib.request
    rng = f"bytes={start}-" + ("" if end is None else str(end))
    req = urllib.request.Request(url, headers={"Range": rng, "User-Agent": ua or "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.read()


def _parse_boxes_sidx(video_id: str, itag: str) -> dict:
    """스트림 머리에서 init 경계(moov 끝)와 sidx 조각 색인을 파싱해 캐시."""
    import struct
    key = (video_id, itag)
    if key in _segidx_cache:
        return _segidx_cache[key]
    ladder = _resolve_ladder(video_id)
    st = _ladder_stream(ladder, itag)
    if not st:
        raise RuntimeError("사다리에 없는 itag")
    head = _fetch_range(st["url"], ladder["ua"], 0, 65535)
    pos, init_end, sidx_at = 0, 0, -1
    while pos + 8 <= len(head):
        size = struct.unpack(">I", head[pos:pos + 4])[0]
        tag = head[pos + 4:pos + 8]
        if size < 8:
            break
        if tag == b"moov":
            init_end = pos + size          # init 세그먼트 = bytes 0..init_end-1
        elif tag == b"sidx":
            sidx_at = pos
            break
        pos += size
    if init_end <= 0 or sidx_at < 0:
        raise RuntimeError("sidx 없음 (이 렁은 HLS 부적격)")
    # sidx 파싱 (ISO 14496-12)
    p = sidx_at + 8
    version = head[p]
    p += 4                                  # version+flags
    p += 4                                  # reference_ID
    timescale = struct.unpack(">I", head[p:p + 4])[0]; p += 4
    if version == 0:
        p += 4                              # earliest_presentation_time
        first_offset = struct.unpack(">I", head[p:p + 4])[0]; p += 4
    else:
        p += 8
        first_offset = struct.unpack(">Q", head[p:p + 8])[0]; p += 8
    p += 2                                  # reserved
    ref_count = struct.unpack(">H", head[p:p + 2])[0]; p += 2
    sidx_size = struct.unpack(">I", head[sidx_at:sidx_at + 4])[0]
    offset = sidx_at + sidx_size + first_offset
    segments = []
    for _ in range(ref_count):
        w1 = struct.unpack(">I", head[p:p + 4])[0]; p += 4
        dur = struct.unpack(">I", head[p:p + 4])[0]; p += 4
        p += 4                              # SAP
        if w1 >> 31:                        # ref_type=1(계층 색인) — 유튜브엔 안 나옴, 방어만
            raise RuntimeError("계층 sidx 미지원")
        size = w1 & 0x7FFFFFFF
        segments.append((offset, size, dur / timescale))
        offset += size
    idx = {"init_end": init_end, "segments": segments}
    _segidx_cache[key] = idx
    return idx


@router.get("/hls/{video_id}/master.m3u8")
async def hls_master(video_id: str):
    """적응형 마스터 플레이리스트 — 유튜브 사다리의 렁들을 변형(variant)으로."""
    if not _VID_RE.fullmatch(video_id):
        raise HTTPException(status_code=404, detail="잘못된 video_id")
    try:
        ladder = await run_in_threadpool(_resolve_ladder, video_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"사다리 해소 실패: {e}")
    await run_in_threadpool(_log_watch, video_id, "video", ladder)
    aud = ladder["audio"]
    lines = ["#EXTM3U", "#EXT-X-VERSION:7",
             f'#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="aud",NAME="audio",DEFAULT=YES,AUTOSELECT=YES,URI="a{aud["itag"]}.m3u8"']
    for v in ladder["video"]:
        bw = int((v["tbr"] + aud["tbr"]) * 1000) or 200000
        lines.append(
            f'#EXT-X-STREAM-INF:BANDWIDTH={bw},RESOLUTION={v["width"]}x{v["height"]},'
            f'CODECS="{v["codec"]},{aud["codec"]}",AUDIO="aud"')
        lines.append(f'v{v["itag"]}.m3u8')
    return Response("\n".join(lines) + "\n",
                    media_type="application/vnd.apple.mpegurl",
                    headers={"Cache-Control": "no-store"})


@router.get("/hls/{video_id}/{name}.m3u8")
async def hls_variant(video_id: str, name: str):
    """변형 플레이리스트 — sidx 조각 색인을 EXT-X-BYTERANGE 로. (v<itag>|a<itag>)"""
    if not _VID_RE.fullmatch(video_id) or name[:1] not in ("v", "a"):
        raise HTTPException(status_code=404, detail="not found")
    itag = name[1:]
    try:
        idx = await run_in_threadpool(_parse_boxes_sidx, video_id, itag)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"조각 색인 실패: {e}")
    segs = idx["segments"]
    target = max(int(d + 0.999) for _, _, d in segs) if segs else 6
    lines = ["#EXTM3U", "#EXT-X-VERSION:7", f"#EXT-X-TARGETDURATION:{target}",
             "#EXT-X-PLAYLIST-TYPE:VOD",
             f'#EXT-X-MAP:URI="s{itag}.mp4",BYTERANGE="{idx["init_end"]}@0"']
    for offset, size, dur in segs:
        lines.append(f"#EXTINF:{dur:.3f},")
        lines.append(f"#EXT-X-BYTERANGE:{size}@{offset}")
        lines.append(f"s{itag}.mp4")
    lines.append("#EXT-X-ENDLIST")
    return Response("\n".join(lines) + "\n",
                    media_type="application/vnd.apple.mpegurl",
                    headers={"Cache-Control": "no-store"})


@router.get("/hls/{video_id}/s{itag}.mp4")
async def hls_segment(video_id: str, itag: str, request: Request):
    """세그먼트 — 브라우저의 Range 를 googlevideo 로 그대로 중계(재인코딩 0)."""
    if not _VID_RE.fullmatch(video_id):
        raise HTTPException(status_code=404, detail="잘못된 video_id")
    try:
        ladder = await run_in_threadpool(_resolve_ladder, video_id)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"사다리 해소 실패: {e}")
    st = _ladder_stream(ladder, itag)
    if not st:
        raise HTTPException(status_code=404, detail="없는 itag")
    rng = request.headers.get("range", "")

    def _open(url):
        import urllib.request
        headers = {"User-Agent": ladder["ua"] or "Mozilla/5.0"}
        if rng:
            headers["Range"] = rng
        return urllib.request.urlopen(
            urllib.request.Request(url, headers=headers), timeout=30)

    try:
        r = await run_in_threadpool(_open, st["url"])
    except Exception:
        # URL 만료(수 시간) — 사다리 새로 해소 후 1회 재시도
        _ladder_cache.pop(video_id, None)
        try:
            ladder = await run_in_threadpool(_resolve_ladder, video_id)
            st = _ladder_stream(ladder, itag) or st
            r = await run_in_threadpool(_open, st["url"])
        except Exception as e:
            raise HTTPException(status_code=502, detail=f"세그먼트 중계 실패: {e}")

    async def _body():
        try:
            while True:
                chunk = await run_in_threadpool(r.read, 1 << 16)
                if not chunk:
                    break
                yield chunk
        finally:
            try:
                r.close()
            except Exception:
                pass

    status = getattr(r, "status", 200)
    headers = {"Cache-Control": "no-store", "Accept-Ranges": "bytes"}
    cr = r.headers.get("Content-Range")
    if cr:
        headers["Content-Range"] = cr
    cl = r.headers.get("Content-Length")
    if cl:
        headers["Content-Length"] = cl
    return StreamingResponse(_body(), status_code=status, media_type="video/mp4",
                             headers=headers)


@router.get("/relay/{video_id}")
async def relay(video_id: str, kind: str = Query(default="audio"), q: str = Query(default="")):
    """유튜브 한 편을 맥 경유로 스트리밍 — 캐시 있으면 직행(Range), 없으면 생방송+tee.
    q=low = 저대역 판(≤480p 유튜브 자체 렌디션, -c copy) — 느린 회선(테슬라)용.
    ★캐시 슬롯 분리(<id>.video.low.mp4) — 같은 슬롯이면 한 번 저화질로 본 영상이
    데스크탑에도 480p 로 나간다(공개파일 저대역 선례)."""
    if not _VID_RE.fullmatch(video_id):
        raise HTTPException(status_code=404, detail="잘못된 video_id")
    if kind not in ("audio", "video"):
        raise HTTPException(status_code=400, detail="kind 는 audio|video")
    if q not in ("", "low"):
        raise HTTPException(status_code=400, detail="q 는 low 또는 생략")
    if kind == "audio":
        q = ""   # 오디오는 저대역 축 없음(이미 가볍다)
    mime = "video/mp4" if kind == "video" else "audio/mp4"
    cache = _CACHE_DIR / f"{video_id}.{kind}{'.low' if q else ''}.mp4"
    if cache.exists() and cache.stat().st_size > 0:
        try:
            os.utime(cache)   # LRU 근거(mtime) 갱신 — 재생할 때마다 젊어진다
        except OSError:
            pass
        hit = _resolve_cache.get((video_id, kind, q))
        await run_in_threadpool(_log_watch, video_id, kind, hit[1] if hit else None)
        return FileResponse(str(cache), media_type=mime)

    try:
        res = await run_in_threadpool(_resolve_cached, video_id, kind, q)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"유튜브 해소 실패: {e}")
    await run_in_threadpool(_log_watch, video_id, kind, res)
    proc, tmp, errf = _start_relay(res, kind)
    head = await _read_init_segment(proc)
    if not head:
        thumbnails.kill_stream(proc)
        # 해소 결과가 부패했을 수 있다(드묾) — 다음 요청이 새로 해소하게 캐시 비움
        _resolve_cache.pop((video_id, kind, q), None)
        raise HTTPException(status_code=502,
                            detail=f"릴레이 시작 실패 (ffmpeg): {_err_tail(errf)}")
    errf.close()   # 시작에 성공했으면 오류문은 필요 없다(자식 fd 는 그대로)
    head = thumbnails.patch_fmp4_duration(head, res["duration"])
    # X-Transcode-Live: 생방송(중단되면 반쪽) — 중간 캐시 금지(공개파일 선례)
    return StreamingResponse(
        _live_body(head, proc, tmp, str(cache)), media_type=mime,
        headers={"X-Transcode-Live": "1", "Cache-Control": "no-store"})
