"""
public_face.py — 공개 얼굴 프로바이더 추상화 + 직접 서빙(direct serving) 게이트웨이.

배경(2026-07-19): 공개 표면 5종(/s 공개파일 · /n 가족신문 · /b 자유게시판 · /h 포털 ·
/r 정기보고)과 루트 창고 얼굴(/ · /manifest · /gb · /f · /login · /logout)은 지금까지
Cloudflare Worker(public-files)가 공개 주소에서 받아, 경로를 백엔드 내부 경로로 매핑하고
X-Showcase-Secret 을 주입해 터널로 중계해 왔다. 이 모듈은 그 매핑 층을 백엔드 안으로
내려서, Worker 없이도(=Cloudflare 없이도) 같은 공개 표면이 성립하게 한다.

구조 — "프로바이더 = 「공개 HTTPS 주소 → localhost:8765」 계약의 구현":
- cloudflare 길: 이름 있는 터널(+도메인) + Worker(R2 캐시·원본 은닉 = 선택적 가속기)
- tailscale 길: Funnel(무도메인 `*.ts.net`) → 이 게이트웨이가 직접 서빙
  AI 모델 프로바이더 갈아끼우듯 한쪽만 고른다. 왕복 시 주소가 바뀌는 건 피할 수 없고,
  이사 공지는 매니페스트 moved_to(아래) + 이웃 폴러 자동 치유로 흡수한다.

직접 서빙 = Host 가상호스팅:
- 요청 Host 가 direct_hosts 에 있을 때만 이 게이트웨이가 Worker 의 경로 지도를 적용해
  **인프로세스 ASGI 프록시**(httpx.ASGITransport — 소켓·자기HTTP 없음, 자기교착 없음)로
  기존 라우터에 시크릿을 주입해 전달한다. 기존 라우터(api_showcase 등)와 보안 모델
  (시크릿 게이트)은 무수정 — 시크릿의 유일 보유자가 Worker 에서 "이 프로세스 자신"으로
  한 명 늘어날 뿐이다.
- 매핑에 없는 경로(/launcher/app, /ping …)는 그대로 통과 → 기존 원격 인증 게이트가
  받는다. direct_hosts 는 _load_external_hostnames(외부 판별)에도 합류해야 한다
  (api_launcher_web 이 이 모듈의 설정 파일을 직접 읽는다).
- cloudflare 모드에선 direct_hosts 가 비어 이 게이트웨이는 완전히 잠잠하다(회귀 0).
- Worker 와의 의도적 차이: R2 엣지 캐시 없음(썸네일·미디어는 브라우저 캐시 헤더로 보완,
  매 요청 맥이 서빙 = tailscale 길의 성능 비용), 원본 은닉 없음.

설정: data/public_face.json
  provider     "cloudflare" | "tailscale"
  direct_hosts 직접 서빙할 Host 목록 (예: ["mac.tailxxxx.ts.net"]) — 포트 없이 소문자
  public_base  내 공개 주소(창고 정체성, 예 "https://mac.tailxxxx.ts.net")
  moved_to     이사 공지 주소 — 매니페스트에 실려 이웃 폴러가 등기부를 자동 치유
apply_public_base() 가 표면 상태 4곳(공개파일·포털·가족신문·게시판)의 public_base 를
일괄 반영한다(주소 자동변경의 "내 쪽 절반").
"""

import json
import os
import threading
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import (FileResponse, JSONResponse, PlainTextResponse,
                               RedirectResponse, StreamingResponse)
from pydantic import BaseModel

_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _ROOT / "data" / "public_face.json"
_SPA_INDEX = _ROOT / "data" / "packages" / "installed" / "tools" / "public-files" / "site" / "index.html"

_DEFAULT_CONFIG = {
    "provider": "cloudflare",
    "direct_hosts": [],
    "public_base": "",
    "moved_to": "",
}

_lock = threading.Lock()
_config_cache: Optional[dict] = None
_config_mtime: float = -1.0

# 인프로세스 프록시용 — api.py 가 부팅 시 attach_app(app) 으로 연결
_app = None
_client = None


