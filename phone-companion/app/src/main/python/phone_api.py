"""폰 로컬 백엔드 — 맥미니 없이 앱모드 UI + **실제 IBL 엔진**을 폰에서 서빙.

M2 본작업: /ibl/execute 가 weather 직접디스패치가 아니라 정본 엔진
(ibl_parser → ibl_engine/ibl_routing → 실제 패키지 핸들러)을 그대로 돈다.

번들: BaseBundle(Kotlin)이 indiebiz_base.zip 정본 트리를 filesDir 로 추출 →
serve(port, base_path) 가 sys.path 에 base/backend 추가 + INDIEBIZ_BASE_PATH 설정.
그러면 api_launcher_web 의 정본 상대경로(ibl_nodes.yaml)와 핸들러의 common 홉이
전부 정본대로 해소된다(폰 전용 override 불필요 — 드리프트 0).

응답 봉투: 런처 JS 는 VIEW_CTX.data = (/ibl/execute 응답)으로 view 를 해석하므로
PC /ibl/execute(api_ibl.py)와 동일하게 — 문자열이면 json.loads, 아니면 그대로 — 최상위 반환.
"""
import os
import sys
import json
import asyncio

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

# serve() 에서 정본 트리 경로가 정해진 뒤 채워진다(트리의 모듈을 import 하므로 지연 바인딩).
_lw = None
_scratch = None
_base = None

# === 분산 IBL: 자율주행 표면 → 맥 백엔드 위임 ===
# 두뇌=맥(claude_code, 단일 설정·프로젝트·스위치), 몸=폰. 폰의 자율주행 표면
# (프로젝트/스위치/시스템AI 채팅)은 맥 백엔드(:8765)로 프록시한다 — 번들 아님.
# 도달=LAN IP 또는 터널 URL(INDIEBIZ_MAC_URL). 인증=맥 원격 런처 세션
# (비번 INDIEBIZ_MAC_PASSWORD → 로그인 → X-Launcher-Session). 둘 다 keys.json/env 로.
# 미설정(오프라인) 시 자율주행은 빈 목록 graceful — 앱모드(폰 로컬 IBL)는 무관히 동작.
_mac_url = None
_mac_password = None
_mac_session = None


def _init_base(base_path):
    """sys.path + INDIEBIZ_BASE_PATH 설정 후 정본 모듈 바인딩."""
    global _lw, _scratch, _base
    _base = base_path
    backend_dir = os.path.join(base_path, "backend")
    if backend_dir not in sys.path:
        sys.path.insert(0, backend_dir)
    os.environ["INDIEBIZ_BASE_PATH"] = base_path
    os.environ["INDIEBIZ_PROFILE"] = "phone"  # #3: runs_on 필터/가드 활성

    # #4 API 키 주입: filesDir/secrets/keys.json (BaseBundle 가 안 지우는 sibling,
    # app-private, APK 밖, git 밖). 핸들러가 os.environ 우선 조회하므로 그대로 동작.
    # 프로비저닝=phone-companion/scripts/provision_phone_keys.py (정본 .env 부분집합 adb 푸시).
    try:
        secrets_path = os.path.join(os.path.dirname(base_path), "secrets", "keys.json")
        if os.path.exists(secrets_path):
            with open(secrets_path, "r", encoding="utf-8") as f:
                _keys = json.load(f) or {}
            for k, v in _keys.items():
                if v and not os.environ.get(k):
                    os.environ[k] = str(v)
            print(f"[phone_api] API 키 주입: {len([k for k in _keys if _keys[k]])}개")
    except Exception as e:
        print(f"[phone_api] 키 주입 스킵: {e}")

    # 분산 IBL: 맥 백엔드 위임 설정(LAN/터널 URL + 원격 런처 비번). keys.json/env 로 주입.
    global _mac_url, _mac_password, _mac_session
    _mac_url = (os.environ.get("INDIEBIZ_MAC_URL") or "").rstrip("/") or None
    _mac_password = os.environ.get("INDIEBIZ_MAC_PASSWORD") or None
    _mac_session = None
    if _mac_url:
        print(f"[phone_api] 맥 위임 대상: {_mac_url} (비번 {'설정됨' if _mac_password else '없음'})")

    # scratch 프로젝트 경로 — scope=project 액션이 경로를 요구하므로 확보(weather/crypto 는 미사용).
    # BaseBundle 이 지우는 indiebiz_base 의 sibling(filesDir/scratch)에 둬 생성물(신문 등)이 영속.
    _scratch = os.path.join(os.path.dirname(base_path), "scratch")
    os.makedirs(os.path.join(_scratch, "outputs"), exist_ok=True)

    import api_launcher_web as lw  # 트리 backend/ 에서. IBL_NODES_PATH 는 정본 상대경로로 자동 해소.
    _lw = lw


app = FastAPI()


