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


# ── 노드의 공개 얼굴 = 레벨 창고(전용 폴더 0~4 + 로그인/레벨) ────────────────
# 설계(FOAF 창고): 레벨0~4 마다 '전용 폴더'가 따로 있다 — 기존 공개파일(사진 바스켓)과 무관.
#   · 기본 내용물 = 그 레벨의 비즈니스 문서(business_documents, 레벨별)가 자동 물질화(.md)
#   · 사용자는 Finder 로 그 폴더에 뭐든 던져넣는다(형식 자유 창고 — schema-on-read)
#   · 익명=레벨0 창고만, 로그인(단일 노드 쿠키 pk)=자기 레벨 이하 전부. 위 레벨은 has_restricted
#     냄새로만(이름·개수 안 샘). 서빙은 즉석 walk(공개파일 '구조' 재사용 — 인덱싱 없음).
# 주소: 노드는 하나, canonical `/manifest`. 창고는 `/w/<level>/`(레벨 자체가 주소 — 슬러그 없음).

_MANIFEST_ABOUT = ("이 노드가 레벨에 따라 공개하는 창고(폴더) 목록. url 로 들어가면 그 창고의 "
                   "파일 목록(JSON)을 받고, 파일 url 로 내용을 가져간다. 운영자가 이웃으로 "
                   "승급하면 더 높은 레벨 창고가 열린다. has_restricted=위 레벨에 잠긴 창고 "
                   "존재(내용은 안 샘 = FOAF 라우팅 단서).")

_WAREHOUSE_ROOT = _ROOT / "공유창고"
_WAREHOUSE_LEVELS = {0: "0", 1: "1", 2: "2", 3: "3", 4: "4"}
_BIZDOC_NAME = "비즈니스문서.md"
_WAREHOUSE_LIST_CAP = 500          # 창고 한 디렉토리 목록 상한(응답 폭주 방지)


def _warehouse_dir(level: int) -> Path:
    return _WAREHOUSE_ROOT / _WAREHOUSE_LEVELS[level]


def _ensure_warehouses() -> None:
    """창고 폴더 0~4 생성 + 레벨별 비즈니스 문서 물질화(DB 가 바뀌면 파일 갱신 — 볼 때 렌더)."""
    try:
        import business_manager
        bm = business_manager.BusinessManager()
    except Exception:
        bm = None
    for lv, name in _WAREHOUSE_LEVELS.items():
        d = _WAREHOUSE_ROOT / name
        d.mkdir(parents=True, exist_ok=True)
        if bm is None:
            continue
        try:
            doc = bm.get_business_document(lv)
            if doc and (doc.get("content") or "").strip():
                body = f"# {doc.get('title') or '비즈니스 문서'}\n\n{doc['content']}\n"
                f = d / _BIZDOC_NAME
                if not f.exists() or f.read_text(encoding="utf-8") != body:
                    f.write_text(body, encoding="utf-8")
        except Exception:
            pass


def _viewer_level(core, request: Request):
    """단일 노드 쿠키(pk) → (viewer, level). 익명이면 (None, 0)."""
    key = request.cookies.get("pk", "")
    viewer = core.find_member(None, key=key) if key else None
    return viewer, (int(viewer.get("level", 0)) if viewer else 0)


def _manifest_payload(node_title: str, base: str, level: int, is_member: bool) -> dict:
    _ensure_warehouses()
    warehouses, has_restricted = [], False
    for lv in sorted(_WAREHOUSE_LEVELS):
        if lv > level:
            has_restricted = True       # 위 레벨 창고 존재만 신호(이름·개수 안 샘)
            continue
        d = _warehouse_dir(lv)
        try:
            cnt = sum(1 for p in d.rglob("*") if p.is_file() and not p.name.startswith("."))
        except Exception:
            cnt = 0
        warehouses.append({
            "level": lv,
            "name": _WAREHOUSE_LEVELS[lv],
            "count": cnt,
            "url": (f"{base}/w/{lv}/" if base else f"/w/{lv}/"),
        })
    return {
        "about": _MANIFEST_ABOUT,
        "title": node_title,
        "node_url": (base + "/manifest") if base else "/manifest",
        "viewer_level": level,
        "is_member": is_member,
        "warehouses": warehouses,
        "has_restricted": has_restricted,
    }


@router.get("/manifest")
async def node_manifest(request: Request, x_showcase_secret: str = Header(default="")):
    """노드의 공개 얼굴 — 슬러그 없는 canonical 창고 목록. 익명=레벨0, 쿠키(pk)=회원 레벨."""
    _check_secret(x_showcase_secret)
    core = _core()
    state = core.load_state()
    portal = core.ensure_default_portal(state)
    viewer, level = _viewer_level(core, request)
    base = (state.get("public_base") or "").rstrip("/")
    return JSONResponse(_manifest_payload(portal.get("title", ""), base, level, bool(viewer)),
                        headers={"Cache-Control": "no-store"})


# ── 창고 서빙 — 목록(즉석 walk) + 파일. 레벨 게이트가 서빙 자체에 걸린다. ────
# 공개파일(/s/)과 달리 주소를 알아도 레벨이 안 되면 403 — 창고의 보안은 주소가 아니라 레벨.