# ── 설정 ─────────────────────────────────────────────────────────────────────

def load_config() -> dict:
    """설정 로드 (mtime 캐시 — 미들웨어가 매 요청 부르므로 디스크 재읽기 최소화)."""
    global _config_cache, _config_mtime
    try:
        mtime = _CONFIG_PATH.stat().st_mtime
    except OSError:
        mtime = -1.0
    with _lock:
        if _config_cache is not None and mtime == _config_mtime:
            return dict(_config_cache)
        cfg = dict(_DEFAULT_CONFIG)
        try:
            cfg.update(json.loads(_CONFIG_PATH.read_text(encoding="utf-8")))
        except Exception:
            pass
        _config_cache = dict(cfg)
        _config_mtime = mtime
        return cfg


def save_config(cfg: dict) -> dict:
    global _config_cache, _config_mtime
    merged = dict(_DEFAULT_CONFIG)
    merged.update(cfg)
    merged["direct_hosts"] = sorted({(h or "").split(":")[0].strip().lower()
                                     for h in (merged.get("direct_hosts") or []) if (h or "").strip()})
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with _lock:
        tmp = _CONFIG_PATH.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(_CONFIG_PATH)
        _config_cache = dict(merged)
        try:
            _config_mtime = _CONFIG_PATH.stat().st_mtime
        except OSError:
            _config_mtime = -1.0
    return merged


def get_public_base() -> str:
    return (load_config().get("public_base") or "").rstrip("/")


def get_moved_to() -> str:
    return (load_config().get("moved_to") or "").rstrip("/")


def is_direct_host(host: str) -> bool:
    """이 Host 를 직접 서빙(공개 얼굴)으로 받는가 — 미들웨어의 유일한 질문."""
    h = (host or "").split(":")[0].strip().lower()
    if not h:
        return False
    return h in set(load_config().get("direct_hosts") or [])


def _read_secret() -> str:
    v = os.environ.get("SHOWCASE_ORIGIN_SECRET", "")
    if v:
        return v
    envp = _ROOT / ".env"
    try:
        for line in envp.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("SHOWCASE_ORIGIN_SECRET="):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return ""


# ── 경로 지도 — worker.js 의 매핑을 그대로 이식 (public-files/site/worker.js 참조) ──

def _enc(s: str) -> str:
    """encodeURIComponent 등가 — 경로 조각·쿼리 값 재인코딩."""
    return quote(s or "", safe="")


