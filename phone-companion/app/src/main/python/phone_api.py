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
from fastapi import FastAPI, Request, Body
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

    # 영속 userdata 디렉토리(filesDir/userdata = indiebiz_base 의 sibling, BaseBundle 재추출에
    # 안 지워짐 — business.db 선례). system_ai_memory 가 대화 DB 를 여기 둔다(동기화 없는 대화는
    # wipe=영구손실). system_ai_memory import 전에 설정해야 모듈 상수가 이 경로를 집는다.
    _userdata = os.path.join(os.path.dirname(base_path), "userdata")
    os.makedirs(_userdata, exist_ok=True)
    os.environ["INDIEBIZ_USERDATA"] = _userdata

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

    # 폰-자아 호스팅 step7: 3티어 모델 config 생성(없으면). 폰-자아가 로컬 하네스로 추론할 때
    # 쓰는 프로바이더. 경량=gemini_http(폰이 구글 API 직접, GEMINI_API_KEY env), 중급·본격=
    # claude_code_remote(맥 claude_code 렌트, 키 불필요). apiKey="" → 프로바이더가 env 폴백.
    _ensure_phone_ai_configs(base_path)

    # scratch 프로젝트 경로 — scope=project 액션이 경로를 요구하므로 확보(weather/crypto 는 미사용).
    # BaseBundle 이 지우는 indiebiz_base 의 sibling(filesDir/scratch)에 둬 생성물(신문 등)이 영속.
    _scratch = os.path.join(os.path.dirname(base_path), "scratch")
    os.makedirs(os.path.join(_scratch, "outputs"), exist_ok=True)

    import api_launcher_web as lw  # 트리 backend/ 에서. IBL_NODES_PATH 는 정본 상대경로로 자동 해소.
    _lw = lw


def _ensure_phone_ai_configs(base_path):
    """폰 3티어 모델 config 생성(없거나 옛 claude_code_remote 면 마이그레이션).

    폰-자아의 두뇌 = 폰 in-process Gemini(gemini_http, REST 직결). 추론 루프·도구 실행·jclass 가
    전부 폰에서 일어나 손이 폰에 있다(맥 claude_code 렌트·역방향 WS 장치 불필요). GEMINI_API_KEY 는
    keys.json 에서 env 주입 → apiKey="" 면 프로바이더가 env 폴백.
    """
    import json as _json
    cfg_dir = os.path.join(base_path, "data")
    os.makedirs(cfg_dir, exist_ok=True)
    defaults = {
        "system_ai_config.json": {"enabled": True, "provider": "gemini_http",
                                   "model": "gemini-3.1-pro-preview", "apiKey": "", "role": ""},
        "midtier_ai_config.json": {"enabled": True, "provider": "gemini_http",
                                   "model": "gemini-3.5-flash", "apiKey": ""},
        "lightweight_ai_config.json": {"enabled": True, "provider": "gemini_http",
                                       "model": "gemini-3.1-flash-lite", "apiKey": ""},
    }
    _RETIRED = {"claude_code_remote", "claude_code", "claude-code-remote"}
    for name, cfg in defaults.items():
        path = os.path.join(cfg_dir, name)
        write = not os.path.exists(path)
        if not write:
            # 옛 claude_code_remote 두뇌면 Gemini 로 마이그레이션(그 외 사용자 값은 보존).
            try:
                with open(path, "r", encoding="utf-8") as f:
                    cur = _json.load(f) or {}
                if cur.get("provider") in _RETIRED:
                    write = True
            except Exception:
                write = True
        if write:
            try:
                with open(path, "w", encoding="utf-8") as f:
                    _json.dump(cfg, f, ensure_ascii=False, indent=2)
                print(f"[phone_api] 폰 AI config: {name} → {cfg['provider']}/{cfg['model']}")
            except Exception as e:
                print(f"[phone_api] config 생성 실패 {name}: {e}")
    if _mac_url:
        print(f"[phone_api] 맥 위임 대상(빌림 전용): {_mac_url} (비번 {'설정됨' if _mac_password else '없음'})")


app = FastAPI()


# #3 폰 인증 게이트 — LAN 노출(0.0.0.0 바인드) 시 인바운드 보호.
# localhost(WebView 자기접속·adb forward loopback)는 무인증 통과. 비localhost(맥→폰 WiFi
# 분산 포워드)는 X-Phone-Token == INDIEBIZ_PHONE_TOKEN 일치 요구. 토큰 미설정이면 비localhost
# 전면 거부(= LAN에 무인증으로 절대 노출 안 함). 맥 _forward_to_phone 이 이 헤더를 동봉한다.
import hmac as _hmac


def _is_local_client(host: str) -> bool:
    return (not host) or host == "localhost" or host == "::1" or host.startswith("127.")


@app.middleware("http")
async def _phone_token_gate(request: Request, call_next):
    client = request.client.host if request.client else ""
    if not _is_local_client(client):
        token = os.environ.get("INDIEBIZ_PHONE_TOKEN")
        sent = request.headers.get("X-Phone-Token")
        if not (token and sent and _hmac.compare_digest(str(sent), str(token))):
            return JSONResponse({"error": "unauthorized: phone token required"}, status_code=401)
    return await call_next(request)


@app.get("/launcher/app")
def launcher_app():
    return HTMLResponse(_lw.get_launcher_webapp_html())


@app.get("/launcher/instruments")
def instruments():
    return JSONResponse(_lw._derive_instruments())


@app.get("/nodes/card")
def capability_card(detail: str = "full"):
    # 이 몸(폰)의 명함 — 몸 독립 소통 연구(실험 1). capability_card 가 몸-인식이라
    # 폰에선 phone_manifest.runnable_actions 만 실린다. 맥의 /nodes/card 와 동일 계약.
    from capability_card import build_card
    return JSONResponse(build_card(detail=detail))


@app.post("/nodes/ask")
def body_ask_endpoint(payload: dict):
    # 부탁 경로(실험 2) — 자연어 부탁을 이 몸(폰)이 자기 사전으로 컴파일·실행.
    # 폰엔 인지 프로바이더가 없어 body_ask 가 Gemini+자기사전으로 능력-감지 폴백.
    # 동기 def(스레드풀) — 컴파일·실행이 이벤트 루프를 막지 않게(자기교착 방지).
    from body_ask import handle_ask
    return JSONResponse(handle_ask((payload or {}).get("message", ""),
                                   dry_run=bool((payload or {}).get("dry_run")),
                                   from_body=(payload or {}).get("from_body", "")))


@app.get("/launcher/config")
def launcher_config():
    # 폰 로컬 = 비번 게이트 없음(localhost 자기 자신)
    return {"remote_enabled": True, "has_password": False, "host": "phone-local"}


@app.post("/launcher/clip-to-mac")
async def clip_to_mac():
    """폰 클립보드 → 맥 클립보드 — 데스크탑 런처 '폰으로' 버튼의 역방향 짝.

    읽기=네이티브 ClipboardManager(PhoneActions.getClipboard — WebView JS 의
    navigator.clipboard.readText 는 안드로이드서 신뢰 불가). Android 10+ 은 포그라운드
    앱만 읽을 수 있는데 버튼 탭 시점엔 이 앱이 포그라운드라 허용 케이스.
    놓기=기존 어휘 [self:output]{op:clipboard}(맥서 pbcopy) 를 _forward_to_mac 으로
    단건 포워드(세션 로그인·재시도 재사용). self:output 은 폰 manifest 서도 runnable 이라
    엔진 자동 위임이 안 됨 — 버튼 의미 자체가 "맥으로"라 명시 포워드가 맞음.
    역방향(맥→폰)과 달리 폰이 발신자·맥은 터널로 상시 도달 가능이라 푸시 큐 불필요.
    """
    def _read():
        from java import jclass  # 능력감지 — 폰에서만 성공 (INDIEBIZ_PROFILE 분기 금지)
        return str(jclass("com.indiebiz.phoneagent.PhoneActions").getClipboard() or "")
    try:
        text = await asyncio.to_thread(_read)
    except Exception:
        return JSONResponse({"success": False, "error": "폰 전용 기능"})
    if not text.strip():
        return JSONResponse({"success": False, "error": "클립보드가 비어 있음"})

    def _send():
        from ibl_engine import _forward_to_mac
        return _forward_to_mac("self", "output",
                               {"op": "clipboard", "content": text}, agent_id="phone")
    res = await asyncio.to_thread(_send)
    # 성공 판정: _output_clipboard 성공 시에만 copied_length 가 (중첩 어디든) 등장한다.
    raw = json.dumps(res, ensure_ascii=False, default=str) if isinstance(res, (dict, list)) else str(res)
    if "copied_length" in raw:
        return JSONResponse({"success": True, "chars": len(text)})
    err = (res.get("error") if isinstance(res, dict) else None) or "맥 전달 실패"
    return JSONResponse({"success": False, "error": str(err)[:120]})


