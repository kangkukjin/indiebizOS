"""api_nas_hls.py — NAS 파인더 동영상의 HLS 적응형 서빙(화질 자동 전환).

공개파일(api_showcase)과 같은 사다리 기계(hls_ladder)를 NAS 로컬 파일에 적용.
NAS 는 지금까지 캐시가 아예 없었다(/nas/transcode = 매 시청 생인코딩) — 여기서
처음으로 렌디션 캐시(data/nas_stream_cache/)가 생기고, 마스터 요청이 결핍 렁을
백그라운드로 빌드한다(전역 단일 워커). 사다리가 없으면 404 — 파인더 팝업이 기존
/nas/file·/nas/transcode 프로그레시브로 폴백하고, 다음 시청부터 적응형.

  GET /nas/hls/master.m3u8?path=   (r= 있으면 변형 플레이리스트)
  GET /nas/hls/seg.mp4?path=&r=    (렌디션 파일 — Range=byterange 세그먼트)

인증: 기존 NAS 세션(nas_session 쿠키) — /nas/transcode 와 동일. 플레이리스트의
URI 는 전부 상대라(같은 /nas/hls/ 아래) 어느 호스트(로컬·터널)로 접속해도 산다.
"""

import hashlib
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from starlette.concurrency import run_in_threadpool

import thumbnails
import hls_ladder
import api_nas

router = APIRouter(prefix="/nas/hls", tags=["nas-hls"])

_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "nas_stream_cache"
_CACHE_CAP = 20 * 1024 * 1024 * 1024   # LRU 상한 — 렌디션은 전부 파생물(재생성 가능)


def _resolve_src(request: Request, path: str) -> Path:
    """세션 인증 + allowed_paths 화이트리스트 + 동영상 판정 — 소스 절대경로 반환."""
    config = api_nas.load_config()
    if not config.get("enabled"):
        raise HTTPException(status_code=503, detail="NAS 서비스가 비활성화되어 있습니다")
    token = request.cookies.get("nas_session") or request.headers.get("X-NAS-Session")
    if not token or not api_nas.verify_session(token):
        raise HTTPException(status_code=401, detail="인증이 필요합니다")
    safe = api_nas.get_safe_path(config.get("allowed_paths", []), path)
    if not safe or not safe.exists() or not safe.is_file():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")
    if thumbnails.classify(str(safe)) != "video":
        raise HTTPException(status_code=404, detail="동영상이 아닙니다")
    return safe


def _orig_cache(src: Path) -> str:
    key = hashlib.md5(str(src).encode("utf-8")).hexdigest()[:16]
    return str(_CACHE_DIR / f"{key}.mp4")


@router.get("/master.m3u8")
async def master(request: Request, path: str = Query(...), r: str = Query(default="")):
    """r 없음=마스터(+결핍 렁 빌드 enqueue), r=렁(tiny|low|orig)=변형."""
    from urllib.parse import quote
    src = _resolve_src(request, path)
    orig_cache = _orig_cache(src)
    qs = f"path={quote(path, safe='')}"

    if not r:
        rungs = await run_in_threadpool(hls_ladder.available_rungs, orig_cache)
        await run_in_threadpool(hls_ladder.ensure_ladder, str(src), orig_cache,
                                prune_root=str(_CACHE_DIR), prune_cap=_CACHE_CAP)
        if not rungs:
            raise HTTPException(status_code=404, detail="사다리 준비 전 — 프로그레시브로 폴백")
        # 상대 URI — 마스터가 /nas/hls/master.m3u8 에 있으니 그대로 형제 해석
        body = await run_in_threadpool(   # rung_meta 의 ffprobe(첫 회) — 루프 밖에서
            hls_ladder.master_m3u8, rungs, lambda rung: f"master.m3u8?{qs}&r={rung}")
    else:
        if r not in hls_ladder.RUNG_ORDER:
            raise HTTPException(status_code=404, detail="없는 렁")
        rp = hls_ladder.rung_path(orig_cache, r)
        idx = await run_in_threadpool(hls_ladder.parse_sidx_file, rp)
        if not idx:
            raise HTTPException(status_code=404, detail="렁 캐시 없음")
        hls_ladder.touch(rp)
        body = hls_ladder.variant_m3u8(idx, f"seg.mp4?{qs}&r={r}")
    return Response(body, media_type="application/vnd.apple.mpegurl",
                    headers={"Cache-Control": "no-store"})


@router.get("/seg.mp4")
async def segment(request: Request, path: str = Query(...), r: str = Query(...)):
    """렌디션 파일 서빙 — hls.js 의 byterange 요청은 FileResponse 의 Range 가 받는다."""
    src = _resolve_src(request, path)
    if r not in hls_ladder.RUNG_ORDER:
        raise HTTPException(status_code=404, detail="없는 렁")
    rp = hls_ladder.rung_path(_orig_cache(src), r)
    if not os.path.isfile(rp):
        raise HTTPException(status_code=404, detail="렁 캐시 없음")
    return FileResponse(rp, media_type="video/mp4",
                        headers={"Cache-Control": "private, max-age=3600"})
