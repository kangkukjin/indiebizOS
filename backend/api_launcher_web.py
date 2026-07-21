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
import re
import json
import uuid
import hashlib
from datetime import datetime

# 원격 웹앱 HTML 3분할 모듈 (2026-07-18, 1500줄 규칙) — get_launcher_webapp_html 이 이어붙인다.
from launcher_web_shell import LAUNCHER_SHELL_HTML
from launcher_web_app import LAUNCHER_APP_JS
from launcher_web_render import LAUNCHER_RENDER_JS

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
# 어휘 없는 순수 앱(상부구조): 파일 하나 = 앱 하나. app: 블록과 동일 스키마이되
# 노드 액션에 매달리지 않는다 — 모드의 action: 은 전부 일반 어휘를 호출한다.
# (하부구조=어휘 / 상부구조=앱 의 깨끗한 이음매 — docs/APP_AS_MANIFEST_DESIGN.md)
INSTRUMENTS_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "instruments")
_instruments_cache = {"mtime": None, "payload": None}


def _repo_base() -> str:
    """레포 루트 절대경로 (매니페스트 %BASE% 토큰 치환용)."""
    try:
        from runtime_utils import get_base_path
        return str(get_base_path())
    except Exception:
        return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _subst_base(obj, base: str):
    """매니페스트 안 %BASE% 토큰을 레포 루트로 재귀 치환 (서버측 — 클라이언트는 실경로만 봄).
    $key/{field} 치환과 무충돌하도록 %BASE% 라는 별도 토큰을 쓴다(폰/타 머신 이식성)."""
    if isinstance(obj, str):
        return obj.replace("%BASE%", base)
    if isinstance(obj, list):
        return [_subst_base(x, base) for x in obj]
    if isinstance(obj, dict):
        return {k: _subst_base(v, base) for k, v in obj.items()}
    return obj


def _load_standalone_instruments() -> list:
    """data/instruments/*.yaml → [(instrument_id, app_dict), ...]. %BASE% 치환 적용."""
    import glob
    import yaml
    out = []
    base = _repo_base()
    for fp in sorted(glob.glob(os.path.join(INSTRUMENTS_DIR, "*.yaml"))):
        try:
            with open(fp, "r", encoding="utf-8") as f:
                m = yaml.safe_load(f) or {}
            if not isinstance(m, dict) or not m.get("instrument"):
                continue
            m = _subst_base(m, base)
            out.append((m["instrument"], m))
        except Exception:
            continue  # 깨진 매니페스트는 조용히 건너뜀(build --check 가 저술 시점에 잡음)
    return out


def _instruments_mtime() -> float:
    """ibl_nodes.yaml + instruments/ 디렉토리의 최신 mtime (둘 중 어느 쪽이 바뀌어도 캐시 무효화)."""
    m = os.path.getmtime(IBL_NODES_PATH)
    if os.path.isdir(INSTRUMENTS_DIR):
        m = max(m, os.path.getmtime(INSTRUMENTS_DIR))
        import glob
        for fp in glob.glob(os.path.join(INSTRUMENTS_DIR, "*.yaml")):
            try:
                m = max(m, os.path.getmtime(fp))
            except OSError:
                pass
    return m

