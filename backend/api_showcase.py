"""
api_showcase.py — 공개파일 라이브 서빙 (인덱싱 없음).

공개 Worker 가 이 엔드포인트로 갤러리를 **실시간**으로 그린다. 사전 인덱싱·manifest·
썸네일 사전 업로드가 없다 — 파일시스템이 곧 진실이라, 파일을 옮기거나 지우면 즉시 반영.
  · /showcase/list/{slug}?path=   — 그 바스켓의 한 디렉토리를 즉석에서 훑어 목록 반환.
  · /showcase/thumb/{slug}/{fid}?rel=  — 썸네일을 그 자리에서 생성(Worker 가 R2 에 캐시).
  · /showcase/media/{slug}/{fid}?rel=  — 원본(EXIF 제거·동영상 H.264 변환·Range).
  · /showcase/subtitle/{slug}/{fid}?rel=&cls= — 형제 자막(srt/ass/smi/vtt)을 WebVTT 로 변환.
보안: X-Showcase-Secret(Worker 만 보유) + slug→바스켓→folder 소속 + 경로 이탈 방어.
raw 절대경로는 절대 안 받는다 — folder_id + 발행 폴더 기준 상대경로(rel)만.

이 라우트들은 is_public_remote_path 에서 /showcase/* 로 열려 터널로 접근(자체 시크릿 게이트).
"""

import os
import json
import asyncio
import hashlib
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Header, Query
from fastapi.responses import FileResponse, Response, StreamingResponse
from starlette.concurrency import run_in_threadpool

import thumbnails
import nas_subtitle

router = APIRouter(prefix="/showcase", tags=["showcase"])

_ROOT = Path(__file__).resolve().parent.parent
_STATE = _ROOT / "data" / "showcase_state.json"
_WEB_MEDIA = _ROOT / "data" / "showcase_stage" / "media_web"   # 트랜스코드 로컬 캐시
_EXCLUDE_DIRS = {"node_modules", ".git", "__pycache__", ".venv", "venv", ".Trash", "thumbnail_cache"}
_THUMB_SIZE = 512


