"""portal_base.py — 포털·창고 공개 서빙의 공용 기반 (시크릿 게이트·코어 로더·세션).

api_portal.py 1903줄 분할(2026-08-05 감사 부채 ⑨)에서 갈라져 나온 층. 여기 있는 것은
**모든 포털 라우트가 공유하는 것**뿐이다: Worker 시크릿 검증, portal_core/portal_html
지연 로더, 뷰어(쿠키→회원) 해소, 로그인 쿠키 굽기.

★`_check_secret` 이 여기 사는 것이 이 분할의 핵심 불변식이다 — 공개 라우트가 세션 없이
통과하는 근거가 이 함수 하나이고, scripts/check_public_routes.py 가 라우트마다 이 이름의
호출을 찾는다(이름으로 인정하므로 import 해서 직접 부르면 된다. 헬퍼로 한 겹 더 감싸면
그 가드가 못 따라갈 수 있다).
"""

import os
from pathlib import Path

from fastapi import HTTPException, Request

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