# app 블록에서 모드(탭) 레벨로 그대로 전달되는 필드
# phone_render 포함: 포털(개인 커뮤니티 홈)이 매니페스트에서 "브라우저에 못 싣는 모드"
# (맥 스피커·네이티브 창 등)를 걸러내는 데 쓴다 — 렌더러들은 미지 필드를 무시하므로 무해.
_APP_MODE_FIELDS = ("note", "auto_run", "inputs", "buttons", "action", "view", "renderer", "compose", "filter", "phone_render")

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

    # (신규) 어휘 없는 순수 앱 — data/instruments/*.yaml. 노드 app: 블록과 동일 처리.
    for gid, app in _load_standalone_instruments():
        if runnable is not None and app.get("phone_render") is False:
            continue
        if gid not in groups:
            groups[gid] = []
            group_seq.append(gid)
        groups[gid].append((gid, app))

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
        # 시스템 표면 플래그 통과 — 데스크탑 앱 그리드가 이걸 보고 제외(런처 직속 창이 진입점).
        # 원격/폰(리모컨) 그리드는 무시하고 그대로 노출.
        if primary.get("system"):
            inst["system"] = True
        # top_buttons: 탭 무관 최상단 고정 버튼(소개발행 등) — 인스트루먼트 레벨 통과.
        if primary.get("top_buttons"):
            inst["top_buttons"] = primary.get("top_buttons")
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
    """tunnel_config.json + public_face.json에서 외부 노출 호스트네임 집합 로드"""
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
    # 직접 서빙(공개 얼굴) 호스트 — tailscale funnel 등. 이게 빠지면 funnel 트래픽이
    # '로컬'로 오인돼 인증 게이트를 건너뛴다(공개 경로 밖 데이터 API 노출 위험).
    try:
        pf_path = os.path.join(os.path.dirname(__file__), "..", "data", "public_face.json")
        if os.path.exists(pf_path):
            with open(pf_path, 'r', encoding='utf-8') as f:
                pf = json.load(f)
            for h in (pf.get("direct_hosts") or []):
                h = (h or "").split(":")[0].strip().lower()
                if h:
                    hosts.add(h)
    except Exception:
        pass
    return hosts


_EXTERNAL_HOSTNAMES = _load_external_hostnames()

# api.py 의 ALLOWED_ORIGINS 리스트 *자체*를 들고 있는다(사본 아님). CORSMiddleware 는
# 생성 시 받은 리스트를 참조로 보관하고 매 요청 `origin in self.allow_origins` 로 확인하므로,
# 같은 객체를 제자리 수정하면 재시작 없이 반영된다. 이게 없으면 새로 발급한 얼굴(ts.net 등)이
# 임포트 시점 1회 계산된 화이트리스트에 영원히 못 들어간다.
_CORS_ORIGINS_REF = None


def _sync_cors_origins():
    """외부 호스트네임 집합을 CORS 화이트리스트에 반영 (추가만 — 기존 항목 불변)"""
    if _CORS_ORIGINS_REF is None:
        return
    for host in _EXTERNAL_HOSTNAMES:
        origin = f"https://{host}"
        if origin not in _CORS_ORIGINS_REF:
            _CORS_ORIGINS_REF.append(origin)


def register_cors_origins(origins: list):
    """api.py 가 부팅 때 자기 ALLOWED_ORIGINS 를 맡긴다 (제자리 수정 대상 등록)"""
    global _CORS_ORIGINS_REF
    _CORS_ORIGINS_REF = origins
    _sync_cors_origins()
    return origins


def reload_external_hostnames():
    """터널 설정 변경 후 호스트네임 캐시 갱신 (+CORS 화이트리스트 동반 갱신)

    ★얼굴 발급/전환 뒤 이 함수 하나만 부르면 인증 게이트(외부 판별)와 CORS 가 함께
    따라온다 — 둘이 갈라져 있어서 ts.net 이 '외부'로는 잡히는데 CORS 에선 막히던 비대칭을
    한 지점으로 묶는다."""
    global _EXTERNAL_HOSTNAMES
    _EXTERNAL_HOSTNAMES = _load_external_hostnames()
    _sync_cors_origins()
    return _EXTERNAL_HOSTNAMES


# 루프백 — 데스크탑 Electron·MCP·스크립트. `localhost` 와 `127.0.0.1` 이 둘 다 실제로 쓰인다
# (Manager.tsx·mcp_server.py·ibl_health_check.py 는 localhost, 나머지 대부분은 127.0.0.1).
_LOOPBACK_HOSTS = {"localhost", "127.0.0.1", "::1", "[::1]", ""}

# 사설망 — 집 와이파이의 폰·구형 기기. 사용자 결정(2026-07-21): LAN 은 로컬로 신뢰한다.
# 100.64/10 은 CGNAT = tailnet 내부 주소(funnel 공개 경로가 아니라 tailnet 직결).
_PRIVATE_HOST_RE = re.compile(
    r"^(?:"
    r"127\.\d{1,3}\.\d{1,3}\.\d{1,3}"          # 루프백 대역 전체
    r"|10\.\d{1,3}\.\d{1,3}\.\d{1,3}"
    r"|192\.168\.\d{1,3}\.\d{1,3}"
    r"|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3}"
    r"|169\.254\.\d{1,3}\.\d{1,3}"             # 링크로컬
    r"|100\.(?:6[4-9]|[7-9]\d|1[01]\d|12[0-7])\.\d{1,3}\.\d{1,3}"  # CGNAT = tailnet
    r")$"
)

