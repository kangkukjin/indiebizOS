"""
api.py - IndieBiz OS Core API Server
최소 시스템: FastAPI + 시스템 AI + 기본 도구
"""

import os
import sys
import json
from pathlib import Path

# Windows 인코딩 문제 해결 (한글 등 비-ASCII 문자 처리)
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        sys.stderr.reconfigure(encoding='utf-8', errors='replace')
    except AttributeError:
        pass  # Python 3.6 이하
    os.environ.setdefault('PYTHONIOENCODING', 'utf-8')

# PATH 환경변수 보강 (ADB 등 외부 도구 접근용)
if sys.platform != "win32":
    _extra_paths = [
        "/opt/homebrew/bin",
        "/usr/local/bin",
        os.path.expanduser("~/Library/Android/sdk/platform-tools"),
    ]
else:
    _extra_paths = [
        os.path.expanduser("~\\AppData\\Local\\Android\\Sdk\\platform-tools"),
    ]
for _p in _extra_paths:
    if os.path.exists(_p) and _p not in os.environ.get("PATH", ""):
        os.environ["PATH"] = _p + os.pathsep + os.environ.get("PATH", "")
from datetime import datetime
from contextlib import asynccontextmanager, nullcontext

# .env 파일 로드 (python-dotenv)
from dotenv import load_dotenv
_base_for_env = Path(os.environ.get("INDIEBIZ_BASE_PATH", str(Path(__file__).parent.parent)))
load_dotenv(_base_for_env / ".env")
# 개발 모드에서는 기존 위치의 .env도 로드 시도
load_dotenv(Path(__file__).parent.parent / ".env")

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

# 경로 설정
BACKEND_PATH = Path(__file__).parent
# 프로덕션에서는 Electron이 INDIEBIZ_BASE_PATH를 사용자 데이터 폴더로 지정
# 개발 모드에서는 기존처럼 backend의 상위 폴더 사용
BASE_PATH = Path(os.environ.get("INDIEBIZ_BASE_PATH", str(BACKEND_PATH.parent)))
DATA_PATH = BASE_PATH / "data"
DATA_PATH.mkdir(parents=True, exist_ok=True)
sys.path.insert(0, str(BACKEND_PATH))

# 매니저 임포트
from project_manager import ProjectManager
from switch_manager import SwitchManager


# ============ 앱 초기화 ============

# ── IBL MCP over HTTP (additive) ────────────────────────────────────────────
# 문제: 내부 claude_code 에이전트의 IBL 도구(mcp__indiebizos__execute_ibl)가 stdio MCP 서버
#   (mcp_server.py)를 매 호출 새로 spawn → python 콜드스타트 + 핸드셰이크 완료 전 첫 호출이
#   나가는 연결 레이스로 "No such tool available" 이 반복됐다(풀네임 에러가 그 증거).
# 해법: 백엔드가 상시 떠 있으니, 같은 MCP 도구를 warm HTTP 엔드포인트(/mcp)로도 노출 → 콜드스타트
#   핸드셰이크가 사라져 레이스가 구조적으로 제거된다. ★기존 stdio 경로(claude_code_mcp.json)는
#   그대로 둔다 — 이건 additive. config 교체·실기 검증은 별도 단계(회귀 0).
_ibl_mcp = None
_ibl_mcp_app = None
try:
    _repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if _repo_root not in sys.path:
        sys.path.insert(0, _repo_root)
    from mcp_server import mcp as _ibl_mcp  # execute_ibl · read_guide 툴 등록됨(run() 은 __main__ 가드라 미실행)
    _ibl_mcp.settings.streamable_http_path = "/"   # 마운트 prefix(/mcp)와 합쳐 최종 경로 = /mcp
    # DNS 리바인딩 방어는 ON 유지(★터널·외부 Host 로 /mcp 무단 IBL 실행 차단) + 로컬 claude CLI 만 허용.
    # allowed_hosts 가 비면 localhost 조차 421 로 거부되므로 반드시 명시.
    from mcp.server.transport_security import TransportSecuritySettings as _TSS
    _local_hosts = ["localhost", "localhost:8765", "127.0.0.1", "127.0.0.1:8765"]
    _ibl_mcp.settings.transport_security = _TSS(
        allowed_hosts=_local_hosts,
        allowed_origins=[f"http://{h}" for h in _local_hosts],
    )
    _ibl_mcp_app = _ibl_mcp.streamable_http_app()   # 이 호출이 session_manager 를 초기화한다(위 설정 반영)
    print("[MCP-HTTP] /mcp 마운트 준비 완료 (additive — stdio 경로 병행, localhost 전용)")