# ============ 모델 기어 (폰 계기판 변속) — model_resolver 번들 위에서 로컬 ============
# ★catch-all(맥 프록시) 보다 먼저. 폰은 api_config 미번들이라 여기 인라인(맥 엔드포인트와 동형).

_GEAR_AXIS_ROLES = {"분류": "classify", "평가": "evaluate", "실행": "execution", "의식": "consciousness"}


def _gear_describe():
    import model_resolver as M
    g = M._load_gear()
    axes = {}
    for axis, role in _GEAR_AXIS_ROLES.items():
        d = M.resolve(role)
        axes[axis] = {"tier": d.get("tier"), "provider": d.get("provider"), "model": d.get("model")}
    return {"current_gear": M.get_gear(), "gears": M.list_gears(),
            "presets": g.get("presets", {}), "axes": axes,
            "tiers": M.TIERS, "axis_names": M.AXES,
            "consciousness_enabled": M.consciousness_enabled()}


def _gear_reset_providers():
    """기어/프리셋/핀 변경 후 폰 init-시점 provider 핫리로드."""
    for mod, fn in (("consciousness_agent", "reset_consciousness_agent"),
                    ("system_ai_core", "reset_system_ai_runner"),
                    ("consciousness_agent", "reset_midtier_provider"),
                    ("consciousness_agent", "reset_lightweight_provider"),
                    ("consciousness_agent", "reset_system_oneshot_provider")):
        try:
            import importlib
            getattr(importlib.import_module(mod), fn)()
        except Exception as e:
            print(f"[phone gear] {mod}.{fn} 리셋 경고: {e}")


def _gear_list_agents():
    """핀 대상 — 시스템 AI + 폰 로컬 프로젝트 에이전트. id=핀 키({project}:{agent_id})."""
    out = [{"id": "system_ai", "name": "시스템 AI", "project": "(시스템)"}]
    try:
        import yaml
        from runtime_utils import get_base_path
        proj_root = os.path.join(str(get_base_path()), "projects")
        if os.path.isdir(proj_root):
            for d in sorted(os.listdir(proj_root)):
                f = os.path.join(proj_root, d, "agents.yaml")
                if not os.path.isfile(f):
                    continue
                try:
                    with open(f, "r", encoding="utf-8") as fh:
                        data = yaml.safe_load(fh) or {}
                    for a in (data.get("agents") or []):
                        if isinstance(a, dict) and a.get("id"):
                            out.append({"id": f"{d}:{a['id']}", "name": a.get("name") or a["id"], "project": d})
                except Exception:
                    pass
    except Exception as e:
        print(f"[phone gear] 에이전트 열거 경고: {e}")
    return out


@app.get("/selfcheck/engine-imports")
def selfcheck_engine_imports():
    """이 몸(android)에 번들된 backend 엔진 모듈이 *전부 import 되나* 검증 — 파생 번들의 그라운드-트루스.

    build_body_bundle.py 가 정적으로 파생한 번들이 실제로 이 하드웨어에서 import-안전한지 확인한다.
    실패가 있으면 = 정적 파생이 놓친 몸-비호환(예: 조건부/동적 import) → data/bodies/android.json
    absent_packages 에 추가해야 할 신호. 단일 코드베이스 다중 몸의 '자연 동기화' 안전망."""
    import importlib, os as _os
    from runtime_utils import get_base_path
    be = _os.path.join(str(get_base_path()), "backend")
    ok, failed = [], {}
    try:
        names = sorted(f[:-3] for f in _os.listdir(be) if f.endswith(".py") and not f.startswith("_"))
    except Exception as e:
        return JSONResponse({"error": f"backend 디렉토리 없음: {e}"}, status_code=500)
    for n in names:
        try:
            importlib.import_module(n)
            ok.append(n)
        except Exception as e:
            failed[n] = f"{type(e).__name__}: {e}"
    return {"total": len(names), "ok": len(ok), "failed": failed}


@app.get("/model-gear")
def phone_get_gear():
    try:
        return _gear_describe()
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.put("/model-gear")
def phone_set_gear(body: dict = Body(...)):
    import model_resolver as M
    name = (body.get("gear") or "").strip()
    if not name or not M.set_gear(name):
        return JSONResponse({"error": f"알 수 없는 기어: {name}"}, status_code=400)
    _gear_reset_providers()
    return {"status": "changed", **_gear_describe()}


@app.put("/model-gear/consciousness")
def phone_set_consciousness(body: dict = Body(...)):
    """의식 토글 — OFF 면 인지 파이프라인이 THINK 경로를 차단(반사 유지 + 나머지 바로 실행).
    핫리로드(매 _decide_request_type 가 consciousness_enabled() 를 새로 읽음) — 재시작 불요."""
    import model_resolver as M
    enabled = body.get("enabled")
    if enabled is None:
        return JSONResponse({"error": "enabled(bool) 값이 필요합니다."}, status_code=400)
    M.set_consciousness(bool(enabled))
    return {"status": "changed", **_gear_describe()}


@app.put("/model-gear/presets")
def phone_set_presets(body: dict = Body(...)):
    import model_resolver as M
    if not M.set_presets(body.get("presets")):
        return JSONResponse({"error": f"잘못된 프리셋(축 {M.AXES}, 티어 {M.TIERS})"}, status_code=400)
    _gear_reset_providers()
    return {"status": "saved", **_gear_describe()}


@app.get("/model-gear/overrides")
def phone_get_overrides():
    import model_resolver as M
    return {"overrides": M.get_overrides(), "agents": _gear_list_agents(), "tiers": M.TIERS}


@app.put("/model-gear/overrides")
def phone_set_overrides(body: dict = Body(...)):
    import model_resolver as M
    cleaned = {k: v for k, v in (body.get("overrides") or {}).items() if v}
    if not M.set_overrides(cleaned):
        return JSONResponse({"error": f"잘못된 핀(티어 {M.TIERS})"}, status_code=400)
    _gear_reset_providers()
    return {"status": "saved", "overrides": M.get_overrides()}


@app.get("/nodes/peer-status")
async def peer_status_local():
    """폰 관점의 피어 = 맥(집 PC). 맥 /ping 으로 생존 확인.

    ※반드시 로컬에서 답한다. catch-all 로 맥에 프록시하면 맥이 *자기 관점*(mac-branch =
    연결된 폰)을 피어로 돌려줘 폰 계기판이 "맥" 대신 "폰"을 가리키는 버그가 난다.
    api_nodes.peer_status 의 phone-branch 와 동일 의미(폰 백엔드는 그 라우터를 안 올리므로 여기서)."""
    if not _mac_url:
        return {"has_peer": False, "peer_name": "맥미니(집 PC)", "peer_icon": "💻",
                "online": False, "detail": "맥 주소(INDIEBIZ_MAC_URL) 미설정"}
    online = False
    try:
        async with httpx.AsyncClient(timeout=2) as c:
            r = await c.get(f"{_mac_url}/ping")
            online = (r.status_code == 200)
    except Exception:
        online = False
    return {"has_peer": True, "peer_name": "맥미니(집 PC)", "peer_icon": "💻",
            "online": bool(online), "detail": None}


@app.get("/ping")
async def ping_local():
    """폰 자신의 생존 신호 — "누구냐"엔 폰이 폰으로 답한다(자기-지식은 빌리지 않는다).

    ※로컬 필수. catch-all 로 맥에 프록시하면 폰이 자기 정체를 'mac'으로 답해버린다
    (맥이 자기 /ping=kind:mac 을 돌려줌). 정체성은 절대 위임 대상이 아니다."""
    try:
        from runtime_utils import detect_body
        kind = detect_body().get("kind", "phone")
    except Exception:
        kind = "phone"
    return {"ok": True, "kind": kind}


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
        rng = request.headers.get("range")  # 오디오/비디오 시킹 — Range 를 맥으로 전달(FileResponse 206 통과)
        if rng:
            headers["range"] = rng
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
    """httpx.Response → 폰 응답. **바이너리/미디어(오디오·이미지·비디오·pdf·octet-stream)는
    원본 Content-Type + 원본 바이트로 통과**한다 — 예전엔 전부 JSON 으로 강제해 mp3 가 깨진
    텍스트로 `{"response": ...}` 래핑돼 <audio> 가 재생 못 했다(폰 오디오 브리핑 재생 버튼
    무반응의 원인). JSON/텍스트 응답은 기존대로."""
    ct = (r.headers.get("content-type") or "").lower()
    if ct and not ct.startswith("text/") and "json" not in ct:
        from starlette.responses import Response as _Resp
        # content-disposition = 창고 파일 내려받기(?download=1)의 저장 강제 + 원래 파일명.
        # 빠뜨리면 폰이 파일을 저장 대신 인라인으로 열고 이름을 잃는다(Worker allowlist 와 같은 부류).
        headers = {k: r.headers[k] for k in ("content-range", "accept-ranges", "content-length",
                                             "content-disposition")
                   if k in r.headers}
        return _Resp(content=r.content, status_code=r.status_code, media_type=ct, headers=headers)
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


