"""
api_photo.py - Photo Manager API
사진/동영상 관리를 위한 엔드포인트
"""

import os
import sys
import hashlib
from typing import Optional
from fastapi import APIRouter, Query, HTTPException
from fastapi.responses import FileResponse, Response

router = APIRouter(prefix="/photo", tags=["photo"])

# 썸네일 캐시 디렉토리
THUMBNAIL_CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "data", "thumbnail_cache"
)


def _get_photo_modules():
    """photo-manager 패키지 모듈 동적 임포트"""
    photo_manager_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "data", "packages", "installed", "tools", "photo-manager"
    )
    if photo_manager_path not in sys.path:
        sys.path.insert(0, photo_manager_path)

    import photo_db
    import scanner
    return photo_db, scanner


# ============ 스캔 관련 ============

@router.get("/scans")
async def list_scans():
    """스캔된 폴더 목록"""
    photo_db, _ = _get_photo_modules()
    return photo_db.list_scans()


@router.post("/scan")
async def scan_directory(path: str = Query(...)):
    """새 스캔 실행"""
    photo_db, scanner = _get_photo_modules()

    path = os.path.expanduser(path)
    path = os.path.abspath(path)

    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="경로를 찾을 수 없습니다")

    if not os.path.isdir(path):
        raise HTTPException(status_code=400, detail="디렉토리가 아닙니다")

    # 스캔 이름 추출
    if path.startswith('/Volumes/'):
        parts = path.split('/')
        if len(parts) == 3:
            scan_name = parts[2]
        elif len(parts) > 3:
            scan_name = f"{parts[2]}/{parts[-1]}"
        else:
            scan_name = 'Unknown'
    else:
        scan_name = os.path.basename(path) or 'LocalDisk'

    # DB 초기화 및 스캔 ID 생성
    photo_db.init_db()
    scan_id = photo_db.get_or_create_scan(scan_name, path)

    # 스캔 실행
    result = scanner.scan_media(path, scan_id)
    return result


@router.get("/scan/preview")
async def preview_scan(path: str = Query(...)):
    """스캔 미리보기 - 파일 개수 및 예상 시간"""
    _, scanner = _get_photo_modules()

    path = os.path.expanduser(path)
    path = os.path.abspath(path)

    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="경로를 찾을 수 없습니다")

    return scanner.quick_scan(path)


@router.get("/scan/check")
async def check_scan_exists(path: str = Query(...)):
    """해당 경로의 스캔 데이터 존재 여부 확인"""
    photo_db, _ = _get_photo_modules()
    photo_db.init_db()

    path = os.path.expanduser(path)
    path = os.path.abspath(path)

    result = photo_db.list_scans()
    for scan in result.get('scans', []):
        if scan['root_path'] == path:
            return {
                "exists": True,
                "scan_name": scan['name'],
                "photo_count": scan['photo_count'],
                "video_count": scan['video_count'],
                "last_scan": scan['last_scan']
            }

    return {"exists": False}


@router.delete("/scan/{scan_id}")
async def delete_scan(scan_id: int):
    """스캔 데이터 삭제"""
    photo_db, _ = _get_photo_modules()
    return photo_db.delete_scan(scan_id)


# ============ 갤러리 ============

@router.get("/gallery")
async def get_gallery(
    path: str = Query(...),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    media_type: Optional[str] = Query(None),
    sort_by: str = Query("taken_date")
):
    """갤러리 조회 (페이지네이션)"""
    photo_db, _ = _get_photo_modules()

    path = os.path.expanduser(path)
    path = os.path.abspath(path)

    return photo_db.get_gallery(path, page, limit, media_type, sort_by)


@router.get("/gps-photos")
async def get_gps_photos(path: str = Query(...)):
    """GPS 정보가 있는 사진들 조회 (지도용)"""
    photo_db, _ = _get_photo_modules()

    path = os.path.expanduser(path)
    path = os.path.abspath(path)

    return photo_db.get_gps_photos(path)


@router.get("/detail/{media_id}")
async def get_media_detail(media_id: int):
    """미디어 상세 정보"""
    photo_db, _ = _get_photo_modules()
    return photo_db.get_media_detail(media_id)


