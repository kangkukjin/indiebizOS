"""portal_auth.py — 포털 회원 신원: 가입·로그인·개인 링크·비밀번호.

  · POST /portal/node/{login,logout,join}  — 슬러그 없는 단일 노드(루트 스코프 쿠키)
  · GET  /portal/key/{slug}/{memberkey}    — 개인 링크 착지(비밀번호 분실 복구 경로 겸용)
  · POST /portal/{join,login,logout,reset,password}/{slug}

가입 규약은 네이버식(아이디+비밀번호) — 승급이 곧 승인이라 가입은 레벨 0 자동 등록 후
즉시 로그인. 자격 저장·해시는 portal_core 단일 소스이고 여기는 HTTP 표면일 뿐이다.

api_portal.py 분할(2026-08-05 감사 부채 ⑨).
"""

import json

from fastapi import APIRouter, HTTPException, Header, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from portal_base import (
    _COOKIE_MAX_AGE, _check_secret, _client_ip, _core, _portal_or_404,
    _renderer, _set_session, _viewer,
)

router = APIRouter()

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


@router.post("/node/join")
async def node_join(request: Request, x_showcase_secret: str = Header(default=""),
                    x_client_ip: str = Header(default="")):
    """창고 가입 — 방문자가 아이디·비밀번호를 만들고 이메일(복구용)을 남긴다.
    레벨 0 자동 등록 → 즉시 로그인(루트 스코프 pk 쿠키, node_login 과 동일).
    회원=이웃(business.db) — 포털 가입(join/{slug})과 같은 전역 명부라, 창고에서
    가입한 계정으로 포털에도 로그인된다(레벨 승급은 창고 주인이 이웃 레벨로)."""
    _check_secret(x_showcase_secret)
    core = _core()
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
    try:
        m = core.create_member(None, name, email, 0, login_id=user_id, password=password)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    core.audit_log(f"join:{ip}", "portal", f"창고 가입 {name} ({user_id})", True)
    try:  # 운영자 알림 — best effort
        from notification_manager import get_notification_manager
        get_notification_manager().info(
            "창고 가입",
            f"{name} 님이 공개 창고에 가입했어요 (레벨 0) — 이웃 레벨을 주면 그 레벨 창고가 열립니다.",
            source="portal")
    except Exception:
        pass
    resp = JSONResponse({"ok": True, "name": name, "level": 0})
    kw = {"max_age": _COOKIE_MAX_AGE} if bool(body.get("auto", True)) else {}
    resp.set_cookie(key="pk", value=m["key"], path="/", httponly=True,
                    samesite="lax", secure=True, **kw)
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