def _warehouse_gate(core, request: Request, level: int) -> None:
    if level not in _WAREHOUSE_LEVELS:
        raise HTTPException(status_code=404, detail="no such warehouse")
    _viewer, vlevel = _viewer_level(core, request)
    if level > vlevel:
        raise HTTPException(status_code=403,
                            detail=f"레벨 {level} 창고입니다 — 로그인하거나 승급이 필요해요")


def _safe_rel(base: Path, rel: str) -> Path:
    p = (base / rel.lstrip("/")).resolve()
    if not str(p).startswith(str(base.resolve()) + os.sep) and p != base.resolve():
        raise HTTPException(status_code=400, detail="bad path")
    return p


@router.get("/warehouse/{level}")
async def warehouse_list(level: int, request: Request, path: str = "",
                         x_showcase_secret: str = Header(default="")):
    """창고 한 디렉토리 즉석 walk — 파일/하위폴더 목록(JSON). AI·사람 공용 통화."""
    _check_secret(x_showcase_secret)
    core = _core()
    _warehouse_gate(core, request, level)
    _ensure_warehouses()
    base_dir = _warehouse_dir(level)
    d = _safe_rel(base_dir, path) if path else base_dir
    if not d.is_dir():
        raise HTTPException(status_code=404, detail="no such folder")
    dirs, files = [], []
    try:
        for p in sorted(d.iterdir(), key=lambda x: x.name):
            if p.name.startswith("."):
                continue
            rel = str(p.relative_to(base_dir))
            if p.is_dir():
                dirs.append({"name": p.name, "path": rel})
            elif p.is_file():
                from urllib.parse import quote
                files.append({"name": p.name, "path": rel, "bytes": p.stat().st_size,
                              "url": f"/w/{level}/file?path={quote(rel)}"})
            if len(dirs) + len(files) >= _WAREHOUSE_LIST_CAP:
                break
    except Exception:
        raise HTTPException(status_code=500, detail="목록을 읽지 못했어요")
    return JSONResponse({"warehouse": _WAREHOUSE_LEVELS[level], "level": level,
                         "path": path, "dirs": dirs, "files": files},
                        headers={"Cache-Control": "no-store"})


@router.get("/warehouse/{level}/file")
async def warehouse_file(level: int, request: Request, path: str = "",
                         x_showcase_secret: str = Header(default="")):
    """창고 파일 서빙 — 같은 레벨 게이트 + 경로 이탈 방어."""
    _check_secret(x_showcase_secret)
    core = _core()
    _warehouse_gate(core, request, level)
    f = _safe_rel(_warehouse_dir(level), path)
    if not f.is_file():
        raise HTTPException(status_code=404, detail="no such file")
    import mimetypes
    ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
    from fastapi.responses import FileResponse
    return FileResponse(str(f), media_type=ctype,
                        headers={"Cache-Control": "no-store"})


# ── 단일 노드 로그인 — 루트(/) 스코프 쿠키 pk. 슬러그 없는 주소에서도 레벨 절단면을 읽게. ──

@router.post("/node/login")
async def node_login(request: Request, x_showcase_secret: str = Header(default=""),
                     x_client_ip: str = Header(default="")):
    _check_secret(x_showcase_secret)
    core = _core()
    ip = _client_ip(request, x_client_ip)
    try:
        body = json.loads((await request.body()).decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="bad json")
    user_id = str(body.get("user_id", "")).strip()
    password = str(body.get("password", ""))
    if not core.login_rate_ok(ip):
        raise HTTPException(status_code=429, detail="시도가 너무 잦아요 — 잠시 후 다시")
    m = core.find_member_by_login(None, user_id)
    if not m or m.get("revoked") or not core.verify_password(m, password):
        core.audit_log(f"node-login-fail:{ip}", "portal", f"login {user_id}", False)
        raise HTTPException(status_code=401, detail="아이디 또는 비밀번호가 맞지 않아요")
    core.audit_log(f"{m['name']}({m['id']})", "portal", "node login", True)
    resp = JSONResponse({"ok": True, "name": m["name"], "level": m["level"]})
    kw = {"max_age": _COOKIE_MAX_AGE} if bool(body.get("auto", True)) else {}
    resp.set_cookie(key="pk", value=m["key"], path="/", httponly=True,
                    samesite="lax", secure=True, **kw)
    resp.headers["Cache-Control"] = "no-store"
    return resp


@router.post("/node/logout")
async def node_logout(x_showcase_secret: str = Header(default="")):
    _check_secret(x_showcase_secret)
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(key="pk", path="/")
    resp.headers["Cache-Control"] = "no-store"
    return resp


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
    portal = _portal_or_404(core, state, slug)
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
    email = str(body.get("email", "")).strip()
    if not name:
        raise HTTPException(status_code=400, detail="이름을 입력해 주세요")
    if not user_id or not password:
        raise HTTPException(status_code=400, detail="아이디와 비밀번호를 입력해 주세요")
    if not core.valid_email(email):
        raise HTTPException(status_code=400, detail="비밀번호 찾기에 쓸 이메일을 정확히 입력해 주세요")

    # 회원 = 이웃(business.db) — 가입하면 이웃 책에 레벨 0 으로 등록/연결된다.
    try:
        m = core.create_member(portal, name, email, 0, login_id=user_id, password=password)
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
    return _set_session(resp, slug, m["key"], persistent=bool(body.get("auto", True)))


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


