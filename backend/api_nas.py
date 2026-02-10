"""
api_nas.py - 원격 Finder (NAS) API
IndieBiz OS - Remote File Access System

외부에서 Cloudflare Tunnel을 통해 파일에 접근할 수 있는 API
"""

import os
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


# ============ 자막 API ============

# 지원하는 자막 확장자
SUBTITLE_EXTENSIONS = {'.srt', '.vtt', '.ass', '.ssa', '.smi'}

# 언어 코드 → 표시명
LANG_NAMES = {
    'ko': '한국어', 'en': 'English', 'ja': '日本語', 'zh': '中文',
    'es': 'Español', 'fr': 'Français', 'de': 'Deutsch', 'pt': 'Português',
    'ru': 'Русский', 'it': 'Italiano', 'th': 'ไทย', 'vi': 'Tiếng Việt',
}


def srt_to_vtt(srt_content: str) -> str:
    """SRT 자막을 WebVTT 형식으로 변환"""
    lines = srt_content.replace('\r\n', '\n').replace('\r', '\n').split('\n')
    vtt_lines = ['WEBVTT', '']

    for line in lines:
        # SRT 타임코드: 00:01:23,456 --> 00:01:25,789
        # VTT 타임코드: 00:01:23.456 --> 00:01:25.789
        if '-->' in line:
            line = line.replace(',', '.')
        vtt_lines.append(line)

    return '\n'.join(vtt_lines)


def ass_to_vtt(ass_content: str) -> str:
    """ASS/SSA 자막을 WebVTT 형식으로 변환 (기본 텍스트만 추출)"""
    import re
    vtt_lines = ['WEBVTT', '']
    counter = 1

    for line in ass_content.split('\n'):
        line = line.strip()
        # Dialogue: 0,0:01:23.45,0:01:25.67,Default,,0,0,0,,자막 텍스트
        if line.startswith('Dialogue:'):
            parts = line.split(',', 9)
            if len(parts) >= 10:
                start_raw = parts[1].strip()
                end_raw = parts[2].strip()

                # ASS 타임코드: H:MM:SS.CC → HH:MM:SS.CCC
                def convert_ass_time(t):
                    # H:MM:SS.CC 형식
                    match = re.match(r'(\d+):(\d{2}):(\d{2})\.(\d{2,3})', t)
                    if match:
                        h, m, s, cs = match.groups()
                        ms = cs.ljust(3, '0')[:3]
                        return f"{int(h):02d}:{m}:{s}.{ms}"
                    return t

                start = convert_ass_time(start_raw)
                end = convert_ass_time(end_raw)

                # 텍스트에서 ASS 태그 제거 {\tag} 및 \N → 줄바꿈
                text = parts[9]
                text = re.sub(r'\{[^}]*\}', '', text)
                text = text.replace('\\N', '\n').replace('\\n', '\n').strip()

                if text:
                    vtt_lines.append(str(counter))
                    vtt_lines.append(f"{start} --> {end}")
                    vtt_lines.append(text)
                    vtt_lines.append('')
                    counter += 1

    return '\n'.join(vtt_lines)


def smi_to_vtt(smi_content: str, lang_class: str = "KRCC") -> str:
    """SMI(SAMI) 자막을 WebVTT 형식으로 변환. lang_class로 언어 필터링 (기본 한국어)"""
    import re
    vtt_lines = ['WEBVTT', '']

    # SYNC + P 블록 추출 (클래스 정보 포함)
    sync_pattern = re.compile(
        r'<SYNC\s+Start\s*=\s*(\d+)\s*>\s*<P\s+Class\s*=\s*(\w+)\s*>(.*?)(?=<SYNC|</BODY|$)',
        re.IGNORECASE | re.DOTALL
    )

    matches = sync_pattern.findall(smi_content)
    if not matches:
        # Class 속성 없는 간단한 SMI → 전체 추출
        simple_pattern = re.compile(
            r'<SYNC\s+Start\s*=\s*(\d+)\s*>.*?<P[^>]*>(.*?)(?=<SYNC|</BODY|$)',
            re.IGNORECASE | re.DOTALL
        )
        matches = [(ms, lang_class, text) for ms, text in simple_pattern.findall(smi_content)]

    if not matches:
        return 'WEBVTT\n'

    # 지정 언어 클래스만 필터링
    cues = []
    for ms_str, cls, raw_text in matches:
        if cls.upper() != lang_class.upper():
            continue
        ms = int(ms_str)
        # HTML 태그 제거
        text = re.sub(r'<[^>]+>', '', raw_text)
        # <br> → 줄바꿈 (태그 제거 전에 처리)
        raw_text_br = re.sub(r'<br\s*/?\s*>', '\n', raw_text, flags=re.IGNORECASE)
        text = re.sub(r'<[^>]+>', '', raw_text_br)
        # HTML 엔티티 변환
        text = text.replace('&nbsp;', ' ').replace('&lt;', '<').replace('&gt;', '>').replace('&amp;', '&')
        text = text.strip()
        if not text or text == ' ':
            cues.append((ms, ''))
        else:
            cues.append((ms, text))

    # 밀리초 → VTT 타임코드
    def ms_to_vtt_time(ms):
        h = ms // 3600000
        m = (ms % 3600000) // 60000
        s = (ms % 60000) // 1000
        ms_rem = ms % 1000
        return f"{h:02d}:{m:02d}:{s:02d}.{ms_rem:03d}"

    counter = 1
    for i, (start_ms, text) in enumerate(cues):
        if not text:
            continue
        # 다음 큐의 시작을 종료 시간으로 사용
        end_ms = start_ms + 5000
        for j in range(i + 1, len(cues)):
            end_ms = cues[j][0]
            break
        if end_ms <= start_ms:
            end_ms = start_ms + 5000

        vtt_lines.append(str(counter))
        vtt_lines.append(f"{ms_to_vtt_time(start_ms)} --> {ms_to_vtt_time(end_ms)}")
        vtt_lines.append(text)
        vtt_lines.append('')
        counter += 1

    return '\n'.join(vtt_lines)


