"""api_bulletin.py — 자유게시판 공개 서빙 + 익명 글쓰기.

공개 Worker(public-files 와 공유)가 /b/<slug>/... 요청을 이 엔드포인트로 끌어온다.
  · GET  /bulletin/page/{slug}            — 게시판 HTML(글 목록 + 쓰기 폼, 동적)
  · GET  /bulletin/media/{slug}/{post_id} — 글 첨부 이미지 (EXIF 제거본)
  · POST /bulletin/post/{slug}            — 익명 글쓰기 (multipart: name·body·image·honeypot)
보안: X-Showcase-Secret(Worker 만 보유) + slug 일치 + 경로 이탈 방어. 로그인 없음(자유게시판).
익명 글쓰기 방어: IP 간격 제한(429) + 이름/본문 캡 + 허니팟 + 이미지 EXIF 제거·다운스케일.

상태·글 로직은 패키지의 bulletin_core(handler 와 sys.modules 공유 인스턴스 — flock·IP캐시 공유).
★bulletin_core 수정 시 이 모듈이 캐시한 인스턴스는 백엔드 재시작으로만 갱신된다.
"""

import os
import sys
import importlib.util
from pathlib import Path

from fastapi import APIRouter, HTTPException, Header, Request, Form, File, UploadFile
from fastapi.responses import FileResponse, HTMLResponse

router = APIRouter(prefix="/bulletin", tags=["bulletin"])

_ROOT = Path(__file__).resolve().parent.parent
_PKG = _ROOT / "data" / "packages" / "installed" / "tools" / "bulletin"


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


def _load(name: str, key: str):
    """패키지 모듈을 sys.modules 공유 키로 로드 (handler 와 같은 인스턴스)."""
    if key in sys.modules:
        return sys.modules[key]
    p = _PKG / f"{name}.py"
    spec = importlib.util.spec_from_file_location(key, str(p))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    sys.modules[key] = mod
    return mod


_CORE = None
_HTML = None


def _core():
    global _CORE
    if _CORE is None:
        _CORE = _load("bulletin_core", "indiebiz_bulletin_core")
    return _CORE


def _html():
    global _HTML
    if _HTML is None:
        _HTML = _load("bulletin_html", "indiebiz_bulletin_html")
    return _HTML


def _board_or_404(slug: str) -> dict:
    c = _core()
    state = c.load_state()
    b = c.get_board(state, slug)
    if not b or b.get("slug") != slug:
        raise HTTPException(status_code=404, detail="no such board")
    return b


# ── 공개 읽기 ────────────────────────────────────────────────────────────

@router.get("/page/{slug}")
async def page(slug: str, x_showcase_secret: str = Header(default="")):
    _check_secret(x_showcase_secret)
    c = _core()
    b = _board_or_404(slug)
    posts = list(reversed(c.load_posts(b["id"])))   # 최신 먼저
    html = _html().render_board(b, posts)
    return HTMLResponse(html, headers={"Cache-Control": "no-cache"})


@router.get("/media/{slug}/{post_id}")
async def media(slug: str, post_id: str, x_showcase_secret: str = Header(default="")):
    _check_secret(x_showcase_secret)
    c = _core()
    b = _board_or_404(slug)
    post = next((p for p in c.load_posts(b["id"]) if p.get("id") == post_id), None)
    if not post or not post.get("image"):
        raise HTTPException(status_code=404, detail="no image")
    target = c.image_path(b["id"], post["image"])
    if not target:
        raise HTTPException(status_code=404, detail="not found")
    return FileResponse(str(target), headers={"Cache-Control": "public, max-age=86400"})


# ── 익명 글쓰기 ──────────────────────────────────────────────────────────

@router.post("/post/{slug}")
async def post(slug: str, request: Request,
               name: str = Form(default=""), body: str = Form(default=""),
               website: str = Form(default=""),           # 허니팟 — 봇이 채우면 조용히 폐기
               image: UploadFile = File(default=None),
               x_showcase_secret: str = Header(default=""), x_client_ip: str = Header(default="")):
    _check_secret(x_showcase_secret)
    c = _core()
    b = _board_or_404(slug)

    # 허니팟: 사람은 비워둔다 — 채워졌으면 성공인 척하고 저장 안 함(봇에 신호 안 줌).
    if (website or "").strip():
        return {"ok": True}

    ip = x_client_ip or (request.client.host if request.client else "")

    image_bytes = None
    if image is not None and getattr(image, "filename", "") and b.get("allow_images", True):
        image_bytes = await image.read()
        if image_bytes and len(image_bytes) > c.IMG_MAX_BYTES:
            raise HTTPException(status_code=413, detail="image too large")
        if not image_bytes:
            image_bytes = None

    try:
        c.add_post(b["id"], name, body, image_bytes=image_bytes, ip=ip)
    except c.TooFast:
        raise HTTPException(status_code=429, detail="too fast")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"ok": True}
