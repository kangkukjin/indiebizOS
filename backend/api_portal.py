"""api_portal.py — 개인 포털(커뮤니티 홈) 공개 서빙 + 회원 실행 게이트.

공개 Worker(public-files 와 공유)가 /h/<slug>/... 요청을 이 엔드포인트로 끌어온다.
  · GET  /portal/page/{slug}            — 공개 홈 (쿠키의 회원키 → 레벨별 절단면)
  · GET  /portal/key/{slug}/{memberkey} — 개인 링크 착지: 장수 쿠키 심고 홈으로 리다이렉트
  · POST /portal/join/{slug}            — 가입 신청 (레벨 0 자동 등록 + 개인 링크 반환)
  · GET  /portal/inst/{slug}/{iid}      — 계기 페이지 (런처 제네릭 렌더러 재사용 — __PORTAL 주입)
  · POST /portal/tool/{slug}/{iid}      — ★회원 실행 게이트: 쿠키→레벨→다이얼→한도→
                                          app: 선언 템플릿 화이트리스트→실행→감사로그
보안: X-Showcase-Secret(Worker 만 보유) + slug 일치. 개인화 응답이라 Worker 는 no-store.
상태·게이트 로직은 community-portal 패키지 portal_core.py 단일 소스(★수정 시 백엔드 재시작).
"""

import os
import re
import json
import time
import threading
from pathlib import Path

from fastapi import APIRouter, HTTPException, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse

router = APIRouter(prefix="/portal", tags=["portal"])

_ROOT = Path(__file__).resolve().parent.parent
_PKG = _ROOT / "data" / "packages" / "installed" / "tools" / "community-portal"

_COOKIE_MAX_AGE = 365 * 24 * 3600


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


def _core():
    """portal_core 공유 인스턴스 (handler 와 같은 sys.modules 키 — 프로세스당 1개)."""
    import sys
    import importlib.util
    name = "indiebiz_portal_core"
    mod = sys.modules.get(name)
    if mod is None:
        spec = importlib.util.spec_from_file_location(name, str(_PKG / "portal_core.py"))
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return mod


_HTML = None