# 프록시(터널·CDN) 경유 신호. 이게 있으면 Host 가 뭐든 외부다.
_PROXY_SIGNAL_HEADERS = ("cf-connecting-ip", "cf-ray", "x-forwarded-for", "x-forwarded-proto")


def is_external_request(request: Request) -> bool:
    """원격(비신뢰) 요청인지 판별 — 인증 게이트의 판정자.

    ★fail-closed 다: **로컬임이 증명될 때만** 로컬이고, 모르는 호스트는 외부로 본다.
    옛 구현은 "알려진 터널 호스트 목록에 있으면 외부"(모르면 로컬)라 fail-open 이었다 —
    사용자가 우리 UI 를 안 거치고 터미널에서 `tailscale funnel 8765` 를 켜면 그 ts.net
    호스트가 등기부에 없어 **로컬로 오인**되고, 인증 게이트를 통째로 건너뛴 데이터 API
    (/projects·/system-ai/chat·대화·키)가 공개 인터넷에 열렸다. 실측으로 재현 확인
    (2026-07-21: 미등록 Host → /projects 200, 등록 Host → 401).

    ★순서가 중요하다 — 프록시 신호를 Host 검사보다 **먼저** 본다. cloudflared 는 구성에
    따라 Host 를 `localhost:8765` 로 재작성해 오리진에 넘긴다(face_provision.py:117 의
    윈도우 실측 기록). Host 부터 보면 그 구성에서 터널 트래픽 전체가 로컬로 통과한다.
    """
    # ① 프록시·CDN 경유 = 외부 확정 (Host 재작성 방어)
    for h in _PROXY_SIGNAL_HEADERS:
        if request.headers.get(h):
            return True

    host = (request.headers.get("host") or "").split(":")[0].strip().lower()

    # ② 알려진 외부 호스트 (터널 설정 + 공개 얼굴 등기부)
    if host and host in _EXTERNAL_HOSTNAMES:
        return True

    # ③ 루프백 / 사설망 = 로컬로 신뢰
    if host in _LOOPBACK_HOSTS or host.endswith(".local") or _PRIVATE_HOST_RE.match(host):
        return False

    # ④ 나머지(모르는 공개 호스트명) = 외부. 여기가 fail-closed 의 핵심이다.
    return True


