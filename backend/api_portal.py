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

_MANIFEST_ABOUT = ("이 노드가 공유하는 파일 목록(요청자 레벨로 절단). url 로 내용을 가져간다. "
                   "운영자가 이웃으로 승급하면 더 많은 파일이 열린다. has_restricted=잠긴 것 "
                   "존재(내용은 안 샘 = FOAF 라우팅 단서).")

_WAREHOUSE_ROOT = _ROOT / "공유창고"
_WAREHOUSE_LEVELS = {0: "0", 1: "1", 2: "2", 3: "3", 4: "4"}
_WAREHOUSE_CONFIG = _ROOT / "data" / "warehouse.json"   # {title} — 미추적(실명 등 PII는 코드 밖)


def _warehouse_title() -> str:
    try:
        return (json.loads(_WAREHOUSE_CONFIG.read_text(encoding="utf-8")).get("title")
                or "공유창고")
    except Exception:
        return "공유창고"
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


def _accessible_files(level: int, base: str = "") -> list:
    """레벨 0..level 창고를 병합한 단일 파일 목록 — 방문자에게 레벨 구조를 흘리지 않는다.
    같은 상대경로는 높은 레벨 판이 이김 → 비즈니스문서.md 가 자동으로 딱 1개(내 레벨 판)."""
    from urllib.parse import quote
    seen = {}
    for lv in sorted((l for l in _WAREHOUSE_LEVELS if l <= level), reverse=True):
        d = _warehouse_dir(lv)
        try:
            for p in d.rglob("*"):
                if not p.is_file() or p.name.startswith("."):
                    continue
                rel = str(p.relative_to(d))
                if rel not in seen:
                    seen[rel] = {"name": rel, "bytes": p.stat().st_size,
                                 "url": f"{base}/f?path={quote(rel)}"}
        except Exception:
            continue
    # 비즈니스문서(노드 소개)가 맨 앞, 나머지는 이름순
    files = sorted(seen.values(), key=lambda f: (f["name"] != _BIZDOC_NAME, f["name"]))
    return files[:_WAREHOUSE_LIST_CAP]


def _manifest_payload(node_title: str, base: str, level: int, is_member: bool) -> dict:
    _ensure_warehouses()
    return {
        "about": _MANIFEST_ABOUT,
        "title": node_title,
        "node_url": (base + "/manifest") if base else "/manifest",
        "viewer_level": level,
        "is_member": is_member,
        "files": _accessible_files(level, base),
        "has_restricted": level < max(_WAREHOUSE_LEVELS),
    }


# ── 창고 홈 (사람용) — 사이트 맨 루트(/)가 이 페이지다. 가장 짧은 주소 = 노드의 얼굴. ──
# 옛 bare-루트 잠금은 showcase(주소=비밀) 시절 규칙 — 창고는 보안이 레벨이라 루트를 당당히 연다.

def _fmt_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f}{unit}" if unit == "B" else f"{n:.1f}{unit}"
        n /= 1024
    return f"{n:.0f}B"


@router.get("/home")
async def node_home(request: Request, x_showcase_secret: str = Header(default="")):
    """창고 홈(사람용 HTML) — 내 레벨 이하 창고의 파일들 + 로그인. 루트(/)에서 서빙."""
    import html as _h
    _check_secret(x_showcase_secret)
    core = _core()
    state = core.load_state()
    portal = core.ensure_default_portal(state)
    viewer, level = _viewer_level(core, request)
    _ensure_warehouses()

    title = _h.escape(_warehouse_title())
    # 단일 목록 — 방문자에게 레벨 구조(어느 파일이 어느 등급인지)를 보여주지 않는다.
    # 비즈니스문서는 내 레벨 판 1개만(높은 레벨 판이 이기는 병합 규칙이 자동으로 보장).
    files = _accessible_files(level)
    rows = "".join(
        f'<li><a href="{_h.escape(f["url"])}">{_h.escape(f["name"])}</a>'
        f'<span class="sz">{_fmt_bytes(f["bytes"])}</span></li>'
        for f in files) or '<li class="empty">비어 있어요</li>'
    sections = [f'<section><ul>{rows}</ul></section>']
    locked_note = ('<p class="locked">🔒 더 높은 레벨의 창고가 있어요 — 로그인하거나 승급하면 열립니다.</p>'
                   if level < max(_WAREHOUSE_LEVELS) else '')
    if viewer:
        who = (f'<span>{_h.escape(viewer.get("name",""))} · 레벨 {level}</span> '
               f'<button onclick="lo()">로그아웃</button>')
        login_form = ''
    else:
        who = '<span>손님 (레벨 0)</span>'
        login_form = ('<form onsubmit="return li(this)"><input name="u" placeholder="아이디" '
                      'autocomplete="username"><input name="p" type="password" placeholder="비밀번호" '
                      'autocomplete="current-password"><button>로그인</button></form>')
    html_doc = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex">
