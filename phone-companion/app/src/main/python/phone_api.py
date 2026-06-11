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

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
import uvicorn

# serve() 에서 정본 트리 경로가 정해진 뒤 채워진다(트리의 모듈을 import 하므로 지연 바인딩).
_lw = None
_scratch = None
_base = None


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


@app.get("/projects")
def projects():
    # 200 이면 런처가 로그인 스킵하고 showApp() (checkSession)
    return JSONResponse([])


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

    config = uvicorn.Config(
        app, host="127.0.0.1", port=int(port), log_level="info", loop="asyncio")
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