def _renderer():
    """홈 HTML 렌더러(패키지 portal_html.py) — 디자인 단일 소스."""
    global _HTML
    if _HTML is None:
        import importlib.util
        spec = importlib.util.spec_from_file_location("_portal_html_api", str(_PKG / "portal_html.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        _HTML = mod
    return _HTML


def _portal_or_404(core, state: dict, slug: str) -> dict:
    p = core.portal_by_slug(state, slug)
    if not p:
        raise HTTPException(status_code=404, detail="no such portal")
    return p


def _viewer(core, portal: dict, request: Request, slug: str):
    key = request.cookies.get(f"pk_{slug}", "")
    return core.find_member(portal, key=key) if key else None


def _client_ip(request: Request, x_client_ip: str) -> str:
    return x_client_ip or (request.client.host if request.client else "")


def _set_session(resp, slug: str, key: str, persistent: bool = True):
    """로그인 쿠키 — persistent(자동 로그인)면 1년, 아니면 브라우저 세션."""
    kw = {"max_age": _COOKIE_MAX_AGE} if persistent else {}
    resp.set_cookie(key=f"pk_{slug}", value=key, path=f"/h/{slug}",
                    httponly=True, samesite="lax", secure=True, **kw)
    resp.headers["Cache-Control"] = "no-store"
    return resp


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


# ── 개인 링크 착지 (운영자 발급 열쇠 → 쿠키. 비밀번호 분실 복구 경로 겸용) ──

@router.get("/key/{slug}/{memberkey}")
async def key_landing(slug: str, memberkey: str, x_showcase_secret: str = Header(default="")):
    _check_secret(x_showcase_secret)
    core = _core()
    state = core.load_state()
    portal = _portal_or_404(core, state, slug)
    m = core.find_member(portal, key=memberkey)
    if not m:
        html = _renderer().render_notice(
            "링크가 유효하지 않아요",
            "회수됐거나 새 링크로 바뀌었을 수 있어요 — 운영자에게 재발급을 부탁하세요.",
            home=f"/h/{slug}/")
        return HTMLResponse(html, status_code=404, headers={"Cache-Control": "no-store"})
    resp = RedirectResponse(url=f"/h/{slug}/", status_code=302)
    return _set_session(resp, slug, memberkey)


# ── 가입 (아이디+비밀번호, 레벨 0 자동 등록 → 즉시 로그인) ────────────────

@router.post("/join/{slug}")
async def join(slug: str, request: Request, x_showcase_secret: str = Header(default=""),
               x_client_ip: str = Header(default="")):
    _check_secret(x_showcase_secret)
    core = _core()
    state = core.load_state()
    _portal_or_404(core, state, slug)
    ip = _client_ip(request, x_client_ip)
    if not core.join_rate_ok(ip):
        raise HTTPException(status_code=429, detail="너무 빨라요 — 잠시 후 다시 시도해 주세요")
    try:
        body = json.loads((await request.body()).decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="bad json")
    name = str(body.get("name", "")).strip()
    user_id = str(body.get("user_id", "")).strip()
    password = str(body.get("password", ""))
    if not name:
        raise HTTPException(status_code=400, detail="이름을 입력해 주세요")
    if not user_id or not password:
        raise HTTPException(status_code=400, detail="아이디와 비밀번호를 입력해 주세요")

    holder = {}

    def _fn(st):
        p = core.portal_by_slug(st, slug)
        if not p:
            raise ValueError("포털이 없습니다")
        holder["m"] = core.create_member(p, name, "", 0, login_id=user_id, password=password)

    try:
        core.mutate_state(_fn)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    core.audit_log(f"join:{ip}", "portal", f"가입 {name} ({user_id})", True, portal=slug)
    try:  # 운영자 알림 — best effort
        from notification_manager import get_notification_manager
        get_notification_manager().info("포털 가입",
                                        f"{name} 님이 '{slug}' 포털에 가입했어요 (레벨 0) — 승급하면 회원 계기가 열립니다.",
                                        source="portal")
    except Exception:
        pass
    resp = JSONResponse({"ok": True, "name": name})
    return _set_session(resp, slug, holder["m"]["key"], persistent=bool(body.get("auto", True)))


# ── 로그인 / 로그아웃 (네이버식 — 아이디+비밀번호, 자동 로그인) ────────────

@router.post("/login/{slug}")
async def login(slug: str, request: Request, x_showcase_secret: str = Header(default=""),
                x_client_ip: str = Header(default="")):
    _check_secret(x_showcase_secret)
    core = _core()
    state = core.load_state()
    portal = _portal_or_404(core, state, slug)
    ip = _client_ip(request, x_client_ip)
    try:
        body = json.loads((await request.body()).decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="bad json")
    user_id = str(body.get("user_id", "")).strip()
    password = str(body.get("password", ""))
    if not core.login_rate_ok(ip):
        raise HTTPException(status_code=429, detail="시도가 너무 잦아요 — 잠시 후 다시")
    m = core.find_member_by_login(portal, user_id)
    if not m or m.get("revoked") or not core.verify_password(m, password):
        core.audit_log(f"login-fail:{ip}", "portal", f"login {user_id}", False, portal=slug)
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 맞지 않아요")

    core.audit_log(f"{m['name']}({m['id']})", "portal", "login", True, portal=slug)
    resp = JSONResponse({"ok": True, "name": m["name"]})
    return _set_session(resp, slug, m["key"], persistent=bool(body.get("auto", True)))


@router.post("/logout/{slug}")
async def logout(slug: str, x_showcase_secret: str = Header(default="")):
    _check_secret(x_showcase_secret)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(key=f"pk_{slug}", path=f"/h/{slug}")
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ── 계기 페이지 — 런처 제네릭 렌더러 재사용 (__PORTAL 매개변수화, 포크 금지) ──

@router.get("/inst/{slug}/{iid}")
async def instrument_page(slug: str, iid: str, request: Request,
                          x_showcase_secret: str = Header(default="")):
    _check_secret(x_showcase_secret)
    core = _core()
    state = core.load_state()
    portal = _portal_or_404(core, state, slug)
    universe = {u["key"]: u for u in core.listable_universe(state)}
    u = universe.get(iid)
    if not u or u["kind"] != "instrument":
        raise HTTPException(status_code=404, detail="no such instrument")
    d = core.display_entry(portal, u)
    viewer = _viewer(core, portal, request, slug)
    lv = int(viewer.get("level", 0)) if viewer else -1
    ml = int(d.get("min_level", 1))
    if not d.get("enabled") or (ml > 0 and lv < ml):
        html = _renderer().render_notice(
            "🔒 회원 전용 계기예요" if d.get("enabled") else "지금은 닫혀 있어요",
            f"레벨 {ml} 이상 이웃만 쓸 수 있어요 — 로그인했는지 확인해 주세요."
            if d.get("enabled") else "운영자가 진열을 켜면 다시 열립니다.",
            home=f"/h/{slug}/")
        return HTMLResponse(html, status_code=403, headers={"Cache-Control": "no-store"})

    inst = core.portal_instrument(iid)
    if not inst:
        raise HTTPException(status_code=404, detail="no such instrument")
    from api_launcher_web import get_launcher_webapp_html
    payload = {"exec": f"/h/{slug}/tool/{iid}", "instrument": inst, "home": f"/h/{slug}/"}
    inject = ("<script>window.__PORTAL="
              + json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")
              + "</script>")
    html = get_launcher_webapp_html().replace("</head>", inject + "\n</head>", 1)
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


# ── 회원 실행 게이트 ─────────────────────────────────────────────────────

@router.post("/tool/{slug}/{iid}")
async def tool_gate(slug: str, iid: str, request: Request,
                    x_showcase_secret: str = Header(default=""),
                    x_client_ip: str = Header(default="")):
    _check_secret(x_showcase_secret)
    core = _core()
    try:
        body = json.loads((await request.body()).decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="bad json")
    code = str(body.get("code", ""))[:2000]
    if not code:
        raise HTTPException(status_code=400, detail="code required")
    ip = _client_ip(request, x_client_ip)
    member_key = request.cookies.get(f"pk_{slug}", "")

    # ① 계기 선언 템플릿 화이트리스트 — 범용 실행이 아니라 선언된 동작의 인스턴스만
    inst = core.portal_instrument(iid)
    if not inst:
        raise HTTPException(status_code=404, detail="no such instrument")
    allowed, reason = core.action_allowed(code, core.collect_templates(inst))
    if not allowed:
        core.audit_log(f"deny:{ip}", iid, code, False, note=reason, portal=slug)
        return JSONResponse({"error": reason}, status_code=403)

    # ② 신원·레벨·한도 (원자적 검사+카운트)
    try:
        auth = core.authorize_and_count(slug, iid, member_key, ip)
    except core.PortalDenied as e:
        core.audit_log(f"deny:{ip}", iid, code, False, note=e.msg, portal=slug)
        return JSONResponse({"error": e.msg}, status_code=e.status)

    # ③ 실행 — 앱 모드와 같은 경로(/ibl/execute 내부 재사용: 프로젝트 해소 + 단일 통화 정규화)
    try:
        from api_ibl import execute_ibl_code, IBLRequest
        result = await execute_ibl_code(IBLRequest(code=code, project_id="앱모드"))
        # 유튜브뮤직 등 클라이언트 재생: googlevideo URL 은 맥 IP 에 잠겨 외부망 회원은 403.
        # 오디오 프록시(/h/<slug>/tune/<vid>)로 바꿔치기 — 맥이 집 IP 로 받아 중계한다.
        if (isinstance(result, dict) and result.get("play_in_client")
                and result.get("stream_url") and result.get("video_id")):
            _tune_cache_put(str(result["video_id"]), str(result["stream_url"]))
            result["stream_url"] = f"/h/{slug}/tune/{result['video_id']}"
        core.audit_log(auth.get("who", "?"), iid, code, True, portal=slug)
        return result
    except HTTPException as e:
        core.audit_log(auth.get("who", "?"), iid, code, False, note=str(e.detail)[:100], portal=slug)
        return JSONResponse({"error": "실행 중 문제가 생겼어요 — 잠시 후 다시 시도해 주세요"},
                            status_code=500)


# ── 오디오 프록시 (유튜브뮤직 외부망 재생) ────────────────────────────────
# googlevideo URL 은 해소한 쪽(맥) IP 에 잠긴다 — 회원이 집 밖(LTE)이면 직접 재생 403.
# 그래서 맥이 집 IP 로 받아 회원에게 중계한다(Range 통과 = 구간 탐색). 회원 쿠키 + ytmusic
# 다이얼 게이트 뒤 — 익명 공개면 유튜브 공개 프록시가 되므로 절대 열지 않는다.

_TUNE_CACHE: dict = {}          # video_id -> (googlevideo_url, expire_ts)
_TUNE_LOCK = threading.Lock()
_VID_RE = re.compile(r"^[A-Za-z0-9_-]{5,20}$")


def _tune_cache_put(vid: str, url: str) -> None:
    m = re.search(r"[?&]expire=(\d{10})", url)
    exp = int(m.group(1)) if m else time.time() + 3600
    with _TUNE_LOCK:
        _TUNE_CACHE[vid] = (url, min(exp, time.time() + 5 * 3600))
        if len(_TUNE_CACHE) > 200:
            now = time.time()
            for k in [k for k, (_, e) in _TUNE_CACHE.items() if e < now]:
                _TUNE_CACHE.pop(k, None)


def _tune_cache_get(vid: str):
    with _TUNE_LOCK:
        v = _TUNE_CACHE.get(vid)
    if v and v[1] > time.time() + 60:
        return v[0]
    return None


def _tune_resolve(vid: str) -> str:
    """video_id → 오디오 스트림 URL. m4a 우선(iOS 사파리는 webm/opus 미지원)."""
    import yt_dlp
    with yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True,
                           "format": "bestaudio[ext=m4a]/bestaudio/best"}) as ydl:
        info = ydl.extract_info(f"https://www.youtube.com/watch?v={vid}", download=False)
        return info.get("url", "") or ""