def is_public_remote_path(method: str, path: str) -> bool:
    """원격에서 인증 없이 허용되는 경로 (로그인 셸 + 자체 인증 보유 경로)"""
    # 런처 앱 셸 + 로그인 흐름
    if path == "/launcher/app":
        return True
    # 홈 화면 설치 3종(매니페스트·서비스워커·아이콘) — 설치 판단은 로그인보다 먼저 일어난다.
    # 셋 다 정적 자산이라 노출해도 새는 정보가 없다(아이콘·앱 이름뿐).
    if method == "GET" and (path == "/launcher/manifest.webmanifest"
                            or path == "/launcher/sw.js"
                            or (path.startswith("/launcher/icon-") and path.endswith(".png"))
                            or path == "/launcher/apple-touch-icon.png"):
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
    # 공개파일 라이브 서빙(/showcase/*: list·thumb·media·origin)은 자체 X-Showcase-Secret 게이트 보유
    if method == "GET" and path.startswith("/showcase/"):
        return True
    # 가족신문 공개 서빙(/family-news/page·media·gb·upload)도 자체 X-Showcase-Secret 게이트 보유.
    # 방명록·업로드는 POST — preview 는 로컬 전용이라 의도적으로 미등록(터널 차단).
    if (path.startswith("/family-news/page/") or path.startswith("/family-news/media/")
            or path.startswith("/family-news/gb/") or path.startswith("/family-news/upload/")):
        return True
    # 개인 포털 공개 서빙(/portal/*)도 자체 X-Showcase-Secret 게이트 보유.
    # join(가입)·tool(회원 실행 게이트)은 POST. 그 외 /portal/ 경로는 없음(전부 등록).
    if method == "GET" and (path.startswith("/portal/page/") or path.startswith("/portal/key/")
                            or path.startswith("/portal/inst/") or path.startswith("/portal/tune/")
                            or path == "/portal/manifest" or path == "/portal/home"
                            or path == "/portal/file" or path == "/portal/gb"):
        return True
    # 창고 방명록 쓰기(손님도 가능 — 이름은 자동 '손님'). warehouse-admin/gb 는 소유자
    # 전용이라 여기 등록하지 않는다(익명 외부는 터널 게이트 401 = 모더레이션 보호).
    if method == "POST" and path == "/portal/gb":
        return True
    # 창고 파일 좋아요(손님도 가능 — IP 단위 중복 방지, 자체 시크릿 게이트 보유)
    if method == "POST" and path == "/portal/like":
        return True
    if method == "POST" and (path.startswith("/portal/join/") or path.startswith("/portal/tool/")
                             or path.startswith("/portal/login/") or path.startswith("/portal/logout/")
                             or path.startswith("/portal/reset/") or path.startswith("/portal/password/")
                             or path == "/portal/node/login" or path == "/portal/node/logout"
                             or path == "/portal/node/join"):
        return True
    # 자유게시판 공개 서빙(/bulletin/page·media)도 자체 X-Showcase-Secret 게이트 보유.
    # 익명 글쓰기는 POST /bulletin/post/ — 로그인 없는 자유게시판.
    if method == "GET" and (path.startswith("/bulletin/page/") or path.startswith("/bulletin/media/")):
        return True
    if method == "POST" and path.startswith("/bulletin/post/"):
        return True
    # 정기보고 발행 면(/report/page)도 자체 X-Showcase-Secret 게이트 보유(읽기 전용).
    if method == "GET" and path.startswith("/report/page/"):
        return True
    return False

# === API 엔드포인트 ===

class ConfigModel(BaseModel):
    enabled: bool
    password: Optional[str] = None  # 새 비밀번호 설정 시에만 전달 (생략 시 기존 유지)

class LoginModel(BaseModel):
    password: str


# 커스텀 React 계기(선언형 밖) id → 컴포넌트 파일. 매니페스트 밖 프론트 등록이라 여기 명시.
_CUSTOM_APP_SOURCES = {
    "binnote": "frontend/src/components/BinNote.tsx",
    "directions": "frontend/src/components/DirectionsInstrument.tsx",
    "newspaper": "frontend/src/components/NewspaperInstrument.tsx",
    "ytmusic": "frontend/src/components/YtMusicInstrument.tsx",
}