<title>{title}</title><link rel="alternate" type="application/json" href="/manifest">
<style>
body{{font-family:-apple-system,'Apple SD Gothic Neo',sans-serif;max-width:680px;margin:2rem auto;padding:0 1rem;color:#222}}
header{{display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:.5rem;border-bottom:2px solid #222;padding-bottom:.7rem}}
h1{{font-size:1.4rem;margin:0}} h2{{font-size:1rem;margin:1.2rem 0 .4rem;color:#555}}
ul{{list-style:none;padding:0;margin:0}} li{{padding:.45rem .2rem;border-bottom:1px solid #eee;display:flex;justify-content:space-between;gap:1rem}}
a{{color:#0a58ca;text-decoration:none;word-break:break-all}} a:hover{{text-decoration:underline}}
.sz{{color:#999;font-size:.85rem;white-space:nowrap}} .empty{{color:#aaa}} .locked{{color:#888;font-size:.9rem}}
form{{display:flex;gap:.4rem;flex-wrap:wrap}} input{{padding:.35rem .5rem;border:1px solid #ccc;border-radius:6px;width:8.5rem}}
button{{padding:.35rem .8rem;border:1px solid #222;background:#222;color:#fff;border-radius:6px;cursor:pointer}}
.acct{{display:flex;align-items:center;gap:.6rem;font-size:.9rem;color:#555}}
</style></head><body>
<header><h1>{title}</h1><div class="acct">{who}{login_form}</div></header>
{''.join(sections)}
{locked_note}
<script>
async function li(f){{const r=await fetch('/login',{{method:'POST',headers:{{'Content-Type':'application/json'}},
body:JSON.stringify({{user_id:f.u.value,password:f.p.value,auto:true}})}});
if(r.ok)location.reload();else alert((await r.json()).detail||'로그인 실패');return false}}
async function lo(){{await fetch('/logout',{{method:'POST'}});location.reload()}}
</script></body></html>"""
    return HTMLResponse(html_doc, headers={"Cache-Control": "no-store"})


@router.get("/manifest")
async def node_manifest(request: Request, x_showcase_secret: str = Header(default="")):
    """노드의 공개 얼굴 — 슬러그 없는 canonical 창고 목록. 익명=레벨0, 쿠키(pk)=회원 레벨."""
    _check_secret(x_showcase_secret)
    core = _core()
    state = core.load_state()
    portal = core.ensure_default_portal(state)
    viewer, level = _viewer_level(core, request)
    base = (state.get("public_base") or "").rstrip("/")
    return JSONResponse(_manifest_payload(_warehouse_title(), base, level, bool(viewer)),
                        headers={"Cache-Control": "no-store"})


# ── 창고 파일 서빙 — /f?path= 단일 관문. 레벨 게이트가 서빙 자체에 걸린다. ────
# 주소에 레벨이 안 드러난다(어느 파일이 어느 등급인지 = 정보라서 숨김). 서버가 방문자 레벨
# 이하 창고를 높은 레벨부터 뒤져 첫 일치를 서빙. 레벨 밖 파일은 403 이 아니라 404(존재 자체
# 를 안 흘림). 공개파일(/s/)과 달리 주소를 알아도 레벨이 안 되면 열리지 않는다.

def _safe_rel(base: Path, rel: str) -> Path:
    p = (base / rel.lstrip("/")).resolve()
    if not str(p).startswith(str(base.resolve()) + os.sep) and p != base.resolve():
        raise HTTPException(status_code=400, detail="bad path")
    return p


@router.get("/file")
async def node_file(request: Request, path: str = "",
                    x_showcase_secret: str = Header(default="")):
    _check_secret(x_showcase_secret)
    core = _core()
    _viewer, level = _viewer_level(core, request)
    _ensure_warehouses()
    for lv in sorted((l for l in _WAREHOUSE_LEVELS if l <= level), reverse=True):
        f = _safe_rel(_warehouse_dir(lv), path)
        if f.is_file():
            import mimetypes
            ctype = mimetypes.guess_type(f.name)[0] or "application/octet-stream"
            from fastapi.responses import FileResponse
            return FileResponse(str(f), media_type=ctype,
                                headers={"Cache-Control": "no-store"})
    raise HTTPException(status_code=404, detail="no such file")


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