@router.get("/thumbnail")
async def get_thumbnail(path: str = Query(...), size: int = Query(200)):
    """이미지 썸네일 생성/반환"""
    path = os.path.expanduser(path)

    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

    # 썸네일 캐시 경로 생성
    path_hash = hashlib.md5(f"{path}:{size}".encode()).hexdigest()
    os.makedirs(THUMBNAIL_CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(THUMBNAIL_CACHE_DIR, f"{path_hash}.jpg")

    # 캐시된 썸네일이 있고, 원본보다 새로우면 반환
    if os.path.exists(cache_path):
        if os.path.getmtime(cache_path) >= os.path.getmtime(path):
            return FileResponse(cache_path, media_type="image/jpeg")

    # 썸네일 생성
    try:
        from PIL import Image

        with Image.open(path) as img:
            # EXIF 회전 정보 적용
            try:
                from PIL import ExifTags
                for orientation in ExifTags.TAGS.keys():
                    if ExifTags.TAGS[orientation] == 'Orientation':
                        break
                exif = img._getexif()
                if exif:
                    orientation_value = exif.get(orientation)
                    if orientation_value == 3:
                        img = img.rotate(180, expand=True)
                    elif orientation_value == 6:
                        img = img.rotate(270, expand=True)
                    elif orientation_value == 8:
                        img = img.rotate(90, expand=True)
            except (AttributeError, KeyError, IndexError):
                pass

            # RGB 변환 (RGBA, P 모드 대응)
            if img.mode in ('RGBA', 'P', 'LA'):
                img = img.convert('RGB')

            # 썸네일 생성
            img.thumbnail((size, size), Image.Resampling.LANCZOS)
            img.save(cache_path, "JPEG", quality=80)

        return FileResponse(cache_path, media_type="image/jpeg")

    except Exception as e:
        # 썸네일 생성 실패 시 빈 이미지 반환
        raise HTTPException(status_code=500, detail=f"썸네일 생성 실패: {str(e)}")


@router.get("/image")
async def get_image(path: str = Query(...)):
    """원본 이미지 반환"""
    path = os.path.expanduser(path)

    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

    # 확장자로 미디어 타입 결정
    ext = os.path.splitext(path)[1].lower()
    media_types = {
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.png': 'image/png',
        '.gif': 'image/gif',
        '.webp': 'image/webp',
        '.bmp': 'image/bmp',
        '.heic': 'image/heic',
        '.heif': 'image/heif',
    }
    media_type = media_types.get(ext, 'application/octet-stream')

    return FileResponse(path, media_type=media_type)


@router.get("/video")
async def get_video(path: str = Query(...), request: "Request" = None):
    """동영상 파일 반환 (Range 요청 지원)"""
    from fastapi import Request
    from starlette.responses import StreamingResponse
    import mimetypes

    path = os.path.expanduser(path)

    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

    # 확장자로 미디어 타입 결정
    ext = os.path.splitext(path)[1].lower()
    media_types = {
        '.mp4': 'video/mp4',
        '.mkv': 'video/x-matroska',
        '.avi': 'video/x-msvideo',
        '.mov': 'video/quicktime',
        '.wmv': 'video/x-ms-wmv',
        '.flv': 'video/x-flv',
        '.webm': 'video/webm',
        '.mpg': 'video/mpeg',
        '.mpeg': 'video/mpeg',
        '.m4v': 'video/x-m4v',
        '.mts': 'video/mp2t',
        '.3gp': 'video/3gpp',
    }
    media_type = media_types.get(ext, 'video/mp4')
    file_size = os.path.getsize(path)

    # Range 요청 지원
    return FileResponse(
        path,
        media_type=media_type,
        filename=os.path.basename(path),
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
        }
    )


@router.get("/video-thumbnail")
async def get_video_thumbnail(path: str = Query(...), size: int = Query(200)):
    """동영상 썸네일 생성/반환 (ffmpeg 사용)"""
    import subprocess

    path = os.path.expanduser(path)

    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

    # 썸네일 캐시 경로 생성
    path_hash = hashlib.md5(f"video:{path}:{size}".encode()).hexdigest()
    os.makedirs(THUMBNAIL_CACHE_DIR, exist_ok=True)
    cache_path = os.path.join(THUMBNAIL_CACHE_DIR, f"{path_hash}.jpg")

    # 캐시된 썸네일이 있고, 원본보다 새로우면 반환
    if os.path.exists(cache_path):
        if os.path.getmtime(cache_path) >= os.path.getmtime(path):
            return FileResponse(cache_path, media_type="image/jpeg")

    # ffmpeg로 썸네일 생성
    try:
        cmd = [
            'ffmpeg',
            '-y',
            '-i', path,
            '-ss', '00:00:01',  # 1초 지점
            '-vframes', '1',
            '-vf', f'scale={size}:{size}:force_original_aspect_ratio=decrease',
            '-q:v', '5',
            cache_path
        ]

        result = subprocess.run(cmd, capture_output=True, timeout=10)

        if os.path.exists(cache_path):
            return FileResponse(cache_path, media_type="image/jpeg")
        else:
            raise HTTPException(status_code=500, detail="썸네일 생성 실패")

    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="ffmpeg가 설치되어 있지 않습니다")
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=500, detail="썸네일 생성 시간 초과")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"썸네일 생성 실패: {str(e)}")