def _detect_smi_languages(file_path: Path) -> list:
    """SMI 파일에서 사용 가능한 언어 클래스를 감지"""
    import re
    try:
        raw = file_path.read_bytes()
        for enc in ['utf-8', 'utf-8-sig', 'cp949', 'euc-kr', 'latin-1']:
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            return [('KRCC', 'ko', '한국어')]

        # .KRCC {Name:Korean; lang:ko-KR; ...} 패턴
        classes = re.findall(
            r'\.(\w+)\s*\{[^}]*Name\s*:\s*([^;]*)[^}]*lang\s*:\s*([^;}\s]*)',
            text, re.IGNORECASE
        )
        if classes:
            results = []
            for cls_name, name, lang in classes:
                lang_code = lang.split('-')[0].lower() if lang else ''
                lang_label = name.strip() or LANG_NAMES.get(lang_code, lang_code)
                results.append((cls_name, lang_code, lang_label))
            return results
    except Exception:
        pass
    return [('KRCC', 'ko', '한국어')]


def detect_subtitles(video_path: Path) -> list:
    """동영상 파일과 같은 디렉토리에서 자막 파일 탐지"""
    video_stem = video_path.stem
    video_dir = video_path.parent
    subtitles = []

    if not video_dir.exists():
        return subtitles

    for f in video_dir.iterdir():
        if not f.is_file():
            continue
        if f.suffix.lower() not in SUBTITLE_EXTENSIONS:
            continue

        # 동영상 이름으로 시작하는 자막만 (예: movie.srt, movie.ko.srt)
        if not f.stem.lower().startswith(video_stem.lower()):
            continue

        # SMI 파일: 내부 언어 클래스별로 별도 항목 생성
        if f.suffix.lower() == '.smi':
            langs = _detect_smi_languages(f)
            for cls_name, lang_code, lang_label in langs:
                subtitles.append({
                    'path': str(f),
                    'filename': f.name,
                    'format': 'smi',
                    'lang_code': lang_code,
                    'lang_label': lang_label,
                    'smi_class': cls_name,
                })
            continue

        # 일반 자막: 언어 태그 추출 (movie.ko.srt → ko)
        remaining = f.stem[len(video_stem):]
        lang_code = ''
        if remaining.startswith('.') and len(remaining) > 1:
            lang_code = remaining[1:]

        lang_label = LANG_NAMES.get(lang_code, lang_code) if lang_code else '기본'

        subtitles.append({
            'path': str(f),
            'filename': f.name,
            'format': f.suffix.lower().lstrip('.'),
            'lang_code': lang_code,
            'lang_label': lang_label,
        })

    # 정렬: 한국어 우선 → 영어 → 나머지
    priority = {'ko': 0, '': 1, 'en': 2}
    subtitles.sort(key=lambda s: (priority.get(s['lang_code'], 99), s['lang_code']))

    return subtitles


@router.get("/subtitles")
async def get_subtitles(
    request: Request,
    path: str = Query(..., description="동영상 파일 경로"),
):
    """동영상에 연결된 자막 파일 목록 반환"""
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

    subtitles = detect_subtitles(safe_path)

    return {"video": str(safe_path), "subtitles": subtitles}