def _map(method: str, path: str, query: dict, raw_query: str):
    """공개 경로 → 내부 경로. 반환:
    {"target","cache"} | {"redirect"} | {"spa": True} | {"status": 404} | None(=통과)
    """
    parts = path.split("/") if path else [""]
    head = parts[0]

    # ── 가족신문 /n/<slug>/... ──
    if head == "n" and len(parts) >= 2 and parts[1]:
        slug, rest = parts[1], parts[2:]
        if not rest:
            return {"redirect": f"/n/{_enc(slug)}/"}
        if rest == [""]:
            return {"target": f"/family-news/page/{_enc(slug)}?path=", "cache": "no-cache"}
        if rest[0] == "e":
            eid = rest[1] if len(rest) > 1 else ""
            if not eid:
                return {"status": 400}
            if len(rest) == 2:
                return {"redirect": f"/n/{_enc(slug)}/e/{_enc(eid)}/"}
            if len(rest) == 3 and rest[2] == "":
                return {"target": f"/family-news/page/{_enc(slug)}?path={_enc('e/' + eid)}",
                        "cache": "no-cache"}
            if rest[2] == "media" and len(rest) > 3 and rest[3]:
                file = "/".join(rest[3:])
                return {"target": f"/family-news/media/{_enc(slug)}/{_enc(eid)}"
                                  f"?rel={_enc('photos/' + file)}",
                        "cache": "public, max-age=86400"}
            return {"status": 404}
        if rest[0] == "gb":
            ed = query.get("edition", "")
            q = f"?edition={_enc(ed)}" if ed else ""
            return {"target": f"/family-news/gb/{_enc(slug)}{q}", "cache": "no-cache"}
        if rest[0] == "upload" and method == "POST":
            q = f"?{raw_query}" if raw_query else ""
            return {"target": f"/family-news/upload/{_enc(slug)}{q}", "cache": "no-cache"}
        return {"status": 404}

    # ── 개인 포털 /h/<slug>/... (쿠키 개인화 — 전부 no-store) ──
    if head == "h" and len(parts) >= 2 and parts[1]:
        slug, rest = parts[1], parts[2:]
        if not rest:
            return {"redirect": f"/h/{_enc(slug)}/"}
        if rest == [""]:
            return {"target": f"/portal/page/{_enc(slug)}", "cache": "no-store"}
        op = rest[0]
        if op == "k" and len(rest) > 1 and rest[1]:
            return {"target": f"/portal/key/{_enc(slug)}/{_enc(rest[1])}", "cache": "no-store"}
        if op in ("join", "login", "logout", "reset", "password") and method == "POST":
            return {"target": f"/portal/{op}/{_enc(slug)}", "cache": "no-store"}
        if op == "inst" and len(rest) > 1 and rest[1]:
            return {"target": f"/portal/inst/{_enc(slug)}/{_enc(rest[1])}", "cache": "no-store"}
        if op == "tune" and len(rest) > 1 and rest[1]:
            return {"target": f"/portal/tune/{_enc(slug)}/{_enc(rest[1])}", "cache": "no-store"}
        if op == "tool" and len(rest) > 1 and rest[1] and method == "POST":
            return {"target": f"/portal/tool/{_enc(slug)}/{_enc(rest[1])}", "cache": "no-store"}
        return {"status": 404}

    # ── 자유게시판 /b/<slug>/... ──
    if head == "b" and len(parts) >= 2 and parts[1]:
        slug, rest = parts[1], parts[2:]
        if not rest:
            return {"redirect": f"/b/{_enc(slug)}/"}
        if rest == [""]:
            return {"target": f"/bulletin/page/{_enc(slug)}", "cache": "no-store"}
        if rest[0] == "post" and method == "POST":
            return {"target": f"/bulletin/post/{_enc(slug)}", "cache": "no-store"}
        if rest[0] == "media" and len(rest) > 1 and rest[1]:
            return {"target": f"/bulletin/media/{_enc(slug)}/{_enc(rest[1])}",
                    "cache": "public, max-age=86400"}
        return {"status": 404}

    # ── 정기보고 /r/<slug>/ ──
    if head == "r" and len(parts) >= 2 and parts[1]:
        slug, rest = parts[1], parts[2:]
        if not rest:
            return {"redirect": f"/r/{_enc(slug)}/"}
        if rest == [""]:
            return {"target": f"/report/page/{_enc(slug)}", "cache": "no-store"}
        return {"status": 404}

    # ── 루트 창고 얼굴 (Worker 루트 경로들) ──
    if path == "":
        return {"target": "/portal/home", "cache": "no-store"}
    if path in ("manifest", "manifest/"):
        return {"target": "/portal/manifest", "cache": "no-store"}
    if path == "login" and method == "POST":
        return {"target": "/portal/node/login", "cache": "no-store"}
    if path == "logout" and method == "POST":
        return {"target": "/portal/node/logout", "cache": "no-store"}
    if path == "gb" and method in ("GET", "POST"):
        q = f"?{raw_query}" if raw_query else ""
        return {"target": f"/portal/gb{q}", "cache": "no-store"}
    if path == "like" and method == "POST":
        return {"target": "/portal/like", "cache": "no-store"}
    if path == "f":
        q = f"?{raw_query}" if raw_query else ""
        return {"target": f"/portal/file{q}", "cache": "no-store"}

    # ── 공개파일 /s/<slug>/... (갤러리 SPA + 데이터) ──
    if head == "s":
        if len(parts) < 3 or not parts[1]:
            return {"spa": True}
        slug, rest = parts[1], parts[2:]
        kind = rest[0]
        if kind == "list":
            p = query.get("path", "")
            return {"target": f"/showcase/list/{_enc(slug)}?path={_enc(p)}", "cache": "no-cache"}
        if kind in ("thumb", "media") and len(rest) > 1 and rest[1]:
            fid = rest[1]
            rel = query.get("rel", "")
            if not rel:
                return {"status": 400}
            return {"target": f"/showcase/{kind}/{_enc(slug)}/{_enc(fid)}?rel={_enc(rel)}",
                    "cache": "public, max-age=86400"}
        return {"spa": True}

    # 매핑 밖 — 일반 앱 라우팅으로 통과(런처 셸·핑 등은 기존 원격 게이트가 받는다)
    return None