# ============ 중복 탐지 ============

@router.get("/duplicates")
async def get_duplicates(path: str = Query(...)):
    """중복 파일 조회 (MD5 해시 기반) - 비동기 실행"""
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    photo_db, _ = _get_photo_modules()

    path = os.path.expanduser(path)
    path = os.path.abspath(path)

    # 스레드풀에서 실행하여 이벤트 루프 블로킹 방지
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as executor:
        result = await loop.run_in_executor(executor, photo_db.get_duplicates, path)

    return result


# ============ 통계 ============

@router.get("/stats")
async def get_stats(path: str = Query(...)):
    """통계 조회 - 비동기 실행"""
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    photo_db, _ = _get_photo_modules()

    path = os.path.expanduser(path)
    path = os.path.abspath(path)

    # 스레드풀에서 실행하여 이벤트 루프 블로킹 방지
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as executor:
        result = await loop.run_in_executor(executor, photo_db.get_stats, path)

    return result


@router.get("/timeline")
async def get_timeline(path: str = Query(...)):
    """타임라인 (월별 촬영 통계) - 비동기 실행"""
    import asyncio
    from concurrent.futures import ThreadPoolExecutor

    photo_db, _ = _get_photo_modules()

    path = os.path.expanduser(path)
    path = os.path.abspath(path)

    # 스레드풀에서 실행하여 이벤트 루프 블로킹 방지
    loop = asyncio.get_event_loop()
    with ThreadPoolExecutor() as executor:
        result = await loop.run_in_executor(executor, photo_db.get_timeline, path)

    return result


