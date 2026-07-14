"""
api_showcase.py — 공개파일 라이브 서빙 (인덱싱 없음).

공개 Worker 가 이 엔드포인트로 갤러리를 **실시간**으로 그린다. 사전 인덱싱·manifest·
썸네일 사전 업로드가 없다 — 파일시스템이 곧 진실이라, 파일을 옮기거나 지우면 즉시 반영.
  · /showcase/list/{slug}?path=   — 그 바스켓의 한 디렉토리를 즉석에서 훑어 목록 반환.
  · /showcase/thumb/{slug}/{fid}?rel=  — 썸네일을 그 자리에서 생성(Worker 가 R2 에 캐시).
  · /showcase/media/{slug}/{fid}?rel=  — 원본(EXIF 제거·동영상 H.264 변환·Range).
보안: X-Showcase-Secret(Worker 만 보유) + slug→바스켓→folder 소속 + 경로 이탈 방어.
raw 절대경로는 절대 안 받는다 — folder_id + 발행 폴더 기준 상대경로(rel)만.

이 라우트들은 is_public_remote_path 에서 /showcase/* 로 열려 터널로 접근(자체 시크릿 게이트).
"""

import os
import json
import tempfile
from pathlib import Path

from fastapi import APIRouter, HTTPException, Header, Query
from fastapi.responses import FileResponse, Response

import thumbnails

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

    dirs, items = [], []
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
    return {"title": basket.get("title") or "공개파일", "path": path, "fid": fid,
            "dirs": dirs, "items": items}


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
        ok = thumbnails.generate_thumbnail(abspath, tmp, _THUMB_SIZE, kind)
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


@router.get("/media/{slug}/{fid}")
async def media(slug: str, fid: str, rel: str = Query(...), x_showcase_secret: str = Header(default="")):
    """원본 서빙 — EXIF 제거·동영상 H.264 변환·Range(FileResponse 자동)."""
    folder, abspath = _resolve(slug, fid, rel, x_showcase_secret)
    settings = _load_state().get("settings") or {}
    kind = thumbnails.classify(abspath)

    # ① 이미지 + EXIF 제거 → 위치·기기 메타 벗긴 JPEG.
    if kind == "photo" and settings.get("strip_exif", True) and thumbnails.needs_exif_strip(abspath):
        data = thumbnails.sanitize_image_bytes(abspath)
        if data:
            return Response(content=data, media_type="image/jpeg")

    # ② 동영상 + 브라우저 비재생 컨테이너 → H.264 MP4(로컬 캐시).
    if kind == "video" and settings.get("transcode_video", True) and thumbnails.needs_video_transcode(abspath):
        import hashlib
        key = hashlib.md5(f"{fid}/{rel}".encode("utf-8")).hexdigest()[:16]
        cache = _WEB_MEDIA / fid / (key + ".mp4")
        if not (cache.exists() and cache.stat().st_size > 0):
            cache.parent.mkdir(parents=True, exist_ok=True)
            thumbnails.transcode_video_to_mp4(abspath, str(cache))
        if cache.exists() and cache.stat().st_size > 0:
            return FileResponse(str(cache), media_type="video/mp4")

    # 그 외(또는 폴백) — FileResponse 가 content-type + Range 자동 처리.
    return FileResponse(abspath, filename=os.path.basename(abspath))