@router.get("/subtitle")
async def get_subtitle_file(
    request: Request,
    path: str = Query(..., description="자막 파일 경로"),
    smi_class: str = Query(default="KRCC", description="SMI 언어 클래스"),
):
    """자막 파일을 WebVTT 형식으로 반환 (SRT/ASS/SMI 자동 변환)"""
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
        raise HTTPException(status_code=404, detail="자막 파일을 찾을 수 없습니다")

    suffix = safe_path.suffix.lower()
    if suffix not in SUBTITLE_EXTENSIONS:
        raise HTTPException(status_code=400, detail="지원하지 않는 자막 형식입니다")

    # 파일 읽기 (바이트를 한 번만 읽고 여러 인코딩 시도 — 디스크 I/O 1회)
    raw_bytes = safe_path.read_bytes()
    content = None
    for encoding in ['utf-8', 'utf-8-sig', 'cp949', 'euc-kr', 'shift_jis', 'latin-1']:
        try:
            content = raw_bytes.decode(encoding)
            break
        except (UnicodeDecodeError, LookupError):
            continue

    if content is None:
        raise HTTPException(status_code=400, detail="자막 파일 인코딩을 인식할 수 없습니다")

    # VTT 변환
    if suffix == '.vtt':
        vtt_content = content
    elif suffix == '.srt':
        vtt_content = srt_to_vtt(content)
    elif suffix in ('.ass', '.ssa'):
        vtt_content = ass_to_vtt(content)
    elif suffix == '.smi':
        vtt_content = smi_to_vtt(content, lang_class=smi_class)
    else:
        raise HTTPException(status_code=400, detail="변환할 수 없는 형식입니다")

    return Response(
        content=vtt_content,
        media_type="text/vtt; charset=utf-8",
        headers={"Content-Type": "text/vtt; charset=utf-8"},
    )


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
        video_codec_args = ["-c:v", "h264_videotoolbox", "-b:v", "4M"]

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


# ============ 음악 스트리밍 ============

def _search_youtube(query: str, count: int = 5) -> list:
    """yt-dlp로 YouTube 검색"""
    import yt_dlp
    results = []
    with yt_dlp.YoutubeDL({
        "quiet": True, "no_warnings": True,
        "extract_flat": True,
        "default_search": f"ytsearch{count}",
    }) as ydl:
        info = ydl.extract_info(f"ytsearch{count}:{query}", download=False)
        for entry in (info.get("entries") or []):
            vid = entry.get("id", "")
            if vid.startswith("UC") or entry.get("_type") == "playlist":
                continue
            dur = entry.get("duration") or 0
            dur_str = f"{int(dur)//60}:{int(dur)%60:02d}" if dur > 0 else ""
            results.append({
                "video_id": vid,
                "title": entry.get("title", ""),
                "channel": entry.get("uploader", entry.get("channel", "")),
                "duration": dur_str,
                "duration_seconds": int(dur),
                "thumbnail": f"https://i.ytimg.com/vi/{vid}/mqdefault.jpg",
            })
    return results


@router.get("/music/search")
@require_auth
async def music_search(request: Request, q: str = Query(..., min_length=1), count: int = 5):
    """YouTube 음악 검색"""
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        results = await loop.run_in_executor(None, _search_youtube, q, min(count, 10))
        return {"results": results, "query": q}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"검색 실패: {str(e)}")