@router.get("/app-source/{app_id}")
def app_source(app_id: str):
    """앱 id → 그 앱을 구성하는 소스(대개 1파일). 앱저장소 '코드보기'용.

    선언형 앱은 instruments yaml 또는 액션의 app: 블록(YAML), 커스텀 React 앱은 .tsx.
    로컬 개인 도구라 리포 안 소스만 읽는다(realpath 로 리포 밖 차단)."""
    import yaml  # 이 모듈은 yaml 을 함수-지역으로 import 하는 관례
    root = os.path.realpath(os.path.dirname(os.path.dirname(IBL_NODES_PATH)))  # repo root

    def _read(rel):
        p = os.path.realpath(os.path.join(root, rel))
        if not p.startswith(root + os.sep) or not os.path.isfile(p):
            return None
        try:
            return open(p, encoding="utf-8").read()
        except Exception:
            return None

    # 1) 커스텀 React 컴포넌트
    if app_id in _CUSTOM_APP_SOURCES:
        rel = _CUSTOM_APP_SOURCES[app_id]
        code = _read(rel)
        if code is not None:
            return {"kind": "component", "path": rel, "lang": "tsx", "code": code}

    # 2) 독립 instruments yaml (data/instruments/<id>.yaml)
    code = _read(os.path.join("data", "instruments", f"{app_id}.yaml"))
    if code is not None:
        return {"kind": "instrument", "path": f"data/instruments/{app_id}.yaml", "lang": "yaml", "code": code}

    # 3) 선언형 app: 블록 (액션의 app.instrument==id 또는 액션명==id)
    try:
        with open(IBL_NODES_PATH, "r", encoding="utf-8") as f:
            nodes = (yaml.safe_load(f) or {}).get("nodes", {})
    except Exception:
        nodes = {}
    for nname, nd in nodes.items():
        for aname, ad in ((nd or {}).get("actions") or {}).items():
            app = (ad or {}).get("app")
            if isinstance(app, dict) and (app.get("instrument") or aname) == app_id:
                block = yaml.safe_dump({"app": app}, allow_unicode=True, sort_keys=False)
                # 소스 파일 best-effort(내용은 동일). ibl_nodes_src/ + 패키지 fragment 검색.
                import glob as _glob
                src_hint = f"{nname}:{aname} 의 app: 블록"
                for fp in (_glob.glob(os.path.join(root, "data", "ibl_nodes_src", "*.yaml"))
                           + _glob.glob(os.path.join(root, "data", "packages", "installed", "tools", "*", "ibl_actions.yaml"))):
                    try:
                        if f"instrument: {app_id}" in open(fp, encoding="utf-8").read():
                            src_hint = os.path.relpath(fp, root) + f" ({nname}:{aname})"
                            break
                    except Exception:
                        continue
                return {"kind": "app-block", "path": src_hint, "lang": "yaml", "code": block}

    raise HTTPException(status_code=404, detail=f"'{app_id}' 앱의 소스를 찾지 못했습니다(선언형/커스텀 매핑 없음).")


