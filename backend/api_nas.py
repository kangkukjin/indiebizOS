"""
api_nas.py - 원격 Finder (NAS) API
IndieBiz OS - Remote File Access System

외부에서 Cloudflare Tunnel을 통해 파일에 접근할 수 있는 API
"""

import os
import json
import hashlib
import secrets
import mimetypes
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List
from functools import wraps

from fastapi import APIRouter, HTTPException, Request, Response, Query
from fastapi.responses import FileResponse, StreamingResponse, HTMLResponse
from pydantic import BaseModel

from runtime_utils import get_data_path as _get_data_path

router = APIRouter(prefix="/nas", tags=["nas"])

# ============ 설정 ============

DATA_PATH = _get_data_path()
NAS_CONFIG_PATH = DATA_PATH / "nas_config.json"

# 기본 설정
DEFAULT_CONFIG = {
    "enabled": False,
    "password_hash": None,  # SHA256 해시
    "allowed_paths": [],  # 허용된 경로 목록 (비어있으면 홈 디렉토리)
    "session_timeout_hours": 24,
    "created_at": None,
}

# 세션 저장소 (메모리)
sessions = {}


# ============ 유틸리티 ============

def load_config() -> dict:
    """NAS 설정 로드"""
    if NAS_CONFIG_PATH.exists():
        with open(NAS_CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
            # 기본값 병합
            return {**DEFAULT_CONFIG, **config}
    return DEFAULT_CONFIG.copy()


def save_config(config: dict):
    """NAS 설정 저장"""
    config['updated_at'] = datetime.now().isoformat()
    with open(NAS_CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


def hash_password(password: str) -> str:
    """비밀번호 SHA256 해시"""
    return hashlib.sha256(password.encode()).hexdigest()


def verify_session(session_token: str) -> bool:
    """세션 유효성 검증"""
    if session_token not in sessions:
        return False

    session = sessions[session_token]
    if datetime.now() > session['expires_at']:
        del sessions[session_token]
        return False

    return True


def get_safe_path(base_paths: List[str], requested_path: str) -> Optional[Path]:
    """
    경로 조작 공격 방지
    요청된 경로가 허용된 기본 경로 내에 있는지 확인
    """
    if not base_paths:
        # 기본값: 홈 디렉토리
        base_paths = [os.path.expanduser("~")]

    # 요청 경로 정규화
    if not requested_path or requested_path == "/":
        # 첫 번째 허용 경로 반환
        return Path(base_paths[0])

    # 절대 경로로 변환
    if requested_path.startswith("/"):
        target = Path(requested_path)
    else:
        target = Path(base_paths[0]) / requested_path

    # realpath로 심볼릭 링크 해석
    try:
        real_target = target.resolve()
    except (OSError, ValueError):
        return None

    # 허용된 경로 내에 있는지 확인
    for base in base_paths:
        try:
            real_base = Path(base).resolve()
            if str(real_target).startswith(str(real_base)):
                return real_target
        except (OSError, ValueError):
            continue

    return None


def get_file_info(path: Path) -> dict:
    """파일/폴더 정보 반환"""
    stat = path.stat()
    is_dir = path.is_dir()

    info = {
        "name": path.name,
        "path": str(path),
        "is_dir": is_dir,
        "size": stat.st_size if not is_dir else None,
        "modified": datetime.fromtimestamp(stat.st_mtime).isoformat(),
        "created": datetime.fromtimestamp(stat.st_ctime).isoformat(),
    }

    if not is_dir:
        # 파일 타입 추정
        mime_type, _ = mimetypes.guess_type(path.name)
        info["mime_type"] = mime_type

        # 파일 카테고리
        if mime_type:
            if mime_type.startswith("video/"):
                info["category"] = "video"
            elif mime_type.startswith("audio/"):
                info["category"] = "audio"
            elif mime_type.startswith("image/"):
                info["category"] = "image"
            elif mime_type.startswith("text/") or mime_type in ["application/json", "application/xml"]:
                info["category"] = "text"
            elif mime_type == "application/pdf":
                info["category"] = "pdf"
            else:
                info["category"] = "other"
        else:
            info["category"] = "other"

    return info


def format_size(size: int) -> str:
    """파일 크기를 읽기 쉬운 형태로 변환"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"


# ============ 인증 데코레이터 ============

def require_auth(func):
    """인증 필요 데코레이터"""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        request: Request = kwargs.get('request') or args[0]

        # 설정 확인
        config = load_config()
        if not config.get('enabled'):
            raise HTTPException(status_code=503, detail="NAS 서비스가 비활성화되어 있습니다")

        # 세션 토큰 확인
        session_token = request.cookies.get('nas_session') or request.headers.get('X-NAS-Session')

        if not session_token or not verify_session(session_token):
            raise HTTPException(status_code=401, detail="인증이 필요합니다")

        return await func(*args, **kwargs)

    return wrapper


# ============ 설정 API ============

class NASConfigUpdate(BaseModel):
    enabled: Optional[bool] = None
    password: Optional[str] = None  # 새 비밀번호 설정 시
    allowed_paths: Optional[List[str]] = None


@router.get("/config")
async def get_nas_config():
    """NAS 설정 조회 (비밀번호 제외)"""
    config = load_config()
    return {
        "enabled": config.get("enabled", False),
        "has_password": config.get("password_hash") is not None,
        "allowed_paths": config.get("allowed_paths", []),
        "session_timeout_hours": config.get("session_timeout_hours", 24),
    }


@router.put("/config")
async def update_nas_config(update: NASConfigUpdate):
    """NAS 설정 업데이트"""
    config = load_config()

    if update.enabled is not None:
        config["enabled"] = update.enabled

    if update.password is not None:
        if len(update.password) < 4:
            raise HTTPException(status_code=400, detail="비밀번호는 4자 이상이어야 합니다")
        config["password_hash"] = hash_password(update.password)

    if update.allowed_paths is not None:
        # 경로 유효성 검증
        valid_paths = []
        for p in update.allowed_paths:
            path = Path(p).expanduser()
            if path.exists() and path.is_dir():
                valid_paths.append(str(path.resolve()))
        config["allowed_paths"] = valid_paths

    if config.get("created_at") is None:
        config["created_at"] = datetime.now().isoformat()

    save_config(config)

    return {"status": "success", "message": "설정이 업데이트되었습니다"}


# ============ 인증 API ============

class LoginRequest(BaseModel):
    password: str


@router.post("/auth/login")
async def nas_login(request: Request, login: LoginRequest, response: Response):
    """NAS 로그인"""
    config = load_config()

    if not config.get("enabled"):
        raise HTTPException(status_code=503, detail="NAS 서비스가 비활성화되어 있습니다")

    if not config.get("password_hash"):
        raise HTTPException(status_code=400, detail="비밀번호가 설정되지 않았습니다")

    # 비밀번호 확인
    if hash_password(login.password) != config["password_hash"]:
        raise HTTPException(status_code=401, detail="비밀번호가 올바르지 않습니다")

    # 세션 생성
    session_token = secrets.token_urlsafe(32)
    timeout_hours = config.get("session_timeout_hours", 24)

    sessions[session_token] = {
        "created_at": datetime.now(),
        "expires_at": datetime.now() + timedelta(hours=timeout_hours),
        "ip": request.client.host if request.client else "unknown",
    }

    # 쿠키 설정
    response.set_cookie(
        key="nas_session",
        value=session_token,
        max_age=timeout_hours * 3600,
        httponly=True,
        samesite="lax",
    )

    return {"status": "success", "message": "로그인 성공", "session_token": session_token}


@router.post("/auth/logout")
async def nas_logout(request: Request, response: Response):
    """NAS 로그아웃"""
    session_token = request.cookies.get('nas_session')

    if session_token and session_token in sessions:
        del sessions[session_token]

    response.delete_cookie("nas_session")

    return {"status": "success", "message": "로그아웃되었습니다"}


@router.get("/auth/check")
async def check_auth(request: Request):
    """인증 상태 확인"""
    config = load_config()

    if not config.get("enabled"):
        return {"authenticated": False, "enabled": False}

    session_token = request.cookies.get('nas_session') or request.headers.get('X-NAS-Session')
    authenticated = session_token and verify_session(session_token)

    return {"authenticated": authenticated, "enabled": True}


# ============ 파일 API ============

@router.get("/files")
async def list_files(
    request: Request,
    path: str = Query(default="", description="디렉토리 경로"),
    show_hidden: bool = Query(default=False, description="숨김 파일 표시"),
):
    """파일 목록 조회"""
    # 인증 확인
    config = load_config()
    if not config.get("enabled"):
        raise HTTPException(status_code=503, detail="NAS 서비스가 비활성화되어 있습니다")

    session_token = request.cookies.get('nas_session') or request.headers.get('X-NAS-Session')
    if not session_token or not verify_session(session_token):
        raise HTTPException(status_code=401, detail="인증이 필요합니다")

    # 경로 검증
    allowed_paths = config.get("allowed_paths", [])
    safe_path = get_safe_path(allowed_paths, path)

    if not safe_path or not safe_path.exists():
        raise HTTPException(status_code=404, detail="경로를 찾을 수 없습니다")

    if not safe_path.is_dir():
        raise HTTPException(status_code=400, detail="디렉토리가 아닙니다")

    # 파일 목록 생성
    items = []
    try:
        for item in safe_path.iterdir():
            # 숨김 파일 필터링
            if not show_hidden and item.name.startswith('.'):
                continue

            try:
                items.append(get_file_info(item))
            except (PermissionError, OSError):
                # 접근 불가 파일 무시
                continue
    except PermissionError:
        raise HTTPException(status_code=403, detail="접근 권한이 없습니다")

    # 정렬: 폴더 먼저, 그 다음 이름순
    items.sort(key=lambda x: (not x['is_dir'], x['name'].lower()))

    # 상위 경로 계산
    parent_path = None
    for base in (allowed_paths or [os.path.expanduser("~")]):
        base_resolved = Path(base).resolve()
        if safe_path != base_resolved and str(safe_path).startswith(str(base_resolved)):
            parent_path = str(safe_path.parent)
            break

    return {
        "path": str(safe_path),
        "parent": parent_path,
        "items": items,
        "total": len(items),
    }


@router.get("/file")
async def get_file(
    request: Request,
    path: str = Query(..., description="파일 경로"),
):
    """파일 다운로드/스트리밍"""
    # 인증 확인
    config = load_config()
    if not config.get("enabled"):
        raise HTTPException(status_code=503, detail="NAS 서비스가 비활성화되어 있습니다")

    session_token = request.cookies.get('nas_session') or request.headers.get('X-NAS-Session')
    if not session_token or not verify_session(session_token):
        raise HTTPException(status_code=401, detail="인증이 필요합니다")

    # 경로 검증
    allowed_paths = config.get("allowed_paths", [])
    safe_path = get_safe_path(allowed_paths, path)

    if not safe_path or not safe_path.exists():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

    if safe_path.is_dir():
        raise HTTPException(status_code=400, detail="디렉토리는 다운로드할 수 없습니다")

    # MIME 타입 결정
    mime_type, _ = mimetypes.guess_type(safe_path.name)
    if not mime_type:
        mime_type = "application/octet-stream"

    # Range 요청 처리 (동영상 스트리밍용)
    range_header = request.headers.get("range")
    file_size = safe_path.stat().st_size

    if range_header:
        # Range 헤더 파싱
        range_match = range_header.replace("bytes=", "").split("-")
        start = int(range_match[0]) if range_match[0] else 0
        end = int(range_match[1]) if range_match[1] else file_size - 1

        if start >= file_size:
            raise HTTPException(status_code=416, detail="Range Not Satisfiable")

        end = min(end, file_size - 1)
        content_length = end - start + 1

        def iter_file():
            with open(safe_path, "rb") as f:
                f.seek(start)
                remaining = content_length
                while remaining > 0:
                    chunk_size = min(8192, remaining)
                    data = f.read(chunk_size)
                    if not data:
                        break
                    remaining -= len(data)
                    yield data

        return StreamingResponse(
            iter_file(),
            status_code=206,
            media_type=mime_type,
            headers={
                "Content-Range": f"bytes {start}-{end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(content_length),
            },
        )

    # 전체 파일 반환
    return FileResponse(
        safe_path,
        media_type=mime_type,
        filename=safe_path.name,
        headers={"Accept-Ranges": "bytes"},
    )


@router.get("/text")
async def get_text_file(
    request: Request,
    path: str = Query(..., description="파일 경로"),
    encoding: str = Query(default="utf-8", description="인코딩"),
):
    """텍스트 파일 내용 조회"""
    # 인증 확인
    config = load_config()
    if not config.get("enabled"):
        raise HTTPException(status_code=503, detail="NAS 서비스가 비활성화되어 있습니다")

    session_token = request.cookies.get('nas_session') or request.headers.get('X-NAS-Session')
    if not session_token or not verify_session(session_token):
        raise HTTPException(status_code=401, detail="인증이 필요합니다")

    # 경로 검증
    allowed_paths = config.get("allowed_paths", [])
    safe_path = get_safe_path(allowed_paths, path)

    if not safe_path or not safe_path.exists():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

    if safe_path.is_dir():
        raise HTTPException(status_code=400, detail="디렉토리입니다")

    # 파일 크기 제한 (10MB)
    if safe_path.stat().st_size > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="파일이 너무 큽니다 (최대 10MB)")

    try:
        content = safe_path.read_text(encoding=encoding)
        return {"path": str(safe_path), "content": content, "size": len(content)}
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail=f"파일을 {encoding}으로 읽을 수 없습니다")


# ============ 상태 API ============

@router.get("/status")
async def get_nas_status():
    """NAS 서비스 상태"""
    config = load_config()

    return {
        "enabled": config.get("enabled", False),
        "has_password": config.get("password_hash") is not None,
        "active_sessions": len(sessions),
        "allowed_paths_count": len(config.get("allowed_paths", [])),
    }


# ============ 웹앱 서빙 ============

@router.get("/app", response_class=HTMLResponse)
async def serve_nas_webapp(request: Request):
    """NAS 웹앱 HTML 반환"""
    config = load_config()

    if not config.get("enabled"):
        return HTMLResponse(content="""
        <!DOCTYPE html>
        <html>
        <head><title>NAS - 비활성화</title></head>
        <body style="font-family: sans-serif; padding: 50px; text-align: center;">
            <h1>🔒 NAS 서비스가 비활성화되어 있습니다</h1>
            <p>IndieBiz OS 설정에서 원격 Finder를 활성화해주세요.</p>
        </body>
        </html>
        """, status_code=503)

    # 웹앱 HTML 반환 (별도 파일 또는 인라인)
    webapp_path = Path(__file__).parent / "nas_webapp.html"
    if webapp_path.exists():
        return HTMLResponse(content=webapp_path.read_text(encoding='utf-8'))

    # 기본 웹앱 (인라인)
    return HTMLResponse(content=get_default_webapp_html())


def get_default_webapp_html() -> str:
    """기본 NAS 웹앱 HTML"""
    return '''<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>IndieBiz Remote Finder</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <style>
        .file-item:hover { background-color: #f3f4f6; }
        .file-item.selected { background-color: #dbeafe; }
        video { max-height: 70vh; }
        img.preview { max-height: 70vh; max-width: 100%; object-fit: contain; }
    </style>
</head>
<body class="bg-gray-100 min-h-screen">
    <div id="app" class="container mx-auto p-4 max-w-4xl">
        <!-- 로그인 화면 -->
        <div id="login-screen" class="hidden">
            <div class="bg-white rounded-xl shadow-lg p-8 max-w-md mx-auto mt-20">
                <h1 class="text-2xl font-bold text-center mb-6">🗂️ IndieBiz Remote Finder</h1>
                <form id="login-form" class="space-y-4">
                    <input type="password" id="password" placeholder="비밀번호"
                        class="w-full px-4 py-3 border rounded-lg focus:ring-2 focus:ring-blue-500 focus:outline-none">
                    <button type="submit"
                        class="w-full py-3 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition">
                        로그인
                    </button>
                    <p id="login-error" class="text-red-500 text-center hidden"></p>
                </form>
            </div>
        </div>

        <!-- 파일 탐색기 화면 -->
        <div id="explorer-screen" class="hidden">
            <!-- 헤더 -->
            <div class="bg-white rounded-xl shadow-lg p-4 mb-4">
                <div class="flex items-center justify-between">
                    <h1 class="text-xl font-bold">🗂️ Remote Finder</h1>
                    <button id="logout-btn" class="text-gray-500 hover:text-red-500">로그아웃</button>
                </div>
                <!-- 경로 표시 -->
                <div id="breadcrumb" class="mt-2 text-sm text-gray-600 flex items-center gap-2">
                    <span id="current-path">/</span>
                </div>
            </div>

            <!-- 파일 목록 -->
            <div class="bg-white rounded-xl shadow-lg overflow-hidden">
                <div id="file-list" class="divide-y">
                    <!-- 파일 아이템들이 여기에 렌더링됨 -->
                </div>
                <div id="empty-message" class="hidden p-8 text-center text-gray-500">
                    폴더가 비어있습니다
                </div>
            </div>
        </div>

        <!-- 미리보기 모달 -->
        <div id="preview-modal" class="hidden fixed inset-0 bg-black/80 flex items-center justify-center z-50 p-4">
            <div class="bg-white rounded-xl max-w-4xl w-full max-h-[90vh] overflow-hidden">
                <div class="flex items-center justify-between p-4 border-b">
                    <h3 id="preview-title" class="font-semibold truncate"></h3>
                    <button id="close-preview" class="text-gray-500 hover:text-gray-700 text-2xl">&times;</button>
                </div>
                <div id="preview-content" class="p-4 overflow-auto max-h-[calc(90vh-80px)]">
                    <!-- 미리보기 콘텐츠 -->
                </div>
            </div>
        </div>
    </div>

    <script>
        const API_BASE = window.location.origin + '/nas';
        let currentPath = '';
        let sessionToken = null;

        // 초기화
        async function init() {
            const authCheck = await fetch(API_BASE + '/auth/check', { credentials: 'include' });
            const authData = await authCheck.json();

            if (!authData.enabled) {
                document.body.innerHTML = '<div class="p-20 text-center"><h1 class="text-2xl">🔒 NAS 비활성화</h1><p>설정에서 활성화해주세요.</p></div>';
                return;
            }

            if (authData.authenticated) {
                showExplorer();
                loadFiles('');
            } else {
                showLogin();
            }
        }

        function showLogin() {
            document.getElementById('login-screen').classList.remove('hidden');
            document.getElementById('explorer-screen').classList.add('hidden');
        }

        function showExplorer() {
            document.getElementById('login-screen').classList.add('hidden');
            document.getElementById('explorer-screen').classList.remove('hidden');
        }

        // 로그인
        document.getElementById('login-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            const password = document.getElementById('password').value;
            const errorEl = document.getElementById('login-error');

            try {
                const res = await fetch(API_BASE + '/auth/login', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ password }),
                    credentials: 'include'
                });

                if (res.ok) {
                    const data = await res.json();
                    sessionToken = data.session_token;
                    showExplorer();
                    loadFiles('');
                } else {
                    errorEl.textContent = '비밀번호가 올바르지 않습니다';
                    errorEl.classList.remove('hidden');
                }
            } catch (err) {
                errorEl.textContent = '연결 오류';
                errorEl.classList.remove('hidden');
            }
        });

        // 로그아웃
        document.getElementById('logout-btn').addEventListener('click', async () => {
            await fetch(API_BASE + '/auth/logout', { method: 'POST', credentials: 'include' });
            showLogin();
        });

        // 파일 목록 로드
        async function loadFiles(path) {
            currentPath = path;

            const res = await fetch(API_BASE + '/files?path=' + encodeURIComponent(path), {
                credentials: 'include'
            });

            if (res.status === 401) {
                showLogin();
                return;
            }

            const data = await res.json();
            renderFiles(data);
        }

        // 파일 목록 렌더링
        function renderFiles(data) {
            const listEl = document.getElementById('file-list');
            const emptyEl = document.getElementById('empty-message');
            const pathEl = document.getElementById('current-path');

            pathEl.textContent = data.path;

            if (data.items.length === 0) {
                listEl.innerHTML = '';
                emptyEl.classList.remove('hidden');
                return;
            }

            emptyEl.classList.add('hidden');

            let html = '';

            // 상위 폴더
            if (data.parent) {
                html += `
                    <div class="file-item p-3 flex items-center gap-3 cursor-pointer" onclick="loadFiles('${data.parent}')">
                        <span class="text-2xl">⬆️</span>
                        <span class="text-gray-600">상위 폴더</span>
                    </div>
                `;
            }

            for (const item of data.items) {
                const icon = item.is_dir ? '📁' : getFileIcon(item.category);
                const size = item.size ? formatSize(item.size) : '';
                const escapedPath = item.path.replace(/'/g, "\\'");

                if (item.is_dir) {
                    html += `
                        <div class="file-item p-3 flex items-center gap-3 cursor-pointer" onclick="loadFiles('${escapedPath}')">
                            <span class="text-2xl">${icon}</span>
                            <div class="flex-1 min-w-0">
                                <p class="font-medium truncate">${item.name}</p>
                            </div>
                        </div>
                    `;
                } else {
                    html += `
                        <div class="file-item p-3 flex items-center gap-3 cursor-pointer" onclick="openFile('${escapedPath}', '${item.category}', '${item.name}')">
                            <span class="text-2xl">${icon}</span>
                            <div class="flex-1 min-w-0">
                                <p class="font-medium truncate">${item.name}</p>
                                <p class="text-sm text-gray-500">${size}</p>
                            </div>
                        </div>
                    `;
                }
            }

            listEl.innerHTML = html;
        }

        function getFileIcon(category) {
            const icons = {
                video: '🎬',
                audio: '🎵',
                image: '🖼️',
                text: '📄',
                pdf: '📕',
                other: '📦'
            };
            return icons[category] || '📦';
        }

        function formatSize(bytes) {
            const units = ['B', 'KB', 'MB', 'GB'];
            let i = 0;
            while (bytes >= 1024 && i < units.length - 1) {
                bytes /= 1024;
                i++;
            }
            return bytes.toFixed(1) + ' ' + units[i];
        }

        // 파일 열기
        function openFile(path, category, name) {
            const modal = document.getElementById('preview-modal');
            const title = document.getElementById('preview-title');
            const content = document.getElementById('preview-content');

            title.textContent = name;

            const fileUrl = API_BASE + '/file?path=' + encodeURIComponent(path);

            if (category === 'video') {
                content.innerHTML = `<video controls autoplay class="w-full"><source src="${fileUrl}"></video>`;
            } else if (category === 'audio') {
                content.innerHTML = `<audio controls autoplay class="w-full"><source src="${fileUrl}"></audio>`;
            } else if (category === 'image') {
                content.innerHTML = `<img src="${fileUrl}" class="preview mx-auto">`;
            } else if (category === 'text') {
                fetch(API_BASE + '/text?path=' + encodeURIComponent(path), { credentials: 'include' })
                    .then(r => r.json())
                    .then(data => {
                        content.innerHTML = `<pre class="whitespace-pre-wrap text-sm bg-gray-50 p-4 rounded">${escapeHtml(data.content)}</pre>`;
                    });
            } else if (category === 'pdf') {
                content.innerHTML = `<iframe src="${fileUrl}" class="w-full h-[70vh]"></iframe>`;
            } else {
                content.innerHTML = `<div class="text-center py-8"><a href="${fileUrl}" download class="px-6 py-3 bg-blue-500 text-white rounded-lg hover:bg-blue-600">다운로드</a></div>`;
            }

            modal.classList.remove('hidden');
        }

        function escapeHtml(str) {
            return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        }

        // 미리보기 닫기
        document.getElementById('close-preview').addEventListener('click', () => {
            document.getElementById('preview-modal').classList.add('hidden');
            document.getElementById('preview-content').innerHTML = '';
        });

        document.getElementById('preview-modal').addEventListener('click', (e) => {
            if (e.target.id === 'preview-modal') {
                document.getElementById('preview-modal').classList.add('hidden');
                document.getElementById('preview-content').innerHTML = '';
            }
        });

        // ESC 키로 모달 닫기
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                document.getElementById('preview-modal').classList.add('hidden');
                document.getElementById('preview-content').innerHTML = '';
            }
        });

        // 시작
        init();
    </script>
</body>
</html>'''