def _read_env(name: str) -> str:
    v = os.environ.get(name, "")
    if v:
        return v
    envp = _ROOT / ".env"
    if envp.exists():
        try:
            for line in envp.read_text(encoding="utf-8").splitlines():
                if line.strip().startswith(name + "="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
        except Exception:
            pass
    return ""


def _load_state() -> dict:
    try:
        return json.loads(_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _check_secret(secret_header: str) -> None:
    secret = _read_env("SHOWCASE_ORIGIN_SECRET")
    if not secret or secret_header != secret:
        raise HTTPException(status_code=403, detail="forbidden")


def _basket(state: dict, slug: str) -> dict:
    b = next((x for x in state.get("baskets", []) if x.get("slug") == slug), None)
    if not b:
        raise HTTPException(status_code=404, detail="no such gallery")
    return b


def _basket_fids(state: dict, basket: dict) -> list:
    if basket.get("all_folders"):
        return [f.get("id") for f in state.get("folders", [])]
    return list(basket.get("folder_ids", []))


def _folder(state: dict, fid: str) -> dict:
    return next((f for f in state.get("folders", []) if f.get("id") == fid), None)


def _safe_abspath(base: str, rel: str):
    """base/rel 을 절대경로로 — base 하위여야(경로 이탈 방어). 아니면 None."""
    base_abs = os.path.abspath(base)
    target = os.path.abspath(os.path.join(base_abs, rel or ""))
    if target == base_abs or target.startswith(base_abs + os.sep):
        return target
    return None


def _resolve(slug: str, fid: str, rel: str, secret_header: str):
    """공통 검증 — 시크릿 + slug→바스켓 + fid 소속 + 경로 이탈. (folder, abspath) 반환."""
    _check_secret(secret_header)
    state = _load_state()
    basket = _basket(state, slug)
    if fid not in _basket_fids(state, basket):
        raise HTTPException(status_code=404, detail="not in gallery")
    folder = _folder(state, fid)
    if not folder:
        raise HTTPException(status_code=404, detail="no folder")
    abspath = _safe_abspath(folder.get("path", ""), rel)
    if not abspath or not os.path.isfile(abspath):
        raise HTTPException(status_code=404, detail="not found")
    return folder, abspath


@router.get("/list/{slug}")
async def list_dir(slug: str, path: str = Query(default=""), x_showcase_secret: str = Header(default="")):
    """바스켓의 한 디렉토리를 즉석에서 훑어 목록 반환. path 는 '<fid>/<하위경로>'.
    빈 path = 바스켓 루트(담긴 폴더들 나열)."""
    _check_secret(x_showcase_secret)
    state = _load_state()
    basket = _basket(state, slug)
    fids = _basket_fids(state, basket)
    folders = [f for f in state.get("folders", []) if f.get("id") in fids]

    if not path:
        # 바스켓 루트 — 담긴 폴더들을 디렉토리로 나열.
        dirs = [{"name": f.get("title") or Path(f.get("path", "")).name, "path": f.get("id")}
                for f in folders]
        return {"title": basket.get("title") or "공개파일", "path": "", "dirs": dirs, "items": []}

    # path = '<fid>' 또는 '<fid>/<sub>'
    fid, _, sub = path.partition("/")
    if fid not in fids:
        raise HTTPException(status_code=404, detail="not in gallery")
    folder = _folder(state, fid)
    if not folder:
        raise HTTPException(status_code=404, detail="no folder")
    base = folder.get("path", "")
    target = _safe_abspath(base, sub)
    if not target or not os.path.isdir(target):
        raise HTTPException(status_code=404, detail="not a dir")
    mode = folder.get("mode", "media")

    dirs, items, sub_files = [], [], []
    try:
        entries = sorted(os.scandir(target), key=lambda e: e.name)
    except OSError:
        entries = []
    for e in entries:
        if e.name.startswith("."):
            continue
        try:
            if e.is_dir():
                if e.name in _EXCLUDE_DIRS:
                    continue
                child = f"{fid}/{sub + '/' if sub else ''}{e.name}"
                dirs.append({"name": e.name, "path": child})
            elif e.is_file():
                kind = thumbnails.classify(e.path)
                if os.path.splitext(e.name)[1].lower() in nas_subtitle.SUBTITLE_EXTENSIONS:
                    sub_files.append((e.name, e.path, int(e.stat().st_mtime)))
                if mode == "media" and kind is None:
                    continue
                st = e.stat()
                rel = os.path.relpath(e.path, os.path.abspath(base)).replace(os.sep, "/")
                items.append({
                    "fid": fid, "rel": rel, "title": e.name,
                    "kind": kind or "file", "mtime": int(st.st_mtime),
                    "thumb": kind in ("photo", "video"),
                })
        except OSError:
            continue
    if sub_files:
        _attach_subs(items, sub_files, os.path.abspath(base))
    return {"title": basket.get("title") or "공개파일", "path": path, "fid": fid,
            "dirs": dirs, "items": items}


def _attach_subs(items, sub_files, base: str) -> None:
    """비디오 아이템에 형제 자막을 subs 로 붙인다 — 자막 파일명이 비디오 이름으로
    시작해야 짝(영화.srt·영화.ko.srt). smi 는 내부 언어 클래스별로 나눈다."""
    smi_langs = {}
    for it in items:
        if it.get("kind") != "video":
            continue
        stem = os.path.splitext(it["title"])[0].lower()
        subs = []
        for name, spath, smtime in sub_files:
            sstem, sext = os.path.splitext(name)
            # 정확히 같거나 '이름.' 접두(영화.ko.srt)만 — 단순 startswith 는
            # '영화2.smi' 가 '영화.mp4' 에도 붙는 과잉 매칭.
            low = sstem.lower()
            if low != stem and not low.startswith(stem + "."):
                continue
            srel = os.path.relpath(spath, base).replace(os.sep, "/")
            if sext.lower() == ".smi":
                if spath not in smi_langs:
                    smi_langs[spath] = nas_subtitle._detect_smi_languages(Path(spath))
                for cls_name, lang_code, lang_label in smi_langs[spath]:
                    subs.append({"rel": srel, "label": lang_label or "자막",
                                 "lang": lang_code, "cls": cls_name, "mtime": smtime})
            else:
                remaining = sstem[len(stem):]
                lang = remaining[1:].lower() if remaining.startswith(".") else ""
                label = nas_subtitle.LANG_NAMES.get(lang, lang) or "자막"
                subs.append({"rel": srel, "label": label, "lang": lang, "mtime": smtime})
        if subs:
            priority = {"ko": 0, "": 1, "en": 2}
            subs.sort(key=lambda s: (priority.get(s.get("lang", ""), 9), s.get("lang", "")))
            it["subs"] = subs


@router.get("/thumb/{slug}/{fid}")
async def thumb(slug: str, fid: str, rel: str = Query(...), x_showcase_secret: str = Header(default="")):
    """썸네일을 그 자리에서 생성해 JPEG 바이트로 반환. Worker 가 R2 에 캐시(mtime 버전키)."""
    folder, abspath = _resolve(slug, fid, rel, x_showcase_secret)
    kind = thumbnails.classify(abspath)
    if kind not in ("photo", "video"):
        raise HTTPException(status_code=404, detail="no thumb")
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tf:
        tmp = tf.name
    try:
        ok = await run_in_threadpool(thumbnails.generate_thumbnail, abspath, tmp, _THUMB_SIZE, kind)
        if not ok or not os.path.exists(tmp) or os.path.getsize(tmp) == 0:
            raise HTTPException(status_code=500, detail="thumb gen failed")
        data = Path(tmp).read_bytes()
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    return Response(content=data, media_type="image/jpeg",
                    headers={"Cache-Control": "public, max-age=86400"})


async def _live_stream(first: bytes, proc, tmp: str, cache_dst: str):
    """스트리밍 트랜스코드 본문 — ffmpeg stdout 을 그대로 흘린다(블로킹 read 는 스레드풀).
    완주 시 캐시 완성(rename), 시청 중단 시엔 백그라운드로 마저 인코딩해 캐시를 완성."""
    try:
        yield first
        while True:
            chunk = await run_in_threadpool(proc.stdout.read, 1 << 16)
            if not chunk:
                break
            yield chunk
        await run_in_threadpool(thumbnails.finish_stream_transcode, proc, tmp, cache_dst)
    except (asyncio.CancelledError, GeneratorExit):
        thumbnails.detach_stream_transcode(proc, tmp, cache_dst)
        raise


@router.get("/media/{slug}/{fid}")
async def media(slug: str, fid: str, rel: str = Query(...), x_showcase_secret: str = Header(default="")):
    """원본 서빙 — EXIF 제거·동영상 H.264 변환(스트리밍)·Range(FileResponse 자동)."""
    folder, abspath = _resolve(slug, fid, rel, x_showcase_secret)
    settings = _load_state().get("settings") or {}
    kind = thumbnails.classify(abspath)

    # ① 이미지 + EXIF 제거 → 위치·기기 메타 벗긴 JPEG.
    if kind == "photo" and settings.get("strip_exif", True) and thumbnails.needs_exif_strip(abspath):
        data = await run_in_threadpool(thumbnails.sanitize_image_bytes, abspath)
        if data:
            return Response(content=data, media_type="image/jpeg")

    # ② 동영상 + 브라우저 비재생 코덱 → H.264 MP4.
    #    캐시가 있으면 직행(Range·seek 완전). 없으면 전체 변환을 기다리지 않고 fMP4 를
    #    인코딩되는 대로 흘린다(긴 영상도 수 초 안에 재생 시작) — 같은 인코딩이 tee 로
    #    faststart 캐시도 만들어(인코딩 1회) 다음 재생부터는 캐시 직행.
    if kind == "video" and settings.get("transcode_video", True):
        key = hashlib.md5(f"{fid}/{rel}".encode("utf-8")).hexdigest()[:16]
        cache = _WEB_MEDIA / fid / (key + ".mp4")
        if cache.exists() and cache.stat().st_size > 0:
            return FileResponse(str(cache), media_type="video/mp4")
        if await run_in_threadpool(thumbnails.needs_video_transcode, abspath):
            proc, tmp = thumbnails.start_stream_transcode(abspath, str(cache))
            first = await run_in_threadpool(proc.stdout.read, 1 << 16)
            if first:
                # X-Transcode-Live: 생방송(중단되면 반쪽)이라 Worker 가 R2 캐시하지 않게.
                return StreamingResponse(
                    _live_stream(first, proc, tmp, str(cache)),
                    media_type="video/mp4",
                    headers={"X-Transcode-Live": "1", "Cache-Control": "no-store"})
            # 첫 바이트도 못 뽑음(ffmpeg 부재 등) — 정리 후 원본 폴백.
            await run_in_threadpool(thumbnails.finish_stream_transcode, proc, tmp, str(cache))

    # 그 외(또는 폴백) — FileResponse 가 content-type + Range 자동 처리.
    return FileResponse(abspath, filename=os.path.basename(abspath))


def _subtitle_vtt(abspath: str, cls: str) -> str:
    """자막 파일 → WebVTT 텍스트. 인코딩 자동 감지(한국어 cp949 흔함)."""
    raw = Path(abspath).read_bytes()
    content = None
    for enc in ("utf-8", "utf-8-sig", "cp949", "euc-kr", "shift_jis", "latin-1"):
        try:
            content = raw.decode(enc)
            break
        except (UnicodeDecodeError, LookupError):
            continue
    if content is None:
        raise HTTPException(status_code=400, detail="자막 인코딩 인식 불가")
    suffix = os.path.splitext(abspath)[1].lower()
    if suffix == ".vtt":
        return content if content.lstrip().startswith("WEBVTT") else "WEBVTT\n\n" + content
    if suffix == ".srt":
        return nas_subtitle.srt_to_vtt(content)
    if suffix in (".ass", ".ssa"):
        return nas_subtitle.ass_to_vtt(content)
    if suffix == ".smi":
        if not cls:
            langs = nas_subtitle._detect_smi_languages(Path(abspath))
            cls = langs[0][0] if langs else "KRCC"
        return nas_subtitle.smi_to_vtt(content, lang_class=cls)
    raise HTTPException(status_code=400, detail="지원하지 않는 자막 형식")


@router.get("/subtitle/{slug}/{fid}")
async def subtitle(slug: str, fid: str, rel: str = Query(...), cls: str = Query(default=""),
                   x_showcase_secret: str = Header(default="")):
    """형제 자막 파일을 WebVTT 로 변환해 반환 — <track> 이 그대로 문다(nas_subtitle 재사용)."""
    folder, abspath = _resolve(slug, fid, rel, x_showcase_secret)
    if os.path.splitext(abspath)[1].lower() not in nas_subtitle.SUBTITLE_EXTENSIONS:
        raise HTTPException(status_code=404, detail="not a subtitle")
    vtt = await run_in_threadpool(_subtitle_vtt, abspath, cls)
    return Response(content=vtt, media_type="text/vtt; charset=utf-8",
                    headers={"Cache-Control": "public, max-age=86400"})