# === 분산 IBL: business.db(주소록 메타데이터) 폰↔맥 합집합 동기화 ===
# 폰이 자기 business.db 를 갖고 작동(자급) + 맥 연결 시 합집합 머지(LWW+tombstone).
# 자동응답=PC전용·메시지내용=릴레이수렴이라, 폰 DB 머지 대상은 주소록 메타데이터뿐.
def _phone_bm():
    """폰 로컬 business.db (영속 userdata 경로 — BaseBundle 재추출에 안 지워짐).
    최초 호출 시 생성+마이그레이션(uuid/deleted 등 동기화 스키마)."""
    from pathlib import Path
    from business_manager import BusinessManager
    userdata = os.path.join(os.path.dirname(_base), "userdata")
    os.makedirs(userdata, exist_ok=True)
    return BusinessManager(db_path=Path(os.path.join(userdata, "business.db")))


# === 폰-자아 프로젝트 (자아별 사적 작업공간 — 대화처럼 로컬·동기화X·맥서 시드 복사) ===
# 사용자 결정(2026-06-14): 프로젝트/스위치는 맥과 폰이 각자여야(다른 몸). 초기엔 맥 복사로
# 시드, 이후 독립 진화. 동기화 안 함. 스위치는 폰에 불필요(제외). 에이전트는 폰 두뇌로 실행.
_phone_pm_inst = None


def _phone_userdata() -> str:
    ud = os.path.join(os.path.dirname(_base), "userdata")
    os.makedirs(ud, exist_ok=True)
    return ud


def _seed_projects(userdata: str):
    """첫 부팅 1회: 번들 _project_seed(구조만) → userdata/projects. 이미 있으면 스킵(독립 보존).
    ★대화(conversations.db)·기억(memory_*.db)·런타임 상태는 시드에 미포함(맥-자아 사적, 두-자아)."""
    import shutil
    proj_dir = os.path.join(userdata, "projects")
    if os.path.exists(os.path.join(proj_dir, "projects.json")):
        return  # 이미 시드/사용 중 — 자아별 독립 보존(재시드 안 함)
    seed = os.path.join(_base, "data", "_project_seed")
    if not os.path.isdir(seed):
        print("[phone_api] 프로젝트 시드 소스 없음 — 빈 상태로 시작")
        return
    os.makedirs(proj_dir, exist_ok=True)
    n = 0
    for name in os.listdir(seed):
        src = os.path.join(seed, name)
        dst = os.path.join(proj_dir, name)
        try:
            if os.path.isfile(src):
                shutil.copy2(src, dst)
            elif os.path.isdir(src):
                shutil.copytree(src, dst, dirs_exist_ok=True)
            n += 1
        except Exception as e:
            print(f"[phone_api] 프로젝트 시드 '{name}' 실패: {e}")
    print(f"[phone_api] 프로젝트 시드 완료: {n}개 항목 → {proj_dir}")


def _phone_pm():
    """폰 로컬 ProjectManager (base_path=userdata → projects/templates 영속). 첫 호출 시 시드."""
    global _phone_pm_inst
    if _phone_pm_inst is None:
        from pathlib import Path
        from project_manager import ProjectManager
        ud = _phone_userdata()
        _seed_projects(ud)
        _phone_pm_inst = ProjectManager(base_path=Path(ud))
    return _phone_pm_inst


async def _mac_post_json(path, payload, *, timeout: float = 60.0):
    """맥 백엔드에 JSON POST(폰이 originator). 401/403 이면 재로그인 후 재시도. 실패 None."""
    if not _mac_url:
        return None

    async def _send():
        headers = {"content-type": "application/json"}
        if _mac_session:
            headers["X-Launcher-Session"] = _mac_session
        async with httpx.AsyncClient(timeout=timeout) as c:
            return await c.post(f"{_mac_url}{path}", json=payload, headers=headers)

    try:
        r = await _send()
        if r.status_code in (401, 403) and _mac_password:
            if await _mac_login():
                r = await _send()
        return r
    except Exception as e:
        print(f"[phone_api] 맥 POST 오류 {path}: {e}")
        return None


def _is_rfc1918(ip: str) -> bool:
    p = ip.split(".")
    if len(p) != 4:
        return False
    try:
        a, b = int(p[0]), int(p[1])
    except ValueError:
        return False
    return a == 10 or (a == 192 and b == 168) or (a == 172 and 16 <= b <= 31)


