"""
원격 런처 웹앱 API
- Cloudflare Tunnel을 통해 외부에서 IndieBiz OS를 제어
- 시스템 AI 채팅, 프로젝트 에이전트 채팅, 스위치 실행
"""

from fastapi import APIRouter, Request, HTTPException, Response
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional
import os
import json
import uuid
import hashlib
from datetime import datetime

router = APIRouter(prefix="/launcher")

# 설정 파일 경로
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "launcher_web_config.json")


@router.get("/file")
async def serve_artifact_file(path: str):
    """산출물 파일 바이트 서빙 — 빌림-완성(borrow-completion)용.

    폰서 mac_only 액션을 호출하면 맥이 실행해 *맥 fs*에 파일을 만든다. 폰은 그 파일을
    이 엔드포인트로 되가져와(_forward_to_mac 의 artifact pull) 로컬에 쓴다 → mac_only 도
    폰서 호출하면 산출물까지 제대로 돌아온다. 인증은 remote_access_guard(외부=세션 필요).
    보안: BASE_PATH 하위(산출물 트리)만, realpath 로 심볼릭 우회 차단, 파일만.
    """
    from fastapi.responses import FileResponse
    from runtime_utils import get_base_path
    import mimetypes
    base = os.path.realpath(str(get_base_path()))
    p = path
    if p.startswith('/outputs/') or p.startswith('/captures/'):
        p = os.path.join(base, 'data', p.lstrip('/'))
    real = os.path.realpath(p)
    if not real.startswith(base):
        return JSONResponse({"error": "접근 권한 없음(산출물 트리 밖)"}, status_code=403)
    if not os.path.isfile(real):
        return JSONResponse({"error": "파일 없음"}, status_code=404)
    mime, _ = mimetypes.guess_type(real)
    return FileResponse(real, media_type=mime or "application/octet-stream")

# 앱 표면 계기 — ibl_nodes.yaml 의 app: 블록에서 자동 파생 (2단계, 단일 진실 소스).
# app: 블록을 단 액션은 빌드(--check) 시 정합성 검증을 통과해야 하며, 여기서 계기로 합성된다.
IBL_NODES_PATH = os.path.join(os.path.dirname(__file__), "..", "data", "ibl_nodes.yaml")
_instruments_cache = {"mtime": None, "payload": None}

# app 블록에서 모드(탭) 레벨로 그대로 전달되는 필드
_APP_MODE_FIELDS = ("note", "auto_run", "inputs", "buttons", "action", "view", "renderer", "compose", "filter")

# 폰 프로파일(#3 runs_on): INDIEBIZ_PROFILE=phone 이면 phone_manifest.json 의 runnable_actions 에
# 없는 계기(=폰서 못 도는 액션)를 홈 그리드에서 숨긴다. PC(프로파일 미설정)면 필터 없음.
_phone_runnable_cache = {"loaded": False, "set": None}


def _phone_runnable_actions():
    """폰 프로파일이면 runnable 액션 집합 반환, 아니면 None(필터 안 함)."""
    if os.environ.get("INDIEBIZ_PROFILE") != "phone":
        return None
    if not _phone_runnable_cache["loaded"]:
        s = None
        try:
            mp = os.path.join(os.path.dirname(IBL_NODES_PATH), "phone_manifest.json")
            with open(mp, "r", encoding="utf-8") as f:
                s = set(json.load(f).get("runnable_actions") or [])
        except Exception:
            s = None  # 매니페스트 없으면 필터 비활성(안전)
        _phone_runnable_cache["set"] = s
        _phone_runnable_cache["loaded"] = True
    return _phone_runnable_cache["set"]


def _derive_instruments() -> dict:
    """ibl_nodes.yaml 의 app: 블록 → 원격 앱 표면 계기 매니페스트 합성.

    - app.instrument 가 같은 액션들은 한 계기의 modes(탭)로 병합 (mode_order 정렬)
    - icon+name 을 선언한 멤버가 계기의 primary (빌드 검증이 정확히 1개 강제)
    - 홈 그리드 정렬은 app.order (미지정 999)
    """
    import yaml
    with open(IBL_NODES_PATH, 'r', encoding='utf-8') as f:
        nodes = (yaml.safe_load(f) or {}).get("nodes", {})

    runnable = _phone_runnable_actions()  # 폰이면 집합, PC면 None

    groups: dict[str, list] = {}
    group_seq: list[str] = []
    for node_name, node in nodes.items():
        if not isinstance(node, dict):
            continue
        for action_name, action in (node.get("actions") or {}).items():
            if not isinstance(action, dict):
                continue
            app = action.get("app")
            if not isinstance(app, dict):
                continue
            # 폰 프로파일: app: 블록은 기본 노출 — 실행은 라우팅(phone_api._code_needs_mac)이
            # 로컬/맥 자동 결정한다(폰 불가 액션도 맥 위임 후 폰서 렌더). phone_render:false 만
            # 숨김 = 폰서 못 보여주는 출력(맥 브라우저·네이티브창) 또는 미검증 보류(ytmusic).
            if runnable is not None and app.get("phone_render") is False:
                continue
            gid = app.get("instrument") or action_name
            if gid not in groups:
                groups[gid] = []
                group_seq.append(gid)
            groups[gid].append((action_name, app))

    instruments = []
    for gid in group_seq:
        members = sorted(groups[gid], key=lambda m: m[1].get("mode_order", 0))
        primary = next((a for _, a in members if a.get("icon") and a.get("name")), members[0][1])
        inst = {
            "id": gid,
            "icon": primary.get("icon", "🔧"),
            "name": primary.get("name", gid),
            "_order": primary.get("order", 999),
        }
        explicit = primary.get("modes")
        if isinstance(explicit, list) and explicit:
            # 명시적 modes — 한 액션이 여러 탭을 선언(주식/코인/자원). 탭별로 다른 액션 호출 가능.
            modes = []
            for m in explicit:
                if not isinstance(m, dict):
                    continue
                # 폰 프로파일: 탭도 phone_render:false 만 숨김(실행은 라우팅이 결정)
                if runnable is not None and m.get("phone_render") is False:
                    continue
                modes.append(m)
            if not modes:
                continue  # 모든 탭이 폰서 제외 → 계기 숨김
            inst["modes"] = modes
        elif len(members) == 1 and not members[0][1].get("mode"):
            app = members[0][1]
            for f in _APP_MODE_FIELDS:
                if f in app:
                    inst[f] = app[f]
        else:
            inst["modes"] = []
            for action_name, app in members:
                mode = {"id": action_name, "name": app.get("mode", action_name)}
                for f in _APP_MODE_FIELDS:
                    if f in app:
                        mode[f] = app[f]
                inst["modes"].append(mode)
        instruments.append(inst)

    instruments.sort(key=lambda i: i["_order"])
    for inst in instruments:
        inst.pop("_order", None)
    return {"version": 2, "source": "ibl_nodes", "instruments": instruments}

# 세션 저장소 (메모리)
sessions = {}

def load_config():
    """설정 로드"""
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {
        "enabled": False,
        "password_hash": None,
    }

def save_config(config):
    """설정 저장"""
    os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
    with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)

def hash_password(password: str) -> str:
    """비밀번호 SHA256 해시 (Finder와 동일 방식)"""
    return hashlib.sha256(password.encode()).hexdigest()

def verify_session(request: Request) -> bool:
    """세션 검증"""
    session_id = request.cookies.get("launcher_session")
    if not session_id:
        session_id = request.headers.get("X-Launcher-Session")
    return session_id in sessions


# === 원격(터널) 요청 판별 ===
# launcher/finder 데이터 엔드포인트는 데스크탑과 공유되므로, 터널을 통해
# 들어온 외부 요청만 골라내 인증 게이트를 적용한다. (localhost 데스크탑은 통과)

