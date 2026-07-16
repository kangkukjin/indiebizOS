"""api_family_news.py — 가족신문 공개 서빙 + 쓰기 방향(방명록·가족 사진 업로드).

공개 Worker(public-files 와 공유)가 /n/<slug>/... 요청을 이 엔드포인트로 끌어온다.
  · GET  /family-news/page/{slug}?path=      — ""=아카이브 홈(동적), "e/<eid>"=판 HTML(정적)
  · GET  /family-news/media/{slug}/{eid}?rel= — 판 사진 (발행판만)
  · GET  /family-news/gb/{slug}?edition=      — 방명록 목록
  · POST /family-news/gb/{slug}               — 방명록 등록 (이름·메시지 캡 + IP 간격 제한)
  · POST /family-news/upload/{slug}           — 가족 사진 업로드 (raw body, 이미지 매직바이트 검사)
보안: X-Showcase-Secret(Worker 만 보유) + slug 일치 + **발행판만** + 경로 이탈 방어.
업로드는 공개되지 않는다 — data/family_news/uploads/ 에 쌓여 다음 판 제작 때 검수 후 실림.

  · GET  /family-news/preview/{eid}/...       — 초안 미리보기. is_public_remote_path 에
    등록하지 않아 터널(원격)에서는 차단, 맥 로컬에서만 열린다.
"""

import os
import re
import json
import time
import secrets
import threading
import importlib.util
from pathlib import Path
from datetime import datetime

from fastapi import APIRouter, HTTPException, Header, Query, Request
from fastapi.responses import FileResponse, Response, HTMLResponse, JSONResponse

router = APIRouter(prefix="/family-news", tags=["family-news"])

_ROOT = Path(__file__).resolve().parent.parent
_DATA = _ROOT / "data" / "family_news"
_STATE = _DATA / "state.json"
_EDITIONS = _DATA / "editions"
_UPLOADS = _DATA / "uploads"
_UPLOADS_META = _UPLOADS / "uploads.json"
_GUESTBOOK = _DATA / "guestbook.json"

_NAME_MAX = 24
_MSG_MAX = 500
_GB_MAX_ENTRIES = 5000
_GB_MIN_INTERVAL_S = 10          # 같은 IP 연속 등록 간격
_UPLOAD_MAX_BYTES = 30 * 1024 * 1024
_UPLOADS_DIR_CAP = 2 * 1024 * 1024 * 1024   # 업로드 폴더 총량 상한 (스팸 방어)

_WRITE_LOCK = threading.Lock()
_LAST_POST_BY_IP: dict = {}

# 이미지 매직바이트 (JPEG/PNG/GIF/WebP/HEIC·HEIF)
_IMG_MAGIC = [b"\xff\xd8\xff", b"\x89PNG", b"GIF8", b"RIFF"]


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


def _check_secret(secret_header: str) -> None:
    secret = _read_env("SHOWCASE_ORIGIN_SECRET")
    if not secret or secret_header != secret:
        raise HTTPException(status_code=403, detail="forbidden")


