"""
api.py - IndieBiz OS Core API Server
최소 시스템: FastAPI + 시스템 AI + 기본 도구
"""

import os
import sys
from pathlib import Path
from datetime import datetime
from contextlib import asynccontextmanager

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

    yield

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

# CORS 설정 (Electron에서 접근 허용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
from api_prompt_generator import router as prompt_generator_router, init_manager as init_prompt_generator_manager
from api_gmail import router as gmail_router
from api_business import router as business_router, init_manager as init_business_manager
from api_multi_chat import router as multi_chat_router, init_manager as init_multi_chat_manager
from api_pcmanager import router as pcmanager_router
from api_photo import router as photo_router

# 매니저 주입
init_projects_managers(project_manager, switch_manager)
init_switches_manager(switch_manager)
init_config_manager(project_manager)
init_agents_manager(project_manager)
init_conversations_manager(project_manager)
init_websocket_manager(project_manager)
init_prompt_generator_manager(project_manager)
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
app.include_router(prompt_generator_router, tags=["prompt-generator"])
app.include_router(gmail_router, tags=["gmail"])
app.include_router(business_router, tags=["business"])
app.include_router(multi_chat_router, tags=["multi-chat"])
app.include_router(pcmanager_router, tags=["pcmanager"])
app.include_router(photo_router, tags=["photo"])


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
    """로컬 이미지 파일 서빙"""
    import os.path

    abs_path = os.path.abspath(path)
    allowed_base = str(BASE_PATH)

    if not abs_path.startswith(allowed_base):
        return {"error": "접근 권한 없음"}

    if not os.path.exists(abs_path):
        return {"error": "파일을 찾을 수 없음"}

    ext = os.path.splitext(abs_path)[1].lower()
    if ext not in ['.jpg', '.jpeg', '.png', '.gif', '.webp']:
        return {"error": "이미지 파일만 허용"}

    mime_types = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.webp': 'image/webp'
    }

    return FileResponse(abs_path, media_type=mime_types.get(ext, 'image/jpeg'))


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
