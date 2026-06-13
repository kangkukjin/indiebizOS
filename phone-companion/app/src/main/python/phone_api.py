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


def _ensure_phone_ai_configs(base_path):
    """폰 3티어 모델 config 를 data/ 에 생성(없을 때만 — 사용자 수정 보존)."""
    import json as _json
    cfg_dir = os.path.join(base_path, "data")
    os.makedirs(cfg_dir, exist_ok=True)
    defaults = {
        "system_ai_config.json": {"enabled": True, "provider": "claude_code_remote",
                                   "model": "opus", "apiKey": "", "role": ""},
        "midtier_ai_config.json": {"enabled": True, "provider": "claude_code_remote",
                                   "model": "sonnet", "apiKey": ""},
        "lightweight_ai_config.json": {"enabled": True, "provider": "gemini_http",
                                       "model": "gemini-3.1-flash-lite", "apiKey": ""},
    }
    for name, cfg in defaults.items():
        path = os.path.join(cfg_dir, name)
        if not os.path.exists(path):
            try:
                with open(path, "w", encoding="utf-8") as f:
                    _json.dump(cfg, f, ensure_ascii=False, indent=2)
                print(f"[phone_api] 폰 AI config 생성: {name} ({cfg['provider']}/{cfg['model']})")
            except Exception as e:
                print(f"[phone_api] config 생성 실패 {name}: {e}")
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


def _run_local_harness(message: str, images: list):
    """폰-자아 로컬 하네스 추론 (process_system_ai_message). 폰이 자기 정체성(world_pulse
    폴백=detect_body)으로 추론하고, 모델은 3티어(경량 gemini_http 직접 / 중급·본격 claude_code_remote
    맥 렌트)로 빌리며, IBL 실행은 폰 로컬(빌린 액션만 맥 위임), 해마는 렌트 인덱스. 실패 시 None."""
    from system_ai_core import process_system_ai_message
    images_data = None
    if images:
        images_data = [{"base64": i.get("base64"), "media_type": i.get("media_type", "image/png")}
                       for i in images if i.get("base64")]
    response_text, _tool_images = process_system_ai_message(
        message=message, history=[], images=images_data
    )
    return {"response": response_text, "provider": "phone-self", "ts": "local"}


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