def _phone_lan_ip():
    """허브(맥)가 이 폰에 닿을 LAN IP. WiFi(wlan0) 사설 IP를 고른다.

    ★맥 URL 이 터널(launcher.*.uk)이면 "맥으로 가는 경로"는 셀룰러(192.0.0.2)라 맥이 못 닿음.
    그래서 경로가 아니라 *인터페이스 열거*로 RFC1918(주로 wlan0)을 직접 고른다 — 맥이 같은
    WiFi LAN 에 있을 때 닿는 주소. (away-case: 다른 LAN/외부면 맥→폰 직결 불가는 별개 과제.)
    """
    try:
        from java import jclass
        NI = jclass("java.net.NetworkInterface")
        Collections = jclass("java.util.Collections")
        # ★Chaquopy 는 추상 Enumeration.nextElement 직접 호출 불가 → Collections.list 로 구체
        # ArrayList 로 materialize 후 size()/get() (구체 메서드)로 순회.
        ifaces = Collections.list(NI.getNetworkInterfaces())
        wlan, other = [], []
        for i in range(ifaces.size()):
            ni = ifaces.get(i)
            try:
                if ni.isLoopback() or not ni.isUp():
                    continue
            except Exception:
                pass
            name = ni.getName() or ""
            addrs = Collections.list(ni.getInetAddresses())
            for j in range(addrs.size()):
                host = (addrs.get(j).getHostAddress() or "").split("%")[0]  # IPv6 zone 제거
                if ":" in host or not _is_rfc1918(host):
                    continue
                (wlan if name.startswith("wlan") else other).append(host)
        if wlan:
            return wlan[0]
        if other:
            return other[0]
    except Exception as e:
        print(f"[phone_api] NetworkInterface IP 실패: {e}")
    # 폴백: 맥(허브) host 로 향하는 인터페이스 (LAN 직결 시 정확)
    try:
        import socket
        host = (_mac_url or "").split("//")[-1].split("/")[0].split(":")[0] or "8.8.8.8"
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect((host, 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return None


async def _register_with_hub(port: int):
    """다중 노드: 이 폰을 허브(맥) 프레즌스 레지스트리에 등록 + 주기 heartbeat.

    폰 수를 고정하지 않는 핵심 — 폰이 부팅 시 스스로 합류하면 허브가 "지금 연결된 노드"를
    안다(다른 폰·허브 설정 무수정). 허브→폰 도달이 가능할 때만(토큰=LAN 노출) 의미가 있으므로
    INDIEBIZ_PHONE_TOKEN + 맥 URL 둘 다 있을 때만 활성. device_registry 로 안정 device_id/별칭.
    """
    if not _mac_url or not os.environ.get("INDIEBIZ_PHONE_TOKEN"):
        return  # LAN 미노출이면 허브가 폰에 못 닿음 → 등록 무의미(폰→맥 빌림은 env 로 계속 동작)
    try:
        import device_registry as dr
        device_id = dr.self_device_id()
        alias = dr.self_alias("phone")
        caps = [dr.PHONE_CLASS]
    except Exception as e:
        print(f"[phone_api] 노드 등록 스킵(device_registry 부재): {e}")
        return

    ip = _phone_lan_ip()
    if not ip:
        print("[phone_api] 노드 등록 스킵: LAN IP 미확인")
        return
    payload = {
        "device_id": device_id, "alias": alias, "capabilities": caps,
        "url": f"http://{ip}:{port}", "auth": "x_phone_token", "owner": "self",
        "primary": False,
    }
    import asyncio
    first = True
    last_ip = ip
    while True:
        # 기본 페이스: 롱폴(서버가 25초 hold)이라 루프 틈은 최소로 — 틈에 온 작업은
        # 다음 폴까지 기다리므로, 이 값이 곧 푸시 전달의 최악 지연이다.
        delay = 0.3
        try:
            if first:
                r = await _mac_post_json("/nodes/register", payload, timeout=20.0)
                if r is not None and getattr(r, "status_code", 0) == 200:
                    print(f"[phone_api] 허브 노드 등록: {alias} @ {payload['url']}")
                    first = False
                    delay = 0.5
                    # 명함 교환(실험 3): 등록 성공 시 맥(허브)의 명함을 가져와 캐시.
                    # 세션 헤더는 _mac_post_json 이 갱신한 _mac_session 재사용.
                    try:
                        import threading as _th
                        from peer_cards import fetch_and_cache as _fcc
                        _h = {"X-Launcher-Session": _mac_session} if _mac_session else {}
                        _th.Thread(target=_fcc, args=(_mac_url, "맥"),
                                   kwargs={"headers": _h}, daemon=True).start()
                    except Exception as _e:
                        print(f"[phone_api] 맥 명함 fetch 스킵: {_e}")
                else:
                    print(f"[phone_api] 허브 등록 실패(재시도): {getattr(r,'status_code',None)}")
                    delay = 60.0
            else:
                # IP 변동(LTE↔Wi-Fi 전환 등) 감지 시 재등록(upsert) — 허브의 직결 URL 을 신선하게.
                cur_ip = _phone_lan_ip()
                if cur_ip and cur_ip != last_ip:
                    last_ip = cur_ip
                    payload["url"] = f"http://{cur_ip}:{port}"
                    first = True
                    delay = 0.5
                    continue
                # heartbeat 롱폴 — LTE 푸시 하행 채널. 서버(hold 25초)가 맥→폰 작업을
                # 응답에 실어 내려보낸다(허브가 CGNAT 뒤의 폰에 인바운드로 못 들어오는 것의 반전).
                r = await _mac_post_json(
                    "/nodes/heartbeat", {"device_id": device_id, "wait": 25.0}, timeout=45.0)
                if r is None or getattr(r, "status_code", 0) != 200:
                    delay = 30.0  # 맥 미도달 — 과폴링 방지
                else:
                    try:
                        body = r.json() or {}
                    except Exception:
                        body = {}
                    if body.get("success") is False:
                        first = True  # 허브 레지스트리가 나를 모름(재설치 등) → 재등록
                        delay = 1.0
                    elif "jobs" not in body:
                        delay = 60.0  # 구버전 허브(롱폴 미지원) — 옛 60초 주기 유지
                    else:
                        _jobs = body.get("jobs") or []
                        if _jobs:
                            import time as _t
                            print(f"[phone_api] push {len(_jobs)}건 수신 @{_t.strftime('%H:%M:%S')}")
                        for job in _jobs:
                            await _run_push_job(job, port)
        except Exception as e:
            print(f"[phone_api] 노드 등록/heartbeat 오류: {e}")
            delay = 30.0
        await asyncio.sleep(delay)


async def _run_push_job(job: dict, port: int):
    """허브가 heartbeat 롱폴로 내려보낸 푸시 작업(맥→폰 반전 전달) 실행.

    직결 포워드(_forward_to_phone)와 같은 페이로드 의미(code+agent_id)로 자기
    /ibl/execute 에 넣는다(localhost=인증 통과, 실행 경로 단일화). 결과는
    /nodes/job-result 로 회신 — 맥의 대기 중 포워드(wait_result)가 동기적으로 받아간다.
    """
    job_id = str(job.get("id") or "")
    code = job.get("code") or ""
    if not code:
        return
    import time as _t
    result = None
    _t0 = _t.time()
    try:
        payload = {"code": code}
        if job.get("agent_id"):
            payload["agent_id"] = job["agent_id"]
        async with httpx.AsyncClient(timeout=120.0) as c:
            r = await c.post(f"http://127.0.0.1:{port}/ibl/execute", json=payload)
            try:
                result = r.json()
            except Exception:
                result = {"result": (r.text or "")[:2000]}
    except Exception as e:
        result = {"success": False, "error": f"푸시 작업 실행 실패: {e}"}
    _t1 = _t.time()
    if job_id:
        try:
            await _mac_post_json("/nodes/job-result",
                                 {"job_id": job_id, "result": result}, timeout=20.0)
        except Exception as e:
            print(f"[phone_api] job-result 회신 실패: {e}")
    print(f"[phone_api] push job {job_id}: 실행 {(_t1-_t0)*1000:.0f}ms + 회신 {(_t.time()-_t1)*1000:.0f}ms")


def _start_hub_registration(port: int):
    """별도 스레드 + asyncio 루프에서 허브 등록/heartbeat 데몬 기동(서빙 비차단)."""
    import threading, asyncio
    def _run():
        try:
            asyncio.run(_register_with_hub(port))
        except Exception as e:
            print(f"[phone_api] 허브 등록 루프 종료: {e}")
    threading.Thread(target=_run, daemon=True).start()


@app.post("/business/sync/run")
async def business_sync_run():
    """폰↔맥 business.db 양방향 합집합 동기화(1왕복): 폰 export → 맥 /business/sync/merge
    (맥이 폰 데이터 머지 후 자기 스냅샷 반환) → 폰이 그 스냅샷을 머지. 맥 미설정/미도달이면 graceful."""
    try:
        from business_sync import export_business_db, merge_business_db
        bm = _phone_bm()
        phone_export = export_business_db(bm)
        r = await _mac_post_json("/business/sync/merge", {"data": phone_export}, timeout=60.0)
        if r is None or getattr(r, "status_code", 0) != 200:
            return JSONResponse({"success": False, "error": "맥 미도달/인증실패",
                                 "status": getattr(r, "status_code", None)})
        mac_payload = r.json() or {}
        stats = merge_business_db(bm, mac_payload.get("data") or {})
        return JSONResponse({"success": True, "merged_from_mac": stats,
                             "mac_received_from_phone": mac_payload.get("stats")})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({"success": False, "error": str(e)})


@app.get("/business/sync/peek")
async def business_sync_peek():
    """폰 로컬 business.db 점검(테스트용) — 이웃·비즈니스 이름·연락처 수."""
    try:
        bm = _phone_bm()
        neighbors = bm.get_neighbors()
        return {"neighbors": [n["name"] for n in neighbors],
                "businesses": [b["name"] for b in bm.get_businesses()],
                "contacts": sum(len(bm.get_contacts(n["id"])) for n in neighbors)}
    except Exception as e:
        return JSONResponse({"error": str(e)})


@app.get("/business/sync/export")
async def business_sync_export():
    """폰 business.db 동기화 스냅샷(tombstone 포함) — 맥 [self:phone_sync]가 adb 로 가져감."""
    try:
        from business_sync import export_business_db
        return {"success": True, "data": export_business_db(_phone_bm())}
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


@app.post("/business/sync/merge")
async def business_sync_merge(payload: dict = Body(...)):
    """맥 export 를 폰 business.db 에 합집합 머지(LWW+tombstone). 맥 [self:phone_sync]가 호출."""
    try:
        from business_sync import export_business_db, merge_business_db
        bm = _phone_bm()
        remote = payload.get("data") if isinstance(payload, dict) and "data" in payload else payload
        if not isinstance(remote, dict):
            return JSONResponse({"success": False, "error": "payload dict 필요"})
        stats = merge_business_db(bm, remote)
        return {"success": True, "stats": stats, "data": export_business_db(bm)}
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


# === 의료기록 폰↔맥 동기화 (health_records.db — business 선례 동형, LWW+tombstone+이미지) ===
@app.post("/health/sync/run")
async def health_sync_run():
    """폰↔맥 의료기록 양방향 합집합 동기화(1왕복): 폰 export → 맥 /health/sync/merge
    (맥이 폰 데이터 머지 후 자기 스냅샷 반환) → 폰이 그 스냅샷을 머지. 이미지 base64 포함이라 긴 타임아웃."""
    try:
        from health_sync import export_health_db, merge_health_db
        phone_export = export_health_db()
        r = await _mac_post_json("/health/sync/merge", {"data": phone_export}, timeout=120.0)
        if r is None or getattr(r, "status_code", 0) != 200:
            return JSONResponse({"success": False, "error": "맥 미도달/인증실패",
                                 "status": getattr(r, "status_code", None)})
        mac_payload = r.json() or {}
        stats = merge_health_db(mac_payload.get("data") or {})
        return JSONResponse({"success": True, "merged_from_mac": stats,
                             "mac_received_from_phone": mac_payload.get("stats")})
    except Exception as e:
        import traceback
        traceback.print_exc()
        return JSONResponse({"success": False, "error": str(e)})


@app.get("/health/sync/export")
async def health_sync_export():
    """폰 health_records.db 동기화 스냅샷(5테이블 + 문서 이미지 base64, tombstone 포함)."""
    try:
        from health_sync import export_health_db
        return {"success": True, "data": export_health_db()}
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


@app.get("/health/sync/peek")
async def health_sync_peek():
    """폰 로컬 health_records.db 점검(테스트용) — 테이블별 행 수 + 이미지 수."""
    try:
        from health_sync import export_health_db
        d = export_health_db()
        out = {t: len(d.get(t, [])) for t in ["persons", "measurements", "symptoms", "medications", "documents"]}
        out["images"] = len(d.get("images", {}))
        return out
    except Exception as e:
        return JSONResponse({"error": str(e)})


# === 폰 입력 기능: 이웃(주소록) 추가 — 폰 자급 + phone→맥 동기화의 입력측 ===
@app.post("/business/neighbor/add")
async def business_neighbor_add(payload: dict = Body(...)):
    """폰 로컬 business.db 에 이웃 추가(+선택 연락처). 다음 [self:phone_sync] 때 맥으로 합쳐짐."""
    try:
        bm = _phone_bm()
        name = (payload.get("name") or "").strip()
        if not name:
            return JSONResponse({"success": False, "error": "이름을 입력하세요."})
        nb = bm.create_neighbor(name=name, info_level=int(payload.get("info_level") or 0))
        ct, cv = (payload.get("contact_type") or "").strip(), (payload.get("contact_value") or "").strip()
        if ct and cv:
            bm.add_contact(nb["id"], ct, cv)
        return {"success": True, "neighbor": nb,
                "message": f"'{name}' 추가됨. 맥에서 '폰 동기화'하면 PC로 반영됩니다."}
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


@app.get("/business/neighbor/form")
def business_neighbor_form():
    """폰에서 이웃을 추가하는 미니 입력 폼(자급형). 추가 후 [self:phone_sync]로 맥에 합쳐짐."""
    html = """<!doctype html><html lang=ko><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>이웃 추가</title><style>
body{font-family:-apple-system,sans-serif;background:#1a1a1a;color:#eee;margin:0;padding:20px}
h1{font-size:20px;margin:0 0 4px} .sub{color:#999;font-size:13px;margin-bottom:20px}
label{display:block;margin:14px 0 4px;font-size:13px;color:#bbb}
input,select{width:100%;box-sizing:border-box;padding:11px;background:#2a2a2a;border:1px solid #444;border-radius:8px;color:#eee;font-size:15px}
.row{display:flex;gap:8px} .row>*{flex:1}
button{width:100%;margin-top:22px;padding:13px;background:#D97706;border:0;border-radius:8px;color:#fff;font-size:16px;font-weight:600}
#msg{margin-top:16px;padding:12px;border-radius:8px;font-size:14px;display:none}
.ok{background:#14532d;color:#bbf7d0} .err{background:#5a1717;color:#fecaca}
</style></head><body>
<h1>이웃 추가</h1><div class=sub>폰 주소록에 저장 → 맥에서 "폰 동기화"하면 PC로 합쳐집니다.</div>
<label>이름 *</label><input id=name placeholder="홍길동" autofocus>
<label>정보 레벨</label>
<select id=level><option value=0>L0 공개</option><option value=1>L1</option><option value=2>L2</option><option value=3>L3</option><option value=4>L4 신뢰</option></select>
<div class=row>
  <div><label>연락처 종류</label><select id=ctype><option value="">(없음)</option><option value=gmail>이메일</option><option value=nostr>Nostr</option><option value=phone>전화</option><option value=kakao>카카오</option></select></div>
  <div><label>연락처 값</label><input id=cvalue placeholder="선택"></div>
</div>
<button onclick=add()>추가</button>
<div id=msg></div>
<script>
async function add(){
  const name=document.getElementById('name').value.trim();
  const m=document.getElementById('msg');
  if(!name){ m.className='err'; m.style.display='block'; m.textContent='이름을 입력하세요.'; return; }
  const body={name, info_level:+document.getElementById('level').value,
    contact_type:document.getElementById('ctype').value, contact_value:document.getElementById('cvalue').value.trim()};
  try{
    const r=await fetch('/business/neighbor/add',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)});
    const d=await r.json();
    m.style.display='block';
    if(d.success){ m.className='ok'; m.textContent=d.message||'추가됨';
      document.getElementById('name').value=''; document.getElementById('cvalue').value=''; }
    else { m.className='err'; m.textContent=d.error||'실패'; }
  }catch(e){ m.className='err'; m.style.display='block'; m.textContent='오류: '+e; }
}
</script></body></html>"""
    return HTMLResponse(html)


@app.get("/projects")
async def projects(request: Request):
    # 폰-로컬 프로젝트(자아별 사적, userdata). 맥 프록시 아님 — 폰은 자기 프로젝트를 본다.
    try:
        pm = await asyncio.to_thread(_phone_pm)
        return JSONResponse({"projects": pm.list_projects()})
    except Exception as e:
        print(f"[phone_api] 로컬 프로젝트 목록 실패: {e}")
        return JSONResponse({"projects": []})


@app.post("/projects")
async def project_create(request: Request):
    """폰-로컬 프로젝트 생성."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    name = (body.get("name") or "").strip()
    if not name:
        return JSONResponse({"error": "name 필요"}, status_code=400)
    try:
        pm = _phone_pm()
        res = await asyncio.to_thread(
            pm.create_project, name, None, body.get("parent_folder"),
            body.get("template_name", "기본"))
        return JSONResponse(res)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.delete("/projects/{project_id}")
async def project_delete(project_id: str):
    """폰-로컬 프로젝트 삭제."""
    try:
        pm = _phone_pm()
        await asyncio.to_thread(pm.delete_project, project_id)
        return JSONResponse({"status": "deleted", "project_id": project_id})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/switches")
async def switches(request: Request):
    return _list_or_empty(await _mac_proxy(request, "/switches"), {"switches": []})


def _phone_agents_yaml(project_id: str):
    """폰 로컬 프로젝트의 agents.yaml 로드 → (data dict, path). 없으면 ({...}, path)."""
    import yaml
    pm = _phone_pm()
    project_path = pm.get_project_path(project_id)
    af = project_path / "agents.yaml"
    if not af.exists():
        return {"agents": [], "common": {}}, af
    with open(af, "r", encoding="utf-8") as f:
        return (yaml.safe_load(f) or {"agents": [], "common": {}}), af


@app.get("/projects/{project_id}/agents")
async def project_agents(project_id: str, request: Request):
    # 폰-로컬 프로젝트의 에이전트 목록. 비밀(api_key)은 응답에서 제거.
    try:
        data, _ = await asyncio.to_thread(_phone_agents_yaml, project_id)
        agents = []
        for a in data.get("agents", []):
            a = dict(a)
            a.pop("api_key", None)
            if isinstance(a.get("ai"), dict):
                a["ai"] = {k: v for k, v in a["ai"].items() if k != "api_key"}
            agents.append(a)
        return JSONResponse({"agents": agents})
    except Exception as e:
        print(f"[phone_api] 로컬 에이전트 목록 실패: {e}")
        return JSONResponse({"agents": []})


@app.post("/projects/{project_id}/agents")
async def agent_create(project_id: str, request: Request):
    """폰-로컬 에이전트 생성 (agents.yaml 에 추가)."""
    import yaml, uuid as _uuid
    try:
        body = await request.json()
    except Exception:
        body = {}
    name = (body.get("name") or "").strip()
    if not name:
        return JSONResponse({"error": "name 필요"}, status_code=400)
    try:
        data, af = await asyncio.to_thread(_phone_agents_yaml, project_id)
        aid = "agent_" + _uuid.uuid4().hex[:8]
        data.setdefault("agents", []).append({
            "id": aid, "name": name, "role": body.get("role", ""),
            "type": body.get("type", "external"),
        })
        def _save():
            with open(af, "w", encoding="utf-8") as f:
                yaml.safe_dump(data, f, allow_unicode=True)
        await asyncio.to_thread(_save)
        return JSONResponse({"status": "created", "agent": {"id": aid, "name": name}})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.delete("/projects/{project_id}/agents/{agent_id}")
async def agent_delete(project_id: str, agent_id: str):
    """폰-로컬 에이전트 삭제."""
    import yaml
    try:
        data, af = await asyncio.to_thread(_phone_agents_yaml, project_id)
        before = len(data.get("agents", []))
        data["agents"] = [a for a in data.get("agents", []) if a.get("id") != agent_id]
        def _save():
            with open(af, "w", encoding="utf-8") as f:
                yaml.safe_dump(data, f, allow_unicode=True)
        await asyncio.to_thread(_save)
        return JSONResponse({"status": "deleted" if len(data["agents"]) < before else "not_found"})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/switches/{switch_id}/execute")
async def switch_execute(switch_id: str, request: Request):
    # 스위치 실행=맥의 IBL/에이전트 — 길어질 수 있어 넉넉한 타임아웃.
    r = await _mac_proxy(request, f"/switches/{switch_id}/execute", timeout=300.0)
    if r is None:
        return JSONResponse({"success": False, "error": "맥 백엔드 미연결(INDIEBIZ_MAC_URL 미설정)"}, status_code=503)
    if r == "error":
        return JSONResponse({"success": False, "error": "맥 백엔드 연결 실패"}, status_code=502)
    return _relay(r)


# === 공유창고 — 맥 프록시 (런처 '공유창고' 표면이 부른다) =========================
# ★창고는 맥에 산다. 공개 얼굴(터널·Worker·레벨 게이트)이 맥에 있으므로 폰이 자기 창고를
# 따로 갖는 건 의미가 없다 — 폰은 /projects·/switches 와 똑같이 *맥 창고의 리모컨*이다.
# 그래서 폰의 값어치 = 사진이 태어나는 자리에서 바로 창고에 넣는 것(올리면 그 레벨로 즉시 공개).
# `add`(맥 로컬 경로 복사)는 폰에 그런 경로가 없으므로 프록시하지 않는다 — 폰은 upload 를 쓴다.

def _relay_raw(r):
    """파일 **내용 그대로** 통과 — 텍스트도 JSON 으로 감싸지 않는다.

    ★`_relay` 는 `text/*` 를 `{"response": ...}` 로 감싼다(비-JSON 텍스트용 안전망). API 응답엔
    맞지만 **창고 파일엔 그 감싸기가 곧 내용 훼손**이다 — .md/.txt/.csv/.html 을 받으면 JSON
    문자열이 담긴 파일이 나온다(실기 검증에서 실제로 밟은 버그. 이미지는 바이너리 경로라
    멀쩡해서 텍스트만 조용히 깨졌다)."""
    from starlette.responses import Response as _Resp
    ct = r.headers.get("content-type") or "application/octet-stream"
    headers = {k: r.headers[k] for k in ("content-range", "accept-ranges", "content-length",
                                         "content-disposition") if k in r.headers}
    return _Resp(content=r.content, status_code=r.status_code, media_type=ct, headers=headers)


async def _wh_proxy(request: Request, path: str, *, timeout: float = 60.0, raw: bool = False):
    """창고 프록시 공통 — 맥 미설정/미도달을 폰 사용자에게 친절히 알린다.
    raw=True 는 파일 내용 경로(열람·내려받기) — 감싸지 않고 원본 바이트."""
    r = await _mac_proxy(request, path, timeout=timeout)
    if r is None:
        return JSONResponse({"error": "맥 백엔드 미연결 — 집 PC 가 켜져 있어야 창고를 씁니다."},
                            status_code=503)
    if r == "error":
        return JSONResponse({"error": "맥 백엔드 연결 실패"}, status_code=502)
    if raw and r.status_code == 200:
        return _relay_raw(r)
    return _relay(r)


@app.get("/portal/warehouse-admin/list")
async def wh_list(request: Request):
    return await _wh_proxy(request, "/portal/warehouse-admin/list")


@app.get("/portal/warehouse-admin/file")
async def wh_file(request: Request):
    # 열람(사진·동영상·텍스트)과 내려받기(?download=1) 둘 다. raw=파일 내용은 감싸지 않는다.
    return await _wh_proxy(request, "/portal/warehouse-admin/file", timeout=180.0, raw=True)


@app.post("/portal/warehouse-admin/upload")
async def wh_upload(request: Request):
    # 폰 사진·영상 원본은 클 수 있고 LTE 면 느리다 — 넉넉한 타임아웃.
    return await _wh_proxy(request, "/portal/warehouse-admin/upload", timeout=600.0)


@app.post("/portal/warehouse-admin/remove")
async def wh_remove(request: Request):
    return await _wh_proxy(request, "/portal/warehouse-admin/remove")


def _run_local_harness(message: str, images: list):
    """폰-자아 로컬 하네스 추론 (process_system_ai_message). 폰이 자기 정체성(world_pulse
    폴백=detect_body)으로 추론하고, 모델은 3티어(경량 gemini_http 직접 / 중급·본격 claude_code_remote
    맥 렌트)로 빌리며, IBL 실행은 폰 로컬(빌린 액션만 맥 위임), 해마는 렌트 인덱스. 실패 시 None."""
    from system_ai_core import process_system_ai_message
    from system_ai_memory import save_conversation, get_history_for_ai
    # 에피소드 기록 — 이 1턴(명령→응답)을 world_pulse.db 에 회고용으로 남긴다. 맥
    # api_websocket 의 start/end_episode 와 동형(에이전트명 "system_ai"). finally 로 성공·
    # 예외 모두에서 end → 실패/포기한 요청도 기록된다(누락이 바로 이 작업의 발단).
    try:
        from episode_logger import EpisodeLogger
        EpisodeLogger.start_episode("system_ai", message)
    except Exception:
        pass
    try:
        images_data = None
        if images:
            images_data = [{"base64": i.get("base64"), "media_type": i.get("media_type", "image/png")}
                           for i in images if i.get("base64")]
        # 직전 대화 로드 → AI 가 turn 사이를 기억(맥 GUI 와 동형). 그리고 이번 사용자 메시지 저장.
        history = get_history_for_ai(limit=7)
        save_conversation("user", message, source="phone")
        response_text, _tool_images = process_system_ai_message(
            message=message, history=history, images=images_data
        )
        # AI 응답 저장 → 과거 대화 뷰 + 다음 turn 기억의 소스.
        if response_text:
            save_conversation("assistant", response_text, source="phone-self")
        return {"response": response_text, "provider": "phone-self", "ts": "local"}
    finally:
        try:
            from episode_logger import EpisodeLogger
            EpisodeLogger.end_episode()
        except Exception:
            pass


@app.post("/system-ai/chat")
async def system_ai_chat(request: Request):
    """폰-자아 호스팅 step7: 로컬 하네스 실행이 1순위(폰이 자기 몸 위에서 추론=자기-모델 참).
    로컬 하네스 미가용/실패 시 맥 프록시 폴백(전환 안전). LLM 왕복이라 긴 타임아웃."""
    try:
        body = await request.json()
    except Exception:
        body = {}
    message = body.get("message", "")
    images = body.get("images")

    # 1순위: 로컬 하네스 (폰-자아). 스레드풀에서 — 동기 파이프라인이 재진입 /ibl/execute 와
    # 같은 루프를 막지 않게(맥 chat_with_system_ai 가 def 인 것과 동일 이유).
    if message:
        try:
            result = await asyncio.to_thread(_run_local_harness, message, images)
            if result and result.get("response"):
                return JSONResponse(result)
            print("[phone_api] 로컬 하네스 빈 응답 → 맥 프록시 폴백")
        except Exception as e:
            import traceback
            print(f"[phone_api] 로컬 하네스 실패 → 맥 프록시 폴백: {e}\n{traceback.format_exc()[-500:]}")

    # 폴백: 맥 프록시 (로컬 하네스 미가용 — 하네스 미번들/모델 미설정/맥 의존 등)
    r = await _mac_proxy(request, "/system-ai/chat", timeout=300.0)
    if r is None:
        return JSONResponse({"response": "맥 백엔드에 연결되어 있지 않습니다. (INDIEBIZ_MAC_URL 미설정 — 집 PC가 켜져 있어야 자율주행이 동작합니다.)"})
    if r == "error":
        return JSONResponse({"response": "맥 백엔드 연결에 실패했습니다. 집 PC와 네트워크를 확인하세요."})
    return _relay(r)


@app.get("/system-ai/conversations")
async def system_ai_conversations(limit: int = 40):
    """폰-자아 과거 대화 조회(로컬 system_ai_memory). 맥 /system-ai/conversations 미러 —
    폰 로컬 하네스가 save_conversation 으로 영속(userdata)한 대화를 런처 이력 뷰가 읽는다.
    맥 프록시 아님: 폰 대화는 폰-자아의 사적 기억(두-자아 원칙)."""
    try:
        from system_ai_memory import get_recent_conversations
        convs = await asyncio.to_thread(get_recent_conversations, limit)
        return JSONResponse({"conversations": convs})
    except Exception as e:
        return JSONResponse({"conversations": [], "error": str(e)})


_phone_agent_runners = {}


def _run_phone_agent(project_id: str, agent_id: str, command: str) -> dict:
    """폰-로컬 프로젝트 에이전트 실행 (번들 AgentRunner, 폰 두뇌). 맥 위임 아님.
    에이전트는 폰의 몸에서 돌고, IBL 은 runs_on 대로 라우팅(anywhere 로컬·mac_only 포워드)."""
    import yaml
    from agent_runner import AgentRunner
    # 에피소드 기록 — 프로젝트 에이전트 1턴을 world_pulse.db 에 남긴다(맥 api_websocket 동형).
    # 부동산 같은 다단계 에이전트가 "뭘 했는지/어디서 느린지" 를 회고할 수 있게. finally 로
    # 조기 반환·예외·포기 모두에서 end → 실패한 실행도 기록된다.
    try:
        from episode_logger import EpisodeLogger
        EpisodeLogger.start_episode(f"{project_id}:{agent_id}", command)
    except Exception:
        pass
    try:
        pm = _phone_pm()
        project_path = pm.get_project_path(project_id)
        af = project_path / "agents.yaml"
        if not af.exists():
            return {"response": "에이전트 설정이 없습니다."}
        with open(af, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        agent_config = next((a for a in data.get("agents", []) if a.get("id") == agent_id), None)
        if not agent_config:
            return {"response": f"에이전트 '{agent_id}'를 찾을 수 없습니다."}
        agent_config = dict(agent_config)
        agent_config["_project_path"] = str(project_path)
        agent_config["_project_id"] = project_id
        # ★폰 에이전트는 폰의 두뇌(Gemini)로 실행(사용자 결정) — 시드된 맥 claude_code 설정을 덮어씀.
        # 맥 두뇌(claude CLI)는 폰에 없다. apiKey 는 env(GEMINI_API_KEY, keys.json 주입) 폴백.
        agent_config["ai"] = {
            "provider": "gemini_http",
            "model": "gemini-3.5-flash",
            "api_key": os.environ.get("GEMINI_API_KEY", ""),
        }
        common_config = data.get("common", {})

        key = f"{project_id}/{agent_id}"
        rec = _phone_agent_runners.get(key)
        runner = rec.get("runner") if rec else None
        if not (runner and getattr(runner, "running", False)):
            runner = AgentRunner(agent_config, common_config)
            runner.start()
            _phone_agent_runners[key] = {"runner": runner}
        if not getattr(runner, "ai", None):
            return {"response": "에이전트 AI 초기화 실패 — 폰에 해당 제공자 키가 없을 수 있습니다."}
        resp = runner.ai.process_message_with_history(message_content=command, history=[])
        return {"response": resp}
    finally:
        try:
            from episode_logger import EpisodeLogger
            EpisodeLogger.end_episode()
        except Exception:
            pass


@app.post("/projects/{project_id}/agents/{agent_id}/start")
async def agent_start(project_id: str, agent_id: str, request: Request):
    # 폰-로컬 에이전트는 command 시점에 lazy 시작 — start 는 ack 만.
    return JSONResponse({"status": "ok", "agent_id": agent_id})


@app.post("/projects/{project_id}/agents/{agent_id}/command")
async def agent_command(project_id: str, agent_id: str, request: Request):
    # 폰-로컬 에이전트 실행(폰 두뇌). 맥 프록시 아님 — 폰 프로젝트는 자아별 사적.
    try:
        body = await request.json()
    except Exception:
        body = {}
    command = body.get("command") or body.get("message") or ""
    if not command:
        return JSONResponse({"response": "(빈 명령)"})
    try:
        result = await asyncio.to_thread(_run_phone_agent, project_id, agent_id, command)
        return JSONResponse(result)
    except Exception as e:
        import traceback
        print(f"[phone_api] 로컬 에이전트 실행 실패: {e}\n{traceback.format_exc()[-400:]}")
        return JSONResponse({"response": f"에이전트 실행 오류: {e}"})


@app.get("/output/{name}")
def output_file(name: str):
    """폰 로컬 생성물(신문 등 HTML)을 런처 오버레이가 띄우도록 서빙.
    os_open(집 PC GUI)이 mac_only 라 폰에선 이 라우트 + 인앱 iframe 으로 본다."""
    from fastapi.responses import FileResponse
    safe = os.path.basename(name)
    path = os.path.join(_scratch, "outputs", safe)
    if os.path.exists(path):
        return FileResponse(path, media_type="text/html")
    return JSONResponse({"error": "파일을 찾을 수 없습니다."}, status_code=404)


@app.post("/ibl/execute")
async def execute(req: Request):
    """정본 통합 실행기로 라우팅 — PC /ibl/execute 와 동일 계약.

    분산 라우팅은 엔진(ibl_engine.execute_ibl)이 액션 단위로 수행한다: 폰서 못 도는
    액션을 만나면 그 액션만 맥(연합 두뇌)에 위임(_forward_to_mac)하고 결과를 받아온다.
    합성 code(&/>>/??)의 각 leaf 가 chokepoint 를 거치므로 혼합 code 도 액션별로 쪼개져
    로컬/맥에서 따로 실행된다. 여기선 항상 로컬 엔진에 넘기면 됨(엔진이 알아서 라우팅)."""
    body = await req.json()
    code = body.get("code", "")
    if not code:
        return JSONResponse({"success": False, "error": "code 파라미터가 필요합니다."})

    # 빌림은 호출하는 주체가 액션 주체(설계결정 §6.4): 맥→폰 위임(_forward_to_phone)이 호출자
    # 신원을 실어 보내면 그걸로 기록하고, 폰 자체 표면 호출(미동봉)이면 폰-자아("phone")로 떨어진다.
    agent_id = body.get("agent_id") or "phone"

    # 무거운 import(system_tools→api_engine 등)는 첫 호출 시 지연 — 트리 + env 준비 후라 안전.
    from system_tools import _execute_ibl_unified

    def _run():
        return _execute_ibl_unified({"code": code}, _scratch, agent_id=agent_id)

    # 엔진은 동기(내부에 자체 이벤트 루프 관리). 서버 asyncio 루프 블록 방지 위해 스레드로.
    result = await asyncio.to_thread(_run)

    obj = result
    if isinstance(obj, str):
        try:
            obj = json.loads(obj)
        except json.JSONDecodeError:
            return JSONResponse({"result": obj})
    # 분산 IBL: 맥서 위임받은 mp3(b64)를 폰 Music 폴더에 네이티브 저장(빌린 연산→로컬 산출물).
    # b64 는 WebView 로 안 보냄(Python↔Kotlin 으로만). 큰 파일도 JS 브리지 우회.
    if isinstance(obj, dict) and obj.get("download_in_client") and obj.get("b64"):
        obj = await asyncio.to_thread(_save_audio_to_phone, obj)
    return JSONResponse(obj)


# ============================================================================
# 사진/미디어 서빙 — 폰 로컬 (몸-로컬 I/O, 맥 프록시 아님). ★catch-all 보다 먼저 등록.
# [self:photo] 가 반환하는 records.image = "/photo/thumbnail?path=<폰 MediaStore 경로>" 를
# 앱모드 image_grid 가 <img src> 로 부른다. 이 경로는 *폰 자신*의 파일(/storage/emulated/0/...)
# 이라 catch-all 로 맥에 프록시하면 맥엔 그 경로가 없어 404 → 사진 뷰어가 통째로 깨졌다(원래 신고건).
# 사진 뷰어는 몸-로컬: 폰이 자기 미디어를 직접 서빙한다(맥이 자기 미디어를 api_photo 로 서빙하듯,
# file_index 가 Spotlight↔MediaStore 로 몸 분기하듯 — 패리티 기본·드리프트 0). 정본 api_photo 의
# 함수(PIL 썸네일·EXIF 회전·FileResponse)를 그대로 위임한다. 폰 사진은 전부 JPEG(A36 검증)라 PIL OK.
# 지연 import = serve() 의 _init_base 후 호출돼 sys.path/INDIEBIZ_BASE_PATH 준비됨.
# ============================================================================
@app.get("/photo/thumbnail")
async def _photo_thumbnail(path: str, size: int = 200):
    from api_photo import get_thumbnail
    return await get_thumbnail(path=path, size=size)


@app.get("/photo/video-thumbnail")
async def _photo_video_thumbnail(path: str, size: int = 200):
    # 동영상 프레임 썸네일 — api_photo 는 ffmpeg 를 쓰지만 폰엔 ffmpeg 가 없다. Android 네이티브
    # ThumbnailUtils(OS 디코더, PhoneActions.videoThumbnail)로 프레임을 뽑아 JPEG 로 서빙한다.
    # 캐시는 api_photo 와 같은 THUMBNAIL_CACHE_DIR 공유(반복 그리드 로드 시 재디코딩 방지).
    # 네이티브 실패 시 정본 api_photo(ffmpeg) 폴백 — 폰엔 보통 미가용이나 맥/일관성 유지.
    import hashlib
    from fastapi.responses import FileResponse

    def _native():
        try:
            from api_photo import THUMBNAIL_CACHE_DIR
            os.makedirs(THUMBNAIL_CACHE_DIR, exist_ok=True)
            cache = os.path.join(
                THUMBNAIL_CACHE_DIR,
                hashlib.md5(f"pv:{path}:{size}".encode()).hexdigest() + ".jpg")
            if (os.path.exists(cache) and os.path.exists(path)
                    and os.path.getmtime(cache) >= os.path.getmtime(path)):
                return cache
            from java import jclass  # Chaquopy — 폰 네이티브에만 존재
            PA = jclass("com.indiebiz.phoneagent.PhoneActions")
            raw = PA.videoThumbnail(path, int(size))
            data = bytes(raw) if raw else b""
            if not data:
                return None
            with open(cache, "wb") as fh:
                fh.write(data)
            return cache
        except Exception:
            return None

    cache = await asyncio.to_thread(_native)
    if cache:
        return FileResponse(cache, media_type="image/jpeg")
    from api_photo import get_video_thumbnail
    return await get_video_thumbnail(path=path, size=size)


@app.get("/photo/image")
async def _photo_image(path: str):
    # 원본 이미지(라이트박스·상세). FileResponse 라 실제 폰 경로면 그대로 서빙.
    from api_photo import get_image
    return await get_image(path=path)


@app.get("/photo/video")
async def _photo_video(path: str, request: Request):
    # 동영상 재생(Range 지원). FileResponse 라 실제 폰 경로면 그대로 서빙.
    from api_photo import get_video
    return await get_video(path=path, request=request)


# ============================================================================
# ★ 패리티 기본값 — catch-all 맥 프록시 (반드시 마지막 라우트로 등록).
# 폰에 명시적 라우트가 없는 모든 요청을 맥으로 포워드(리모컨). FastAPI 는 더 구체적인
# 명시 라우트를 먼저 매칭하므로, 로컬 하네스(/system-ai/chat·conversations)·sync·ibl 등
# "충분한 이유가 있어 폰에서 다르게 동작하는" 것만 위에서 가로채고 나머지는 자동으로 맥.
# → 맥에 새 엔드포인트가 생기면 폰에서 *그냥 된다*. 갈라짐이 기본이 아니라 패리티가 기본.
# (사용자 원칙 2026-06-14: "맥에서 되는 건 폰에서도 되게, 어길 충분한 이유가 없으면.")
# ============================================================================
@app.api_route("/{full_path:path}", methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
async def _catch_all_mac_proxy(full_path: str, request: Request):
    path = "/" + full_path
    r = await _mac_proxy(request, path, timeout=120.0)
    if r is None:
        return JSONResponse(
            {"error": "맥 백엔드 미연결(INDIEBIZ_MAC_URL 미설정 — 이 기능은 집 PC가 필요합니다)"},
            status_code=503)
    if r == "error":
        return JSONResponse({"error": "맥 백엔드 연결 실패 — 집 PC와 네트워크를 확인하세요."},
                            status_code=502)
    return _relay(r)


def _save_audio_to_phone(obj: dict) -> dict:
    """맥서 받은 mp3(b64) → 디코드 → Kotlin MediaSaver 로 폰 Music 폴더 저장.
    b64 는 응답에서 제거. 성공/실패를 saved 플래그+message 로 WebView 에 알린다."""
    import base64
    b64 = obj.pop("b64", "")
    fn = obj.get("filename") or "track.mp3"
    try:
        data = base64.b64decode(b64)
        from java import jclass
        media_saver = jclass("com.indiebiz.phoneagent.MediaSaver")
        res = media_saver.saveAudio(data, fn)
        res = str(res)
        if res.startswith("ERROR"):
            obj["saved"] = False
            obj["message"] = f"폰 저장 실패: {res}"
        else:
            obj["saved"] = True
            obj["saved_path"] = res
            obj["message"] = f"폰 음악 폴더에 저장됨: {fn}"
    except Exception as e:
        obj["saved"] = False
        obj["message"] = f"폰 저장 실패: {e.__class__.__name__}: {e}"
    return obj


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

    # 몸 독립 부팅 배선 — 에피소드 로거 등(맥 api.py 와 같은 공유 함수). 폰도 자기 실행을
    # (성공·실패 모두) world_pulse.db 에 에피소드로 기록해 회고할 수 있어야 한다. 몸 종속
    # 부팅(터널·임베딩모델 로딩·world_pulse 수집기)은 폰에서 의도적으로 빼지만, 몸 독립인
    # 에피소드 기록을 빼는 건 누락(드리프트)이었다 — boot_common 으로 양쪽이 같이 받는다.
    try:
        from boot_common import wire_local_subsystems
        wire_local_subsystems(profile="phone")
    except Exception as e:
        import traceback
        print(f"[phone_api] 부팅 배선 스킵: {e}\n{traceback.format_exc()[-300:]}")

    # 반응형→능동/백그라운드 층: 상주 스케줄러 폴링 루프 기동. 폰-자아가 "매일 아침 X"·
    # "N시간마다 Y"(self:trigger{type:schedule}/self:schedule)를 스스로 돌리려면 calendar_manager
    # 의 60초 폴링 루프가 폰 프로세스 안에서 살아 있어야 한다. 폰 백엔드는 백그라운드 상주
    # (App.kt 라이프사이클)이라 데몬 루프 viable. 저장소=폰 filesDir/data/calendar_events.json
    # (폰 자신의 일정 — 두-자아 분리). 실패해도 백엔드 부팅은 계속(앱모드 무관히 동작).
    try:
        from calendar_manager import get_calendar_manager
        get_calendar_manager().start()
        print("[phone_api] 상주 스케줄러 기동 (self:trigger/schedule 폴링 루프)")
    except Exception as e:
        import traceback
        print(f"[phone_api] 스케줄러 기동 스킵: {e}\n{traceback.format_exc()[-300:]}")

    # 기본 localhost 전용(WebView 자기접속). 분산 IBL 에서 맥(두뇌)이 폰(몸)으로 직접
    # phone_only 액션을 포워드하려면 폰이 LAN 도달 가능해야 하므로, keys.json 에
    # INDIEBIZ_BIND_HOST=0.0.0.0 주입 시 LAN 바인딩(=WiFi 노출 → #3 폰 인증 필요).
    # 바인드: 명시 INDIEBIZ_BIND_HOST 우선. 없으면 인증 토큰(INDIEBIZ_PHONE_TOKEN) 보유 시에만
    # LAN 노출(0.0.0.0) — 노출과 인증을 한 묶음으로 결합(토큰 없이는 절대 LAN 바인드 안 함).
    _bind = os.environ.get("INDIEBIZ_BIND_HOST")
    if not _bind:
        _bind = "0.0.0.0" if os.environ.get("INDIEBIZ_PHONE_TOKEN") else "127.0.0.1"
    print(f"[phone_api] bind host={_bind} (phone_token={'있음' if os.environ.get('INDIEBIZ_PHONE_TOKEN') else '없음'})")

    # 다중 노드: 허브(맥) 프레즌스 레지스트리에 자기등록 + heartbeat (LAN 노출+토큰 시에만).
    try:
        _start_hub_registration(int(port))
    except Exception as e:
        print(f"[phone_api] 허브 등록 기동 스킵: {e}")
    config = uvicorn.Config(
        app, host=_bind,
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