# ── 비밀번호 찾기 (임시 비밀번호를 등록 이메일로 발송) ─────────────────────

def _send_email(to: str, subject: str, body: str):
    """시스템 Gmail 계정으로 발송. (성공, 오류메시지)."""
    try:
        from channel_engine import _get_system_gmail_address
        from api_gmail import get_gmail_client_for_email
        sys_email = _get_system_gmail_address()
        if not sys_email:
            return False, "시스템 Gmail 계정이 설정되지 않았어요 (gmail extension config.yaml)"
        client = get_gmail_client_for_email(sys_email)
        if not client:
            return False, "Gmail 클라이언트를 준비하지 못했어요 (인증 필요)"
        client.send_message(to=to, subject=subject, body=body)
        return True, ""
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def _reset_email_body(portal: dict, home: str, member: dict, temp: str) -> str:
    title = portal.get("title") or "포털"
    return (
        f"{member.get('name','')}님, 안녕하세요.\n\n"
        f"'{title}' 로그인용 임시 비밀번호를 보내드려요.\n\n"
        f"    아이디: {member.get('login_id','')}\n"
        f"    임시 비밀번호: {temp}\n\n"
        f"이 비밀번호로 로그인한 뒤, 홈에서 '비밀번호 변경'으로 원하는 비밀번호로 바꿔 주세요.\n"
        f"로그인: {home}\n\n"
        f"본인이 요청하지 않았다면 이 메일은 무시하셔도 됩니다 (기존 비밀번호는 이미 바뀌었으니, "
        f"다시 '비밀번호 찾기'로 재설정해 주세요).\n"
    )


@router.post("/reset/{slug}")
async def reset_password(slug: str, request: Request, x_showcase_secret: str = Header(default=""),
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
    email = str(body.get("email", "")).strip()
    if not core.valid_email(email):
        raise HTTPException(status_code=400, detail="가입할 때 쓴 이메일을 정확히 입력해 주세요")
    # 메일 폭탄 방어 — 같은 이메일·같은 IP 둘 다 제한.
    if not core.reset_rate_ok(email.lower()) or not core.reset_rate_ok(f"ip:{ip}"):
        raise HTTPException(status_code=429, detail="요청이 너무 잦아요 — 잠시 후 다시 시도해 주세요")

    m = core.find_member_by_email(portal, email)
    if not m or m.get("revoked") or not m.get("login_id"):
        # 작은 가족 포털이라 명확히 안내(남용은 rate limit 이 막음).
        return JSONResponse({"ok": False, "detail": "그 이메일로 가입된 계정이 없어요"}, status_code=404)

    temp = core.gen_temp_password()
    home = core.portal_url(state, portal) or f"/h/{slug}/"
    # ★비밀번호는 메일 발송에 성공한 뒤에만 바꾼다(발송 실패로 잠기는 것 방지).
    ok, err = _send_email(email, f"[{portal.get('title','포털')}] 임시 비밀번호",
                          _reset_email_body(portal, home, m, temp))
    if not ok:
        core.audit_log(f"reset-fail:{ip}", "portal", f"pw reset {m.get('login_id')}", False,
                       note=err, portal=slug)
        raise HTTPException(status_code=502, detail=f"메일을 보내지 못했어요: {err}")

    core.set_password(m, temp)   # 이웃 레코드의 portal_pw 갱신(전역)
    core.audit_log(f"reset:{ip}", "portal", f"pw reset {m.get('login_id')}", True, portal=slug)
    resp = JSONResponse({"ok": True, "message": "등록된 이메일로 임시 비밀번호를 보냈어요 — 메일함을 확인해 주세요"})
    resp.headers["Cache-Control"] = "no-store"
    return resp


# ── 비밀번호 변경 (로그인한 회원 본인) ────────────────────────────────────

@router.post("/password/{slug}")
async def change_password(slug: str, request: Request, x_showcase_secret: str = Header(default="")):
    _check_secret(x_showcase_secret)
    core = _core()
    state = core.load_state()
    portal = _portal_or_404(core, state, slug)
    viewer = _viewer(core, portal, request, slug)
    if not viewer:
        raise HTTPException(status_code=401, detail="로그인이 필요해요")
    try:
        body = json.loads((await request.body()).decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="bad json")
    new_pw = str(body.get("new_password", ""))
    m = core.find_member(portal, member_id=viewer["id"])
    if not m:
        raise HTTPException(status_code=400, detail="회원을 찾을 수 없어요")
    try:
        core.set_password(m, new_pw)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    core.audit_log(f"{viewer['name']}({viewer['id']})", "portal", "pw change", True, portal=slug)
    resp = JSONResponse({"ok": True, "message": "비밀번호를 바꿨어요"})
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
