"""
api_nas.py - 원격 Finder (NAS) API
IndieBiz OS - Remote File Access System

외부에서 Cloudflare Tunnel을 통해 파일에 접근할 수 있는 API
"""

import os
import sys
import platform
import stat as stat_module
import json
import hashlib
import secrets
import mimetypes
import subprocess
import shutil
import time
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, List
from functools import wraps

from fastapi import APIRouter, HTTPException, Request, Response, Query
from fastapi.responses import FileResponse, StreamingResponse, HTMLResponse
from pydantic import BaseModel

from runtime_utils import get_data_path as _get_data_path
from nas_subtitle import (
    detect_subtitles, srt_to_vtt, ass_to_vtt, smi_to_vtt,
    SUBTITLE_EXTENSIONS, LANG_NAMES, api_get_subtitles, api_get_subtitle_file,
)
from nas_music import api_music_search, api_music_stream
from nas_webapp import get_default_webapp_html

router = APIRouter(prefix="/nas", tags=["nas"])

# ============ 설정 ============

DATA_PATH = _get_data_path()
NAS_CONFIG_PATH = DATA_PATH / "nas_config.json"

# 스트리밍 청크 크기 (64KB - 8KB에서 8배 증가, Cloudflare Tunnel 호환성 유지)
STREAM_CHUNK_SIZE = 64 * 1024

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

# 설정 캐시 (디스크 I/O 감소)
_config_cache = None
_config_cache_mtime = 0

# ============ 트랜스코딩 설정 ============

FFMPEG_PATH = shutil.which("ffmpeg") or "/opt/homebrew/bin/ffmpeg"
FFPROBE_PATH = shutil.which("ffprobe") or "/opt/homebrew/bin/ffprobe"

# 프로브 결과 캐시: {(file_path, mtime): probe_result}
_probe_cache: dict = {}
_PROBE_CACHE_MAX = 200

# 활성 트랜스코딩 프로세스 추적
_active_transcodes: dict = {}

# 플랫폼별 H.264 인코더 자동 감지 (한 번만 실행)
_hw_encoder: str | None = None

def _detect_h264_encoder() -> str:
    """사용 가능한 H.264 인코더를 감지하여 반환. HW 가속 우선, 실패 시 libx264 폴백."""
    global _hw_encoder
    if _hw_encoder is not None:
        return _hw_encoder

    # 플랫폼별 HW 인코더 후보 (우선순위 순)
    candidates = []
    if sys.platform == "darwin":
        candidates = ["h264_videotoolbox"]
    elif sys.platform == "win32":
        candidates = ["h264_nvenc", "h264_qsv", "h264_amf"]
    else:  # Linux
        candidates = ["h264_nvenc", "h264_vaapi", "h264_qsv"]

    for enc in candidates:
        try:
            r = subprocess.run(
                [FFMPEG_PATH, "-hide_banner", "-f", "lavfi", "-i", "nullsrc=s=64x64:d=0.1",
                 "-c:v", enc, "-f", "null", "-"],
                capture_output=True, timeout=10
            )
            if r.returncode == 0:
                _hw_encoder = enc
                return _hw_encoder
        except Exception:
            continue

    # 모든 HW 인코더 실패 → 소프트웨어 폴백
    _hw_encoder = "libx264"
    return _hw_encoder

# 브라우저 호환 코덱/컨테이너
BROWSER_COMPATIBLE_VIDEO = {"h264", "av1", "vp8", "vp9"}
BROWSER_COMPATIBLE_AUDIO = {"aac", "mp3", "opus", "vorbis", "flac"}
BROWSER_COMPATIBLE_CONTAINERS = {"mp4", "webm", "ogg", "mov"}


# ============ 유틸리티 ============