except Exception as _e:
    print(f"[MCP-HTTP] 마운트 준비 실패 (무시, stdio 경로는 유지): {_e}")
    _ibl_mcp = None
    _ibl_mcp_app = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작/종료 시 실행"""

    # 번들 런타임 PATH 설정 (내장 Python의 Scripts/site-packages를 PATH/sys.path에 등록)
    # → subprocess에서 yt-dlp 등 pip CLI 도구를 찾을 수 있고, import도 정상 동작
    from runtime_utils import setup_bundled_runtime_paths
    setup_bundled_runtime_paths()

    # 몸 독립 부팅 배선 — 에피소드 로거 등(맥·폰·미래 몸 공통). boot_common 한 곳에서
    # 켜므로 새 몸의 진입점을 만들 때 베끼다 빠뜨릴 수 없다(헌법1조: 몸 독립은 공유 배선,
    # 몸 종속만 각 진입점이 profile 게이트로 명시 분기). 폰은 phone_api.serve() 가 같이 호출.
    try:
        from boot_common import wire_local_subsystems
        wire_local_subsystems(profile="mac")
    except Exception as e:
        print(f"[boot] 부팅 배선 실패 (무시): {e}")

    print("🚀 IndieBiz OS 서버 시작")

    # (완료 task 정리는 위 wire_local_subsystems 로 이관 — 몸 독립이라 맥·폰 공유)

    # 다중 노드: 이 기기(맥/허브)를 프레즌스 레지스트리에 자기등록. compute-class·주(主).
    # 폰들이 부팅 시 /nodes/register 로 합류 → "지금 연결된 노드"를 연결로 확인(폰 수 무고정).
    try:
        import device_registry as _dr
        _self = _dr.ensure_self(auth="launcher_session", primary=True)
        print(f"[device_registry] 자기등록: {_self.get('alias')} ({_self.get('device_id')}) "
              f"caps={_self.get('capabilities')}")
    except Exception as e:
        print(f"[device_registry] 자기등록 실패 (무시): {e}")

    # World Pulse: 펄스 수집 & 자가점검 스케줄 등록 (스케줄러 시작 전에 등록해야 함)
    try:
        from world_pulse import register_pulse_tasks
        register_pulse_tasks()
        print("[WorldPulse] 펄스 수집 & 자가점검 스케줄 등록")
    except Exception as e:
        print(f"[WorldPulse] 등록 실패 (무시): {e}")

    # 통합 스케줄러 자동 시작
    from calendar_manager import get_calendar_manager
    calendar_manager = get_calendar_manager()
    calendar_manager.start()

    # 채널 폴러 자동 시작
    from channel_poller import get_channel_poller
    poller = get_channel_poller()
    poller.start()

    # 폰 컴패니언 알림 폴러 — 2026-06-06 사용자 요청으로 일단 중단.
    # 알림/걸음/위치 신호를 indiebizOS 에 저장할 필요가 없다고 판단해 비활성화.
    # 재개하려면 아래 3줄의 주석을 해제하면 됨 (NIP-17 DM → SQLite 저장 재개).
    # try:
    #     import phone_notifications
    #     phone_notifications.start_poller(interval=60)
    # except Exception as e:
    #     print(f"[phone_notifications] 폴러 기동 실패: {e}")

    # 시스템 AI Runner 자동 시작 (위임 체인 지원)
    from system_ai_runner import start_system_ai_runner, stop_system_ai_runner
    system_ai_runner = start_system_ai_runner()

    # Cloudflare 터널 자동 시작 (설정에 따라)
    try:
        from api_tunnel import auto_start_if_enabled as tunnel_auto_start
        tunnel_auto_start()
    except Exception as e:
        print(f"[Tunnel] 자동 시작 중 오류: {e}")

    # IBL 용례 임베딩 모델 백그라운드 로딩 (서버 블로킹 없음)
    try:
        from ibl_usage_db import IBLUsageDB
        IBLUsageDB._start_background_model_load()
    except Exception as e:
        print(f"[IBL] 모델 로딩 시작 실패 (무시): {e}")

    # 첫 실행 해마 공급 — 모델·용례·런타임이 없으면(주로 fresh 윈도우 설치) GitHub Release 에셋에서
    # userData 로 내려받고 임베딩 런타임을 설치한다(백그라운드·멱등, 이미 있으면 즉시 통과).
    # INDIEBIZ_HIPPOCAMPUS_AUTO=0 으로 끌 수 있다. 데스크탑 진입점 전용(폰-자아는 렌트 모드).
    try:
        from hippocampus_provision import provision_async
        provision_async(enabled=os.environ.get("INDIEBIZ_HIPPOCAMPUS_AUTO", "1") != "0")
    except Exception as e:
        print(f"[해마공급] 시작 실패 (무시): {e}")

    # 첫 실행 ffmpeg 공급 — 라디오(ffplay)·유튜브 재생용 ffmpeg 가 없으면(주로 fresh 윈도우)
    # 정적 빌드를 userData/bin 에 내려받는다(백그라운드·멱등, 시스템 ffmpeg 있으면 즉시 통과).
    # INDIEBIZ_FFMPEG_AUTO=0 으로 끌 수 있다. 재시작 후엔 register_bin_path 만으로 즉시 인식.
    try:
        from ffmpeg_provision import provision_async as _ffmpeg_provision_async
        _ffmpeg_provision_async(enabled=os.environ.get("INDIEBIZ_FFMPEG_AUTO", "1") != "0")
    except Exception as e:
        print(f"[ffmpeg공급] 시작 실패 (무시): {e}")

    # World Pulse: 오늘의 세계 상태 스냅샷 확인 (없으면 백그라운드 수집)
    # 서버 시작을 블로킹하지 않도록 별도 스레드에서 실행
    import threading
    def _deferred_world_pulse():
        try:
            from world_pulse import ensure_today_pulse
            result = ensure_today_pulse()
            status = result.get("status", "unknown")
            if status == "exists":
                print(f"[WorldPulse] 오늘 스냅샷 확인됨 ({result.get('date')})")
            elif status == "collected":
                print(f"[WorldPulse] 오늘 스냅샷 신규 수집 완료 ({result.get('date')})")
            elif status == "error":
                print(f"[WorldPulse] 수집 실패: {result.get('detail')}")
        except Exception as e:
            print(f"[WorldPulse] 초기화 실패 (무시): {e}")
    threading.Thread(target=_deferred_world_pulse, daemon=True).start()
    print("[WorldPulse] 백그라운드 수집 스레드 시작")

    # IBL MCP HTTP 세션 매니저를 앱 수명 동안 켠다(마운트한 /mcp 가 동작하려면 필수).
    # 실패/미준비면 nullcontext 로 조용히 통과(기존 stdio 경로는 영향 없음).
    _mcp_ctx = _ibl_mcp.session_manager.run() if _ibl_mcp is not None else nullcontext()
    async with _mcp_ctx:
        yield

    # Cloudflare 터널 종료
    try:
        from api_tunnel import stop_tunnel
        result = stop_tunnel()
        if result.get("success"):
            print("[Tunnel] 터널 종료됨")
    except Exception as e:
        print(f"[Tunnel] 종료 중 오류: {e}")

    # 시스템 AI Runner 종료
    stop_system_ai_runner()

    # 채널 폴러 종료
    poller.stop()

    # 통합 스케줄러 종료
    calendar_manager.stop()
    print("👋 IndieBiz OS 서버 종료")

app = FastAPI(
    title="IndieBiz OS API",
    description="IndieBiz OS - AI Agent Platform",
    version="0.1.0",
    lifespan=lifespan
)

# IBL MCP over HTTP — warm 엔드포인트 /mcp (additive, stdio 병행). 세션 매니저는 lifespan 에서 켠다.
if _ibl_mcp_app is not None:
    app.mount("/mcp", _ibl_mcp_app)

# CORS 설정 (Electron 및 로컬 개발 환경에서 접근 허용)
# 보안: 허용된 오리진만 명시적으로 지정
ALLOWED_ORIGINS = os.environ.get("CORS_ORIGINS", "").split(",") if os.environ.get("CORS_ORIGINS") else [
    "http://localhost:5173",      # Vite 개발 서버
    "http://localhost:3000",      # React 개발 서버
    "http://127.0.0.1:5173",
    "http://127.0.0.1:3000",
    "app://.",                    # Electron 앱
    "file://",                    # Electron 로컬 파일
]

# Cloudflare Tunnel 도메인 자동 추가 (원격 접속용)
try:
    _tunnel_config_path = os.path.join(os.path.dirname(__file__), "..", "data", "tunnel_config.json")
    if os.path.exists(_tunnel_config_path):
        with open(_tunnel_config_path, 'r', encoding='utf-8') as _f:
            _tunnel_cfg = json.load(_f)
        for _key in ["finder_hostname", "launcher_hostname", "hostname"]:
            _host = _tunnel_cfg.get(_key, "")
            if _host:
                _origin = f"https://{_host}"
                if _origin not in ALLOWED_ORIGINS:
                    ALLOWED_ORIGINS.append(_origin)
except Exception:
    pass

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS", "PATCH"],
    allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
)


# === 원격 접근 인증 게이트 ===
# 데이터 엔드포인트(/projects, /switches, /system-ai/chat 등)는 데스크탑과 공유되어
# 로컬에선 무인증으로 열려 있다. 터널을 통해 들어온 외부 요청에 대해서만 런처 세션을
# 강제해, 비밀번호 없이 데이터·API 키가 새는 것을 막는다. (localhost 데스크탑은 통과)
@app.middleware("http")
async def remote_access_guard(request: Request, call_next):
    if request.method != "OPTIONS":
        try:
            from api_launcher_web import (
                is_external_request,
                is_public_remote_path,
                verify_session,
            )
            if is_external_request(request):
                path = request.url.path
                if not is_public_remote_path(request.method, path) and not verify_session(request):
                    return JSONResponse(
                        {"detail": "인증이 필요합니다. 원격 런처에 로그인하세요."},
                        status_code=401,
                    )
        except Exception:
            # 게이트 자체의 오류로 서비스가 막히지 않도록 보수적으로 통과
            pass
    return await call_next(request)

# 매니저 인스턴스
project_manager = ProjectManager(BASE_PATH)
switch_manager = SwitchManager()


# ============ 라우터 임포트 및 매니저 주입 ============

from api_projects import router as projects_router, init_managers as init_projects_managers, init_multi_chat_manager as init_projects_multi_chat
from api_switches import router as switches_router, init_manager as init_switches_manager
from api_config import router as config_router, init_manager as init_config_manager
from api_system_ai import router as system_ai_router
from api_agents import router as agents_router, init_manager as init_agents_manager
from api_conversations import router as conversations_router, init_manager as init_conversations_manager
from api_websocket import router as websocket_router, init_manager as init_websocket_manager
from api_packages import router as packages_router
from api_scheduler import router as scheduler_router
from api_notifications import router as notifications_router
from api_gmail import router as gmail_router
from api_business import router as business_router, init_manager as init_business_manager
from api_health import router as health_router
from api_multi_chat import router as multi_chat_router, init_manager as init_multi_chat_manager
from api_pcmanager import router as pcmanager_router
from api_photo import router as photo_router
from api_android import router as android_router
from api_nas import router as nas_router
from api_launcher_web import router as launcher_web_router
from api_tunnel import router as tunnel_router, auto_start_if_enabled as tunnel_auto_start
from api_ibl import router as ibl_router
from api_nodes import router as nodes_router
from api_xray import router as xray_router
from api_lecture_workspace import router as lecture_workspace_router

# 매니저 주입
init_projects_managers(project_manager, switch_manager)
init_switches_manager(switch_manager)
init_config_manager(project_manager)
init_agents_manager(project_manager)
init_conversations_manager(project_manager)
init_websocket_manager(project_manager)
init_business_manager()
init_multi_chat_manager()  # AI 설정은 필요시 전달

# 다중채팅 매니저를 api_projects에도 주입 (휴지통 통합용)
from api_multi_chat import get_manager as get_multi_chat_manager
init_projects_multi_chat(get_multi_chat_manager())


# ============ 라우터 등록 ============

app.include_router(projects_router, tags=["projects"])
app.include_router(switches_router, tags=["switches"])
app.include_router(config_router, tags=["config"])
app.include_router(system_ai_router, tags=["system-ai"])
app.include_router(agents_router, tags=["agents"])
app.include_router(conversations_router, tags=["conversations"])
app.include_router(websocket_router, tags=["websocket"])
app.include_router(packages_router, tags=["packages"])
app.include_router(scheduler_router, tags=["scheduler"])
app.include_router(notifications_router, tags=["notifications"])
app.include_router(gmail_router, tags=["gmail"])
app.include_router(business_router, tags=["business"])
app.include_router(health_router, tags=["health-sync"])
app.include_router(multi_chat_router, tags=["multi-chat"])
app.include_router(pcmanager_router, tags=["pcmanager"])
app.include_router(photo_router, tags=["photo"])
app.include_router(android_router, tags=["android"])
app.include_router(nas_router, tags=["nas"])
app.include_router(launcher_web_router, tags=["launcher-web"])
app.include_router(tunnel_router, tags=["tunnel"])
app.include_router(ibl_router, tags=["ibl"])
app.include_router(nodes_router, tags=["nodes"])
app.include_router(xray_router, tags=["xray"])
app.include_router(lecture_workspace_router, tags=["lecture-workspace"])

from api_phone import router as phone_router
app.include_router(phone_router, tags=["phone"])

# ============ NAS Finder 정적 파일 마운트 ============
# 주의: 마운트는 반드시 라우터 등록 **후**에 해야 함
static_path = BACKEND_PATH / "static" / "nas"
if static_path.exists():
    app.mount("/nas/app", StaticFiles(directory=str(static_path), html=True), name="nas_app")


# ============ 헬스 체크 ============

@app.get("/")
async def root():
    return {"status": "ok", "message": "IndieBiz OS Server", "version": "0.1.0"}

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "base_path": str(BASE_PATH)
    }


@app.get("/ping")
async def ping():
    """경량 생존 신호 — 피어(다른 몸)가 인증 없이 '연결됐나'만 확인. 민감정보 없음.
    폰 계기판이 맥(집 PC)의 연결상태를 표시할 때 이 엔드포인트를 핑한다(공개 경로)."""
    try:
        from runtime_utils import detect_body
        kind = detect_body().get("kind", "")
    except Exception:
        kind = ""
    return {"ok": True, "kind": kind}


# ============ 이미지 서빙 ============

@app.get("/image")
async def serve_image(path: str):
    """
    로컬 이미지 파일 서빙

    보안 강화:
    - realpath로 심볼릭 링크 우회 방지
    - 허용된 디렉토리 목록으로 접근 제한
    - 파일 확장자 검증
    """
    import os.path

    # /outputs/ 또는 /captures/로 시작하는 상대 경로를 절대 경로로 변환
    if path.startswith('/outputs/') or path.startswith('/captures/'):
        path = str(BASE_PATH / 'data' / path.lstrip('/'))

    # realpath: 심볼릭 링크를 모두 해석한 실제 경로 반환
    # (abspath만 사용하면 심볼릭 링크 우회 공격에 취약)
    real_path = os.path.realpath(path)

    # 허용된 기본 디렉토리 목록
    allowed_bases = [
        str(BASE_PATH),
        os.path.expanduser("~"),  # 사용자 홈 디렉토리 (사진 등)
    ]

    # 환경변수로 추가 허용 경로 설정 가능
    extra_paths = os.environ.get("ALLOWED_IMAGE_PATHS", "")
    if extra_paths:
        allowed_bases.extend(extra_paths.split(os.pathsep))

    # 허용된 경로인지 확인
    is_allowed = any(
        real_path.startswith(os.path.realpath(base))
        for base in allowed_bases
    )

    if not is_allowed:
        return {"error": "접근 권한 없음"}

    if not os.path.exists(real_path):
        return {"error": "파일을 찾을 수 없음"}

    # 파일인지 확인 (디렉토리 접근 방지)
    if not os.path.isfile(real_path):
        return {"error": "파일만 접근 가능"}

    ext = os.path.splitext(real_path)[1].lower()
    if ext not in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
        return {"error": "이미지 파일만 허용"}

    mime_types = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.webp': 'image/webp'
    }

    return FileResponse(real_path, media_type=mime_types.get(ext, 'image/jpeg'))


# ============ 메인 ============

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("INDIEBIZ_API_PORT", 8765))

    print(f"🚀 IndieBiz OS 서버 시작: http://localhost:{port}")

    # 프로덕션(패키징)에서는 reload 비활성화 (파일 감시자 오류 방지)
    is_production = os.environ.get("INDIEBIZ_PRODUCTION", "").lower() in ("1", "true")

    # reload_delay: 시스템 AI가 backend/*.py를 여러 번 빠르게 편집할 때 (예:
    # 패치 → 검증 → 추가 패치) 매 편집마다 reload되어 WebSocket이 끊기고 자기
    # 컨텍스트를 잃는 자해 패턴을 방지. 2초 디바운스로 일반적인 연쇄 편집은
    # 한 번의 reload로 묶이게 한다. (uvicorn 기본 0.25초 → 2.0초)
    uvicorn.run(
        "api:app",
        # 기본 localhost 전용. 분산 IBL LAN 테스트 등 LAN 도달이 필요하면 .env 에
        # INDIEBIZ_BIND_HOST=0.0.0.0 으로 opt-in(=LAN 노출, 외부요청 인증 게이트는
        # 터널 호스트네임 기준이라 LAN 직결은 우회됨 — 신뢰 LAN에서만).
        host=os.environ.get("INDIEBIZ_BIND_HOST", "127.0.0.1"),
        port=port,
        reload=not is_production,
        reload_delay=2.0,
        log_level="warning"
    )