def _load_external_hostnames():
    """tunnel_config.json에서 외부 노출 호스트네임 집합 로드"""
    hosts = set()
    try:
        cfg_path = os.path.join(os.path.dirname(__file__), "..", "data", "tunnel_config.json")
        if os.path.exists(cfg_path):
            with open(cfg_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
            for key in ("launcher_hostname", "finder_hostname", "hostname"):
                h = (cfg.get(key) or "").strip().lower()
                if h:
                    hosts.add(h)
    except Exception:
        pass
    return hosts


_EXTERNAL_HOSTNAMES = _load_external_hostnames()


def reload_external_hostnames():
    """터널 설정 변경 후 호스트네임 캐시 갱신"""
    global _EXTERNAL_HOSTNAMES
    _EXTERNAL_HOSTNAMES = _load_external_hostnames()
    return _EXTERNAL_HOSTNAMES


def is_external_request(request: Request) -> bool:
    """터널 호스트네임으로 들어온 원격 요청인지 판별"""
    host = (request.headers.get("host") or "").split(":")[0].strip().lower()
    if host and host in _EXTERNAL_HOSTNAMES:
        return True
    # 호스트네임 설정이 비어있을 때를 위한 폴백: Cloudflare 경유 신호
    if request.headers.get("cf-connecting-ip"):
        return True
    return False


def is_public_remote_path(method: str, path: str) -> bool:
    """원격에서 인증 없이 허용되는 경로 (로그인 셸 + 자체 인증 보유 경로)"""
    # 런처 앱 셸 + 로그인 흐름
    if path == "/launcher/app":
        return True
    if path in ("/launcher/auth/login", "/launcher/auth/logout"):
        return True
    # 생존 핑(피어 연결상태 표시용) — 민감정보 없음, 다른 몸이 무인증으로 핑
    if method == "GET" and path == "/ping":
        return True
    if method == "GET" and path == "/launcher/config":
        return True
    # 원격 파인더(/nas/*)는 자체 session_token 인증을 사용하므로 위임
    if path == "/nas" or path.startswith("/nas/"):
        return True
    return False

# === API 엔드포인트 ===

class ConfigModel(BaseModel):
    enabled: bool
    password: Optional[str] = None  # 새 비밀번호 설정 시에만 전달 (생략 시 기존 유지)

class LoginModel(BaseModel):
    password: str

@router.get("/config")
async def get_config():
    """설정 조회"""
    config = load_config()
    return {
        "enabled": config.get("enabled", False),
        "has_password": bool(config.get("password_hash"))
    }

@router.post("/config")
async def set_config(update: ConfigModel):
    """설정 저장 (비밀번호는 해시로만 저장)"""
    config = load_config()
    config["enabled"] = update.enabled

    if update.password is not None and update.password != "":
        if len(update.password) < 4:
            raise HTTPException(status_code=400, detail="비밀번호는 4자 이상이어야 합니다")
        config["password_hash"] = hash_password(update.password)

    # 레거시 평문 비밀번호 필드가 남아있으면 제거
    config.pop("password", None)

    save_config(config)
    return {"success": True}

@router.get("/instruments")
async def get_instruments():
    """앱 표면 계기 매니페스트 — ibl_nodes.yaml app: 블록에서 파생 (mtime 캐시).

    표면은 이걸 해석만 한다 (선언형). 새 IBL 액션에 app: 블록만 달면 자동 등장.
    원격 인증: api.py:remote_access_guard가 외부 요청에 launcher 세션을 요구
    (화이트리스트 아님 — 데이터 엔드포인트라 로그인 후 접근이 맞음).
    """
    try:
        mtime = os.path.getmtime(IBL_NODES_PATH)
        if _instruments_cache["mtime"] != mtime:
            _instruments_cache["payload"] = _derive_instruments()
            _instruments_cache["mtime"] = mtime
        return _instruments_cache["payload"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"계기 파생 실패: {e}")


@router.post("/auth/login")
async def login(data: LoginModel, response: Response):
    """로그인"""
    config = load_config()

    if not config.get("enabled"):
        raise HTTPException(status_code=403, detail="원격 런처가 비활성화되어 있습니다")

    # 레거시 평문 비밀번호 자동 마이그레이션 (있으면 해시로 전환 후 평문 제거)
    if config.get("password") and not config.get("password_hash"):
        config["password_hash"] = hash_password(config["password"])
        config.pop("password", None)
        save_config(config)

    password_hash = config.get("password_hash")
    if not password_hash:
        raise HTTPException(status_code=400, detail="비밀번호가 설정되지 않았습니다")

    if hash_password(data.password) != password_hash:
        raise HTTPException(status_code=401, detail="비밀번호가 틀렸습니다")

    session_id = str(uuid.uuid4())
    sessions[session_id] = {
        "created": datetime.now().isoformat()
    }

    response.set_cookie(
        key="launcher_session",
        value=session_id,
        httponly=True,
        secure=True,        # 터널은 HTTPS 전용
        samesite="strict",
        max_age=60 * 60 * 24 * 7,  # 7일
    )

    return {"success": True, "session_id": session_id}

@router.post("/auth/logout")
async def logout(request: Request, response: Response):
    """로그아웃"""
    session_id = request.cookies.get("launcher_session")
    if session_id and session_id in sessions:
        del sessions[session_id]
    response.delete_cookie("launcher_session")
    return {"success": True}

@router.get("/app", response_class=HTMLResponse)
async def get_webapp():
    """원격 런처 웹앱"""
    return get_launcher_webapp_html()


def get_launcher_webapp_html():
    """원격 런처 웹앱 HTML — 3표면(자율주행/수동/앱) 구조"""
    return """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0">
<title>IndieBiz OS — Remote Launcher</title>
<!-- 폰 라디오 재생용: 한국 방송은 HLS(.m3u8)라 Android WebView 직접재생에 hls.js 필요 -->
<script src="https://cdn.jsdelivr.net/npm/hls.js@1"></script>
<!-- 지도 render 프리미티브(길찾기·부동산·상권·CCTV): leaflet -->
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://cdn.jsdelivr.net/npm/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
* { margin:0; padding:0; box-sizing:border-box; -webkit-tap-highlight-color:transparent; }
:root{
  --bg:#15151f; --bg2:#1c1c2b; --bg3:#262640; --line:#33334d;
  --txt:#ececf2; --dim:#9a9ab0; --acc:#e94560; --acc2:#ff6b81;
  --ok:#3ecf8e; --warn:#f5a623; --unknown:#7a7a92; --info:#4a9fe0;
  --up:#e94560; --down:#3f7fe0;
}
body{ font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,sans-serif; background:var(--bg); color:var(--txt); min-height:100vh; -webkit-font-smoothing:antialiased; }
button{ font-family:inherit; cursor:pointer; }
input,textarea,select{ font-family:inherit; }
::-webkit-scrollbar{ width:8px; height:8px; }
::-webkit-scrollbar-thumb{ background:var(--bg3); border-radius:4px; }

/* 로그인 */
.login{ display:flex; flex-direction:column; align-items:center; justify-content:center; min-height:100vh; padding:20px; }
.login-box{ background:var(--bg2); padding:36px 28px; border-radius:18px; width:100%; max-width:380px; box-shadow:0 12px 48px rgba(0,0,0,.4); }
.login-box h1{ font-size:24px; text-align:center; }
.login-box p.sub{ color:var(--dim); text-align:center; font-size:13px; margin:6px 0 26px; }
.inp{ width:100%; padding:14px 16px; border:1px solid var(--line); border-radius:10px; background:var(--bg); color:var(--txt); font-size:16px; }
.inp:focus{ outline:none; border-color:var(--acc); }
.btn{ width:100%; padding:14px; background:var(--acc); color:#fff; border:none; border-radius:10px; font-size:16px; font-weight:600; margin-top:14px; transition:background .15s; }
.btn:hover{ background:var(--acc2); }
.btn:disabled{ background:var(--line); cursor:not-allowed; }
.err{ color:var(--acc); text-align:center; margin-top:14px; font-size:13px; min-height:18px; }

/* 앱 셸 */
.app{ display:none; flex-direction:column; height:100vh; }
.app.on{ display:flex; }
.top{ display:flex; align-items:center; justify-content:space-between; padding:10px 14px; background:var(--bg2); border-bottom:1px solid var(--line); flex-shrink:0; }
.top .brand{ display:flex; align-items:center; gap:8px; font-weight:700; font-size:15px; }
.top .badge{ background:var(--acc); color:#fff; font-size:10px; font-weight:700; padding:3px 7px; border-radius:8px; letter-spacing:.5px; }
.iconbtn{ background:var(--bg3); border:none; color:var(--txt); width:34px; height:34px; border-radius:8px; font-size:15px; }
.iconbtn:hover{ background:var(--acc); }

/* 표면 토글 */
.surfaces{ display:flex; gap:6px; padding:8px 14px; background:var(--bg2); border-bottom:1px solid var(--line); flex-shrink:0; }
.surf-tab{ flex:1; padding:10px 6px; background:var(--bg); border:1px solid var(--line); border-radius:10px; color:var(--dim); font-size:13px; font-weight:600; display:flex; flex-direction:column; align-items:center; gap:3px; transition:all .15s; }
.surf-tab .em{ font-size:18px; }
.surf-tab.on{ background:var(--acc); border-color:var(--acc); color:#fff; }
.surf-tab .hint{ font-size:9px; font-weight:400; opacity:.7; }

.panel{ flex:1; overflow-y:auto; display:none; }
.panel.on{ display:flex; flex-direction:column; }
.wrap{ max-width:720px; width:100%; margin:0 auto; padding:16px; }

/* 공통 */
.row{ display:flex; gap:8px; }
.field{ flex:1; padding:12px 14px; border:1px solid var(--line); border-radius:10px; background:var(--bg2); color:var(--txt); font-size:15px; }
.field:focus{ outline:none; border-color:var(--acc); }
.go{ padding:12px 18px; background:var(--acc); color:#fff; border:none; border-radius:10px; font-weight:600; white-space:nowrap; }
.go:hover{ background:var(--acc2); }
.go:disabled{ background:var(--line); }
.muted{ color:var(--dim); font-size:13px; }
.card{ background:var(--bg2); border:1px solid var(--line); border-radius:12px; padding:14px; margin-bottom:10px; }
.spin{ width:22px; height:22px; border:2px solid var(--line); border-top-color:var(--acc); border-radius:50%; animation:sp 1s linear infinite; }
@keyframes sp{ to{ transform:rotate(360deg); } }
.center{ display:flex; align-items:center; justify-content:center; gap:10px; padding:30px; color:var(--dim); }
.pill{ display:inline-block; padding:2px 8px; border-radius:8px; font-size:11px; font-weight:600; }

/* === 자율주행 (드릴다운: 대상 선택 → 대화, 전체 폭) === */
.ap-browse{ flex:1; overflow-y:auto; padding:14px; }
.ap-browse h3{ font-size:11px; text-transform:uppercase; color:var(--dim); margin:16px 4px 8px; letter-spacing:.5px; }
.ap-browse h3:first-child{ margin-top:2px; }
.ap-bhead{ display:flex; align-items:center; gap:10px; margin-bottom:8px; }
.ap-bhead h2{ font-size:18px; }
.ap-card{ display:flex; align-items:center; gap:13px; padding:15px 16px; background:var(--bg2); border:1px solid var(--line); border-radius:13px; margin-bottom:9px; }
.ap-card:hover{ border-color:var(--acc); }
.ap-card .ic{ font-size:22px; width:28px; text-align:center; flex-shrink:0; }
.ap-card .tx{ flex:1; min-width:0; display:flex; flex-direction:column; }
.ap-card .tx .nm{ font-weight:600; font-size:15px; }
.ap-card .tx .ds{ font-size:12px; color:var(--dim); margin-top:2px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.ap-card .chev{ color:var(--dim); font-size:20px; flex-shrink:0; }
.ap-chat{ flex:1; display:flex; flex-direction:column; min-height:0; }
.ap-head{ padding:11px 14px; background:var(--bg2); border-bottom:1px solid var(--line); display:flex; align-items:center; gap:10px; }
.ap-head .ap-head-t{ min-width:0; flex:1; }
.ap-head h2{ font-size:16px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.ap-head p{ font-size:11px; color:var(--dim); margin-top:2px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
.msgs{ flex:1; overflow-y:auto; padding:16px; }
.msgs .empty{ color:var(--dim); text-align:center; padding:40px 20px; font-size:14px; line-height:1.6; }
.msg{ margin-bottom:14px; display:flex; gap:10px; }
.msg.user{ flex-direction:row-reverse; }
.av{ width:30px; height:30px; border-radius:50%; background:var(--bg3); display:flex; align-items:center; justify-content:center; flex-shrink:0; font-size:15px; }
.bub{ max-width:78%; background:var(--bg2); border:1px solid var(--line); padding:10px 13px; border-radius:13px; font-size:14px; line-height:1.5; white-space:pre-wrap; word-break:break-word; }
.msg.user .bub{ background:var(--acc); border-color:var(--acc); }
.ap-hist-sep{ text-align:center; color:var(--dim); font-size:12px; margin:14px 0 4px; opacity:.7; }
.composer{ padding:12px 16px; background:var(--bg2); border-top:1px solid var(--line); display:flex; gap:8px; }
.composer textarea{ flex:1; padding:11px 14px; border:1px solid var(--line); border-radius:10px; background:var(--bg); color:var(--txt); font-size:14px; resize:none; max-height:120px; }
.composer textarea:focus{ outline:none; border-color:var(--acc); }
.sw-item{ display:flex; align-items:center; gap:12px; }
.sw-item .nm{ flex:1; font-weight:600; font-size:14px; }
.sw-item .pr{ font-size:11px; color:var(--dim); }

/* === 수동 === */
.step{ margin-bottom:16px; }
.step-label{ font-size:11px; color:var(--dim); text-transform:uppercase; letter-spacing:.5px; margin-bottom:7px; font-weight:600; }
.codebox{ width:100%; min-height:64px; padding:13px; border:1px solid var(--line); border-radius:10px; background:#11111a; color:#a5d6ff; font-family:'SF Mono',Menlo,monospace; font-size:13px; line-height:1.5; resize:vertical; }
.eff{ background:var(--bg2); border:1px solid var(--line); border-left-width:3px; border-radius:8px; padding:11px 13px; margin-bottom:8px; }
.eff.read{ border-left-color:var(--ok); }
.eff.write{ border-left-color:var(--warn); }
.eff.unknown{ border-left-color:var(--unknown); }
.eff .h{ display:flex; align-items:center; gap:8px; font-size:13px; font-weight:600; }
.eff .e{ font-size:13px; color:var(--dim); margin-top:5px; line-height:1.45; }
.s-read{ background:rgba(62,207,142,.16); color:var(--ok); }
.s-write{ background:rgba(245,166,35,.16); color:var(--warn); }
.s-unknown{ background:rgba(122,122,146,.2); color:var(--dim); }
.warnbox{ background:rgba(245,166,35,.1); border:1px solid var(--warn); border-radius:10px; padding:12px; margin-bottom:12px; font-size:13px; display:flex; align-items:flex-start; gap:9px; }
.warnbox input{ margin-top:2px; width:17px; height:17px; accent-color:var(--warn); }
.result{ background:#11111a; border:1px solid var(--line); border-radius:10px; padding:13px; font-family:'SF Mono',Menlo,monospace; font-size:12px; line-height:1.5; white-space:pre-wrap; word-break:break-word; max-height:340px; overflow:auto; color:#cfe9ff; }
.refbox{ font-size:12px; color:var(--dim); background:var(--bg); border:1px dashed var(--line); border-radius:8px; padding:10px; margin-top:8px; white-space:pre-wrap; max-height:160px; overflow:auto; display:none; }
.linkbtn{ background:none; border:none; color:var(--info); font-size:12px; padding:4px 0; text-decoration:underline; }
.btnrow{ display:flex; gap:8px; flex-wrap:wrap; }
.btn2{ padding:11px 16px; border:1px solid var(--line); background:var(--bg3); color:var(--txt); border-radius:10px; font-weight:600; font-size:14px; }
.btn2:hover{ border-color:var(--acc); }
.btn2.danger{ color:#e5484d; padding:11px 12px; }
/* 계기판 헤더 + IBL이란 설명 */
.dash-head{ display:flex; align-items:center; justify-content:space-between; gap:10px; margin-bottom:14px; flex-wrap:wrap; }
.dash-titles{ min-width:0; }
.dash-title{ font-size:17px; font-weight:700; color:var(--txt); }
.dash-sub{ font-size:11px; color:var(--dim); margin-top:2px; }
.dash-btns{ display:flex; gap:7px; flex-shrink:0; }
.dash-btn{ padding:7px 13px; border:1px solid var(--line); background:var(--bg2); color:var(--dim); border-radius:999px; font-size:12.5px; font-weight:600; transition:all .15s; }
.dash-btn:hover{ border-color:var(--acc); color:var(--txt); }
.dash-btn.on{ background:var(--acc); border-color:var(--acc); color:#fff; }
.about{ background:var(--bg2); border:1px solid var(--line); border-radius:12px; padding:15px 16px; margin-bottom:14px; font-size:13px; line-height:1.6; color:var(--txt); }
.about p{ margin:0 0 8px; }
.about b{ color:#fff; font-weight:700; }
.about .about-h{ font-size:15px; font-weight:700; color:var(--acc2); margin-bottom:8px; }
.about .about-sec{ font-size:12.5px; font-weight:700; color:var(--txt); margin:14px 0 6px; padding-top:11px; border-top:1px solid var(--line); }
.about ul{ margin:6px 0 8px; padding-left:18px; }
.about li{ margin-bottom:3px; }
.about code{ font-family:'SF Mono',Menlo,monospace; font-size:11.5px; background:var(--bg); color:#a5d6ff; padding:1px 5px; border-radius:5px; }
.about .about-dim{ color:var(--dim); font-size:12px; }
.about .about-code{ font-family:'SF Mono',Menlo,monospace; font-size:12px; background:var(--bg); color:#a5d6ff; border:1px solid var(--line); border-radius:8px; padding:9px 11px; margin:6px 0 4px; word-break:break-all; }
.btn2.danger:hover{ border-color:#e5484d; }
.ap-newbtn{ width:100%; padding:13px; margin:2px 0 6px; border:1px dashed var(--line); background:transparent; color:var(--acc); border-radius:11px; font-weight:600; font-size:14px; cursor:pointer; }
.ap-newbtn:hover{ border-color:var(--acc); background:var(--bg2); }
.ap-form{ display:flex; flex-direction:column; gap:6px; padding:4px; }
.ap-form label{ font-size:12px; color:var(--dim); margin-top:8px; }
.ap-form input,.ap-form textarea,.ap-form select{ padding:11px 12px; border:1px solid var(--line); background:var(--bg2); color:var(--txt); border-radius:10px; font-size:14px; font-family:inherit; }
.ap-form-row{ display:flex; gap:8px; margin-top:14px; }
.ap-form-row .btn2,.ap-form-row .go{ flex:1; }
.btn2.prim{ background:var(--acc); border-color:var(--acc); color:#fff; }
.btn2.prim:hover{ background:var(--acc2); }
.btn2:disabled{ opacity:.5; }
/* 둘러보기 팔레트 */
.palette{ margin-top:18px; border-top:1px solid var(--line); padding-top:14px; }
.cat-node{ margin-bottom:10px; }
.cat-node h4{ font-size:12px; color:var(--acc2); margin-bottom:5px; }
.act-chip{ display:inline-block; margin:3px 4px 0 0; padding:5px 10px; background:var(--bg3); border:1px solid var(--line); border-radius:8px; font-size:12px; }
.act-chip:hover{ border-color:var(--acc); }

/* === 앱 === */
.grid{ display:grid; grid-template-columns:repeat(3,1fr); gap:12px; }
.tile{ background:var(--bg2); color:var(--txt); border:1px solid var(--line); border-radius:16px; padding:20px 10px; display:flex; flex-direction:column; align-items:center; gap:8px; }
.tile:hover{ border-color:var(--acc); transform:translateY(-2px); }
.tile .em{ font-size:30px; }
.tile .nm{ font-size:13px; font-weight:600; }
.fileov{ position:fixed; inset:0; z-index:1000; background:var(--bg); display:flex; flex-direction:column; }
.fileov-bar{ display:flex; align-items:center; justify-content:space-between; gap:10px; padding:8px 12px; background:var(--bg2); border-bottom:1px solid var(--line); color:var(--txt); font-size:13px; flex-shrink:0; }
.fileov iframe{ flex:1; border:none; width:100%; background:#fff; }
.inst-head{ display:flex; align-items:center; gap:10px; margin-bottom:14px; }
.back{ background:var(--bg3); border:none; color:var(--txt); width:34px; height:34px; border-radius:9px; font-size:16px; }
.back:hover{ background:var(--acc); }
.inst-head h2{ font-size:17px; }
.tabs{ display:flex; gap:6px; margin-bottom:12px; }
.tab{ padding:8px 14px; background:var(--bg2); border:1px solid var(--line); border-radius:9px; font-size:13px; color:var(--dim); }
.tab.on{ background:var(--acc); border-color:var(--acc); color:#fff; }
.calgrid{ display:grid; grid-template-columns:repeat(7,1fr); gap:3px; margin-top:10px; }
.calwd{ text-align:center; font-size:11px; color:var(--dim); padding:4px 0; }
.calday{ position:relative; aspect-ratio:1; display:flex; align-items:center; justify-content:center; font-size:14px; border-radius:8px; background:var(--bg2); cursor:pointer; }
.calday.calhas{ font-weight:700; }
.calday.calsel{ background:var(--acc); color:#fff; }
.caldot{ position:absolute; bottom:5px; left:50%; transform:translateX(-50%); width:5px; height:5px; border-radius:50%; background:var(--acc); }
.calday.calsel .caldot{ background:#fff; }
.calpanel{ margin-top:12px; border-top:1px solid var(--line); padding-top:10px; }
.lmaptoggle{ position:absolute; top:10px; right:10px; z-index:500; background:rgba(20,20,35,.85); color:#fff; border:1px solid var(--line); border-radius:18px; padding:7px 14px; font-size:13px; font-weight:600; }
.lmaptoggle.on{ background:var(--acc); border-color:var(--acc); }
.chips{ display:flex; gap:6px; flex-wrap:wrap; margin-bottom:12px; }
.chip{ padding:6px 12px; background:var(--bg2); border:1px solid var(--line); border-radius:20px; font-size:12px; }
.filters{ display:flex; gap:6px; flex-wrap:wrap; }
.fchip{ padding:5px 12px; background:var(--bg2); border:1px solid var(--line); border-radius:8px; font-size:12px; color:var(--dim); }
.fchip.on{ background:var(--acc); border-color:var(--acc); color:#fff; }
.chip:hover{ border-color:var(--acc); }
.bookcard{ display:flex; gap:12px; }
.bookcard img{ width:56px; height:80px; object-fit:cover; border-radius:6px; background:var(--bg3); flex-shrink:0; }
.card .t{ font-weight:600; font-size:14px; margin-bottom:3px; }
.card .m{ font-size:12px; color:var(--dim); line-height:1.5; }
.posters{ display:grid; grid-template-columns:repeat(2,minmax(0,1fr)); gap:10px; }
.poster{ min-width:0; }
.poster img{ width:100%; aspect-ratio:3/4; object-fit:cover; border-radius:8px; background:var(--bg3); cursor:pointer; }
.poster .t{ font-size:13px; font-weight:600; margin-top:6px; }
.poster .m{ font-size:11px; color:var(--dim); margin-top:2px; }
.kv{ display:flex; justify-content:space-between; padding:6px 0; border-bottom:1px solid var(--line); font-size:13px; }
.kv .k{ color:var(--dim); }
.big{ font-size:30px; font-weight:700; }
.note{ font-size:11px; color:var(--warn); background:rgba(245,166,35,.1); border-radius:8px; padding:8px 10px; margin-bottom:12px; }
/* 메신저/커뮤니티: 대화 버블(thread) + 작성바(compose) */
.thread{ display:flex; flex-direction:column; gap:6px; padding:4px 0 2px; }
.tmsg{ display:flex; flex-direction:column; align-items:flex-start; }
.tmsg.me{ align-items:flex-end; }
.tbub{ max-width:78%; padding:9px 13px; border-radius:14px; border-bottom-left-radius:4px; font-size:14px; line-height:1.5; white-space:pre-wrap; word-break:break-word; background:var(--bg2); border:1px solid var(--line); }
.tmsg.me .tbub{ background:var(--acc); border-color:var(--acc); color:#fff; border-bottom-left-radius:14px; border-bottom-right-radius:4px; }
.tfoot{ font-size:10px; color:var(--dim); margin-top:2px; padding:0 5px; }
.composebar{ position:sticky; bottom:0; display:flex; gap:8px; padding:10px 0 6px; margin-top:8px; background:linear-gradient(transparent,var(--bg) 35%); }
.composebar .field{ border-radius:22px; }
.composebar .go{ border-radius:22px; }
/* master-detail 반응형(메신저): 넓으면 2분할(리스트+상세), 좁으면 드릴(리스트↔상세 토글) */
.mdsplit{ display:flex; flex-direction:column; gap:10px; }
.mddetail{ display:flex; flex-direction:column; min-width:0; }
.mdph{ flex:1; display:flex; align-items:center; justify-content:center; color:var(--dim); font-size:13px; padding:40px 0; }
@media(min-width:760px){
  .mdsplit{ flex-direction:row; height:calc(100vh - 250px); }
  .mdlist{ width:258px; flex-shrink:0; overflow-y:auto; padding-right:6px; }
  .mddetail{ flex:1; border-left:1px solid var(--line); padding-left:14px; overflow-y:auto; }
  .mdback{ display:none; }
}
@media(max-width:759px){
  .mdsplit.has-detail .mdlist{ display:none; }
  .mdsplit:not(.has-detail) .mddetail{ display:none; }
}
a{ color:var(--info); }
@media(max-width:560px){
  .grid{ grid-template-columns:repeat(3,1fr); }
  .surf-tab .hint{ display:none; }
}
</style>
</head>
<body>

<!-- 로그인 -->
<div class="login" id="login">
  <div class="login-box">
    <h1>IndieBiz OS</h1>
    <p class="sub">Remote Launcher</p>
    <input type="password" class="inp" id="pw" placeholder="비밀번호" autocomplete="current-password">
    <button class="btn" id="loginBtn" onclick="doLogin()">로그인</button>
    <p class="err" id="loginErr"></p>
  </div>
</div>

<!-- 앱 -->
<div class="app" id="app">
  <div class="top">
    <div class="brand"><span>IndieBiz OS</span><span class="badge" id="surfBadge">REMOTE</span></div>
    <div style="display:flex; gap:8px;" id="headerActions">
      <button class="iconbtn" onclick="refreshSurface()" title="새로고침">↻</button>
      <button class="iconbtn" onclick="doLogout()" title="로그아웃">⏻</button>
    </div>
  </div>
  <div class="surfaces">
    <button class="surf-tab on" id="t-autopilot" onclick="setSurface('autopilot')">
      <span class="em">🛰️</span><span>자율주행</span><span class="hint">속도·표현력</span></button>
    <button class="surf-tab" id="t-manual" onclick="setSurface('manual')">
      <span class="em">⚙️</span><span>계기판</span><span class="hint">표현력·주권</span></button>
    <button class="surf-tab" id="t-app" onclick="setSurface('app')">
      <span class="em">📱</span><span>앱</span><span class="hint">속도·주권</span></button>
  </div>

  <!-- 자율주행 — 드릴다운: ① 대상 선택(시스템AI/스위치/프로젝트→에이전트) → ② 대화/결과 -->
  <div class="panel on" id="p-autopilot">
    <!-- ① 대상 브라우저 (루트 ↔ 프로젝트 에이전트 드릴) -->
    <div class="ap-browse" id="ap-browse">
      <div class="ap-bhead" id="ap-bhead" style="display:none">
        <button class="back" onclick="apBrowseRoot()">←</button>
        <h2 id="apBrowseTitle"></h2>
      </div>
      <div id="apBrowse"></div>
    </div>
    <!-- ② 대화 / 결과 (전체 폭) -->
    <div class="ap-chat" id="ap-chat" style="display:none">
      <div class="ap-head">
        <button class="back" onclick="apExitChat()">←</button>
        <div class="ap-head-t"><h2 id="apTitle">시스템 AI</h2><p id="apSub"></p></div>
      </div>
      <div class="msgs" id="apMsgs"></div>
      <div class="composer" id="apComposer">
        <textarea id="apInput" rows="1" placeholder="메시지..." onkeydown="apKey(event)"></textarea>
        <button class="go" id="apSend" onclick="apSend()">전송</button>
      </div>
    </div>
  </div>

  <!-- 계기판 -->
  <div class="panel" id="p-manual">
    <div class="wrap">
      <!-- 계기판 헤더 — IBL 사전 / IBL이란? -->
      <div class="dash-head">
        <div class="dash-titles">
          <div class="dash-title">계기판</div>
          <div class="dash-sub">자연어를 IBL로 번역·검수해 실행합니다</div>
        </div>
        <div class="dash-btns">
          <button class="dash-btn" id="btnDict" onclick="togglePalette()">📖 IBL 사전</button>
          <button class="dash-btn" id="btnAbout" onclick="toggleAbout()">❔ IBL이란?</button>
        </div>
      </div>
      <!-- IBL이란? 설명 -->
      <div id="mAbout" class="about" style="display:none">
        <div class="about-h">IBL (IndieBiz Logic)</div>
        <p>indiebizOS의 <b>신경계 역할을 하는 언어</b>. 세 가지로 이루어집니다 — <b>어휘</b>(조합 가능한 액션) · <b>문법</b>(쓰고 잇는 규칙) · <b>통화</b>(흐르는 데이터).</p>
        <div class="about-sec">어휘 — 무엇을 할 수 있나</div>
        <p>액션 하나가 IBL이 할 수 있는 일 하나. 예: <code>[sense:weather]</code>. 대상에 따라 <b>5개 노드</b>로 나뉩니다.</p>
        <ul>
          <li><code>sense</code> 감각 — 바깥 정보 수집·검색 (날씨·주가·뉴스·웹)</li>
          <li><code>self</code> 자기 — 내 기억·파일·설정·일정</li>
          <li><code>limbs</code> 손발 — 기기·도구 조작 (브라우저·화면·음악·폰)</li>
          <li><code>others</code> 관계 — 이웃·위임·메시징</li>
          <li><code>engines</code> 엔진 — 콘텐츠 생성·변환 (문서·슬라이드·차트)</li>
        </ul>
        <p class="about-dim">액션은 셋 중 하나를 합니다 — <b>생성</b>(통화를 낸다) · <b>변환</b>(통화를 바꾼다) · <b>행동</b>(세상에 작용).</p>
        <div class="about-sec">문법 — 어떻게 쓰고 잇나</div>
        <div class="about-code">[node:action]{params}</div>
        <ul>
          <li>값은 <code>{key: 값}</code>. 예: <code>[sense:weather]{city:"수원"}</code></li>
          <li>한 액션 안의 변형은 <code>op</code> 로: <code>{op:"query"}</code></li>
          <li>잇기 — <code>&gt;&gt;</code> 순차(앞 결과를 뒤로) · <code>&amp;</code> 병렬 · <code>??</code> 폴백</li>
        </ul>
        <div class="about-sec">통화 — 무엇이 흐르나</div>
        <p>통화는 단 하나, <b>items</b> — 열린 항목들의 목록. 한 액션의 결과가 다음으로 <code>&gt;&gt;</code> 흐릅니다. 이게 IBL을 낱말이 아니라 <b>문장</b>으로 만듭니다.</p>
        <p class="about-dim"><b>변환자</b>(통화를 받아 통화를 냄): <code>filter · sort · take · select · dedup · groupby · join · union · merge</code></p>
        <div class="about-code">[sense:realty]{region:"강남구"} &gt;&gt; sort &gt;&gt; take{n:3}</div>
      </div>
      <!-- IBL 사전(액션 팔레트) -->
      <div id="palette" class="palette" style="display:none"></div>
      <!-- 다른 몸(피어) 연결상태 — 폰이면 맥, 맥-원격이면 폰 -->
      <div id="peerStatus" style="display:none"></div>
      <div class="step">
        <div class="step-label">① 의도 (자연어)</div>
        <div class="row">
          <input class="field" id="mIntent" placeholder='예: 서울 날씨 알려줘 / 강남구 아파트 실거래가' onkeydown="if(event.key==='Enter')mTranslate()">
          <button class="go" id="mTransBtn" onclick="mTranslate()">번역</button>
        </div>
      </div>
      <div id="mAfterTranslate" style="display:none">
        <div class="step">
          <div class="step-label">② IBL 코드 (수정 가능)</div>
          <textarea class="codebox" id="mCode"></textarea>
          <button class="linkbtn" onclick="toggleRefs()">참고 용례 보기/숨기기</button>
          <div class="refbox" id="mRefs"></div>
        </div>
        <div class="btnrow">
          <button class="btn2 prim" id="mValBtn" onclick="mValidate()">검수 (dry-run)</button>
        </div>
      </div>
      <div id="mAfterValidate" style="display:none">
        <div class="step" style="margin-top:16px">
          <div class="step-label">③ 효과 검수 — 코드가 아니라 무슨 일이 일어나는지</div>
          <div id="mSteps"></div>
        </div>
        <div id="mSideWarn"></div>
        <div class="btnrow">
          <button class="btn2 prim" id="mExecBtn" onclick="mExecute()">실행</button>
        </div>
      </div>
      <div id="mAfterExecute" style="display:none">
        <div class="step" style="margin-top:16px">
          <div class="step-label">④ 결과</div>
          <div class="result" id="mResult"></div>
          <div class="btnrow" style="margin-top:10px">
            <button class="btn2" id="mDistillBtn" onclick="mDistill()">✓ 이 결과 학습 (해마 증류)</button>
          </div>
          <p class="muted" id="mDistillMsg" style="margin-top:8px"></p>
        </div>
      </div>
    </div>
  </div>

  <!-- 앱 -->
  <div class="panel" id="p-app">
    <div class="wrap" id="appHome"></div>
    <div class="wrap" id="appInst" style="display:none"></div>
  </div>
</div>

<script>
const API='';
let surface='autopilot';
let apChat={ type:'system', projectId:null, agentId:null, agentName:null };
let apProjects=[];
let apSwitches=[];

/* ===== 공통 ===== */
function esc(s){ const d=document.createElement('div'); d.textContent=(s==null?'':String(s)); return d.innerHTML; }
function jfetch(url,opt){ return fetch(API+url, Object.assign({headers:{'Content-Type':'application/json'}}, opt||{})); }
async function ibl(code){
  const r=await jfetch('/ibl/execute',{method:'POST',body:JSON.stringify({code,project_id:'앱모드',project_path:'.'})});
  if(!r.ok) throw new Error('[HTTP '+r.status+']');
  const data=await r.json();
  /* 합성(>>) 액션은 final_result(마지막 단계)를 펼쳐 단일 액션처럼 노출 — view의 from/{필드}가 풀리도록 */
  if(data && typeof data==='object' && 'final_result' in data){
    const fr=data.final_result;
    if(typeof fr==='string'){ try{ return JSON.parse(fr); }catch(e){ return {message:fr}; } }
    if(fr && typeof fr==='object') return fr;
  }
  return data;
}

/* ===== 로그인 ===== */
document.addEventListener('DOMContentLoaded',()=>{
  document.getElementById('pw').addEventListener('keydown',e=>{ if(e.key==='Enter')doLogin(); });
  checkSession();
});
async function checkSession(){
  // 비번 없는 표면(폰 자급·로컬)은 게이트 자체가 무의미 → config로 즉시 진입(맥 프록시 의존 제거).
  // 폰은 has_password=false 라 /projects(맥 터널 왕복) 결과와 무관히 바로 런처가 뜬다 = 로그인 화면 없음.
  try{ const c=await(await jfetch('/launcher/config')).json(); if(c && c.has_password===false){ showApp(); return; } }catch(e){}
  try{ const r=await jfetch('/projects'); if(r.ok){ showApp(); } }catch(e){}
}
async function doLogin(){
  const pw=document.getElementById('pw').value;
  const el=document.getElementById('loginErr'); el.textContent='';
  try{
    const r=await jfetch('/launcher/auth/login',{method:'POST',body:JSON.stringify({password:pw})});
    if(r.ok){ showApp(); } else { const d=await r.json().catch(()=>({})); el.textContent=d.detail||'로그인 실패'; }
  }catch(e){ el.textContent='서버 연결 실패'; }
}
async function doLogout(){ try{ await jfetch('/launcher/auth/logout',{method:'POST'}); }catch(e){} location.reload(); }
let IS_PHONE=false;
async function showApp(){
  document.getElementById('login').style.display='none';
  document.getElementById('app').classList.add('on');
  // 자급 컴패니언(폰-로컬)인지 판별 — REMOTE 배지·로그아웃(⏻)·새로고침(↻)은 원격 시나리오
  // 전용이라 폰에선 숨긴다(폰=자기 몸, 로그아웃/원격 새로고침 의미 없음).
  try{ const r=await jfetch('/launcher/config'); if(r.ok){ const c=await r.json();
    IS_PHONE=(c.host==='phone-local');
    if(IS_PHONE){ const b=document.getElementById('surfBadge'); if(b) b.style.display='none';
      const ha=document.getElementById('headerActions'); if(ha) ha.style.display='none'; }
  } }catch(e){}
  apLoad();
  loadPeer(); setInterval(loadPeer, 20000);  /* 다른 몸 연결상태 폴링(계기판) */
}

/* ===== 다른 몸(피어) 연결상태 — 계기판 안에 표기 ===== */
function renderPeer(d){
  const el=document.getElementById('peerStatus'); if(!el) return;
  if(!d){ el.style.display='none'; return; }
  const online = !!(d.has_peer && d.online);
  const name = d.peer_name || '다른 몸';
  const status = !d.has_peer ? '미연동' : (online ? '연결됨' : '오프라인');
  const dot = online ? '#10b981' : '#d6d3d1';
  el.innerHTML =
    '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:'+dot+'"></span>'+
    '<span style="color:'+(online?'#44403c':'#a8a29e')+';margin-left:8px">'+((d.peer_icon||'📱'))+' '+esc(name)+'</span>'+
    '<span style="color:'+(online?'#059669':'#a8a29e')+';margin-left:6px">· '+status+'</span>';
  el.style.cssText='display:flex;align-items:center;font-size:12px;padding:8px 2px;margin-bottom:8px';
}
async function loadPeer(){
  try{ const r=await jfetch('/nodes/peer-status'); if(r.ok){ renderPeer(await r.json()); return; } }catch(e){}
  renderPeer(null);
}

/* ===== 표면 토글 ===== */
function setSurface(s){
  surface=s;
  ['autopilot','manual','app'].forEach(k=>{
    document.getElementById('t-'+k).classList.toggle('on',k===s);
    document.getElementById('p-'+k).classList.toggle('on',k===s);
  });
  if(s==='app' && !appHomeRendered) renderAppHome();
}
function refreshSurface(){
  if(surface==='autopilot') apLoad();
  else if(surface==='app'){ appBackHome(); appHomeRendered=false; renderAppHome(true); }  /* 매니페스트 강제 재fetch */
}

/* ================= 자율주행 (드릴다운) ================= */
let apAgents=[]; let apAgProject=null;
async function apLoad(){ await apLoadProjects(); await apLoadSwitches(); apBrowseRoot(); }
async function apLoadProjects(){
  try{ const r=await jfetch('/projects'); if(r.ok){ const d=await r.json(); apProjects=d.projects||[]; } }catch(e){}
}
async function apLoadSwitches(){
  try{ const r=await jfetch('/switches'); if(r.ok){ const d=await r.json(); apSwitches=d.switches||[]; } }catch(e){}
}
function apShowBrowse(){ document.getElementById('ap-browse').style.display=''; document.getElementById('ap-chat').style.display='none'; }
function apShowChat(){ document.getElementById('ap-browse').style.display='none'; document.getElementById('ap-chat').style.display='flex'; }
function apCard(ic,nm,ds,onclick,chev){
  return '<div class="ap-card" onclick="'+onclick+'"><span class="ic">'+ic+'</span>'+
    '<span class="tx"><span class="nm">'+esc(nm)+'</span>'+(ds?'<span class="ds">'+esc(ds)+'</span>':'')+'</span>'+
    (chev?'<span class="chev">›</span>':'')+'</div>';
}
/* ① 루트: 시스템 AI / 스위치 / 프로젝트 */
function apBrowseRoot(){
  apShowBrowse();
  document.getElementById('ap-bhead').style.display='none';
  let h='<h3>시스템</h3>';
  h+=apCard('🤖','시스템 AI','IndieBiz OS 전체를 관리','apPickSystem()',false);
  // 스위치는 폰-자아엔 불필요(사용자 결정) — 폰에선 숨기고 원격/맥에선 노출.
  if(!IS_PHONE) h+=apCard('⚡','스위치','원클릭 자동화 실행','apBrowseSwitches()',true);
  h+=apCard('⏰','스케줄','반복 작업 보기·삭제','apBrowseSchedules()',true);
  h+='<h3>프로젝트 '+apProjects.length+'</h3>';
  h+='<button class="ap-newbtn" onclick="apProjectCreate()">＋ 프로젝트 만들기</button>';
  h+=apProjects.map(p=>
    '<div class="ap-card" onclick="apBrowseProject(\\''+esc(p.id)+'\\')"><span class="ic">'+(p.icon||'📁')+'</span>'+
    '<span class="tx"><span class="nm">'+esc(p.name)+'</span><span class="ds">에이전트 선택</span></span>'+
    '<span class="chev">›</span>'+
    '<button class="btn2 danger" onclick="event.stopPropagation();apProjectDelete(\\''+esc(p.id)+'\\',\\''+esc(p.name)+'\\')">🗑</button></div>'
  ).join('');
  document.getElementById('apBrowse').innerHTML=h;
}
/* 프로젝트 생성/삭제 — POST/DELETE /projects 는 catch-all 로 맥 (패리티) */
async function apProjectCreate(){
  const name=(prompt('새 프로젝트 이름:')||'').trim(); if(!name) return;
  try{ const r=await jfetch('/projects',{method:'POST',body:JSON.stringify({name,template_name:'기본'})});
    if(r.ok){ await apLoadProjects(); apBrowseRoot(); }
    else{ const d=await r.json().catch(()=>({})); alert('생성 실패: '+(d.error||d.detail||r.status)); }
  }catch(e){ alert('오류: '+e.message); }
}
async function apProjectDelete(id,name){
  if(!confirm('"'+name+'" 프로젝트를 삭제할까요? (에이전트·대화 모두 삭제)')) return;
  try{ const r=await jfetch('/projects/'+encodeURIComponent(id),{method:'DELETE'});
    if(r.ok){ await apLoadProjects(); apBrowseRoot(); }
    else{ const d=await r.json().catch(()=>({})); alert('삭제 실패: '+(d.error||d.detail||r.status)); }
  }catch(e){ alert('오류: '+e.message); }
}
/* ①-b 프로젝트 드릴 → 에이전트 전체 목록 (옛 ags[0] 자동선택 버그 제거) */
async function apBrowseProject(pid){
  const p=apProjects.find(x=>x.id===pid); if(!p) return;
  try{
    const r=await jfetch('/projects/'+encodeURIComponent(pid)+'/agents');
    if(!r.ok){ alert('에이전트 로드 실패'); return; }
    const d=await r.json(); apAgents=d.agents||[]; apAgProject=p;
    if(!apAgents.length){ alert('이 프로젝트에 에이전트가 없습니다.'); return; }
    apShowBrowse();
    document.getElementById('ap-bhead').style.display='flex';
    document.getElementById('apBrowseTitle').textContent=p.name;
    document.getElementById('apBrowse').innerHTML='<h3>에이전트 '+apAgents.length+'</h3>'+
      '<button class="ap-newbtn" onclick="apAgentCreate(\\''+esc(pid)+'\\')">＋ 에이전트 추가</button>'+
      apAgents.map((a,i)=>
        '<div class="ap-card" onclick="apPickAgent('+i+')"><span class="ic">👤</span>'+
        '<span class="tx"><span class="nm">'+esc(a.name)+'</span><span class="ds">'+esc((a.role||'').substring(0,48)||'에이전트')+'</span></span>'+
        '<button class="btn2 danger" onclick="event.stopPropagation();apAgentDelete(\\''+esc(pid)+'\\',\\''+esc(a.id)+'\\',\\''+esc(a.name)+'\\')">🗑</button></div>'
      ).join('');
  }catch(e){ alert('에이전트 로드 실패'); }
}
/* 에이전트 생성/삭제 — POST/DELETE /projects/{id}/agents 는 catch-all 로 맥 (패리티) */
async function apAgentCreate(pid){
  const name=(prompt('새 에이전트 이름:')||'').trim(); if(!name) return;
  const role=(prompt('역할 설명 (선택):')||'').trim();
  try{ const r=await jfetch('/projects/'+encodeURIComponent(pid)+'/agents',{method:'POST',body:JSON.stringify({name,role})});
    if(r.ok){ apBrowseProject(pid); }
    else{ const d=await r.json().catch(()=>({})); alert('생성 실패: '+(d.error||d.detail||r.status)); }
  }catch(e){ alert('오류: '+e.message); }
}
async function apAgentDelete(pid,aid,name){
  if(!confirm('"'+name+'" 에이전트를 삭제할까요?')) return;
  try{ const r=await jfetch('/projects/'+encodeURIComponent(pid)+'/agents/'+encodeURIComponent(aid),{method:'DELETE'});
    if(r.ok){ apBrowseProject(pid); }
    else{ const d=await r.json().catch(()=>({})); alert('삭제 실패: '+(d.error||d.detail||r.status)); }
  }catch(e){ alert('오류: '+e.message); }
}
/* ①-c 스위치 목록 (+ 생성/삭제 — 맥 패리티) */
function apBrowseSwitches(){
  apShowBrowse();
  document.getElementById('ap-bhead').style.display='flex';
  document.getElementById('apBrowseTitle').textContent='스위치';
  const box=document.getElementById('apBrowse');
  let h='<button class="ap-newbtn" onclick="apSwitchForm()">＋ 스위치 만들기</button>';
  if(!apSwitches.length){ h+='<p class="muted" style="padding:24px;text-align:center">스위치가 없습니다</p>'; }
  else { h+='<h3>스위치 '+apSwitches.length+'</h3>'+apSwitches.map(s=>
    '<div class="ap-card"><span class="ic">⚡</span><span class="tx"><span class="nm">'+esc(s.name)+'</span><span class="ds">'+esc((s.prompt||s.command||'').substring(0,50))+'</span></span>'+
    '<button class="btn2" onclick="apRunSwitch(\\''+esc(s.id)+'\\',this)">실행</button>'+
    '<button class="btn2 danger" onclick="apSwitchDelete(\\''+esc(s.id)+'\\',\\''+esc(s.name)+'\\')">🗑</button></div>'
  ).join(''); }
  box.innerHTML=h;
}
/* 스위치 생성 폼 (이름+명령+프로젝트→에이전트). POST /switches 는 catch-all 로 맥. */
function apSwitchForm(){
  const box=document.getElementById('apBrowse');
  const projOpts=apProjects.map(p=>'<option value="'+esc(p.id)+'">'+esc(p.name)+'</option>').join('');
  box.innerHTML='<h3>새 스위치</h3><div class="ap-form">'+
    '<label>이름</label><input id="swName" placeholder="예: 아침 뉴스 브리핑">'+
    '<label>명령 (프롬프트)</label><textarea id="swCmd" rows="3" placeholder="이 스위치가 실행할 지시"></textarea>'+
    '<label>프로젝트</label><select id="swProj" onchange="apSwitchLoadAgents()">'+projOpts+'</select>'+
    '<label>에이전트</label><select id="swAgent"><option>로딩…</option></select>'+
    '<div class="ap-form-row"><button class="btn2" onclick="apBrowseSwitches()">취소</button>'+
    '<button class="go" onclick="apSwitchCreate()">만들기</button></div></div>';
  apSwitchLoadAgents();
}
async function apSwitchLoadAgents(){
  const ps=document.getElementById('swProj'); if(!ps) return;
  const sel=document.getElementById('swAgent'); sel.innerHTML='<option>로딩…</option>';
  try{ const r=await jfetch('/projects/'+encodeURIComponent(ps.value)+'/agents'); const d=await r.json();
    sel.innerHTML=(d.agents||[]).map(a=>'<option value="'+esc(a.name)+'">'+esc(a.name)+'</option>').join('')||'<option value="">(에이전트 없음)</option>';
  }catch(e){ sel.innerHTML='<option value="">(로드 실패)</option>'; }
}
async function apSwitchCreate(){
  const name=(document.getElementById('swName').value||'').trim();
  const command=(document.getElementById('swCmd').value||'').trim();
  const projectId=document.getElementById('swProj').value;
  const agentName=document.getElementById('swAgent').value;
  if(!name||!command){ alert('이름과 명령을 입력하세요'); return; }
  try{
    const r=await jfetch('/switches',{method:'POST',body:JSON.stringify({name,command,config:{projectId,agentName},icon:'⚡'})});
    if(r.ok){ await apLoadSwitches(); apBrowseSwitches(); }
    else{ const d=await r.json().catch(()=>({})); alert('생성 실패: '+(d.error||d.detail||r.status)); }
  }catch(e){ alert('오류: '+e.message); }
}
async function apSwitchDelete(id,name){
  if(!confirm('"'+name+'" 스위치를 삭제할까요?')) return;
  try{
    const r=await jfetch('/switches/'+encodeURIComponent(id),{method:'DELETE'});
    if(r.ok){ await apLoadSwitches(); apBrowseSwitches(); }
    else{ const d=await r.json().catch(()=>({})); alert('삭제 실패: '+(d.error||d.detail||r.status)); }
  }catch(e){ alert('오류: '+e.message); }
}
/* ①-d 스케줄 목록 (반복 트리거 보기·삭제 — self:trigger op:list/delete via /ibl/execute).
   trigger_engine 은 폰 로컬 번들이라 이 자아의 스케줄(대화처럼 자아별 사적)을 보여준다. */
function apScheduleWhen(cfg){
  cfg=cfg||{};
  if(cfg.interval_minutes) return cfg.interval_minutes+'분마다';
  const rep=cfg.repeat||cfg.frequency||''; const time=cfg.time||'';
  if(rep==='daily') return '매일 '+time;
  if(rep==='weekly') return '매주 '+time;
  if(rep) return rep+' '+time;
  if(time) return time;
  try{ return JSON.stringify(cfg); }catch(e){ return '예약'; }
}
async function apBrowseSchedules(){
  apShowBrowse();
  document.getElementById('ap-bhead').style.display='flex';
  document.getElementById('apBrowseTitle').textContent='스케줄';
  const box=document.getElementById('apBrowse');
  box.innerHTML='<p class="muted" style="padding:20px;text-align:center">불러오는 중…</p>';
  try{
    const r=await jfetch('/ibl/execute',{method:'POST',body:JSON.stringify({code:'[self:trigger]{op: "list", type: "schedule"}'})});
    const d=await r.json(); const trigs=d.triggers||[];
    if(!trigs.length){ box.innerHTML='<p class="muted" style="padding:24px;text-align:center;line-height:1.7">반복 스케줄이 없습니다.<br><span style="font-size:13px">시스템 AI에게 "매일 아침 9시에 뉴스 알려줘"처럼 말해 만들 수 있어요.</span></p>'; return; }
    box.innerHTML='<h3>반복 스케줄 '+trigs.length+'</h3>'+trigs.map(t=>{
      const en=t.enabled!==false;
      return '<div class="ap-card"><span class="ic">'+(en?'⏰':'⏸️')+'</span>'+
        '<span class="tx"><span class="nm">'+esc(t.name||t.id)+'</span><span class="ds">'+esc(apScheduleWhen(t.config))+' · '+esc((t.pipeline||'').substring(0,38))+'</span></span>'+
        '<button class="btn2 danger" onclick="apScheduleDelete(\\''+esc(t.id)+'\\',\\''+esc(t.name||t.id)+'\\')">🗑</button></div>';
    }).join('');
  }catch(e){ box.innerHTML='<p class="muted" style="padding:24px;text-align:center">불러오기 실패: '+esc(e.message)+'</p>'; }
}
async function apScheduleDelete(id,name){
  if(!confirm('"'+name+'" 스케줄을 삭제할까요?')) return;
  try{
    const r=await jfetch('/ibl/execute',{method:'POST',body:JSON.stringify({code:'[self:trigger]{op: "delete", id: "'+id+'"}'})});
    if(r.ok){ apBrowseSchedules(); } else { const d=await r.json().catch(()=>({})); alert('삭제 실패: '+(d.error||d.detail||r.status)); }
  }catch(e){ alert('오류: '+e.message); }
}
/* ② 대상 확정 → 대화/결과 (전체 폭) */
function apPickSystem(){
  apChat={ type:'system', projectId:null, agentId:null, agentName:null };
  apOpenChat('🤖 시스템 AI','IndieBiz OS 전체를 관리합니다');
}
function apPickAgent(i){
  const a=apAgents[i], p=apAgProject; if(!a||!p) return;
  apChat={ type:'agent', projectId:p.id, agentId:a.id, agentName:a.name };
  apOpenChat(p.name+' · '+a.name, (a.role||'').substring(0,80));
}
function apOpenChat(title,sub){
  document.getElementById('apTitle').textContent=title;
  document.getElementById('apSub').textContent=sub||'';
  document.getElementById('apMsgs').innerHTML='<div class="empty">메시지를 입력해 시작하세요.</div>';
  apShowChat();
  apLoadHistory();  // 시스템 AI·에이전트 모두 과거 대화 자동 로드(연속성)
  setTimeout(()=>{ try{ document.getElementById('apInput').focus(); }catch(e){} },50);
}
/* 과거 대화 로드 — 채팅 진입 시 이전 대화를 버블로 표시.
   시스템 AI=/system-ai/conversations / 에이전트=/conversations/{pid}/{aid}/messages (맥/폰 공통) */
async function apLoadHistory(){
  try{
    let convs=[];
    if(apChat.type==='system'){
      const r=await jfetch('/system-ai/conversations?limit=40'); if(!r.ok) return;
      convs=((await r.json()).conversations||[]).map(m=>({role:(m.role==='user')?'user':'assistant', content:m.content||''}));
    }else if(apChat.type==='agent'){
      const r=await jfetch('/conversations/'+encodeURIComponent(apChat.projectId)+'/'+encodeURIComponent(apChat.agentId)+'/messages?limit=40');
      if(!r.ok) return;
      const msgs=((await r.json()).messages||[]).slice().reverse();  // DESC → 시간순
      convs=msgs.map(m=>({role:(m.is_agent===true)?'assistant':'user', content:m.content||''}));
    }else return;
    if(!convs.length) return;  // 이력 없으면 안내문 유지
    const c=document.getElementById('apMsgs'); c.innerHTML='';
    convs.forEach(m=>{ apAddMsg(m.role, m.content); });
    const sep=document.createElement('div'); sep.className='ap-hist-sep'; sep.textContent='― 여기부터 새 대화 ―';
    c.appendChild(sep); c.scrollTop=c.scrollHeight;
  }catch(e){}
}
function apExitChat(){ apBrowseRoot(); }
async function apRunSwitch(id,btn){
  btn.disabled=true; btn.textContent='실행 중...';
  try{ const r=await jfetch('/switches/'+encodeURIComponent(id)+'/execute',{method:'POST'}); alert(r.ok?'스위치를 실행했습니다':'실행 실패'); }
  catch(e){ alert('오류: '+e.message); }
  finally{ btn.disabled=false; btn.textContent='실행'; }
}
function apAddMsg(role,text){
  const c=document.getElementById('apMsgs');
  const ph=c.querySelector('.empty'); if(ph) ph.remove();
  const el=document.createElement('div'); el.className='msg '+role;
  el.innerHTML='<div class="av">'+(role==='user'?'🧑':'🤖')+'</div><div class="bub">'+esc(text)+'</div>';
  c.appendChild(el); c.scrollTop=c.scrollHeight;
}
function apKey(e){ if(e.key==='Enter'&&!e.shiftKey){ e.preventDefault(); apSend(); } }
/* 어시스턴트(에이전트/시스템AI 발신) 메시지를 {id,content} 배열(시간순)로 — 폴링용.
   시스템 AI=/system-ai/conversations(role==assistant), 에이전트=/conversations/.../messages(from==agent).
   id 를 마커로 쓰는 이유: limit 윈도가 슬라이딩하면 개수 비교는 신규 메시지를 놓칠 수 있다. */
async function apAssistantMsgs(){
  if(apChat.type==='system'){
    const r=await jfetch('/system-ai/conversations?limit=40');
    if(!r.ok) return null;
    return ((await r.json()).conversations||[]).filter(m=>m.role==='assistant').map(m=>({id:m.id,content:m.content||''}));
  }else{
    const r=await jfetch('/conversations/'+encodeURIComponent(apChat.projectId)+'/'+encodeURIComponent(apChat.agentId)+'/messages?limit=40');
    if(!r.ok) return null;
    const msgs=((await r.json()).messages||[]).slice().reverse();  // DESC → 시간순
    return msgs.filter(m=>m.is_agent===true).map(m=>({id:m.id,content:m.content||''}));
  }
}
function apMaxId(arr){ let mx=0; (arr||[]).forEach(m=>{ if(m.id>mx) mx=m.id; }); return mx; }
function apSleep(ms){ return new Promise(res=>setTimeout(res,ms)); }
/* 백그라운드 명령의 답을 대화 DB 폴링으로 회수. baselineId 보다 큰 id의 어시스턴트 메시지가
   나타나면 그 내용 반환. 각 폴링은 짧은 요청이라 터널 100초 타임아웃에 안 걸린다. 최대 ~10분. */
async function apPollAssistant(baselineId,bub){
  const dots=['작업 중…','작업 중… ·','작업 중… · ·','작업 중… · · ·'];
  for(let i=0;i<200;i++){
    await apSleep(i<6?1500:3000);  // 짧은 답은 빨리, 긴 작업은 느슨하게
    if(bub) bub.textContent=dots[i%dots.length];
    let a; try{ a=await apAssistantMsgs(); }catch(e){ continue; }  // 일시 오류는 넘김
    if(a==null) continue;
    const fresh=a.filter(m=>m.id>baselineId);
    if(fresh.length) return fresh[fresh.length-1].content;
  }
  return '⏳ 아직 처리 중입니다. 잠시 후 대화를 다시 열어 확인해 주세요.';
}
async function apSend(){
  const inp=document.getElementById('apInput'); const msg=inp.value.trim(); if(!msg) return;
  apAddMsg('user',msg); inp.value='';
  const btn=document.getElementById('apSend'); btn.disabled=true;
  apAddMsg('assistant','…'); const last=document.getElementById('apMsgs').lastChild.querySelector('.bub');
  try{
    // 시스템 AI·에이전트 공통: 영상 생성처럼 수 분짜리 작업이 Cloudflare 터널 100초 타임아웃(524)에
    // 걸려 "실패"로 보이던 문제 해결 — 백그라운드로 보내고(즉시 반환) 대화 DB를 폴링해 답을 받는다.
    const baselineId=apMaxId(await apAssistantMsgs());
    let r;
    if(apChat.type==='system'){
      r=await jfetch('/system-ai/chat',{method:'POST',body:JSON.stringify({message:msg,background:true})});
    }else{
      await jfetch('/projects/'+encodeURIComponent(apChat.projectId)+'/agents/'+encodeURIComponent(apChat.agentId)+'/start',{method:'POST'});
      r=await jfetch('/projects/'+encodeURIComponent(apChat.projectId)+'/agents/'+encodeURIComponent(apChat.agentId)+'/command',{method:'POST',body:JSON.stringify({command:msg,background:true})});
    }
    if(!r.ok){ const d=await r.json().catch(()=>({})); last.textContent='['+r.status+'] '+(d.detail||'오류'); return; }
    last.textContent='작업 중…';
    last.textContent=await apPollAssistant(baselineId,last);
  }catch(e){ last.textContent='연결 오류: '+e.message; }
  finally{ btn.disabled=false; }
}

/* ================= 수동 ================= */
let mLastIntent='', mLastScore=0;
function resetManualFrom(stage){
  if(stage<=3) document.getElementById('mAfterValidate').style.display='none';
  if(stage<=4) document.getElementById('mAfterExecute').style.display='none';
}
async function mTranslate(){
  const intent=document.getElementById('mIntent').value.trim(); if(!intent) return;
  mLastIntent=intent;
  const btn=document.getElementById('mTransBtn'); btn.disabled=true; btn.textContent='…';
  resetManualFrom(2); document.getElementById('mAfterTranslate').style.display='none';
  try{
    const r=await jfetch('/ibl/translate',{method:'POST',body:JSON.stringify({intent})});
    const d=await r.json();
    document.getElementById('mCode').value=d.ibl_code||d.raw||'';
    document.getElementById('mRefs').textContent=d.references||'(참고 용례 없음)';
    document.getElementById('mAfterTranslate').style.display='block';
  }catch(e){ alert('번역 실패: '+e.message); }
  finally{ btn.disabled=false; btn.textContent='번역'; }
}
function toggleRefs(){ const b=document.getElementById('mRefs'); b.style.display=b.style.display==='block'?'none':'block'; }
async function mValidate(){
  const code=document.getElementById('mCode').value.trim(); if(!code) return;
  const btn=document.getElementById('mValBtn'); btn.disabled=true; btn.textContent='검수 중…';
  resetManualFrom(4);
  try{
    const r=await jfetch('/ibl/validate',{method:'POST',body:JSON.stringify({code})});
    const d=await r.json();
    const box=document.getElementById('mSteps');
    if(!d.valid){
      box.innerHTML='<div class="eff write"><div class="h">⚠ 구문 오류</div><div class="e">'+esc(d.syntax_error||'알 수 없는 오류')+'</div></div>';
      document.getElementById('mSideWarn').innerHTML='';
      document.getElementById('mExecBtn').disabled=true;
      document.getElementById('mAfterValidate').style.display='block';
      return;
    }
    const steps=d.steps||[];
    box.innerHTML=steps.map(s=>{
      const sf=s.safety||'unknown';
      return '<div class="eff '+sf+'"><div class="h"><span class="pill s-'+sf+'">'+sf+'</span>['+esc(s.node)+':'+esc(s.action)+']</div>'+
        '<div class="e">'+esc(s.effect||'(설명 없음)')+'</div></div>';
    }).join('');
    if(d.has_side_effect){
      document.getElementById('mSideWarn').innerHTML=
        '<label class="warnbox"><input type="checkbox" id="mConfirm" onchange="document.getElementById(\\'mExecBtn\\').disabled=!this.checked"><span><b>부작용(쓰기/외부 전송)이 있는 액션</b>입니다. 실행하면 되돌릴 수 없을 수 있습니다. 확인 후 체크하세요.</span></label>';
      document.getElementById('mExecBtn').disabled=true;
    }else{
      document.getElementById('mSideWarn').innerHTML='';
      document.getElementById('mExecBtn').disabled=false;
    }
    document.getElementById('mAfterValidate').style.display='block';
  }catch(e){ alert('검수 실패: '+e.message); }
  finally{ btn.disabled=false; btn.textContent='검수 (dry-run)'; }
}
async function mExecute(){
  const code=document.getElementById('mCode').value.trim(); if(!code) return;
  const btn=document.getElementById('mExecBtn'); btn.disabled=true; btn.textContent='실행 중…';
  try{
    const r=await jfetch('/ibl/execute',{method:'POST',body:JSON.stringify({code,project_id:'수동모드',project_path:'.'})});
    const d=await r.json();
    document.getElementById('mResult').textContent=JSON.stringify(d,null,2);
    document.getElementById('mDistillMsg').textContent='';
    document.getElementById('mDistillBtn').disabled=false;
    document.getElementById('mAfterExecute').style.display='block';
    document.getElementById('mAfterExecute').scrollIntoView({behavior:'smooth',block:'nearest'});
  }catch(e){ alert('실행 실패: '+e.message); }
  finally{ btn.disabled=false; btn.textContent='실행'; }
}
async function mDistill(){
  const code=document.getElementById('mCode').value.trim();
  const btn=document.getElementById('mDistillBtn'); btn.disabled=true;
  try{
    const r=await jfetch('/ibl/distill',{method:'POST',body:JSON.stringify({intent:mLastIntent,code,top_score:mLastScore})});
    const d=await r.json();
    document.getElementById('mDistillMsg').textContent=d.distilled?'✓ 해마에 학습되었습니다':('학습 안 함'+(d.reason?' — '+d.reason:''));
  }catch(e){ document.getElementById('mDistillMsg').textContent='학습 실패: '+e.message; btn.disabled=false; }
}
/* 둘러보기 팔레트 */
let paletteLoaded=false;
function closeAbout(){ const a=document.getElementById('mAbout'); if(a) a.style.display='none'; const b=document.getElementById('btnAbout'); if(b) b.classList.remove('on'); }
function closePalette(){ const p=document.getElementById('palette'); if(p) p.style.display='none'; const b=document.getElementById('btnDict'); if(b) b.classList.remove('on'); }
async function togglePalette(){
  const p=document.getElementById('palette');
  const open = p.style.display==='none';
  closeAbout();
  if(open){ p.style.display='block'; document.getElementById('btnDict').classList.add('on'); if(!paletteLoaded) await loadPalette(); }
  else closePalette();
}
function toggleAbout(){
  const a=document.getElementById('mAbout');
  const open = a.style.display==='none';
  closePalette();
  a.style.display = open?'block':'none';
  document.getElementById('btnAbout').classList.toggle('on', open);
}
async function loadPalette(){
  const p=document.getElementById('palette'); p.innerHTML='<div class="center"><div class="spin"></div></div>';
  try{
    const r=await jfetch('/ibl/actions/catalog'); const d=await r.json();
    const nodes=d.nodes||{}; let html='<input class="field" placeholder="액션 검색..." oninput="filterPalette(this.value)" style="margin-bottom:10px">';
    html+='<div id="palette-list">';
    for(const node in nodes){
      const acts=nodes[node].actions||{};
      html+='<div class="cat-node" data-node="'+esc(node)+'"><h4>'+esc(node)+'</h4>';
      for(const a in acts){
        const seed='['+node+':'+a+']{}';
        html+='<span class="act-chip" data-key="'+esc((node+' '+a).toLowerCase())+'" onclick="seedAction(\\''+esc(seed)+'\\')">'+esc(a)+'</span>';
      }
      html+='</div>';
    }
    html+='</div>'; p.innerHTML=html; paletteLoaded=true;
  }catch(e){ p.innerHTML='<p class="muted">카탈로그 로드 실패</p>'; }
}
function filterPalette(q){
  q=(q||'').toLowerCase().trim();
  document.querySelectorAll('#palette-list .act-chip').forEach(c=>{
    c.style.display=(!q||c.dataset.key.indexOf(q)>=0)?'inline-block':'none';
  });
}
function seedAction(seed){
  document.getElementById('mCode').value=seed;
  document.getElementById('mAfterTranslate').style.display='block';
  document.getElementById('mCode').focus();
  document.getElementById('palette').scrollIntoView({behavior:'smooth',block:'nearest'});
}

/* ================= 앱 (제네릭 렌더러 — /launcher/instruments 매니페스트 해석) ================= */
let appHomeRendered=false;
let INSTRUMENTS=[];
let CUR={inst:null, mode:null, optCache:{}};
let VIEW_CTX=null; /* 마지막 렌더의 {view,data} — 행 버튼/드릴 디스패치용 */
let SPLIT=false, LIST=null; /* master-detail: SPLIT=2분할 모드, LIST={view,data}=리스트 컨텍스트 */
const CUSTOM_RENDERERS={}; /* escape hatch: manifest renderer:"custom:이름" → 전용 렌더 함수 (지도·플레이어 등) */

async function loadInstruments(force){
  if(INSTRUMENTS.length && !force) return;  /* force=true 면 매니페스트 재fetch (계기/어휘 변경 반영) */
  try{ const r=await jfetch('/launcher/instruments'); if(r.ok){ const d=await r.json(); INSTRUMENTS=d.instruments||[]; } }catch(e){}
}
async function renderAppHome(force){
  const home=document.getElementById('appHome');
  home.innerHTML='<div class="center"><div class="spin"></div></div>';
  await loadInstruments(force);
  if(!INSTRUMENTS.length){ home.innerHTML='<p class="muted">계기 매니페스트를 불러오지 못했습니다</p>'; return; }
  home.innerHTML=
    '<p class="muted" style="margin-bottom:12px">직접 조작 — 아이콘을 눌러 바로 실행 (0 토큰)</p>'+
    '<div class="grid">'+INSTRUMENTS.map((inst,ix)=>
      '<button class="tile" onclick="openInstrument('+ix+')"><span class="em">'+esc(inst.icon||'🔧')+'</span><span class="nm">'+esc(inst.name)+'</span></button>'
    ).join('')+'</div>';
  appHomeRendered=true;
}
function appBackHome(){
  document.getElementById('appInst').style.display='none';
  document.getElementById('appHome').style.display='block';
}
function openInstrument(ix){
  const inst=INSTRUMENTS[ix]; if(!inst) return;
  CUR={inst:inst, mode:null, optCache:{}}; VIEW_CTX=null;
  // 홈에서 계기로 들어갈 때만 history 항목 push(뒤로가기로 그리드 복귀). 중복 push 방지.
  const _fromHome=document.getElementById('appHome').style.display!=='none';
  document.getElementById('appHome').style.display='none';
  const box=document.getElementById('appInst'); box.style.display='block';
  if(_fromHome){ try{ history.pushState({inst:1}, ''); }catch(e){} }
  let h='<div class="inst-head"><button class="back" onclick="history.back()">←</button><h2>'+esc(inst.icon||'')+' '+esc(inst.name)+'</h2></div>';
  if(inst.renderer&&inst.renderer.indexOf('custom:')===0){
    box.innerHTML=h+'<div id="modeBody"></div>';
    const fn=CUSTOM_RENDERERS[inst.renderer.slice(7)];
    if(fn) fn(inst,document.getElementById('modeBody'));
    else document.getElementById('modeBody').innerHTML='<p class="muted">렌더러 없음: '+esc(inst.renderer)+'</p>';
    return;
  }
  if(inst.modes && inst.modes.length>1){  // 모드 1개면 탭 바 불필요(공간 절약) — setMode(0)이 가드(if(t))라 안전
    h+='<div class="tabs">'+inst.modes.map((m,i)=>'<button class="tab" id="modeTab'+i+'" onclick="setMode('+i+')">'+esc(m.name)+'</button>').join('')+'</div>';
  }
  h+='<div id="modeBody"></div>';
  box.innerHTML=h;
  setMode(0);
}
function setMode(i){
  const inst=CUR.inst; const modes=inst.modes||[inst]; const mode=modes[i];
  CUR.mode=mode; VIEW_CTX=null; SPLIT=false; LIST=null;
  if(inst.modes) modes.forEach((m,j)=>{ const t=document.getElementById('modeTab'+j); if(t)t.classList.toggle('on',j===i); });
  CUR.optCache={};
  CUR.catFilter=null;  // 동적 필터(from_field) 선택값 — 모드 진입 시 초기화
  CUR.filterVal=(mode.filter&&mode.filter.items)?((mode.filter.items.find(x=>x.default)||mode.filter.items[0]||{}).value):null;
  let h='';
  if(mode.note) h+='<div class="note">'+esc(mode.note)+'</div>';
  const inputs=mode.inputs||[];
  if(inputs.length){
    h+='<div class="row" style="flex-wrap:wrap">'+inputs.map(inp=>{
      if(inp.type==='select')
        return '<select class="field" id="in_'+esc(inp.key)+'" style="flex:0 1 130px" onchange="selChanged(\\''+esc(inp.key)+'\\')"><option value="">'+esc(inp.label||'전체')+'</option></select>';
      return '<input class="field" style="min-width:0" id="in_'+esc(inp.key)+'" value="'+esc(loadInpVal(inst.id,mode.id,inp.key,inp.default))+'" placeholder="'+esc(inp.placeholder||'')+'" onchange="saveInpVals()" onkeydown="if(event.key===\\'Enter\\')runMode()">';
    }).join('')+'<button class="go" onclick="runMode()">조회</button></div>';
  }
  inputs.forEach(inp=>{
    if(inp.chips&&inp.chips.length)
      h+='<div class="chips" style="margin-top:10px">'+inp.chips.map(c=>
        '<span class="chip" onclick="chipRun(\\''+esc(inp.key)+'\\',\\''+esc(c)+'\\')">'+esc(c)+'</span>').join('')+'</div>';
  });
  // 기간 토글(차트 범위) — 클릭 즉시 그 기간으로 재조회
  if(mode.filter&&mode.filter.items){
    h+='<div class="filters" style="margin-top:10px">'+mode.filter.items.map(x=>
      '<button class="fchip'+(String(x.value)===String(CUR.filterVal)?' on':'')+'" data-v="'+esc(String(x.value))+'" onclick="setFilter(\\''+esc(String(x.value))+'\\')">'+esc(x.label)+'</button>').join('')+'</div>';
  }
  const btns=mode.buttons||[];
  if(btns.length)
    h+='<div class="btnrow" style="margin-top:10px">'+btns.map((b,bi)=>
      '<button class="btn2" onclick="fireButton('+bi+',this)">'+esc(b.label)+'</button>').join('')+'</div>';
  h+='<div id="instOut"></div>';
  document.getElementById('modeBody').innerHTML=h;
  // select 채우기는 선언 순서대로 — 정적 옵션(동기)이 먼저 값을 잡아야 종속 옵션이 그 값을 읽는다
  (async()=>{ for(const inp of inputs){ if(inp.type==='select') await fillOptions(inp); } if(mode.auto_run) runMode(); })();
}
/* options_action 의 $key 를 형제 입력값으로 치환 — 비어 있으면 missing 표시(종속 대기) */
function resolveOptionsAction(template){
  let missing=false;
  const code=String(template).replace(/\\$(\\w+)/g,(m,k)=>{ const el=document.getElementById('in_'+k); const v=el?String(el.value):''; if(!v) missing=true; return v.replace(/"/g,''); });
  return {code, missing};
}
/* 배열은 option_value/option_label로, 딕셔너리({이름:코드})는 entries로 정규화 → [{value,label}] */
function normalizeOptions(raw,inp){
  if(Array.isArray(raw)) return raw.map(o=>({value:o[inp.option_value||'value'], label:o[inp.option_label||'label']}));
  if(raw&&typeof raw==='object') return Object.entries(raw).map(([k,v])=>({value:v, label:k}));
  return [];
}
function setOptions(sel,opts,def){
  while(sel.options.length>1) sel.remove(1);  /* placeholder 1개 유지 */
  opts.forEach(o=>{ const el=document.createElement('option'); el.value=o.value; el.textContent=o.label; sel.appendChild(el); });
  if(def!=null && opts.some(o=>String(o.value)===String(def))) sel.value=def;
}
async function fillOptions(inp){
  const sel=document.getElementById('in_'+inp.key); if(!sel) return;
  if(Array.isArray(inp.options)){ setOptions(sel, inp.options.map(o=>({value:o.value,label:o.label})), inp.default); return; }
  if(!inp.options_action) return;
  const {code,missing}=resolveOptionsAction(inp.options_action);
  if(missing){ setOptions(sel, [], null); return; }   /* 종속 부모 미선택 — 비워두고 대기 */
  let opts=CUR.optCache[code];
  if(!opts){ try{ const d=await ibl(code); opts=normalizeOptions(jget(d,inp.options_from),inp); CUR.optCache[code]=opts; }catch(e){ opts=[]; } }
  if(document.getElementById('in_'+inp.key)!==sel) return;
  setOptions(sel, opts, inp.default);
}
/* select 변경 시, 그 키에 의존하는 종속 select 들을 비우고 다시 채운다 (cascade) */
function selChanged(key){
  const mode=CUR.mode; if(!mode) return;
  (mode.inputs||[]).forEach(inp=>{
    if(inp.type==='select' && inp.options_action && new RegExp('\\\\$'+key+'\\\\b').test(inp.options_action)) fillOptions(inp);
  });
}
function chipRun(key,val){ const el=document.getElementById('in_'+key); if(el) el.value=val; runMode(); }
/* 폰 라디오: 백엔드가 play_in_client+stream_url 반환 → WebView 가 직접 재생(소리=폰 스피커).
   한국 방송=HLS(.m3u8)라 hls.js, ICY/mp3 등은 네이티브 <audio>. */
let _radioHls=null;
function _radioAudioEl(){ let a=document.getElementById('radioAudio'); if(!a){ a=document.createElement('audio'); a.id='radioAudio'; a.autoplay=true; a.addEventListener('ended',_npHide); document.body.appendChild(a); } return a; }
/* 전역 미니플레이어: 클라이언트 오디오(라디오·유튜브뮤직)는 #radioAudio 전역 엘리먼트라
   계기를 벗어나도 계속 재생된다. 재생 중이면 어디서든 보이는 정지 바를 띄워(클라이언트 관심사=
   IBL 왕복 없이 stopRadioStream 직접) "멈출 방법 없음" 해소. 곡이 끝나면(ended) 자동 숨김. */
function _npBar(){
  let b=document.getElementById('nowPlaying');
  if(!b){
    b=document.createElement('div'); b.id='nowPlaying';
    b.style.cssText='position:fixed;left:0;right:0;bottom:0;z-index:9998;display:none;align-items:center;gap:10px;padding:10px 14px;background:#1a1a2e;border-top:1px solid #333;box-shadow:0 -2px 10px rgba(0,0,0,.5)';
    b.innerHTML='<span style="font-size:18px">\\u266a</span><span id="npTitle" style="flex:1;color:#eee;font-size:14px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap"></span><button onclick="stopRadioStream()" style="background:#e94560;color:#fff;border:none;border-radius:18px;padding:8px 18px;font-size:15px;font-weight:bold">\\u25a0 \\uc815\\uc9c0</button>';
    document.body.appendChild(b);
  }
  return b;
}
function _npShow(label){ const b=_npBar(); const t=document.getElementById('npTitle'); if(t) t.textContent=label||'\\uc7ac\\uc0dd \\uc911'; b.style.display='flex'; }
function _npHide(){ const b=document.getElementById('nowPlaying'); if(b) b.style.display='none'; }
function playRadioStream(url,vol,label){
  const a=_radioAudioEl();
  if(_radioHls){ try{_radioHls.destroy();}catch(e){} _radioHls=null; }
  if(typeof vol==='number') a.volume=Math.max(0,Math.min(1,vol/100));
  if(/\\.m3u8/i.test(url) && window.Hls && Hls.isSupported()){
    _radioHls=new Hls(); _radioHls.loadSource(url); _radioHls.attachMedia(a);
    _radioHls.on(Hls.Events.MANIFEST_PARSED,()=>a.play().catch(()=>{}));
  } else { a.src=url; a.play().catch(()=>{}); }
  _npShow(label);
}
function stopRadioStream(){
  if(_radioHls){ try{_radioHls.destroy();}catch(e){} _radioHls=null; }
  const a=document.getElementById('radioAudio'); if(a){ a.pause(); a.removeAttribute('src'); a.load(); }
  _npHide();
}
/* CCTV 영상(item2): 지도 마커 클릭 → 전체화면 <video> 오버레이로 HLS 재생.
   onclick 은 URL 대신 _streamUrls 정수 인덱스를 넘겨 따옴표 이스케이프 함정을 원천 회피. */
var _streamUrls=[], _cctvHls=null;
function playStream(idx){
  const url=_streamUrls[idx]; if(!url) return;
  let ov=document.getElementById('streamOverlay');
  if(!ov){
    ov=document.createElement('div'); ov.id='streamOverlay';
    ov.style.cssText='position:fixed;inset:0;background:#000;z-index:9999;display:flex';
    ov.innerHTML='<button onclick="closeStream()" style="position:absolute;top:12px;right:12px;z-index:2;background:rgba(0,0,0,.6);color:#fff;border:none;border-radius:20px;padding:8px 16px;font-size:16px">✕ 닫기</button><video id="streamVideo" controls autoplay playsinline muted style="width:100%;height:100%;object-fit:contain"></video>';
    document.body.appendChild(ov);
  }
  ov.style.display='flex';
  const v=document.getElementById('streamVideo');
  if(_cctvHls){ try{_cctvHls.destroy();}catch(e){} _cctvHls=null; }
  if(/\\.m3u8/i.test(url) && window.Hls && Hls.isSupported()){
    _cctvHls=new Hls(); _cctvHls.loadSource(url); _cctvHls.attachMedia(v);
    _cctvHls.on(Hls.Events.MANIFEST_PARSED,()=>v.play().catch(()=>{}));
  } else { v.src=url; v.play().catch(()=>{}); }
}
function closeStream(){
  if(_cctvHls){ try{_cctvHls.destroy();}catch(e){} _cctvHls=null; }
  const v=document.getElementById('streamVideo'); if(v){ v.pause(); v.removeAttribute('src'); v.load(); }
  const ov=document.getElementById('streamOverlay'); if(ov) ov.style.display='none';
}
/* 사진 라이트박스(image_grid): 썸네일 클릭 → 원본 이미지/동영상을 전체화면 오버레이로.
   full URL 은 클릭된 엘리먼트의 <img src>(이미 URL 인코딩됨)에서 파생 — 썸네일→원본 엔드포인트
   치환(thumbnail→image, video-thumbnail→video)+size 파라미터 제거. 따옴표 이스케이프 무필요. */
function openMediaFromEl(el){
  const im=el.querySelector('img'); if(!im) return;
  const src=im.getAttribute('src')||''; if(!src) return;
  const isVid=src.indexOf('video-thumbnail')>=0;
  const full=src.replace('/photo/video-thumbnail','/photo/video').replace('/photo/thumbnail','/photo/image').replace(/[?&]size=\\d+/,'');
  let ov=document.getElementById('mediaOverlay');
  if(!ov){
    ov=document.createElement('div'); ov.id='mediaOverlay';
    ov.style.cssText='position:fixed;inset:0;background:rgba(0,0,0,.93);z-index:9999;display:flex;align-items:center;justify-content:center';
    ov.onclick=function(e){ if(e.target===ov||e.target.id==='mediaClose') closeMedia(); };
    ov.innerHTML='<button id="mediaClose" style="position:absolute;top:12px;right:12px;background:rgba(0,0,0,.6);color:#fff;border:none;border-radius:20px;padding:8px 16px;font-size:16px">✕ 닫기</button><div id="mediaBody" style="max-width:100%;max-height:100%;display:flex;align-items:center;justify-content:center"></div>';
    document.body.appendChild(ov);
  }
  document.getElementById('mediaBody').innerHTML = isVid
    ? '<video src="'+full+'" controls autoplay playsinline style="max-width:100%;max-height:92vh"></video>'
    : '<img src="'+full+'" style="max-width:100%;max-height:92vh;object-fit:contain">';
  ov.style.display='flex';
}
function closeMedia(){
  const b=document.getElementById('mediaBody'); if(b) b.innerHTML='';
  const ov=document.getElementById('mediaOverlay'); if(ov) ov.style.display='none';
}
async function fireButton(bi,btn){
  const b=(CUR.mode.buttons||[])[bi]; if(!b) return;
  btn.disabled=true;
  try{ const d=await ibl(b.action);
    if(d&&d.stop_in_client){ stopRadioStream(); }
    else if(d&&d.error){ alert(d.error); }
    else if(b.refresh){ runMode(); }  // 실행 후 현재 모드 재조회(토글/재생성 즉시 반영)
  }
  catch(e){ alert('실행 실패: '+e.message); }
  finally{ btn.disabled=false; }
}

/* ----- 액션 템플릿: $key=사용자 입력, {path}=데이터 행 필드 ----- */
function jget(o,path){ if(!path) return o; return String(path).split('.').reduce((a,k)=>(a==null?undefined:a[k]),o); }
function buildAction(template,values){
  let code=template.replace(/\\$(\\w+)/g,(m,k)=>{
    const v=values[k]; return v==null?'':String(v).replace(/\\\\/g,'\\\\\\\\').replace(/"/g,'\\\\"');
  });
  code=code.replace(/\\w+:\\s*"",?\\s*/g,'');  /* 빈 입력 파라미터 제거 */
  code=code.replace(/,\\s*\\}/g,'}').replace(/\\{\\s*,/g,'{');
  return code;
}
function viewList(data,from){ if(from==='.') return [data]; const a=jget(data,from); return Array.isArray(a)?a:[]; }
function rowAction(template,item){
  return template.replace(/\\{([\\w.]+)\\}/g,(m,path)=>{ const v=jget(item,path); return v==null?'':String(v).replace(/"/g,''); });
}

/* ----- 표시 템플릿: "{path|filter|...}" → 문자열 (HTML 이스케이프 포함) ----- */
function applyFilter(v,f){
  if(f==='round') return v==null?v:Math.round(Number(v));
  if(f==='num') return v==null?null:Number(v).toLocaleString();
  if(f==='abs') return v==null?v:Math.abs(Number(v));
  if(f==='arrow') return (Number(v)||0)>=0?'▲':'▼';
  if(f.indexOf('opt:')===0){ const a=f.slice(4).split(','); return (v==null||v===''||Number(v)===0)?'':(a[0]||'')+v+(a[1]||''); }
  if(f.indexOf('trunc:')===0){ const n=parseInt(f.slice(6))||40; const s=String(v==null?'':v); return s.length>n?s.slice(0,n)+'…':s; }
  return v;
}
function tpl(t,data){
  if(t==null) return '';
  return String(t).replace(/\\{([^{}]+)\\}/g,(m,expr)=>{
    const parts=expr.split('|'); let v=jget(data,parts[0].trim());
    for(let i=1;i<parts.length;i++) v=applyFilter(v,parts[i].trim());
    return v==null?'':esc(v);
  });
}

function statusGlyph(s){ return s==='sent'?'✓':s==='pending'?'⏳':s==='failed'?'⚠':''; }

/* ----- 뷰 렌더 (순수 함수: view+data → HTML 문자열) ----- */
function renderView(view,data){
  if(data&&data.error) return '<p class="muted">'+esc(data.error)+'</p>';
  if(data&&data.success===false) return '<p class="muted">'+esc(data.message||'실패')+'</p>';
  return (view||[]).map((p,vi)=>renderPrim(p,vi,data)).join('');
}
/* ----- 동적 필터(filter.from_field): 결과-필드 distinct 칩 + 클라이언트 측 거르기(재조회 없음) ----- */
function dynFilterOf(mode){ return (mode&&mode.filter&&mode.filter.from_field)?mode.filter:null; }
function applyCatFilter(mode,data){  /* CUR.catFilter 적용된 데이터(map 마커·card_list 동시 거름) */
  const f=dynFilterOf(mode); if(!f||CUR.catFilter==null||!data) return data;
  const from=f.from||'items';
  const arr=viewList(data,from).filter(it=>String(jget(it,f.from_field))===String(CUR.catFilter));
  const nd={}; for(const k in data) nd[k]=data[k]; nd[from]=arr; return nd;
}
function renderDynFilter(mode,data){
  const f=dynFilterOf(mode); if(!f||!data) return '';
  const from=f.from||'items'; const seen={}; const cats=[];
  viewList(data,from).forEach(it=>{ const v=jget(it,f.from_field); if(v&&!seen[v]){ seen[v]=1; cats.push(String(v)); } });
  if(!cats.length) return '';
  // 칩 값은 data-c 속성에 담고(esc), 클릭은 그 속성을 읽는다 — onclick 인라인 따옴표 이스케이프 회피.
  let h='<div class="filters" style="margin-bottom:10px">';
  h+='<button class="fchip'+(CUR.catFilter==null?' on':'')+'" onclick="setCatFilter(null)">전체</button>';
  h+=cats.slice(0,12).map(c=>'<button class="fchip'+(String(CUR.catFilter)===String(c)?' on':'')
    +'" data-c="'+esc(c)+'" onclick="setCatFilter(this.getAttribute(\\'data-c\\'))">'+esc(c)+'</button>').join('');
  return h+'</div>';
}
/* 비분할 모드 본문 = 동적필터 칩 + (필터 적용된) 뷰 + 작성바. runMode/mapViewEvent/setCatFilter 공유. */
function renderModeBody(mode,data){
  return renderDynFilter(mode,data)+renderView(mode.view,applyCatFilter(mode,data))+renderComposeBar(mode.compose);
}
function setCatFilter(v){
  CUR.catFilter=v;
  if(!VIEW_CTX||VIEW_CTX.refresh!=='mode') return;
  // 인터랙티브 지도 viewport 보존 — 재렌더가 지도를 재생성하므로(데스크탑은 map 유지라 불필요)
  for(const k in _LMAPS){ const m=_LMAPS[k];
    try{ if(m&&m.getContainer&&document.body.contains(m.getContainer())) _mapKeepView={c:m.getCenter(),z:m.getZoom()}; }catch(e){} }
  const out=document.getElementById('instOut'); if(!out) return;
  out.innerHTML=renderModeBody(CUR.mode,VIEW_CTX.data); initMaps();
}
function trendColor(p,data){ if(!p.trend) return null; return (Number(jget(data,p.trend))||0)>=0?'var(--up)':'var(--down)'; }
function emptyMsg(p,data){
  const m=(p.empty_from?jget(data,p.empty_from):null)||p.empty||'결과가 없습니다';
  return '<p class="muted" style="margin-top:10px">'+esc(m)+'</p>';
}
/* 지도 render 프리미티브 — leaflet. innerHTML 후 initMaps()로 지연 초기화.
   봉투: route_map{origin,destination,path:[[lat,lng]],summary} | location_map{center,markers:[{name,lat,lng}]}.
   spec: {type:'map', from:'map_data'(봉투 위치), markers:'cctvs'(추가 마커, 옵션)} */
var _MAP_QUEUE={}, _mapSeq=0, _LMAPS={};
// 인터랙티브 지도(on:) — _mapProg=프로그래매틱 이동(fitBounds/setView) 가드(재조회 피드백 루프 차단),
// _mapKeepView=재조회 재렌더 너머 viewport 보존(데스크탑 didFit 가드의 원격판).
var _mapProg=false, _mapKeepView=null;
/* 뷰-이벤트(map moveend/marker_click) → 액션 재조회 후 현재 모드 view 재렌더. viewport 는 _mapKeepView 로 보존. */
async function mapViewEvent(tpl,payload){
  if(!tpl||!VIEW_CTX) return;
  const vals=Object.assign({},gatherInputs(),payload);
  let d; try{ d=await ibl(buildAction(tpl,vals)); }catch(e){ return; }
  if(!d||d.error||d.success===false) return;
  VIEW_CTX.data=d;
  const out=document.getElementById('instOut'); if(!out) return;
  // 모드 뷰면 동적필터 재적용(새 결과 → catFilter 초기화), 드릴 뷰면 그대로.
  if(VIEW_CTX.refresh==='mode'){ CUR.catFilter=null; out.innerHTML=renderModeBody(CUR.mode,d); }
  else out.innerHTML=renderView(VIEW_CTX.view,d)+renderComposeBar(VIEW_CTX.compose);
  initMaps();
}
/* 지도가 세로 스와이프를 먹어 페이지 스크롤을 막는 문제 해결:
   기본은 dragging(한 손가락 패닝) 끔 → 한 손가락 스와이프는 페이지 스크롤로 통과.
   핀치 줌(touchZoom)은 그대로(두 손가락이라 스크롤과 충돌 없음). 패닝이 필요하면 토글로 켠다. */
function toggleMapDrag(id,btn){
  const map=_LMAPS[id]; if(!map) return;
  if(map.dragging.enabled()){ map.dragging.disable(); btn.textContent='🔓 지도 이동'; btn.classList.remove('on'); }
  else { map.dragging.enable(); btn.textContent='🔒 스크롤'; btn.classList.add('on'); }
}
function initMaps(){
  if(typeof L==='undefined') return;
  // 재렌더로 DOM 에서 분리된 옛 지도 정리 — 누수 + 분리된 지도의 moveend 핸들러가 전역 가드 간섭하는 것 방지.
  for(const k in _LMAPS){ const mp=_LMAPS[k];
    try{ if(!mp||!mp.getContainer||!document.body.contains(mp.getContainer())){ if(mp&&mp.remove) mp.remove(); delete _LMAPS[k]; } }
    catch(e){ delete _LMAPS[k]; } }
  for(const id in _MAP_QUEUE){
    const el=document.getElementById(id); if(!el||el._inited) continue;
    el._inited=true; const spec=_MAP_QUEUE[id]; delete _MAP_QUEUE[id];
    try{
      const map=L.map(id,{attributionControl:false,dragging:false});  // 한 손가락 패닝 끔(페이지 스크롤 통과). 토글로 켬.
      _LMAPS[id]=map;
      L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19}).addTo(map);
      const B=[]; const md=spec.md||{};
      if(md.path&&md.path.length){
        L.polyline(md.path,{color:'#e11d48',weight:5,opacity:0.85}).addTo(map);
        md.path.forEach(ll=>B.push(ll));
        if(md.origin){ L.marker([md.origin.lat,md.origin.lng]).addTo(map).bindPopup('출발 · '+esc(md.origin.name||'')); B.push([md.origin.lat,md.origin.lng]); }
        if(md.destination){ L.marker([md.destination.lat,md.destination.lng]).addTo(map).bindPopup('도착 · '+esc(md.destination.name||'')); B.push([md.destination.lat,md.destination.lng]); }
      }
      (md.markers||[]).forEach(m=>{ if(m.lat==null||m.lng==null) return; L.marker([m.lat,m.lng]).addTo(map).bindPopup(esc(m.name||'')); B.push([m.lat,m.lng]); });
      // marker_click: IBL 템플릿(문자열·재조회) | {stream:true}(마커 url 영상 재생, IBL 없음·_mapKeepView 안 건드림) | 없음(팝업+▶영상버튼).
      const clickSpec=spec.on&&spec.on.marker_click;
      const clickStream=clickSpec&&typeof clickSpec==='object'&&clickSpec.stream;
      const clickTpl=(typeof clickSpec==='string')?clickSpec:null;
      (spec.markers||[]).forEach(m=>{ if(m.lat==null||m.lng==null) return;
        const mk=L.marker([m.lat,m.lng]).addTo(map); const nm=m.name||m.title||'마커';
        if(clickStream){
          if(m.url){ const i=_streamUrls.push(m.url)-1; mk.on('click',()=>playStream(i)); }
          else mk.bindPopup('<b>'+esc(nm)+'</b>');
        } else if(clickTpl){
          mk.on('click',()=>{ _mapKeepView={c:map.getCenter(),z:map.getZoom()};
            mapViewEvent(clickTpl,{id:String(m.id==null?'':m.id),name:String(nm),lat:String(m.lat),lng:String(m.lng),url:String(m.url==null?'':m.url)}); });
        } else {
          let btn='';
          if(m.url){ const i=_streamUrls.push(m.url)-1; btn='<br><button class="go" style="margin-top:6px;padding:4px 12px" onclick="playStream('+i+')">▶ 영상</button>'; }
          mk.bindPopup('<b>'+esc(nm)+'</b>'+btn);
        }
        B.push([m.lat,m.lng]); });
      // 인터랙티브(on:)면 viewport 보존(첫 로드만 fit)·재조회 피드백 가드. 정적이면 매번 fit(기존 동작).
      if(spec.on&&_mapKeepView){ _mapProg=true; map.setView(_mapKeepView.c,_mapKeepView.z); _mapKeepView=null; }
      else if(B.length){ if(spec.on) _mapProg=true; map.fitBounds(B,{padding:[28,28],maxZoom:15}); }
      else if(md.center&&md.center.lat!=null){ if(spec.on) _mapProg=true; map.setView([md.center.lat,md.center.lng],13); }
      else map.setView([37.4979,127.0276],11);
      if(spec.on){
        const moveTpl=spec.on.moveend||spec.on.center_drag;
        if(moveTpl) map.on('moveend',()=>{ if(_mapProg){ _mapProg=false; return; } // 프로그래매틱 이동 무시
          if(map._reqT) clearTimeout(map._reqT);
          map._reqT=setTimeout(()=>{ const c=map.getCenter(); _mapKeepView={c:c,z:map.getZoom()};
            const r=Math.round(map.distance(c,map.getBounds().getNorthEast()));
            mapViewEvent(moveTpl,{lat:c.lat.toFixed(6),lng:c.lng.toFixed(6),radius:String(r)}); },600); });
        setTimeout(()=>{ _mapProg=false; },500); // fit 이 moveend 안 내도 가드 해제(백업)
      }
      setTimeout(()=>map.invalidateSize(),60);
    }catch(e){ el.innerHTML='<p class="muted">지도 로드 실패</p>'; }
  }
}
/* 달력 render 프리미티브 — 월 그리드. 날짜 있는 이벤트만 표시(날 없는 반복 스케줄 제외).
   날짜 탭→그날 일정+삭제+추가(date 자동 주입). 한 번에 하나라 전역 _calCur 로 단순화
   (onclick=정수 인덱스만→따옴표 함정 회피). 월/선택일은 _calState 로 add/delete 새로고침 너머 보존. */
var _calCur=null, _calState={y:null,m:null,sel:null};
function _pad2(n){ return (n<10?'0':'')+n; }
function _calSetup(p,data){
  const evs=viewList(data,p.from||'events').filter(e=>e&&e.date);  // 날짜 없는 이벤트 제외
  const now=new Date();
  _calCur={prim:p, events:evs,
    y:(_calState.y!=null?_calState.y:now.getFullYear()),
    m:(_calState.m!=null?_calState.m:now.getMonth()),
    sel:_calState.sel};
}
function _calDraw(){
  const host=document.getElementById('calHost'); if(!host||!_calCur) return;
  const c=_calCur, y=c.y, m=c.m, byDay={};
  c.events.forEach(e=>{ const ps=String(e.date).split('-'); if(ps.length<3) return;
    const ey=+ps[0], em=+ps[1]-1, ed=+ps[2], rep=e.repeat||'none';
    const show=(rep==='yearly')?(em===m):(ey===y&&em===m);  // 생일·기념일은 월-일만, 일회성은 연-월
    if(show){ (byDay[ed]=byDay[ed]||[]).push(e); } });
  const first=new Date(y,m,1).getDay(), days=new Date(y,m+1,0).getDate();
  let h='<div class="card"><div class="row" style="align-items:center;justify-content:space-between">'
    +'<button class="iconbtn" onclick="_calNav(-1)">◀</button><b>'+y+'년 '+(m+1)+'월</b>'
    +'<button class="iconbtn" onclick="_calNav(1)">▶</button></div><div class="calgrid">';
  ['일','월','화','수','목','금','토'].forEach(w=>{ h+='<div class="calwd">'+w+'</div>'; });
  for(let i=0;i<first;i++) h+='<div></div>';
  for(let d=1;d<=days;d++){ const hs=byDay[d]?' calhas':'', sl=(c.sel===d)?' calsel':'';
    h+='<div class="calday'+hs+sl+'" onclick="_calPick('+d+')">'+d+(byDay[d]?'<span class="caldot"></span>':'')+'</div>'; }
  h+='</div>';
  if(c.sel){ const list=byDay[c.sel]||[]; c._dayList=list;
    h+='<div class="calpanel"><div class="step-label">'+y+'-'+_pad2(m+1)+'-'+_pad2(c.sel)+'</div>';
    if(list.length) list.forEach((e,i)=>{ h+='<div class="kv"><span class="k">'+esc(e.title||'')+'</span>'
      +(c.prim.delete_action?'<button class="linkbtn" onclick="_calDel('+i+')">삭제</button>':'')+'</div>'; });
    else h+='<p class="muted">일정 없음</p>';
    if(c.prim.add) h+='<div class="row" style="margin-top:8px"><input class="field" style="min-width:0" id="calAddTitle" placeholder="일정 제목"><button class="go" onclick="_calAdd()">추가</button></div>';
    h+='</div>'; }
  h+='</div>'; host.innerHTML=h;
}
function _calNav(delta){ if(!_calCur) return; let m=_calCur.m+delta, y=_calCur.y;
  if(m<0){m=11;y--;} if(m>11){m=0;y++;} _calCur.m=m; _calCur.y=y; _calCur.sel=null;
  _calState.y=y; _calState.m=m; _calState.sel=null; _calDraw(); }
function _calPick(d){ if(!_calCur) return; _calCur.sel=(_calCur.sel===d?null:d); _calState.sel=_calCur.sel; _calDraw(); }
async function _calAdd(){ if(!_calCur||!_calCur.prim.add||!_calCur.sel) return;
  const t=document.getElementById('calAddTitle'), title=t?t.value.trim():''; if(!title){ alert('일정 제목을 입력하세요'); return; }
  const date=_calCur.y+'-'+_pad2(_calCur.m+1)+'-'+_pad2(_calCur.sel);
  try{ await dispatchAction(_calCur.prim.add.action,{title:title,date:date}); }catch(e){ alert('추가 실패: '+e.message); } }
async function _calDel(i){ if(!_calCur||!_calCur._dayList) return; const item=_calCur._dayList[i]; if(!item) return;
  try{ await dispatchAction(_calCur.prim.delete_action,{},item); }catch(e){ alert('삭제 실패: '+e.message); } }
function renderPrim(p,vi,data){
  if(p.type==='calendar'){ _calSetup(p,data); setTimeout(_calDraw,0); return '<div id="calHost"></div>'; }
  if(p.type==='map'){
    const md=p.from?jget(data,p.from):data;
    let mk=p.markers?viewList(data,p.markers):[];
    if(p.max&&mk.length>p.max) mk=mk.slice(0,p.max);  // 마커 폭주 방지(상권 등 수천건)
    const id='lmap_'+(_mapSeq++);
    _MAP_QUEUE[id]={md:md,markers:mk,on:p.on||null};
    return '<div style="position:relative;margin-bottom:10px">'
      +'<div id="'+id+'" class="lmap" style="height:320px;border-radius:12px;overflow:hidden;background:var(--bg3)"></div>'
      +'<button class="lmaptoggle" onclick="toggleMapDrag(\\''+id+'\\',this)">🔓 지도 이동</button></div>';
  }
  if(p.type==='metric'){
    const col=trendColor(p,data);
    return '<div class="card">'+(p.label?'<div class="muted">'+tpl(p.label,data)+'</div>':'')+
      '<div class="big"'+(col?' style="color:'+col+'"':'')+'>'+tpl(p.big,data)+(p.unit?' <span style="font-size:14px">'+tpl(p.unit,data)+'</span>':'')+'</div>'+
      (p.sub?'<div'+(col?' style="color:'+col+'; font-weight:600"':' class="muted"')+'>'+tpl(p.sub,data)+'</div>':'')+'</div>';
  }
  if(p.type==='kv')
    return '<div class="card">'+(p.title?'<div class="step-label">'+esc(p.title)+'</div>':'')+
      (p.rows||[]).map(r=>'<div class="kv"><span class="k">'+tpl(r.k,data)+'</span><span>'+tpl(r.v,data)+'</span></div>').join('')+'</div>';
  if(p.type==='kv_list'){
    const arr=viewList(data,p.from);
    if(!arr.length) return emptyMsg(p,data);
    return '<div class="card">'+(p.title?'<div class="step-label">'+esc(p.title)+'</div>':'')+
      arr.map(it=>'<div class="kv"><span class="k">'+tpl(p.k,it)+'</span><span>'+tpl(p.v,it)+'</span></div>').join('')+'</div>';
  }
  if(p.type==='card_list'){
    const arr=viewList(data,p.from);
    if(!arr.length) return emptyMsg(p,data);
    const c=p.card||{};
    return arr.map((it,ri)=>{
      const click=p.item_click?' onclick="rowDrill('+vi+','+ri+')" style="cursor:pointer"':'';
      let body='<div class="t">'+tpl(c.title,it)+'</div><div class="m">'+(c.lines||[]).map(l=>tpl(l,it)).join('<br>')+'</div>';
      if(c.link&&c.link.href){
        const href=tpl(c.link.href,it);
        if(href) body+='<a href="'+href+'" target="_blank" style="font-size:12px" onclick="event.stopPropagation()">'+esc(c.link.label||'상세 →')+'</a>';
      }
      if(c.image){ const img=tpl(c.image,it); return '<div class="card bookcard"'+click+'>'+(img?'<img src="'+img+'" loading="lazy">':'<img>')+'<div>'+body+'</div></div>'; }
      return '<div class="card"'+click+'>'+body+'</div>';
    }).join('');
  }
  if(p.type==='image_grid'){
    const arr=viewList(data,p.from);
    if(!arr.length) return emptyMsg(p,data);
    return '<div class="posters">'+arr.map(it=>{
      const img=p.image?tpl(p.image,it):'';
      // 클릭=원본/동영상 라이트박스. URL 은 클릭 시 <img src>에서 파생(따옴표 이스케이프 회피, CCTV playStream 선례).
      const click=img?' onclick="openMediaFromEl(this)" style="cursor:pointer"':'';
      return '<div class="poster"'+click+'>'+(img?'<img src="'+img+'" loading="lazy">':'<div style="aspect-ratio:3/4;background:var(--bg3);border-radius:8px"></div>')+
        '<div class="t">'+tpl(p.title,it)+'</div><div class="m">'+(p.lines||[]).map(l=>tpl(l,it)).join('<br>')+'</div></div>';
    }).join('')+'</div>';
  }
  if(p.type==='thread'){
    const arr=viewList(data,p.from);
    if(!arr.length) return emptyMsg(p,data);
    return '<div class="thread">'+arr.map(it=>{
      const mine=p.mine?!!jget(it,p.mine):false;
      const st=p.status?statusGlyph(jget(it,p.status)||''):'';
      const foot=[p.meta?tpl(p.meta,it):'', p.time?tpl(p.time,it):'', st].filter(Boolean).join(' · ');
      return '<div class="tmsg'+(mine?' me':'')+'"><div class="tbub">'+tpl(p.text,it)+'</div>'+(foot?'<div class="tfoot">'+foot+'</div>':'')+'</div>';
    }).join('')+'</div>';
  }
  if(p.type==='form'){
    let h='<div class="card">'+(p.title?'<div class="step-label">'+esc(p.title)+'</div>':'');
    (p.fields||[]).forEach((f,fi)=>{
      const val=tpl(f.value||'',data); const id='ff_'+vi+'_'+f.key;
      h+='<div style="margin-bottom:8px"><label class="muted" style="display:block;font-size:11px;margin-bottom:3px">'+esc(f.label||'')+'</label>';
      if(f.type==='select') h+='<select class="field" id="'+id+'">'+(f.options||[]).map(o=>'<option value="'+esc(String(o.value))+'"'+(String(o.value)===String(val)?' selected':'')+'>'+esc(o.label)+'</option>').join('')+'</select>';
      else if(f.type==='textarea') h+='<textarea class="field" id="'+id+'" rows="3">'+esc(val)+'</textarea>';
      else if(f.type==='toggle') h+='<select class="field" id="'+id+'"><option value="0"'+(String(val)!=='1'?' selected':'')+'>꺼짐</option><option value="1"'+(String(val)==='1'?' selected':'')+'>켜짐</option></select>';
      else if(f.type==='images'){
        // 썸네일(전 표면 /image?path=) + 제거. 추가(파일선택)는 데스크탑 전용이라 원격엔 없음.
        let arr=[]; try{ const j=JSON.parse(val); arr=Array.isArray(j)?j:(val?[val]:[]); }catch(e){ arr=val?[val]:[]; }
        h+='<div style="display:flex;flex-wrap:wrap;gap:8px">';
        arr.forEach(pth=>{ h+='<div style="position:relative">'
          +'<img src="'+API+'/image?path='+encodeURIComponent(pth)+'" style="width:64px;height:64px;object-fit:cover;border-radius:8px;border:1px solid var(--line)">'
          +(f.remove_action?'<button onclick="imgRemove('+vi+','+fi+',\\''+encodeURIComponent(pth)+'\\')" style="position:absolute;top:-6px;right:-6px;width:20px;height:20px;border-radius:50%;background:#333;color:#fff;border:none;font-size:12px;line-height:1;cursor:pointer">×</button>':'')
          +'</div>'; });
        if(!arr.length) h+='<span class="muted" style="font-size:12px">이미지 없음 (사진 추가는 데스크탑에서)</span>';
        h+='</div>';
      }
      else h+='<input class="field" id="'+id+'" value="'+esc(val)+'" placeholder="'+esc(f.placeholder||'')+'">';
      h+='</div>';
    });
    h+='<div style="display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-top:4px">'
      +'<button class="go" onclick="formSave('+vi+',this)">'+esc(p.button||'저장')+'</button>';
    // 보조 액션(즐겨찾기 토글·삭제 등) — 드릴 데이터 컨텍스트로 실행
    (p.actions||[]).forEach((a,ai)=>{
      const dz=a.style==='danger'?';color:#c0392b;border-color:#e8b9b3':'';
      h+='<button class="linkbtn" style="padding:9px 13px;border:1px solid var(--line);border-radius:10px'+dz+'" onclick="formAct('+vi+','+ai+',this)">'+esc(tpl(a.label,data))+'</button>';
    });
    h+='</div></div>';
    return h;
  }
  if(p.type==='editable_list'){
    const arr=viewList(data,p.from);
    let h='<div class="card">'+(p.title?'<div class="step-label">'+esc(p.title)+'</div>':'');
    if(!arr.length) h+='<p class="muted">'+esc(p.empty||'없음')+'</p>';
    arr.forEach((it,ri)=>{ h+='<div class="kv"><span class="k">'+tpl(p.display,it)+'</span>'+(p.delete_action?'<button class="linkbtn" onclick="elDelete('+vi+','+ri+')">삭제</button>':'')+'</div>'; });
    if(p.add){
      h+='<div class="row" style="flex-wrap:wrap;margin-top:8px">'+(p.add.fields||[]).map(f=> f.type==='select'
        ? '<select class="field" id="ea_'+vi+'_'+f.key+'" style="flex:0 1 110px"><option value="">'+esc(f.placeholder||'')+'</option>'+(f.options||[]).map(o=>'<option value="'+esc(String(o.value))+'">'+esc(o.label)+'</option>').join('')+'</select>'
        : '<input type="'+(f.type==='date'?'date':'text')+'" class="field" style="min-width:0" id="ea_'+vi+'_'+f.key+'" placeholder="'+esc(f.placeholder||'')+'">').join('')
        +'<button class="go" onclick="elAdd('+vi+',this)">'+esc((p.add.button)||'추가')+'</button></div>';
    }
    h+='</div>'; return h;
  }
  if(p.type==='sparkline'){
    const arr=viewList(data,p.from);
    const vals=arr.map(x=>Number(p.y?x[p.y]:x)).filter(v=>!isNaN(v));
    if(vals.length<2) return '';
    const col=trendColor(p,data)||'var(--acc)';
    const w=280,hh=50,mn=Math.min.apply(null,vals),mx=Math.max.apply(null,vals),rg=(mx-mn)||1;
    const pts=vals.map((v,i)=>((i/(vals.length-1))*w).toFixed(1)+','+(hh-((v-mn)/rg*hh)).toFixed(1)).join(' ');
    return '<div class="card"><svg viewBox="0 0 '+w+' '+hh+'" style="width:100%; height:50px" preserveAspectRatio="none"><polyline points="'+pts+'" fill="none" stroke="'+col+'" stroke-width="2"/></svg></div>';
  }
  if(p.type==='list_action'){
    const arr=viewList(data,p.from);
    if(!arr.length) return emptyMsg(p,data);
    return arr.map((it,ri)=>
      '<div class="card sw-item">'+(p.icon?'<span>'+esc(p.icon)+'</span>':'')+
      '<div style="flex:1"><div class="nm">'+tpl(p.title,it)+'</div><div class="pr">'+tpl(p.sub,it)+'</div></div>'+
      (p.button?'<button class="btn2" onclick="rowBtn('+vi+','+ri+',this)">'+esc(p.button.label||'▶')+'</button>':'')+
      (p.button2?'<button class="btn2" onclick="rowBtn('+vi+','+ri+',this,\\'button2\\')">'+esc(p.button2.label||'⬇')+'</button>':'')+'</div>'
    ).join('');
  }
  return '';
}

/* ----- 실행/디스패치 ----- */
/* 계기 입력값 영속화(localStorage) — 데스크탑 bespoke 계기가 쓰던 결정화를 제네릭 렌더러에도.
   키=계기id+모드id+입력key 별. 바꾼 키워드 등이 리로드 후에도 유지(이전엔 매번 default로 리셋). */
function _inpLS(instId,modeId,key){ return 'lz.inp.'+instId+'.'+modeId+'.'+key; }
function loadInpVal(instId,modeId,key,def){
  try{ const v=localStorage.getItem(_inpLS(instId,modeId,key)); return (v!=null)?v:(def||''); }catch(e){ return def||''; }
}
function saveInpVals(){
  const m=CUR.mode, inst=CUR.inst; if(!m||!inst) return;
  (m.inputs||[]).forEach(inp=>{ const el=document.getElementById('in_'+inp.key);
    if(el){ try{ localStorage.setItem(_inpLS(inst.id,m.id,inp.key), el.value); }catch(e){} } });
}
function gatherInputs(){
  const vals={};
  (CUR.mode.inputs||[]).forEach(inp=>{ const el=document.getElementById('in_'+inp.key); vals[inp.key]=el?el.value.trim():''; });
  if(CUR.mode.filter&&CUR.filterVal!=null) vals[CUR.mode.filter.key||'filter']=CUR.filterVal;
  saveInpVals();  // 조회 시점에도 현재 값 영속화(onchange 못 탄 경우 안전망)
  return vals;
}
function setFilter(v){
  CUR.filterVal=v;
  document.querySelectorAll('#modeBody .fchip').forEach(b=>b.classList.toggle('on', b.getAttribute('data-v')===String(v)));
  runMode();
}
async function runMode(){
  const mode=CUR.mode; if(!mode||!mode.action) return;
  const out=document.getElementById('instOut'); if(!out) return;
  const vals=gatherInputs();
  for(const inp of (mode.inputs||[])) if(inp.required&&!vals[inp.key]) return;
  out.innerHTML='<div class="center"><div class="spin"></div></div>';
  try{
    const d=await ibl(buildAction(mode.action,vals));
    SPLIT=(mode.view||[]).some(p=>p&&p.type==='card_list'&&p.master_detail);
    if(SPLIT){
      LIST={view:mode.view,data:d}; VIEW_CTX=null;
      out.innerHTML='<div class="mdsplit" id="mdSplit"><div class="mdlist" id="mdList">'+renderView(mode.view,d)+'</div>'
        +'<div class="mddetail" id="mdDetail"><div class="mdph">← 목록에서 대화를 선택하세요</div></div></div>';
      initMaps();
    } else {
      LIST=null; VIEW_CTX={view:mode.view,data:d,compose:mode.compose,refresh:'mode'}; CUR.catFilter=null;
      out.innerHTML=renderModeBody(mode,d);
      initMaps();
    }
    // 폰: 생성된 HTML(신문 등)을 조회 직후 자동으로 띄운다(별도 '띄우기' 탭 불필요).
    if(IS_PHONE && d && typeof d==='object' && typeof d.file==='string' && /\\.html?$/i.test(d.file)) openFileOverlay(d.file, d.html);
  }catch(e){ out.innerHTML='<p class="muted">오류: '+esc(e.message)+'</p>'; }
}
/* 작성바(compose) — $text=작성 내용, 드릴이면 {field}=대화 상대 행 필드. 전송 후 현재 뷰 새로고침. */
/* compose 발신 채널 후보 — 드릴 데이터 연락처에서 발신 가능한 채널만, 없으면 기본(primary) 폴백 */
function composeChannelOptions(cmp){
  const ch=cmp&&cmp.channels; const data=VIEW_CTX&&VIEW_CTX.data;
  if(!ch||!data||typeof data!=='object') return [];
  const mk=(ct,to,label)=>({key:ct+'|'+to,channel_type:ct,to:to,label:label});
  let opts=viewList(data,ch.from).map(c=>({ct:String(jget(c,ch.type)||''),to:String(jget(c,ch.value)||'')}))
    .filter(o=>o.to&&(!ch.sendable||ch.sendable.indexOf(o.ct)>=0)).map(o=>mk(o.ct,o.to,o.ct+' · '+o.to));
  if(!opts.length){ const ct=String(jget(data,'channel')||''),to=String(jget(data,'to')||''); if(to) opts=[mk(ct,to,ct||'기본')]; }
  const seen={}; return opts.filter(o=>seen[o.key]?false:(seen[o.key]=1,true));
}
function renderComposeBar(cmp){
  if(!cmp) return '';
  const opts=composeChannelOptions(cmp);
  let sel='';
  if(opts.length>=2) sel='<select id="composeChannel" class="field" style="flex:0 0 auto;max-width:42%;border-radius:22px">'
    +opts.map(o=>'<option value="'+esc(o.key)+'">'+esc(o.label)+'</option>').join('')+'</select>';
  return '<div class="composebar">'+sel+'<input id="composeInput" class="field" placeholder="'+esc(cmp.placeholder||'메시지 입력…')+'" '
    +'onkeydown="if(event.key===\\'Enter\\')composeSend(document.getElementById(\\'composeSendBtn\\'))">'
    +'<button id="composeSendBtn" class="go" onclick="composeSend(this)">'+esc(cmp.button||'전송')+'</button></div>';
}
/* 현재 렌더 중인 view(탭이면 활성 탭 view, 아니면 모드/드릴 view) */
function activeView(){ return (VIEW_CTX&&(VIEW_CTX._activeView||VIEW_CTX.view))||[]; }

/* 드릴 새로고침 — 드릴이면 드릴 액션 재실행 후 재렌더, 아니면 모드 재실행 */
async function refreshCurrent(){
  if(VIEW_CTX&&VIEW_CTX.refresh==='drill'){
    const nd=await ibl(VIEW_CTX.action); if(nd&&typeof nd==='object') nd._item=VIEW_CTX.item;
    VIEW_CTX.data=nd; renderDrill();
  } else { runMode(); }
}

/* 액션 실행기: $field 치환 + {path}(rowContext, 기본 현재 데이터) 치환 → 실행 → 새로고침.
   opts.back=true 면 성공 후 새로고침 대신 목록으로 복귀(삭제 등 — 현재 상세가 사라지는 경우). */
async function dispatchAction(template,fieldValues,rowContext,opts){
  let code=buildAction(template,fieldValues||{});
  const ctx=rowContext||(VIEW_CTX&&VIEW_CTX.data);
  if(ctx) code=rowAction(code,ctx);
  const d=await ibl(code);
  if(d&&(d.error||d.success===false)){ alert(d.error||d.message||'실패'); return false; }
  if(opts&&opts.back) runMode(); else await refreshCurrent();
  return true;
}

/* 드릴 렌더 — 탭(대화/정보) + 활성 view + 활성 compose */
function renderDrill(){
  const out = SPLIT ? document.getElementById('mdDetail') : document.getElementById('instOut');
  if(!out||!VIEW_CTX) return;
  let h = SPLIT ? '<button class="linkbtn mdback" onclick="mdBack()">‹ 목록</button>'
                : '<button class="linkbtn" onclick="runMode()">‹ 목록으로</button>';
  let av, ac;
  if(VIEW_CTX.tabs&&VIEW_CTX.tabs.length){
    const ai=Math.min(VIEW_CTX.activeTab||0,VIEW_CTX.tabs.length-1);
    h+='<div class="tabs">'+VIEW_CTX.tabs.map((t,i)=>'<button class="tab'+(i===ai?' on':'')+'" onclick="drillTab('+i+')">'+esc(t.name)+'</button>').join('')+'</div>';
    av=VIEW_CTX.tabs[ai].view; ac=VIEW_CTX.tabs[ai].compose;
  } else { av=VIEW_CTX.view; ac=VIEW_CTX.compose; }
  VIEW_CTX._activeView=av; VIEW_CTX._activeCompose=ac;
  out.innerHTML=h+renderView(av,VIEW_CTX.data)+renderComposeBar(ac);
  initMaps();
}
function drillTab(i){ if(VIEW_CTX){ VIEW_CTX.activeTab=i; renderDrill(); } }
function mdBack(){ const s=document.getElementById('mdSplit'); if(s) s.classList.remove('has-detail'); }

async function composeSend(btn){
  const cmp=VIEW_CTX&&(VIEW_CTX._activeCompose||VIEW_CTX.compose); if(!cmp) return;
  const inp=document.getElementById('composeInput'); const text=inp?inp.value.trim():''; if(!text) return;
  const fields={text};
  const opts=composeChannelOptions(cmp);
  if(opts.length){ const selEl=document.getElementById('composeChannel'); const key=selEl?selEl.value:opts[0].key; const sel=opts.filter(o=>o.key===key)[0]||opts[0]; fields.channel_type=sel.channel_type; fields.to=sel.to; }
  btn.disabled=true;
  try{ await dispatchAction(cmp.action,fields); }
  catch(e){ alert('전송 실패: '+e.message); }
  finally{ btn.disabled=false; }
}
async function formSave(vi,btn){
  const p=activeView()[vi]; if(!p) return;
  const vals={}; (p.fields||[]).forEach(f=>{ const el=document.getElementById('ff_'+vi+'_'+f.key); if(el) vals[f.key]=el.value; });
  btn.disabled=true; try{ await dispatchAction(p.action,vals); }catch(e){ alert('저장 실패: '+e.message); } finally{ btn.disabled=false; }
}
/* images 필드 — 첨부 이미지 제거(드릴 데이터 컨텍스트로 remove_image). 추가는 데스크탑 전용. */
async function imgRemove(vi,fi,encPath){
  const p=activeView()[vi]; if(!p) return;
  const f=(p.fields||[])[fi]; if(!f||!f.remove_action) return;
  try{ await dispatchAction(f.remove_action,{path:decodeURIComponent(encPath)}); }
  catch(e){ alert('이미지 제거 실패: '+e.message); }
}
/* form 보조 액션(즐겨찾기 토글·삭제 등) — 드릴 데이터 컨텍스트로 실행. back=true면 목록 복귀. */
async function formAct(vi,ai,btn){
  const p=activeView()[vi]; if(!p||!p.actions||!p.actions[ai]) return;
  const a=p.actions[ai];
  if(a.confirm && !confirm(a.confirm)) return;
  btn.disabled=true;
  try{ await dispatchAction(a.action,{},null,{back:a.back}); }
  catch(e){ alert('실패: '+e.message); }
  finally{ btn.disabled=false; }
}
async function elAdd(vi,btn){
  const p=activeView()[vi]; if(!p||!p.add) return;
  const vals={}; (p.add.fields||[]).forEach(f=>{ const el=document.getElementById('ea_'+vi+'_'+f.key); if(el) vals[f.key]=el.value; });
  btn.disabled=true; try{ await dispatchAction(p.add.action,vals); }catch(e){ alert('추가 실패: '+e.message); } finally{ btn.disabled=false; }
}
async function elDelete(vi,ri){
  const p=activeView()[vi]; if(!p) return;
  const arr=viewList(VIEW_CTX.data,p.from); const item=arr[ri]; if(item==null) return;
  try{ await dispatchAction(p.delete_action,{},item); }catch(e){ alert('삭제 실패: '+e.message); }
}
function rowItem(vi,ri){
  if(!VIEW_CTX) return null;
  const p=activeView()[vi]; if(!p) return null;
  const arr=viewList(VIEW_CTX.data,p.from);
  return arr[ri]==null?null:{prim:p,item:arr[ri]};
}
/* 잠깐 뜨는 토스트(저장 알림 등) — alert 대신 비차단. */
function toast(msg){
  let t=document.getElementById('toastMsg');
  if(!t){ t=document.createElement('div'); t.id='toastMsg';
    t.style.cssText='position:fixed;left:50%;bottom:80px;transform:translateX(-50%);z-index:9999;background:#222;color:#fff;padding:10px 18px;border-radius:20px;font-size:14px;max-width:80%;text-align:center;box-shadow:0 2px 10px rgba(0,0,0,.5)';
    document.body.appendChild(t); }
  t.textContent=msg; t.style.display='block';
  clearTimeout(t._h); t._h=setTimeout(()=>{t.style.display='none';},2600);
}
async function rowBtn(vi,ri,btn,key){
  key=key||'button';
  const r=rowItem(vi,ri); if(!r||!r.prim[key]) return;
  // stream:true 버튼 = 클라이언트 스트림 재생(CCTV '보기'). IBL 실행 없이 행 url 을 playStream(hls.js) 오버레이로.
  if(r.prim[key].stream){ if(r.item&&r.item.url){ const i=_streamUrls.push(r.item.url)-1; playStream(i); } return; }
  const action=rowAction(r.prim[key].action,r.item);
  btn.disabled=true; const old=btn.textContent; btn.textContent='…';
  try{
    const d=await ibl(action);
    if(d&&d.play_in_client&&d.stream_url){ playRadioStream(d.stream_url,d.volume,d.title||d.station||d.name); }  // 폰 라디오·유튜브뮤직: WebView 직접 재생 + 미니플레이어
    else if(d&&d.download_in_client){ toast(d.saved===false?('⚠ '+(d.message||'저장 실패')):('📥 '+(d.message||'저장됨'))); }  // mp3 폰 저장 결과
    else if(d&&d.error){
      // 폰: os_open(집 PC GUI)이 mac_only 로 막히면, 로컬 생성한 HTML 을 인앱 뷰어로 띄운다.
      const m=action.match(/path:\\s*"([^"]+\\.html?)"/i);
      if(d.mac_only && m){ openFileOverlay(m[1]); }
      else alert(d.error);
    }
    else{  // 즐겨찾기 추가/삭제 등: 성공 메시지 토스트 + refresh 플래그면 현재 뷰 재조회
      if(d&&d.message) toast(d.message);
      if(r.prim[key].refresh) await refreshCurrent();
    }
  }
  catch(e){ alert('실행 실패: '+e.message); }
  finally{ btn.disabled=false; btn.textContent=old; }
}
function openFileOverlay(path, html){
  const name=path.split('/').pop().split('\\\\').pop();
  const ov=document.createElement('div'); ov.className='fileov';
  ov.innerHTML='<div class="fileov-bar"><span>'+esc(name)+'</span>'
    +'<button class="iconbtn" onclick="history.back()">✕</button></div>';
  // iframe은 DOM으로 만들어 srcdoc/src를 *프로퍼티*로 설정(문자열 이스케이프 불필요).
  // html 콘텐츠가 동봉됐으면 srcdoc으로 직접 띄운다 — 파일이 다른 몸(맥)에 있어 /output 로
  // 못 찾는 경우(포워드 산출)에도 콘텐츠로 렌더. 없으면 기존대로 /output 파일 서빙.
  const ifr=document.createElement('iframe');
  // html 동봉이면 srcdoc, 아니면 로컬 경로를 /launcher/file 로 서빙(옛 /output 은 라우트 없음=404).
  // 빌림-완성으로 포워드 산출 파일도 폰 로컬에 있어 이 경로로 띄워진다.
  if(html){ ifr.srcdoc=html; } else { ifr.src=API+'/launcher/file?path='+encodeURIComponent(path); }
  ov.appendChild(ifr);
  document.body.appendChild(ov);
  // 안드로이드 뒤로가기로 닫히게 — SPA 라 WebView 백스택이 비면 뒤로가기가 앱을 종료(홈)시킨다.
  // history 항목을 push → canGoBack=true → 뒤로가기는 goBack→popstate 로 오버레이만 닫고
  // 앱모드 화면에 머문다(앱 종료 아님).
  try{ history.pushState({fileov:1}, ''); }catch(e){}
}
// 안드로이드 뒤로가기 일반 처리 — 가장 위(깊은) 것부터 한 단계만 닫는다. 각 "깊이 들어가기"
// (계기 열기·오버레이)가 history.pushState 로 항목을 쌓아 두면, 뒤로가기는 여기서 앱 안에서
// 한 단계 뒤로 가고, 더 닫을 게 없을 때만 네이티브가 앱을 종료한다. 모든 시각 ←/✕ 버튼도
// history.back() 으로 이 경로를 타 일관성 유지.
window.addEventListener('popstate', function(){
  const _ov=document.querySelector('.fileov');
  if(_ov){ _ov.remove(); return; }              // 1) 파일 오버레이(신문 등)
  const _inst=document.getElementById('appInst');
  if(_inst && _inst.style.display!=='none'){ appBackHome(); return; }  // 2) 계기 → 앱 그리드
});
async function rowDrill(vi,ri){
  // split이면 리스트(LIST)에서 행을 찾아 상세 패널(#mdDetail)로, 아니면 현재 view(VIEW_CTX)에서 instOut으로.
  const src = SPLIT ? LIST : VIEW_CTX; if(!src) return;
  const p=(src.view||[])[vi]; if(!p||!p.item_click) return;
  // 동적 카테고리 필터가 활성이면 카드가 필터된 배열로 렌더되므로 ri 도 그 기준 → 같은 필터 적용 후 인덱싱(비분할만; split=master_detail 은 동적필터 없음).
  const drillData = SPLIT ? src.data : applyCatFilter(CUR.mode, src.data);
  const item=viewList(drillData,p.from)[ri]; if(item==null) return;
  const dc=p.item_click;
  const detail = SPLIT ? document.getElementById('mdDetail') : document.getElementById('instOut');
  detail.innerHTML='<div class="center"><div class="spin"></div></div>';
  try{
    const code=rowAction(buildAction(dc.action,gatherInputs()),item);  /* $입력(현재 다이얼)+{필드}(클릭 행) 둘 다 치환 */
    const d=await ibl(code);
    if(d&&typeof d==='object') d._item=item; /* 드릴 뷰에서 클릭한 행 참조용 */
    VIEW_CTX={view:dc.view,tabs:dc.tabs,activeTab:0,data:d,action:code,item:item,compose:dc.compose,refresh:'drill'};
    if(SPLIT){ const s=document.getElementById('mdSplit'); if(s) s.classList.add('has-detail'); }
    renderDrill();
  }catch(e){ detail.innerHTML='<p class="muted">오류: '+esc(e.message)+'</p>'; }
}
</script>
</body>
</html>
"""