def load_config() -> dict:
    """NAS 설정 로드 (mtime 기반 캐시 — 파일 변경 시에만 디스크 읽기)"""
    global _config_cache, _config_cache_mtime
    if NAS_CONFIG_PATH.exists():
        current_mtime = NAS_CONFIG_PATH.stat().st_mtime
        if _config_cache is not None and current_mtime == _config_cache_mtime:
            return _config_cache
        with open(NAS_CONFIG_PATH, 'r', encoding='utf-8') as f:
            config = json.load(f)
            merged = {**DEFAULT_CONFIG, **config}
            _config_cache = merged
            _config_cache_mtime = current_mtime
            return merged
    return DEFAULT_CONFIG.copy()


def save_config(config: dict):
    """NAS 설정 저장 (캐시 무효화 포함)"""
    global _config_cache, _config_cache_mtime
    config['updated_at'] = datetime.now().isoformat()
    with open(NAS_CONFIG_PATH, 'w', encoding='utf-8') as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    # 저장 후 캐시 즉시 갱신
    _config_cache = {**DEFAULT_CONFIG, **config}
    _config_cache_mtime = NAS_CONFIG_PATH.stat().st_mtime


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
    if not requested_path or requested_path in ("/", ""):
        # 첫 번째 허용 경로 반환
        return Path(base_paths[0])

    # 절대 경로로 변환 (Windows: C:\... / D:\... , Unix: /...)
    req_path = Path(requested_path)
    if req_path.is_absolute():
        target = req_path
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
    """파일/폴더 정보 반환 (stat 1회만 호출)"""
    st = path.stat()
    is_dir = stat_module.S_ISDIR(st.st_mode)

    info = {
        "name": path.name,
        "path": str(path),
        "is_dir": is_dir,
        "size": st.st_size if not is_dir else None,
        "modified": datetime.fromtimestamp(st.st_mtime).isoformat(),
        "created": datetime.fromtimestamp(st.st_ctime).isoformat(),
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


def probe_video(file_path: Path) -> dict:
    """ffprobe로 동영상 코덱/컨테이너/내장자막 분석 (mtime 기반 캐시)"""
    path_str = str(file_path)
    mtime = file_path.stat().st_mtime
    cache_key = (path_str, mtime)

    if cache_key in _probe_cache:
        return _probe_cache[cache_key]

    try:
        result = subprocess.run(
            [FFPROBE_PATH, "-v", "quiet", "-print_format", "json",
             "-show_streams", "-show_format", path_str],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode != 0:
            return {"error": "ffprobe failed", "needs_transcode": True}
        info = json.loads(result.stdout)
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
        return {"error": str(e), "needs_transcode": True}

    streams = info.get("streams", [])
    fmt = info.get("format", {})

    video_codec = None
    audio_codec = None
    subtitle_tracks = []
    duration = float(fmt.get("duration", 0))

    for s in streams:
        codec_type = s.get("codec_type")
        codec_name = s.get("codec_name", "").lower()
        if codec_type == "video" and video_codec is None:
            video_codec = codec_name
        elif codec_type == "audio" and audio_codec is None:
            audio_codec = codec_name
        elif codec_type == "subtitle":
            track_index = len(subtitle_tracks)
            lang = s.get("tags", {}).get("language", "")
            title = s.get("tags", {}).get("title", "")
            subtitle_tracks.append({
                "index": track_index,
                "codec": codec_name,
                "language": lang,
                "title": title or LANG_NAMES.get(lang, lang) or f"Track {track_index}",
            })

    container = file_path.suffix.lower().lstrip(".")

    video_ok = video_codec in BROWSER_COMPATIBLE_VIDEO
    audio_ok = audio_codec in BROWSER_COMPATIBLE_AUDIO or audio_codec is None
    container_ok = container in BROWSER_COMPATIBLE_CONTAINERS
    needs_transcode = not (video_ok and audio_ok and container_ok)

    probe_result = {
        "video_codec": video_codec,
        "audio_codec": audio_codec,
        "container": container,
        "duration": duration,
        "needs_transcode": needs_transcode,
        "video_compatible": video_ok,
        "audio_compatible": audio_ok,
        "container_compatible": container_ok,
        "subtitle_tracks": subtitle_tracks,
    }

    # 캐시 저장 (최대치 초과 시 절반 삭제)
    if len(_probe_cache) >= _PROBE_CACHE_MAX:
        keys = list(_probe_cache.keys())
        for k in keys[:len(keys) // 2]:
            del _probe_cache[k]
    _probe_cache[cache_key] = probe_result

    return probe_result


def _kill_transcode(process: subprocess.Popen):
    """트랜스코딩 FFmpeg 프로세스를 안전하게 종료"""
    try:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
    except Exception:
        pass


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
                    chunk_size = min(STREAM_CHUNK_SIZE, remaining)
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


# ============ 자막 API (nas_subtitle.py에서 로직 처리) ============

@router.get("/subtitles")
async def get_subtitles(
    request: Request,
    path: str = Query(..., description="동영상 파일 경로"),
):
    """동영상에 연결된 자막 파일 목록 반환"""
    return await api_get_subtitles(request, path, load_config, verify_session, get_safe_path)


@router.get("/subtitle")
async def get_subtitle_file(
    request: Request,
    path: str = Query(..., description="자막 파일 경로"),
    smi_class: str = Query(default="KRCC", description="SMI 언어 클래스"),
):
    """자막 파일을 WebVTT 형식으로 반환"""
    return await api_get_subtitle_file(request, path, smi_class, load_config, verify_session, get_safe_path)


# ============ 트랜스코딩 API ============

@router.get("/probe")
async def probe_file(
    request: Request,
    path: str = Query(..., description="동영상 파일 경로"),
):
    """동영상 코덱/컨테이너 분석 (트랜스코딩 필요 여부 판단)"""
    config = load_config()
    if not config.get("enabled"):
        raise HTTPException(status_code=503, detail="NAS 서비스가 비활성화되어 있습니다")

    session_token = request.cookies.get('nas_session') or request.headers.get('X-NAS-Session')
    if not session_token or not verify_session(session_token):
        raise HTTPException(status_code=401, detail="인증이 필요합니다")

    allowed_paths = config.get("allowed_paths", [])
    safe_path = get_safe_path(allowed_paths, path)

    if not safe_path or not safe_path.exists():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

    result = probe_video(safe_path)
    result["path"] = str(safe_path)
    return result


@router.get("/transcode")
async def transcode_video(
    request: Request,
    path: str = Query(..., description="동영상 파일 경로"),
    start: float = Query(default=0, description="시작 시간 (초)"),
):
    """동영상 실시간 트랜스코딩 (H.264+AAC fMP4 스트림)"""
    config = load_config()
    if not config.get("enabled"):
        raise HTTPException(status_code=503, detail="NAS 서비스가 비활성화되어 있습니다")

    session_token = request.cookies.get('nas_session') or request.headers.get('X-NAS-Session')
    if not session_token or not verify_session(session_token):
        raise HTTPException(status_code=401, detail="인증이 필요합니다")

    allowed_paths = config.get("allowed_paths", [])
    safe_path = get_safe_path(allowed_paths, path)

    if not safe_path or not safe_path.exists():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

    # 코덱 분석 → 스트림별로 copy 가능 여부 판단
    probe = probe_video(safe_path)
    v_ok = probe.get("video_compatible")
    a_ok = probe.get("audio_compatible")

    if v_ok:
        video_codec_args = ["-c:v", "copy"]
    else:
        encoder = _detect_h264_encoder()
        video_codec_args = ["-c:v", encoder, "-b:v", "4M"]
        # libx264는 preset 설정으로 속도/품질 균형
        if encoder == "libx264":
            video_codec_args.extend(["-preset", "fast"])

    if a_ok:
        audio_codec_args = ["-c:a", "copy"]
    else:
        audio_codec_args = ["-c:a", "aac", "-b:a", "128k", "-ac", "2"]

    # FFmpeg 명령 구성
    cmd = [FFMPEG_PATH]
    if start > 0:
        cmd.extend(["-ss", str(start)])
    cmd.extend([
        "-i", str(safe_path),
        *video_codec_args,
        *audio_codec_args,
        "-f", "mp4",
        "-movflags", "frag_keyframe+empty_moov+default_base_moof",
        "-v", "quiet",
        "pipe:1"
    ])

    try:
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="FFmpeg를 찾을 수 없습니다")

    request_id = f"{id(request)}_{time.time()}"
    _active_transcodes[request_id] = process

    def stream_ffmpeg():
        try:
            while True:
                chunk = process.stdout.read(STREAM_CHUNK_SIZE)
                if not chunk:
                    break
                yield chunk
        except GeneratorExit:
            pass
        finally:
            _kill_transcode(process)
            _active_transcodes.pop(request_id, None)

    return StreamingResponse(
        stream_ffmpeg(),
        media_type="video/mp4",
        headers={
            "Content-Type": "video/mp4",
            "Cache-Control": "no-cache",
            "X-Transcode-Start": str(start),
        },
    )


@router.get("/embedded-subtitle")
async def get_embedded_subtitle(
    request: Request,
    path: str = Query(..., description="동영상 파일 경로"),
    track: int = Query(default=0, description="자막 트랙 인덱스"),
):
    """내장 자막 추출 (MKV/MP4 → WebVTT 변환)"""
    config = load_config()
    if not config.get("enabled"):
        raise HTTPException(status_code=503, detail="NAS 서비스가 비활성화되어 있습니다")

    session_token = request.cookies.get('nas_session') or request.headers.get('X-NAS-Session')
    if not session_token or not verify_session(session_token):
        raise HTTPException(status_code=401, detail="인증이 필요합니다")

    allowed_paths = config.get("allowed_paths", [])
    safe_path = get_safe_path(allowed_paths, path)

    if not safe_path or not safe_path.exists():
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

    try:
        result = subprocess.run(
            [FFMPEG_PATH, "-i", str(safe_path),
             "-map", f"0:s:{track}", "-f", "webvtt", "-v", "quiet", "pipe:1"],
            capture_output=True, timeout=30
        )
        if result.returncode != 0 or not result.stdout:
            raise HTTPException(status_code=404, detail="자막 트랙을 추출할 수 없습니다")

        return Response(
            content=result.stdout,
            media_type="text/vtt; charset=utf-8",
            headers={"Content-Type": "text/vtt; charset=utf-8"},
        )
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="자막 추출 시간 초과")
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="FFmpeg를 찾을 수 없습니다")


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


# ============ 음악 스트리밍 (nas_music.py에서 로직 처리) ============

@router.get("/music/search")
@require_auth
async def music_search(request: Request, q: str = Query(..., min_length=1), count: int = 5):
    """YouTube 음악 검색"""
    return await api_music_search(request, q, count, STREAM_CHUNK_SIZE)


@router.get("/music/stream/{video_id}")
@require_auth
async def music_stream(request: Request, video_id: str):
    """YouTube 오디오 스트리밍"""
    return await api_music_stream(request, video_id, STREAM_CHUNK_SIZE)


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
    # 1) static/nas/index.html 우선
    static_webapp = Path(__file__).parent / "static" / "nas" / "index.html"
    if static_webapp.exists():
        return HTMLResponse(content=static_webapp.read_text(encoding='utf-8'))
    # 2) nas_webapp.html 폴백
    webapp_path = Path(__file__).parent / "nas_webapp.html"
    if webapp_path.exists():
        return HTMLResponse(content=webapp_path.read_text(encoding='utf-8'))

    # 기본 웹앱 (인라인 — nas_webapp.py에서 제공)
    return HTMLResponse(content=get_default_webapp_html())