# ── 인프로세스 프록시 ────────────────────────────────────────────────────────

def attach_app(app) -> None:
    """api.py 부팅 시 호출 — 인프로세스 ASGI 클라이언트 준비."""
    global _app
    _app = app


def _get_client():
    global _client
    if _client is None:
        import httpx
        if _app is None:
            raise RuntimeError("public_face: attach_app() 미호출")
        _client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=_app),
            base_url="http://public-face.internal",
            timeout=httpx.Timeout(300.0),
        )
    return _client


_PASS_RESP_HEADERS = ("location", "set-cookie", "content-length", "content-range",
                      "accept-ranges", "content-disposition")


async def _proxy(request: Request, target: str, cache: str):
    """내부 경로로 중계 — worker.js 의 proxy* 함수들과 같은 헤더 규율."""
    headers = {"X-Showcase-Secret": _read_secret()}
    for name in ("content-type", "cookie", "range", "user-agent"):
        v = request.headers.get(name)
        if v:
            headers[name] = v
    # 클라이언트 IP — 터널/funnel 이 앞에 있으면 X-Forwarded-For, 아니면 소켓 주소
    fwd = (request.headers.get("x-forwarded-for") or "").split(",")[0].strip()
    ip = fwd or (request.client.host if request.client else "")
    if ip:
        headers["X-Client-Ip"] = ip

    body = await request.body() if request.method in ("POST", "PUT", "PATCH") else None
    client = _get_client()
    req = client.build_request(request.method, target, headers=headers, content=body)
    resp = await client.send(req, stream=True)

    out_headers = {"content-type": resp.headers.get("content-type", "text/plain; charset=utf-8"),
                   "cache-control": cache}
    for name in _PASS_RESP_HEADERS:
        if name == "set-cookie":
            continue  # 다중 헤더 — 아래에서 append
        v = resp.headers.get(name)
        if v:
            out_headers[name] = v

    from starlette.background import BackgroundTask
    out = StreamingResponse(resp.aiter_raw(), status_code=resp.status_code,
                            headers=out_headers, background=BackgroundTask(resp.aclose))
    for sc in resp.headers.get_list("set-cookie"):
        out.headers.append("set-cookie", sc)
    return out


async def handle(request: Request):
    """직접 서빙 진입점 — 미들웨어가 direct host 요청에 대해 호출.
    None 반환 = 매핑 밖(일반 앱 라우팅으로 통과)."""
    path = request.url.path.lstrip("/")
    query = dict(request.query_params)
    raw_query = request.url.query or ""
    m = _map(request.method.upper(), path, query, raw_query)
    if m is None:
        return None
    if "redirect" in m:
        return RedirectResponse(m["redirect"], status_code=301)
    if "status" in m:
        return PlainTextResponse("not found" if m["status"] == 404 else "bad request",
                                 status_code=m["status"])
    if m.get("spa"):
        if _SPA_INDEX.exists():
            return FileResponse(str(_SPA_INDEX), media_type="text/html",
                                headers={"Cache-Control": "no-cache"})
        return PlainTextResponse("index.html 미배포", status_code=500)
    return await _proxy(request, m["target"], m.get("cache") or "no-store")


# ── 주소 일괄 반영 — "주소 자동변경"의 내 쪽 절반 ───────────────────────────────

