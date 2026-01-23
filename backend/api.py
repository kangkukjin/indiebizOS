"""
api.py - IndieBiz OS Core API Server
최소 시스템: FastAPI + 시스템 AI + 기본 도구
"""

import os
import sys
from pathlib import Path

# PATH 환경변수 보강 (ADB 등 외부 도구 접근용)
# Homebrew, Android SDK 등의 경로를 추가
_extra_paths = [
    "/opt/homebrew/bin",
    "/usr/local/bin",
    os.path.expanduser("~/Library/Android/sdk/platform-tools"),
]
for _p in _extra_paths:
    if os.path.exists(_p) and _p not in os.environ.get("PATH", ""):
        os.environ["PATH"] = _p + ":" + os.environ.get("PATH", "")
from datetime import datetime
from contextlib import asynccontextmanager

# .env 파일 로드 (python-dotenv)
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

# 경로 설정
BASE_PATH = Path(__file__).parent.parent
BACKEND_PATH = Path(__file__).parent
DATA_PATH = BACKEND_PATH / "data"
DATA_PATH.mkdir(exist_ok=True)
sys.path.insert(0, str(BACKEND_PATH))

# 매니저 임포트
from project_manager import ProjectManager
from switch_manager import SwitchManager


# ============ 앱 초기화 ============

@asynccontextmanager
async def lifespan(app: FastAPI):
    """앱 시작/종료 시 실행"""
    print("🚀 IndieBiz OS 서버 시작")

    # 스케줄러 자동 시작
    from scheduler import get_scheduler
    scheduler = get_scheduler()
    scheduler.start()

    # 채널 폴러 자동 시작
    from channel_poller import get_channel_poller
    poller = get_channel_poller()
    poller.start()

    # 시스템 AI Runner 자동 시작 (위임 체인 지원)
    from system_ai_runner import start_system_ai_runner, stop_system_ai_runner
    system_ai_runner = start_system_ai_runner()

    yield

    # 시스템 AI Runner 종료
    stop_system_ai_runner()

    # 채널 폴러 종료
    poller.stop()

    # 스케줄러 종료
    scheduler.stop()
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
        allowed_bases.extend(extra_paths.split(":"))

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

    uvicorn.run(
        "api:app",
        host="127.0.0.1",
        port=port,
        reload=True,
        log_level="warning"
    )
