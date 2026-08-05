"""portal_face.py — 개인 포털의 공개 면(홈 페이지)과 PWA 설치 자산.

  · GET /portal/page/{slug}                     — 공개 홈 (쿠키의 회원키 → 레벨별 절단면)
  · GET /portal/pwa/{slug}/manifest.webmanifest — 포털마다 독립 앱으로 설치
  · GET /portal/pwa/{slug}/sw.js · icon/{size}

api_portal.py 분할(2026-08-05 감사 ⑨). 창고(공개 파일)는 portal_warehouse.py — 이 파일은
'포털'이라는 대상별 홈만 본다.
"""

import json
from pathlib import Path

from fastapi import APIRouter, HTTPException, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response, FileResponse

from portal_base import _ROOT, _check_secret, _core, _portal_or_404, _renderer, _viewer

router = APIRouter()

# ── 공개 홈 (포털별 절단면) ──────────────────────────────────────────────

@router.get("/page/{slug}")
async def page(slug: str, request: Request, x_showcase_secret: str = Header(default="")):
    _check_secret(x_showcase_secret)
    core = _core()
    state = core.load_state()
    portal = _portal_or_404(core, state, slug)
    viewer = _viewer(core, portal, request, slug)
    tiles = core.visible_tiles(state, portal, viewer.get("level") if viewer else None)
    html = _renderer().render_home(portal, viewer, tiles)
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


# ── PWA(홈 화면 설치) — 포털마다 독립 앱 ─────────────────────────────────────
# 알림 없는 최소 PWA: manifest + 아이콘 + 얇은 서비스워커. 가족·이웃이 포털을
# 홈 화면에 얹어 앱처럼 연다(즐겨찾기보다 한 단계 가깝다).
#   · scope/start_url = /h/<slug>/ → 포털마다 별개 앱(가족용·친구용 아이콘이 따로 선다)
#   · 서비스워커는 반드시 scope 안(/h/<slug>/sw.js)에서 서빙돼야 그 경로를 제어한다
#   · ★푸시 없음 — 같은 origin 다중 PWA 는 안드로이드가 알림 권한을 WebAPK 하나에
#     위임해 버린다(2026-08-01 웹푸시 은퇴의 진범). 알림이 필요해지면 origin 분리부터.
#   · 캐시 없음 — 포털 HTML 은 쿠키 개인화라 워커가 캐시하면 남의 화면이 뜬다.
_PWA_THEME = "#8a5a2b"
_PWA_BG = "#f6f1e7"
_ICON_DIR = _ROOT / "data" / "portal_icons"


def _icon_char(title: str) -> str:
    """아이콘에 새길 한 글자 — 제목의 첫 글자(이모지·기호는 건너뛴다)."""
    for ch in title:
        if ch.isalnum():
            return ch.upper()
    return "홈"


def _portal_icon(slug: str, title: str, size: int) -> Path:
    """포털 아이콘 PNG(디스크 캐시). 제목이 바뀌면 지문이 바뀌어 자동 재생성."""
    import hashlib
    from PIL import Image, ImageDraw, ImageFont
    tag = hashlib.sha1(f"{title}|{size}".encode("utf-8")).hexdigest()[:8]
    path = _ICON_DIR / f"{slug}-{size}-{tag}.png"
    if path.exists():
        return path
    _ICON_DIR.mkdir(parents=True, exist_ok=True)
    for old in _ICON_DIR.glob(f"{slug}-{size}-*.png"):
        try:
            old.unlink()          # 제목이 바뀐 옛 아이콘은 남겨둘 이유가 없다
        except OSError:
            pass
    img = Image.new("RGB", (size, size), _PWA_THEME)
    draw = ImageDraw.Draw(img)
    font = None
    for fp in ("/System/Library/Fonts/AppleSDGothicNeo.ttc",
               "/System/Library/Fonts/Supplemental/AppleGothic.ttf",
               "/Library/Fonts/Arial Unicode.ttf"):
        if Path(fp).exists():
            try:
                font = ImageFont.truetype(fp, int(size * 0.46))
                break
            except Exception:
                continue
    if font is not None:
        ch = _icon_char(title)
        box = draw.textbbox((0, 0), ch, font=font)
        draw.text(((size - (box[2] - box[0])) / 2 - box[0],
                   (size - (box[3] - box[1])) / 2 - box[1]),
                  ch, font=font, fill=_PWA_BG)
    tmp = path.with_suffix(".tmp")
    img.save(str(tmp), "PNG")
    tmp.replace(path)             # 원자 교체 — 반쯤 쓰인 파일을 브라우저가 물지 않게
    return path


@router.get("/pwa/{slug}/manifest.webmanifest")
async def pwa_manifest(slug: str, x_showcase_secret: str = Header(default="")):
    _check_secret(x_showcase_secret)
    core = _core()
    portal = _portal_or_404(core, core.load_state(), slug)
    title = (portal.get("title") or "포털").strip()
    base = f"/h/{slug}/"
    return JSONResponse({
        "name": title,
        "short_name": title[:12],
        "start_url": base,
        "scope": base,
        "display": "standalone",
        "background_color": _PWA_BG,
        "theme_color": _PWA_THEME,
        "lang": "ko",
        "icons": [
            {"src": base + "icon-192.png", "sizes": "192x192",
             "type": "image/png", "purpose": "any maskable"},
            {"src": base + "icon-512.png", "sizes": "512x512",
             "type": "image/png", "purpose": "any maskable"},
        ],
    }, media_type="application/manifest+json")


@router.get("/pwa/{slug}/sw.js")
async def pwa_sw(slug: str, x_showcase_secret: str = Header(default="")):
    _check_secret(x_showcase_secret)
    core = _core()
    _portal_or_404(core, core.load_state(), slug)
    # 설치 자격을 얻기 위한 최소 워커. fetch 는 가로채되 그대로 흘려보낸다
    # (캐시하면 쿠키 개인화 HTML 이 다른 회원에게 샌다).
    js = ("self.addEventListener('install',function(){self.skipWaiting();});\n"
          "self.addEventListener('activate',function(e){e.waitUntil(self.clients.claim());});\n"
          "self.addEventListener('fetch',function(){});\n")
    return Response(content=js, media_type="application/javascript")


@router.get("/pwa/{slug}/icon/{size}")
async def pwa_icon(slug: str, size: int, x_showcase_secret: str = Header(default="")):
    _check_secret(x_showcase_secret)
    if size not in (192, 512):
        raise HTTPException(status_code=404, detail="no such icon size")
    core = _core()
    portal = _portal_or_404(core, core.load_state(), slug)
    path = _portal_icon(slug, (portal.get("title") or "포털").strip(), size)
    return FileResponse(str(path), media_type="image/png")