@router.get("/config")
async def get_config():
    """설정 조회"""
    config = load_config()
    import platform as _plat
    _sys = _plat.system()
    return {
        "enabled": config.get("enabled", False),
        "has_password": bool(config.get("password_hash")),
        # 이 허브가 어느 OS 인가 — 원격런처가 붙여넣기 안내 키를 고르는 데만 쓴다
        # (⌘V vs Ctrl+V). 표면 라벨 자체는 OS 중립('PC로 보내기').
        "platform": {"Darwin": "mac", "Windows": "windows"}.get(_sys, "linux"),
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
        mtime = _instruments_mtime()
        if _instruments_cache["mtime"] != mtime:
            _instruments_cache["payload"] = _derive_instruments()
            _instruments_cache["mtime"] = mtime
        return _instruments_cache["payload"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"계기 파생 실패: {e}")


class AppLayoutModel(BaseModel):
    """앱모드 홈 레이아웃 — 자유배치·폴더·앱저장소 상태 (launcher_layout 스키마)."""
    version: int = 1
    positions: dict = {}
    folders: dict = {}
    membership: dict = {}
    removed: list = []
    uninstalled: list = []
    promoted: list = []  # 런처 모드 선택기에 승격한 앱(순서 = 바 표시 순서)


@router.get("/app-layout")
async def get_app_layout():
    """앱모드 홈 레이아웃 로드 — 위치/폴더/소속/앱저장소(removed) 상태."""
    from launcher_layout import load_layout
    return load_layout()


@router.put("/app-layout")
async def put_app_layout(data: AppLayoutModel):
    """앱모드 홈 레이아웃 저장 — 드래그 배치·폴더 정리·앱 추가/제거 후 지속."""
    from launcher_layout import save_layout
    return save_layout(data.model_dump())


@router.post("/app-layout/reset/{app_id}")
async def reset_app_layout(app_id: str):
    """휴지통 의미 — 앱이 사용 중 쌓은 데이터를 지우고 초기화(앱이 선언한 reset IBL 실행)."""
    from launcher_layout import reset_app_data
    return reset_app_data(app_id)


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


# ── 홈 화면 설치 (웹 앱 매니페스트 + 아이콘 + 서비스워커) ──────────────────
# 원격런처를 안드로이드·아이폰·태블릿 어디서든 '설치'하게 하는 3종 세트. 브라우저가
# 이걸 읽어야 아이콘·이름·주소창 없는 독립 창을 우리가 정한 대로 띄운다.
# ★셋 다 로그인 전에 읽혀야 한다(설치 판단이 로그인보다 먼저) → is_public_remote_path 등록.
# ★이름 주의: 여기서 말하는 '매니페스트'는 웹 표준이다 — 계기 매니페스트
#   (/launcher/instruments)·창고 매니페스트(/portal/manifest)와 다른 물건.

_LAUNCHER_ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets", "launcher")


@router.get("/manifest.webmanifest")
async def launcher_manifest():
    """웹 앱 매니페스트 — 아이콘·이름·창 모양 선언."""
    return JSONResponse({
        "name": "IndieBiz OS",
        "short_name": "IndieBiz",
        "description": "내 시스템을 어디서나 — 자율주행·조종실·앱·공유창고",
        "start_url": "/launcher/app",
        "scope": "/launcher/",
        "display": "standalone",
        "orientation": "portrait-primary",
        "background_color": "#F5F1EB",
        "theme_color": "#D97706",
        "lang": "ko",
        "icons": [
            {"src": "/launcher/icon-192.png", "sizes": "192x192", "type": "image/png"},
            {"src": "/launcher/icon-512.png", "sizes": "512x512", "type": "image/png"},
            # maskable=안드로이드가 원형·둥근사각으로 잘라 쓰는 판(마크를 안전지대 안에 축소)
            {"src": "/launcher/icon-maskable-512.png", "sizes": "512x512", "type": "image/png",
             "purpose": "maskable"},
        ],
    }, media_type="application/manifest+json")


@router.get("/sw.js")
async def launcher_service_worker():
    """서비스워커 — **캐시하지 않는다**.

    크롬이 '설치 가능'으로 판정하려면 fetch 핸들러를 가진 서비스워커가 있어야 한다.
    그 조건만 만족시키고 요청은 전부 네트워크로 흘려보낸다(respondWith 없음 = 기본 동작).
    원격런처는 세션 쿠키로 개인화되고 실시간 상태를 그리는 표면이라 **캐싱이 곧 버그**다
    (포털 /h/ 를 no-store 로 두는 것과 같은 이유).
    """
    js = (
        "self.addEventListener('install', function(e){ self.skipWaiting(); });\n"
        "self.addEventListener('activate', function(e){ e.waitUntil(self.clients.claim()); });\n"
        "// 통과만 한다 — 캐시 없음(개인화·실시간 표면)\n"
        "self.addEventListener('fetch', function(e){});\n"
    )
    return Response(content=js, media_type="application/javascript",
                    headers={"Cache-Control": "no-cache"})


@router.get("/icon-192.png")
async def launcher_icon_192():
    return _launcher_asset("icon-192.png")


@router.get("/icon-512.png")
async def launcher_icon_512():
    return _launcher_asset("icon-512.png")


@router.get("/icon-maskable-512.png")
async def launcher_icon_maskable():
    return _launcher_asset("icon-maskable-512.png")


@router.get("/apple-touch-icon.png")
async def launcher_apple_icon():
    return _launcher_asset("apple-touch-icon.png")


def _launcher_asset(name: str):
    from fastapi.responses import FileResponse
    p = os.path.join(_LAUNCHER_ASSETS, name)
    if not os.path.exists(p):
        return JSONResponse({"error": "not found"}, status_code=404)
    # 아이콘은 좀처럼 안 바뀌므로 길게 캐시(바뀌면 파일명을 바꾼다)
    return FileResponse(p, media_type="image/png",
                        headers={"Cache-Control": "public, max-age=604800"})


def get_launcher_webapp_html():
    """원격 런처 웹앱 HTML — 3표면(자율주행/수동/앱) 구조.

    2026-07-18 모듈화(1500줄 규칙): 거대 단일 문자열을 launcher_web_shell(문서 셸)·
    launcher_web_app(앱 셸 JS)·launcher_web_render(뷰 렌더 JS) 세 모듈로 분리 —
    여기서 그대로 이어붙인다(바이트 동일 조립). ★renderPrim(p.type 디스패치)은
    launcher_web_render.py 에 산다 — 뷰-렌더러 가드가 그 파일 경로를 스캔한다.
    """
    return LAUNCHER_SHELL_HTML + LAUNCHER_APP_JS + LAUNCHER_RENDER_JS