@router.get("/timeline-zoom")
async def get_timeline_zoom_data(
    path: str = Query(...),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(1000)
):
    """
    줌 가능한 타임라인 데이터 (사진/동영상용)
    - start_date, end_date: YYYY-MM-DD 형식 (없으면 전체 범위)
    - limit: 반환할 파일 수 (줌인 시 개별 파일 표시용)
    """
    import unicodedata
    import sqlite3
    from datetime import datetime

    photo_db, _ = _get_photo_modules()

    path = os.path.expanduser(path)
    path = os.path.abspath(path)
    path = unicodedata.normalize('NFC', path)

    # 스캔 찾기
    result = photo_db.list_scans()
    scan = None
    for s in result.get('scans', []):
        scan_path = unicodedata.normalize('NFC', s.get('root_path', ''))
        if scan_path == path:
            scan = s
            break

    if not scan:
        return {"success": False, "error": "스캔 데이터가 없습니다. 먼저 스캔을 실행하세요."}

    scan_id = scan['id']

    # DB 연결 - photo_scans 디렉토리 사용
    db_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "data", "packages", "photo_scans", f"scan_{scan_id}.db"
    )

    if not os.path.exists(db_path):
        return {"success": False, "error": f"데이터베이스 파일을 찾을 수 없습니다."}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # 날짜 필드: taken_date 우선, 없으면 mtime 사용
    date_field = "COALESCE(taken_date, mtime)"

    # 1. 전체 시간 범위 조회
    cursor.execute(f"""
        SELECT MIN({date_field}) as min_date, MAX({date_field}) as max_date, COUNT(*) as total_files
        FROM media_files
        WHERE {date_field} IS NOT NULL
    """)
    range_row = cursor.fetchone()
    time_range = {
        "min_date": range_row['min_date'],
        "max_date": range_row['max_date'],
        "total_files": range_row['total_files']
    }

    # 2. 날짜 조건 생성
    date_condition = f"{date_field} IS NOT NULL"
    if start_date:
        date_condition += f" AND substr({date_field}, 1, 10) >= '{start_date}'"
    if end_date:
        date_condition += f" AND substr({date_field}, 1, 10) <= '{end_date}'"

    # 3. 선택 범위 통계
    cursor.execute(f"""
        SELECT COUNT(*) as file_count,
               COALESCE(SUM(size), 0) as total_size,
               MIN({date_field}) as range_start,
               MAX({date_field}) as range_end,
               SUM(CASE WHEN media_type = 'photo' THEN 1 ELSE 0 END) as photo_count,
               SUM(CASE WHEN media_type = 'video' THEN 1 ELSE 0 END) as video_count
        FROM media_files
        WHERE {date_condition}
    """)
    stats_row = cursor.fetchone()
    stats = {
        "file_count": stats_row['file_count'],
        "total_size_mb": round(stats_row['total_size'] / (1024 * 1024), 2),
        "range_start": stats_row['range_start'],
        "range_end": stats_row['range_end'],
        "photo_count": stats_row['photo_count'],
        "video_count": stats_row['video_count']
    }

    # 4. 줌 레벨에 따른 밀도 데이터 (일/월/년 단위)
    if start_date and end_date:
        try:
            d1 = datetime.strptime(start_date, "%Y-%m-%d")
            d2 = datetime.strptime(end_date, "%Y-%m-%d")
            days_diff = (d2 - d1).days
        except:
            days_diff = 365
    else:
        days_diff = 3650  # 약 10년으로 가정

    if days_diff <= 31:
        # 일 단위
        group_expr = f"substr({date_field}, 1, 10)"
        density_label = "day"
    elif days_diff <= 365:
        # 월 단위
        group_expr = f"substr({date_field}, 1, 7)"
        density_label = "month"
    else:
        # 년 단위
        group_expr = f"substr({date_field}, 1, 4)"
        density_label = "year"

    cursor.execute(f"""
        SELECT {group_expr} as period,
               COUNT(*) as file_count,
               SUM(size) as total_size,
               SUM(CASE WHEN media_type = 'photo' THEN 1 ELSE 0 END) as photos,
               SUM(CASE WHEN media_type = 'video' THEN 1 ELSE 0 END) as videos
        FROM media_files
        WHERE {date_condition}
        GROUP BY period
        ORDER BY period
    """)

    density = []
    for row in cursor.fetchall():
        density.append({
            "period": row['period'],
            "file_count": row['file_count'],
            "size_mb": round(row['total_size'] / (1024 * 1024), 2),
            "photos": row['photos'],
            "videos": row['videos']
        })

    # 5. 개별 파일 목록 (줌인 상태에서만 의미 있음)
    files = []
    if stats['file_count'] <= limit:
        cursor.execute(f"""
            SELECT id, filename, path, size, mtime, taken_date, media_type, extension,
                   width, height, camera_make, camera_model
            FROM media_files
            WHERE {date_condition}
            ORDER BY {date_field}
            LIMIT {limit}
        """)
        for row in cursor.fetchall():
            files.append({
                "id": row['id'],
                "filename": row['filename'],
                "path": row['path'],
                "size_mb": round(row['size'] / (1024 * 1024), 2),
                "mtime": row['mtime'],
                "taken_date": row['taken_date'],
                "media_type": row['media_type'],
                "extension": row['extension'] or '',
                "width": row['width'],
                "height": row['height'],
                "camera": f"{row['camera_make'] or ''} {row['camera_model'] or ''}".strip() or None
            })

    conn.close()

    return {
        "success": True,
        "time_range": time_range,
        "stats": stats,
        "density": density,
        "density_label": density_label,
        "files": files,
        "show_files": len(files) > 0
    }


# ============ 외부 플레이어 ============

@router.post("/open-external")
async def open_in_external_player(path: str = Query(...)):
    """시스템 기본 앱으로 파일 열기"""
    import subprocess
    import platform

    path = os.path.expanduser(path)

    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="파일을 찾을 수 없습니다")

    try:
        system = platform.system()
        if system == 'Darwin':  # macOS
            subprocess.Popen(['open', path])
        elif system == 'Windows':
            os.startfile(path)
        else:  # Linux
            subprocess.Popen(['xdg-open', path])

        return {"success": True, "path": path}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"파일 열기 실패: {str(e)}")


# ============ 창 열기 ============

_pending_window_requests = []


@router.post("/open-window")
async def request_open_window(path: Optional[str] = None):
    """Photo Manager 창 열기 요청 (도구에서 호출)"""
    request_id = os.urandom(8).hex()
    _pending_window_requests.append({
        "id": request_id,
        "path": path
    })
    return {"status": "requested", "request_id": request_id, "path": path}


@router.get("/pending-windows")
async def get_pending_windows():
    """대기 중인 창 열기 요청 조회 (프론트엔드 폴링용)"""
    global _pending_window_requests
    requests = _pending_window_requests.copy()
    _pending_window_requests = []
    return {"requests": requests}