@app.get("/launcher/app")
def launcher_app():
    return HTMLResponse(_lw.get_launcher_webapp_html())


@app.get("/launcher/instruments")
def instruments():
    return JSONResponse(_lw._derive_instruments())


@app.get("/launcher/config")
def launcher_config():
    # 폰 로컬 = 비번 게이트 없음(localhost 자기 자신)
    return {"remote_enabled": True, "has_password": False, "host": "phone-local"}


# === 맥 위임 프록시 (분산 IBL) ===

async def _mac_login() -> bool:
    """맥 원격 런처에 로그인 → 세션 토큰 확보. LAN 직결 시 맥이 비-외부로 보고
    인증을 건너뛸 수 있으나(api_launcher_web.is_external_request), 터널 경유엔 필수.
    비번 미설정이면 로그인 생략(LAN 경로 의존)."""
    global _mac_session
    if not _mac_url or not _mac_password:
        return False
    try:
        async with httpx.AsyncClient(timeout=15) as c:
            r = await c.post(f"{_mac_url}/launcher/auth/login",
                             json={"password": _mac_password})
        if r.status_code == 200:
            _mac_session = (r.json() or {}).get("session_id") or \
                r.cookies.get("launcher_session")
            return bool(_mac_session)
    except Exception as e:
        print(f"[phone_api] 맥 로그인 실패: {e}")
    return False


async def _mac_proxy(request: Request, path: str, *, timeout: float = 60.0):
    """들어온 요청을 맥 백엔드로 그대로 포워드. 401/403 이면 1회 재로그인 후 재시도.
    맥 미설정/미도달이면 None 반환(호출부가 graceful 폴백)."""
    if not _mac_url:
        return None
    method = request.method
    try:
        body = await request.body()
    except Exception:
        body = b""
    params = dict(request.query_params)

    async def _send():
        headers = {}
        if _mac_session:
            headers["X-Launcher-Session"] = _mac_session
        ct = request.headers.get("content-type")
        if ct:
            headers["content-type"] = ct
        async with httpx.AsyncClient(timeout=timeout) as c:
            return await c.request(method, f"{_mac_url}{path}",
                                   content=body or None, params=params or None,
                                   headers=headers)

    try:
        r = await _send()
        if r.status_code in (401, 403) and _mac_password:
            if await _mac_login():
                r = await _send()
        return r
    except Exception as e:
        print(f"[phone_api] 맥 프록시 오류 {path}: {e}")
        return "error"


def _relay(r):
    """httpx.Response → JSONResponse(가능하면 JSON, 아니면 텍스트)."""
    try:
        return JSONResponse(r.json(), status_code=r.status_code)
    except Exception:
        return JSONResponse({"response": r.text}, status_code=r.status_code)


def _list_or_empty(r, default):
    """자율주행 표면이 checkSession() 으로 읽는 GET 리스트 라우트용.
    ★폰은 내 기기 — 맥 인증 실패/미도달을 폰 사용자에게 '맥 로그인창'으로 전가하지 않는다.
    맥이 200 데이터를 주면 그대로, 그밖(미연결 None/예외 'error'/**비-200 401·403·5xx**)이면
    default 를 200 으로. 401 을 폰 런처로 전파하면 checkSession 이 비번 게이트를 띄우는 회귀(버그2)."""
    if r is None or r == "error" or getattr(r, "status_code", 0) != 200:
        return JSONResponse(default)
    return _relay(r)


@app.get("/projects")
async def projects(request: Request):
    # 맥 연결 시 맥의 프로젝트 목록을 그대로 — 폰이 PC와 같은 프로젝트를 본다.
    # 미연결/인증실패면 200 빈 목록 → 런처가 로그인 스킵하고 앱모드 진입(checkSession).
    return _list_or_empty(await _mac_proxy(request, "/projects"), [])


@app.get("/switches")
async def switches(request: Request):
    return _list_or_empty(await _mac_proxy(request, "/switches"), {"switches": []})


@app.get("/projects/{project_id}/agents")
async def project_agents(project_id: str, request: Request):
    return _list_or_empty(await _mac_proxy(request, f"/projects/{project_id}/agents"),
                          {"agents": []})


@app.post("/switches/{switch_id}/execute")
async def switch_execute(switch_id: str, request: Request):
    # 스위치 실행=맥의 IBL/에이전트 — 길어질 수 있어 넉넉한 타임아웃.
    r = await _mac_proxy(request, f"/switches/{switch_id}/execute", timeout=300.0)
    if r is None:
        return JSONResponse({"success": False, "error": "맥 백엔드 미연결(INDIEBIZ_MAC_URL 미설정)"}, status_code=503)
    if r == "error":
        return JSONResponse({"success": False, "error": "맥 백엔드 연결 실패"}, status_code=502)
    return _relay(r)