@router.get("/music/stream/{video_id}")
@require_auth
async def music_stream(request: Request, video_id: str):
    """YouTube 오디오 스트리밍 (yt-dlp → stdout → 클라이언트)"""
    import asyncio, re
    if not re.match(r'^[a-zA-Z0-9_-]{11}$', video_id):
        raise HTTPException(status_code=400, detail="잘못된 video_id")

    url = f"https://www.youtube.com/watch?v={video_id}"
    cmd = [
        "yt-dlp",
        "-f", "bestaudio[ext=webm]/bestaudio",
        "-o", "-",
        "--no-playlist",
        "--no-warnings",
        url,
    ]
    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )

        async def audio_gen():
            try:
                while True:
                    chunk = await process.stdout.read(STREAM_CHUNK_SIZE)
                    if not chunk:
                        break
                    yield chunk
            finally:
                if process.returncode is None:
                    process.kill()
                    await process.wait()

        return StreamingResponse(
            audio_gen(),
            media_type="audio/webm",
            headers={"Cache-Control": "no-cache"},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"스트리밍 실패: {str(e)}")


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
        async function openFile(path, category, name) {
            const modal = document.getElementById('preview-modal');
            const title = document.getElementById('preview-title');
            const content = document.getElementById('preview-content');

            title.textContent = name;

            const fileUrl = API_BASE + '/file?path=' + encodeURIComponent(path);

            if (category === 'video') {
                // 코덱 분석
                let probeData = null;
                try {
                    const probeRes = await fetch(API_BASE + '/probe?path=' + encodeURIComponent(path), { credentials: 'include' });
                    if (probeRes.ok) probeData = await probeRes.json();
                } catch(e) {}

                const needsTranscode = probeData && probeData.needs_transcode;

                // 외부 자막 수집
                let trackTags = '';
                try {
                    const subRes = await fetch(API_BASE + '/subtitles?path=' + encodeURIComponent(path), { credentials: 'include' });
                    if (subRes.ok) {
                        const subData = await subRes.json();
                        if (subData.subtitles && subData.subtitles.length > 0) {
                            subData.subtitles.forEach((sub, idx) => {
                                let subUrl = API_BASE + '/subtitle?path=' + encodeURIComponent(sub.path);
                                if (sub.smi_class) subUrl += '&smi_class=' + encodeURIComponent(sub.smi_class);
                                const isDefault = idx === 0 ? 'default' : '';
                                const label = sub.lang_label || sub.filename;
                                const srclang = sub.lang_code || 'ko';
                                trackTags += `<track kind="subtitles" src="${subUrl}" srclang="${srclang}" label="${label}" ${isDefault}>`;
                            });
                        }
                    }
                } catch(e) {}

                // 내장 자막 수집
                if (probeData && probeData.subtitle_tracks && probeData.subtitle_tracks.length > 0) {
                    probeData.subtitle_tracks.forEach((st, idx) => {
                        const stUrl = API_BASE + '/embedded-subtitle?path=' + encodeURIComponent(path) + '&track=' + st.index;
                        const isDefault = !trackTags && idx === 0 ? 'default' : '';
                        const label = st.title || st.language || ('Track ' + st.index);
                        const srclang = st.language || 'und';
                        trackTags += `<track kind="subtitles" src="${stUrl}" srclang="${srclang}" label="[내장] ${label}" ${isDefault}>`;
                    });
                }

                if (needsTranscode) {
                    // 트랜스코딩 모드
                    const srcUrl = API_BASE + '/transcode?path=' + encodeURIComponent(path);
                    content.innerHTML = `
                        <video id="nas-video" controls autoplay class="w-full" crossorigin="anonymous">
                            <source src="${srcUrl}" type="video/mp4">
                            ${trackTags}
                        </video>
                        <div id="seek-notice" class="text-center text-sm text-gray-500 mt-2 hidden">탐색 중...</div>
                    `;
                    // 탐색(seek) 처리: 새 트랜스코딩 세션
                    const video = document.getElementById('nas-video');
                    let isSeeking = false;
                    video.addEventListener('seeking', () => {
                        if (isSeeking) return;
                        isSeeking = true;
                        const seekTime = video.currentTime;
                        document.getElementById('seek-notice').classList.remove('hidden');
                        video.src = API_BASE + '/transcode?path=' + encodeURIComponent(path) + '&start=' + seekTime;
                        video.play().catch(() => {});
                        setTimeout(() => {
                            isSeeking = false;
                            document.getElementById('seek-notice').classList.add('hidden');
                        }, 3000);
                    });
                } else {
                    // 직접 재생 (호환 코덱)
                    content.innerHTML = `<video controls autoplay class="w-full" crossorigin="anonymous"><source src="${fileUrl}">${trackTags}</video>`;
                }
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

        // 미디어 요소 정리 (메모리 누수 방지)
        function cleanupMediaElements() {
            const container = document.getElementById('preview-content');
            const videos = container.querySelectorAll('video');
            const audios = container.querySelectorAll('audio');
            videos.forEach(v => { v.pause(); v.removeAttribute('src'); v.load(); });
            audios.forEach(a => { a.pause(); a.removeAttribute('src'); a.load(); });
        }

        function closePreviewModal() {
            cleanupMediaElements();
            document.getElementById('preview-modal').classList.add('hidden');
            document.getElementById('preview-content').innerHTML = '';
        }

        // 미리보기 닫기
        document.getElementById('close-preview').addEventListener('click', closePreviewModal);

        document.getElementById('preview-modal').addEventListener('click', (e) => {
            if (e.target.id === 'preview-modal') closePreviewModal();
        });

        // ESC 키로 모달 닫기
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') closePreviewModal();
        });

        // 시작
        init();
    </script>
</body>
</html>'''