def _load_state() -> dict:
    try:
        return json.loads(_STATE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _check_slug(state: dict, slug: str) -> None:
    if not slug or slug != state.get("slug"):
        raise HTTPException(status_code=404, detail="no such paper")


def _published(state: dict) -> list:
    eds = [e for e in state.get("editions", []) if e.get("published_at")]
    return sorted(eds, key=lambda e: e.get("no", 0), reverse=True)


def _edition_dir(eid: str) -> Path:
    """판 디렉토리 — 경로 이탈 방어(editions/ 하위여야)."""
    base = _EDITIONS.resolve()
    target = (base / eid).resolve()
    if target.parent != base or not target.is_dir():
        raise HTTPException(status_code=404, detail="no edition")
    return target


_RENDERER = None


def _renderer():
    """신문 HTML 렌더러(패키지 newspaper_html.py) — 디자인 단일 소스를 공유."""
    global _RENDERER
    if _RENDERER is None:
        p = _ROOT / "data" / "packages" / "installed" / "tools" / "family-news" / "newspaper_html.py"
        spec = importlib.util.spec_from_file_location("_family_newspaper_html_api", str(p))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _RENDERER = mod
    return _RENDERER


# ── 공개 읽기 ────────────────────────────────────────────────────────────

@router.get("/page/{slug}")
async def page(slug: str, path: str = Query(default=""), x_showcase_secret: str = Header(default="")):
    """path=""(아카이브 홈, 동적) 또는 "e/<eid>"(발행판 정적 HTML)."""
    _check_secret(x_showcase_secret)
    state = _load_state()
    _check_slug(state, slug)
    if not path:
        html = _renderer().render_home(state.get("title", "우리 가족 신문"), _published(state))
        return HTMLResponse(html, headers={"Cache-Control": "no-cache"})
    m = re.fullmatch(r"e/([A-Za-z0-9_-]+)", path)
    if not m:
        raise HTTPException(status_code=404, detail="not found")
    eid = m.group(1)
    if not any(e["id"] == eid for e in _published(state)):
        raise HTTPException(status_code=404, detail="not published")
    idx = _edition_dir(eid) / "index.html"
    if not idx.is_file():
        raise HTTPException(status_code=404, detail="not found")
    return HTMLResponse(idx.read_text(encoding="utf-8"), headers={"Cache-Control": "no-cache"})


@router.get("/media/{slug}/{eid}")
async def media(slug: str, eid: str, rel: str = Query(...), x_showcase_secret: str = Header(default="")):
    """발행판 사진 서빙. rel 은 판 디렉토리 기준(photos/...) — 이탈 방어."""
    _check_secret(x_showcase_secret)
    state = _load_state()
    _check_slug(state, slug)
    if not any(e["id"] == eid for e in _published(state)):
        raise HTTPException(status_code=404, detail="not published")
    ed_dir = _edition_dir(eid)
    target = (ed_dir / rel).resolve()
    if not str(target).startswith(str(ed_dir) + os.sep) or not target.is_file():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(str(target), headers={"Cache-Control": "public, max-age=86400"})


# ── 방명록 ──────────────────────────────────────────────────────────────

def _load_gb() -> list:
    try:
        return json.loads(_GUESTBOOK.read_text(encoding="utf-8"))
    except Exception:
        return []


@router.get("/gb/{slug}")
async def gb_list(slug: str, edition: str = Query(default=""), x_showcase_secret: str = Header(default="")):
    _check_secret(x_showcase_secret)
    state = _load_state()
    _check_slug(state, slug)
    entries = _load_gb()
    if edition:
        entries = [e for e in entries if e.get("edition") == edition]
    out = [{"name": e.get("name", ""), "msg": e.get("msg", ""), "at": e.get("at", ""),
            "edition": e.get("edition", "")}
           for e in entries[-200:]]
    out.reverse()
    return {"entries": out}


@router.post("/gb/{slug}")
async def gb_post(slug: str, request: Request, x_showcase_secret: str = Header(default=""),
                  x_client_ip: str = Header(default="")):
    _check_secret(x_showcase_secret)
    state = _load_state()
    _check_slug(state, slug)
    try:
        body = json.loads((await request.body()).decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="bad json")
    name = str(body.get("name", "")).strip()[:_NAME_MAX]
    msg = str(body.get("msg", "")).strip()[:_MSG_MAX]
    edition = str(body.get("edition", "")).strip()[:40]
    if not name or not msg:
        raise HTTPException(status_code=400, detail="name/msg required")
    if edition and not any(e["id"] == edition for e in state.get("editions", [])):
        edition = ""
    ip = x_client_ip or (request.client.host if request.client else "")
    now = time.time()
    if ip and now - _LAST_POST_BY_IP.get(ip, 0) < _GB_MIN_INTERVAL_S:
        raise HTTPException(status_code=429, detail="too fast")
    _LAST_POST_BY_IP[ip] = now
    entry = {"name": name, "msg": msg, "edition": edition,
             "at": datetime.now().strftime("%Y-%m-%d %H:%M"), "ip": ip}
    with _WRITE_LOCK:
        entries = _load_gb()
        entries.append(entry)
        entries = entries[-_GB_MAX_ENTRIES:]
        _DATA.mkdir(parents=True, exist_ok=True)
        tmp = _GUESTBOOK.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(entries, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(_GUESTBOOK)
    return {"ok": True}


# ── 가족 사진 업로드 ─────────────────────────────────────────────────────

def _dir_size(p: Path) -> int:
    total = 0
    try:
        for f in p.iterdir():
            if f.is_file():
                total += f.stat().st_size
    except OSError:
        pass
    return total


def _looks_image(head: bytes, filename: str) -> bool:
    if any(head.startswith(m) for m in _IMG_MAGIC):
        return True
    # HEIC/HEIF/AVIF: ftyp 박스 (offset 4)
    if len(head) > 12 and head[4:8] == b"ftyp":
        return True
    return False


@router.post("/upload/{slug}")
async def upload(slug: str, request: Request, name: str = Query(default=""),
                 filename: str = Query(default="photo.jpg"), edition: str = Query(default=""),
                 x_showcase_secret: str = Header(default=""), x_client_ip: str = Header(default="")):
    """가족 사진 업로드 — raw body(멀티파트 아님). 공개되지 않고 다음 판 재료로만 쌓인다."""
    _check_secret(x_showcase_secret)
    state = _load_state()
    _check_slug(state, slug)
    name = name.strip()[:_NAME_MAX]
    if not name:
        raise HTTPException(status_code=400, detail="name required")
    cl = request.headers.get("content-length")
    if cl and int(cl) > _UPLOAD_MAX_BYTES:
        raise HTTPException(status_code=413, detail="too large")
    body = await request.body()
    if len(body) > _UPLOAD_MAX_BYTES:
        raise HTTPException(status_code=413, detail="too large")
    if len(body) < 100 or not _looks_image(body[:16], filename):
        raise HTTPException(status_code=400, detail="not an image")
    _UPLOADS.mkdir(parents=True, exist_ok=True)
    if _dir_size(_UPLOADS) + len(body) > _UPLOADS_DIR_CAP:
        raise HTTPException(status_code=507, detail="storage full")

    ext = os.path.splitext(filename)[1].lower()
    if not re.fullmatch(r"\.[a-z0-9]{1,5}", ext or ""):
        ext = ".jpg"
    fname = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{secrets.token_hex(3)}{ext}"
    (_UPLOADS / fname).write_bytes(body)

    ip = x_client_ip or (request.client.host if request.client else "")
    entry = {"file": fname, "name": name, "edition": edition[:40],
             "at": datetime.now().strftime("%Y-%m-%d %H:%M"), "ip": ip, "used_in": None}
    with _WRITE_LOCK:
        try:
            metas = json.loads(_UPLOADS_META.read_text(encoding="utf-8"))
        except Exception:
            metas = []
        metas.append(entry)
        tmp = _UPLOADS_META.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(metas, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(_UPLOADS_META)
    return {"ok": True}


# ── 미리보기 (맥 로컬 전용 — is_public_remote_path 미등록이라 터널 차단) ──

@router.get("/preview/{eid}/")
async def preview_index(eid: str):
    idx = _edition_dir(eid) / "index.html"
    if not idx.is_file():
        raise HTTPException(status_code=404, detail="not found")
    return HTMLResponse(idx.read_text(encoding="utf-8"), headers={"Cache-Control": "no-cache"})


@router.get("/preview/{eid}/media/{fname}")
async def preview_media(eid: str, fname: str):
    ed_dir = _edition_dir(eid)
    target = (ed_dir / "photos" / fname).resolve()
    if not str(target).startswith(str(ed_dir) + os.sep) or not target.is_file():
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(str(target))