@app.post("/system-ai/chat")
async def system_ai_chat(request: Request):
    # 시스템 AI 채팅=맥 claude_code 의식+실행 — LLM 왕복이라 긴 타임아웃.
    r = await _mac_proxy(request, "/system-ai/chat", timeout=300.0)
    if r is None:
        return JSONResponse({"response": "맥 백엔드에 연결되어 있지 않습니다. (INDIEBIZ_MAC_URL 미설정 — 집 PC가 켜져 있어야 자율주행이 동작합니다.)"})
    if r == "error":
        return JSONResponse({"response": "맥 백엔드 연결에 실패했습니다. 집 PC와 네트워크를 확인하세요."})
    return _relay(r)


@app.post("/projects/{project_id}/agents/{agent_id}/start")
async def agent_start(project_id: str, agent_id: str, request: Request):
    r = await _mac_proxy(request, f"/projects/{project_id}/agents/{agent_id}/start", timeout=120.0)
    if r is None or r == "error":
        return JSONResponse({"success": False, "error": "맥 백엔드 미연결"}, status_code=503)
    return _relay(r)


@app.post("/projects/{project_id}/agents/{agent_id}/command")
async def agent_command(project_id: str, agent_id: str, request: Request):
    # 에이전트 명령=맥 claude_code 실행 — 긴 타임아웃.
    r = await _mac_proxy(request, f"/projects/{project_id}/agents/{agent_id}/command", timeout=300.0)
    if r is None:
        return JSONResponse({"response": "맥 백엔드에 연결되어 있지 않습니다."})
    if r == "error":
        return JSONResponse({"response": "맥 백엔드 연결에 실패했습니다."})
    return _relay(r)


@app.get("/output/{name}")
def output_file(name: str):
    """폰 로컬 생성물(신문 등 HTML)을 런처 오버레이가 띄우도록 서빙.
    os_open(집 PC GUI)이 home_only 라 폰에선 이 라우트 + 인앱 iframe 으로 본다."""
    from fastapi.responses import FileResponse
    safe = os.path.basename(name)
    path = os.path.join(_scratch, "outputs", safe)
    if os.path.exists(path):
        return FileResponse(path, media_type="text/html")
    return JSONResponse({"error": "파일을 찾을 수 없습니다."}, status_code=404)


@app.post("/ibl/execute")
async def execute(req: Request):
    """정본 통합 실행기로 라우팅 — PC /ibl/execute 와 동일 계약."""
    body = await req.json()
    code = body.get("code", "")
    if not code:
        return JSONResponse({"success": False, "error": "code 파라미터가 필요합니다."})

    # 무거운 import(system_tools→api_engine 등)는 첫 호출 시 지연 — 트리 + env 준비 후라 안전.
    from system_tools import _execute_ibl_unified

    def _run():
        return _execute_ibl_unified({"code": code}, _scratch, agent_id="phone")

    # 엔진은 동기(내부에 자체 이벤트 루프 관리). 서버 asyncio 루프 블록 방지 위해 스레드로.
    result = await asyncio.to_thread(_run)

    if isinstance(result, str):
        try:
            return JSONResponse(json.loads(result))
        except json.JSONDecodeError:
            return JSONResponse({"result": result})
    return JSONResponse(result)


# 서버 생명주기 — 액티비티가 start(앱 열기)/stop(앱 닫기)으로 제어.
_server = None
_serving = False


def is_serving() -> bool:
    return _serving


def serve(port=8765, base_path=None):
    """비-메인 스레드에서 호출 → 시그널 핸들러 금지.

    base_path: BaseBundle 이 추출한 정본 엔진 트리 루트(필수).
    이미 서빙 중이면 조기 반환(중복 바인드 방지).
    """
    global _server, _serving
    if not base_path:
        raise RuntimeError("base_path 필요 — BaseBundle.ensure() 결과를 넘기세요.")
    if _serving:
        return
    _init_base(base_path)

    # 기본 localhost 전용(WebView 자기접속). 분산 IBL 에서 맥(두뇌)이 폰(몸)으로 직접
    # phone_only 액션을 포워드하려면 폰이 LAN 도달 가능해야 하므로, keys.json 에
    # INDIEBIZ_BIND_HOST=0.0.0.0 주입 시 LAN 바인딩(=WiFi 노출 → #3 폰 인증 필요).
    config = uvicorn.Config(
        app, host=os.environ.get("INDIEBIZ_BIND_HOST", "127.0.0.1"),
        port=int(port), log_level="info", loop="asyncio")
    _server = uvicorn.Server(config)
    _server.install_signal_handlers = lambda: None
    _serving = True
    try:
        asyncio.run(_server.serve())   # should_exit=True 되면 반환
    finally:
        _serving = False
        _server = None


def stop():
    """다른 스레드에서 호출 — uvicorn 에 종료 신호. 데몬 serve 스레드가 곧 빠져나간다."""
    s = _server
    if s is not None:
        s.should_exit = True
