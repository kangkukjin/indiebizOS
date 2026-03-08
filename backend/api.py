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
from contextlib import asynccontextmanager

# .env 파일 로드 (python-dotenv)
from dotenv import load_dotenv
_base_for_env = Path(os.environ.get("INDIEBIZ_BASE_PATH", str(Path(__file__).parent.parent)))
load_dotenv(_base_for_env / ".env")
# 개발 모드에서는 기존 위치의 .env도 로드 시도
load_dotenv(Path(__file__).parent.parent / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
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

def _auto_register_packages():
    """서버 시작 시 수동 설치된 패키지의 IBL 액션을 자동 등록.

    installed/tools/ 내 ibl_actions.yaml이 있지만 _ibl_provenance.yaml에
    등록되지 않은 패키지를 찾아 자동으로 register_actions() 호출.
    """
    import yaml
    from ibl_action_manager import register_actions, _load_provenance

    tools_dir = DATA_PATH / "packages" / "installed" / "tools"
    if not tools_dir.exists():
        return

    # provenance에서 이미 등록된 패키지 집합
    prov = _load_provenance()
    registered_pkgs = set()
    for node_actions in prov.values():
        if isinstance(node_actions, dict):
            for owner in node_actions.values():
                registered_pkgs.add(owner)

    # 미등록 패키지 탐색 및 등록
    count = 0
    for pkg_dir in sorted(tools_dir.iterdir()):
        if not pkg_dir.is_dir() or pkg_dir.name.startswith('.'):
            continue
        if pkg_dir.name in registered_pkgs:
            continue
        if not (pkg_dir / "ibl_actions.yaml").exists():
            continue

        result = register_actions(pkg_dir.name)
        registered = result.get("registered", 0)
        if registered > 0:
            count += 1
            print(f"  → {pkg_dir.name}: {registered}개 액션 자동 등록")

    if count > 0:
        print(f"[AutoRegister] {count}개 패키지 자동 등록 완료")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작/종료 시 실행"""

    # 번들 런타임 PATH 설정 (내장 Python의 Scripts/site-packages를 PATH/sys.path에 등록)
    # → subprocess에서 yt-dlp 등 pip CLI 도구를 찾을 수 있고, import도 정상 동작
    from runtime_utils import setup_bundled_runtime_paths
    setup_bundled_runtime_paths()

    print("🚀 IndieBiz OS 서버 시작")

    # 통합 스케줄러 자동 시작
    from calendar_manager import get_calendar_manager
    calendar_manager = get_calendar_manager()
    calendar_manager.start()

    # 채널 폴러 자동 시작
    from channel_poller import get_channel_poller
    poller = get_channel_poller()
    poller.start()

    # 시스템 AI Runner 자동 시작 (위임 체인 지원)
    from system_ai_runner import start_system_ai_runner, stop_system_ai_runner
    system_ai_runner = start_system_ai_runner()

    # 패키지 IBL 액션 자동 등록 (수동 설치된 패키지 감지)
    try:
        _auto_register_packages()
    except Exception as e:
        print(f"[AutoRegister] 오류: {e}")

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

    # World Pulse: 오늘의 세계 상태 스냅샷 확인 (없으면 백그라운드 수집)
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
from api_indienet import router as indienet_router
from api_packages import router as packages_router
from api_scheduler import router as scheduler_router
from api_notifications import router as notifications_router
from api_gmail import router as gmail_router
from api_business import router as business_router, init_manager as init_business_manager
from api_multi_chat import router as multi_chat_router, init_manager as init_multi_chat_manager
from api_pcmanager import router as pcmanager_router
from api_photo import router as photo_router
from api_android import router as android_router
from api_nas import router as nas_router
from api_launcher_web import router as launcher_web_router
from api_tunnel import router as tunnel_router, auto_start_if_enabled as tunnel_auto_start

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
app.include_router(indienet_router, tags=["indienet"])
app.include_router(packages_router, tags=["packages"])
app.include_router(scheduler_router, tags=["scheduler"])
app.include_router(notifications_router, tags=["notifications"])
app.include_router(gmail_router, tags=["gmail"])
app.include_router(business_router, tags=["business"])
app.include_router(multi_chat_router, tags=["multi-chat"])
app.include_router(pcmanager_router, tags=["pcmanager"])
app.include_router(photo_router, tags=["photo"])
app.include_router(android_router, tags=["android"])
app.include_router(nas_router, tags=["nas"])
app.include_router(launcher_web_router, tags=["launcher-web"])
app.include_router(tunnel_router, tags=["tunnel"])

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

    uvicorn.run(
        "api:app",
        host="127.0.0.1",
        port=port,
        reload=not is_production,
        log_level="warning"
    )