@router.get("/tune/{slug}/{video_id}")
def tune(slug: str, video_id: str, request: Request,
         x_showcase_secret: str = Header(default=""),
         x_client_ip: str = Header(default="")):
    """오디오 스트림 중계 — 동기 def(스레드풀)라 이벤트 루프를 막지 않는다."""
    _check_secret(x_showcase_secret)
    core = _core()
    state = core.load_state()
    portal = _portal_or_404(core, state, slug)
    if not _VID_RE.match(video_id):
        raise HTTPException(status_code=400, detail="bad video id")

    # 회원 게이트: ytmusic 다이얼(켬 + 레벨) — 손님 불가(익명이면 공개 프록시가 됨)
    viewer = _viewer(core, portal, request, slug)
    universe = {u["key"]: u for u in core.listable_universe(state)}
    u = universe.get("ytmusic")
    d = core.display_entry(portal, u) if u else {}
    if not u or not d.get("enabled"):
        raise HTTPException(status_code=403, detail="닫혀 있는 계기입니다")
    if not viewer or int(viewer.get("level", 0)) < max(1, int(d.get("min_level", 1))):
        raise HTTPException(status_code=403, detail="회원 전용입니다")

    url = _tune_cache_get(video_id)
    if not url:
        # 캐시 미스 = ▶(카운트 완료) 경유가 아닌 수제/만료 요청 — 사용량으로 계산 후 해소
        member_key = request.cookies.get(f"pk_{slug}", "")
        ip = _client_ip(request, x_client_ip)
        try:
            core.authorize_and_count(slug, "ytmusic", member_key, ip)
        except core.PortalDenied as e:
            raise HTTPException(status_code=e.status, detail=e.msg)
        try:
            url = _tune_resolve(video_id)
        except Exception:
            url = ""
        if not url:
            raise HTTPException(status_code=502, detail="오디오를 가져오지 못했어요")
        _tune_cache_put(video_id, url)

    import requests as _rq
    fwd = {}
    rng = request.headers.get("range")
    if rng:
        fwd["Range"] = rng
    try:
        r = _rq.get(url, headers=fwd, stream=True, timeout=(10, 30))
        if r.status_code in (403, 410):     # URL 만료/IP 불일치 — 1회 재해소
            r.close()
            url = _tune_resolve(video_id)
            _tune_cache_put(video_id, url)
            r = _rq.get(url, headers=fwd, stream=True, timeout=(10, 30))
    except Exception:
        raise HTTPException(status_code=502, detail="스트림 연결 실패")
    if r.status_code not in (200, 206):
        r.close()
        raise HTTPException(status_code=502, detail="스트림 오류")
    headers = {k: r.headers[k] for k in ("Content-Type", "Content-Length", "Content-Range")
               if k in r.headers}
    headers.setdefault("Content-Type", "audio/mp4")
    headers["Accept-Ranges"] = "bytes"
    headers["Cache-Control"] = "no-store"
    return StreamingResponse(r.iter_content(65536), status_code=r.status_code, headers=headers)