def apply_public_base(base: str) -> dict:
    """표면 상태 4곳의 public_base 를 일괄 갱신. 반환 = 갱신 결과 지도."""
    base = (base or "").rstrip("/")
    results = {}

    # ① 공개파일 (showcase_state.json settings.public_base) — 다른 표면들의 기본값 뿌리
    try:
        p = _ROOT / "data" / "showcase_state.json"
        st = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
        st.setdefault("settings", {})["public_base"] = base
        p.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
        results["showcase"] = True
    except Exception as e:
        results["showcase"] = f"실패: {e}"

    # ② 포털 (portal_core 단일 소스 — flock 직렬화 경유)
    try:
        from api_portal import _core
        core = _core()

        def _set(st):
            st["public_base"] = base
        core.mutate_state(_set)
        results["portal"] = True
    except Exception as e:
        results["portal"] = f"실패: {e}"

    # ③ 가족신문 (data/family_news/state.json 등 패키지 상태 — 키만 교체)
    try:
        fn_state = None
        for cand in (_ROOT / "data" / "family_news" / "state.json",
                     _ROOT / "data" / "family-news" / "state.json"):
            if cand.exists():
                fn_state = cand
                break
        if fn_state:
            st = json.loads(fn_state.read_text(encoding="utf-8"))
            st["public_base"] = base
            fn_state.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
            results["family_news"] = True
        else:
            results["family_news"] = "상태 파일 없음(첫 발행 시 showcase 기본값 상속)"
    except Exception as e:
        results["family_news"] = f"실패: {e}"

    # ④ 게시판 (data/bulletin/state.json settings.public_base)
    try:
        p = _ROOT / "data" / "bulletin" / "state.json"
        if p.exists():
            st = json.loads(p.read_text(encoding="utf-8"))
            st.setdefault("settings", {})["public_base"] = base
            p.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
            results["bulletin"] = True
        else:
            results["bulletin"] = "상태 파일 없음"
    except Exception as e:
        results["bulletin"] = f"실패: {e}"

    return results


# ── 설정 API (로컬 전용 — is_public_remote_path 미등록 = 터널서 401) ─────────────

router = APIRouter(prefix="/public-face", tags=["public-face"])


class FaceConfig(BaseModel):
    provider: Optional[str] = None
    direct_hosts: Optional[list] = None
    public_base: Optional[str] = None
    moved_to: Optional[str] = None


@router.get("/config")
async def get_face_config():
    cfg = load_config()
    return {"success": True, **cfg, "spa_present": _SPA_INDEX.exists()}


@router.put("/config")
async def put_face_config(update: FaceConfig):
    cfg = load_config()
    up = update.dict(exclude_none=True)
    if up.get("provider") and up["provider"] not in ("cloudflare", "tailscale"):
        return JSONResponse({"success": False, "error": "provider 는 cloudflare|tailscale"},
                            status_code=400)
    cfg.update(up)
    merged = save_config(cfg)
    _reload_external_hostnames()
    return {"success": True, **merged}


@router.post("/apply-base")
async def post_apply_base(update: FaceConfig):
    base = (update.public_base or get_public_base())
    if not base:
        return JSONResponse({"success": False, "error": "public_base 가 비어 있습니다"},
                            status_code=400)
    return {"success": True, "base": base, "applied": apply_public_base(base)}


@router.post("/move")
async def post_move(update: FaceConfig):
    """이사 선언 — public_base 를 새 주소로 바꾸고 moved_to 로 공지.
    옛 주소가 살아 있는 동안 이웃 폴러가 매니페스트의 moved_to 를 보고 등기부를 치유한다."""
    new_base = (update.public_base or "").rstrip("/")
    if not new_base:
        return JSONResponse({"success": False, "error": "public_base(새 주소)가 필요합니다"},
                            status_code=400)
    cfg = load_config()
    cfg["public_base"] = new_base
    cfg["moved_to"] = new_base
    merged = save_config(cfg)
    applied = apply_public_base(new_base)
    _reload_external_hostnames()
    return {"success": True, **merged, "applied": applied}


def _reload_external_hostnames():
    """원격 인증 게이트의 호스트 캐시 갱신 (직접 서빙 호스트도 '외부'로 취급돼야 한다)."""
    try:
        from api_launcher_web import reload_external_hostnames
        reload_external_hostnames()
    except Exception:
        pass
