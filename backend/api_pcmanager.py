"""
api_pcmanager.py - PC Manager API
파일 탐색기 기능을 위한 엔드포인트
"""

import os
import platform
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Query, HTTPException

router = APIRouter(prefix="/pcmanager", tags=["pcmanager"])


def get_home_path() -> str:
    """홈 디렉토리 경로 반환"""
    return str(Path.home())


def get_drives() -> list:
    """드라이브/볼륨 목록 반환"""
    drives = []
    system = platform.system()

    if system == "Darwin":  # macOS
        # 내장 디스크
        drives.append({
            "name": "Macintosh HD",
            "path": "/",
            "type": "internal"
        })

        # /Volumes에서 외장 드라이브 탐색
        volumes_path = Path("/Volumes")
        if volumes_path.exists():
            for vol in volumes_path.iterdir():
                if vol.is_dir() and vol.name != "Macintosh HD":
                    drives.append({
                        "name": vol.name,
                        "path": str(vol),
                        "type": "external"
                    })

    elif system == "Windows":
        import string
        for letter in string.ascii_uppercase:
            drive_path = f"{letter}:\\"
            if os.path.exists(drive_path):
                drives.append({
                    "name": f"{letter}:",
                    "path": drive_path,
                    "type": "internal" if letter == "C" else "external"
                })

    else:  # Linux
        drives.append({
            "name": "Root",
            "path": "/",
            "type": "internal"
        })
        # /media, /mnt에서 마운트된 드라이브 탐색
        for mount_point in ["/media", "/mnt"]:
            mount_path = Path(mount_point)
            if mount_path.exists():
                for user_dir in mount_path.iterdir():
                    if user_dir.is_dir():
                        for vol in user_dir.iterdir():
                            if vol.is_dir():
                                drives.append({
                                    "name": vol.name,
                                    "path": str(vol),
                                    "type": "external"
                                })

    return drives


@router.get("/drives")
async def list_drives():
    """드라이브/볼륨 목록"""
    return {"drives": get_drives()}


@router.get("/list")
async def list_directory(path: Optional[str] = Query(None)):
    """디렉토리 내용 목록"""

    # 경로가 없으면 홈 디렉토리
    if not path or path.strip() == "":
        path = get_home_path()

    target_path = Path(path)

    # 경로 유효성 검사
    if not target_path.exists():
        raise HTTPException(status_code=404, detail="경로를 찾을 수 없습니다")

    if not target_path.is_dir():
        raise HTTPException(status_code=400, detail="디렉토리가 아닙니다")

    items = []

    try:
        for entry in sorted(target_path.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
            # 숨김 파일 건너뛰기 (옵션)
            if entry.name.startswith('.'):
                continue

            try:
                stat = entry.stat()
                item = {
                    "name": entry.name,
                    "path": str(entry),
                    "type": "directory" if entry.is_dir() else "file",
                    "size": stat.st_size if entry.is_file() else None,
                    "modified": stat.st_mtime
                }
                items.append(item)
            except (PermissionError, OSError):
                # 권한 오류 무시
                continue

    except PermissionError:
        raise HTTPException(status_code=403, detail="접근 권한이 없습니다")

    return {
        "path": str(target_path),
        "items": items
    }


@router.get("/info")
async def get_path_info(path: str = Query(...)):
    """경로 정보 조회"""
    target_path = Path(path)

    if not target_path.exists():
        raise HTTPException(status_code=404, detail="경로를 찾을 수 없습니다")

    try:
        stat = target_path.stat()
        return {
            "name": target_path.name,
            "path": str(target_path),
            "type": "directory" if target_path.is_dir() else "file",
            "size": stat.st_size,
            "modified": stat.st_mtime,
            "created": stat.st_ctime
        }
    except PermissionError:
        raise HTTPException(status_code=403, detail="접근 권한이 없습니다")


# 창 열기 요청 저장소 (프론트엔드가 폴링)
_pending_window_requests = []


@router.post("/open-window")
async def request_open_window(path: Optional[str] = None):
    """PC Manager 창 열기 요청 (도구에서 호출)"""
    request_id = os.urandom(8).hex()
    _pending_window_requests.append({
        "id": request_id,
        "path": path,
        "timestamp": platform.system()  # 임시로 시스템 정보 활용
    })
    return {"status": "requested", "request_id": request_id, "path": path}


@router.get("/pending-windows")
async def get_pending_windows():
    """대기 중인 창 열기 요청 조회 (프론트엔드 폴링용)"""
    global _pending_window_requests
    requests = _pending_window_requests.copy()
    _pending_window_requests = []  # 조회 후 비움
    return {"requests": requests}


@router.get("/open")
async def open_path_in_finder(path: str = Query(...), reveal: bool = Query(True)):
    """파일/폴더 열기
    - reveal=True: Finder에서 파일 선택 (기본값)
    - reveal=False: 기본 앱으로 파일 열기
    """
    import subprocess

    target_path = Path(path)
    if not target_path.exists():
        raise HTTPException(status_code=404, detail="경로를 찾을 수 없습니다")

    system = platform.system()
    try:
        if system == "Darwin":  # macOS
            if reveal:
                # -R 옵션: Finder에서 해당 파일을 선택한 상태로 열기
                subprocess.run(["open", "-R", path], check=True)
            else:
                # 기본 앱으로 파일 열기
                subprocess.run(["open", path], check=True)
        elif system == "Windows":
            if reveal:
                subprocess.run(["explorer", "/select,", path], check=True)
            else:
                subprocess.run(["start", "", path], shell=True, check=True)
        else:  # Linux
            if reveal:
                subprocess.run(["xdg-open", str(target_path.parent)], check=True)
            else:
                subprocess.run(["xdg-open", path], check=True)
        return {"success": True, "path": path}
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"열기 실패: {e}")


# ============ 분석 모드 API ============

def _get_storage_db():
    """storage_db 모듈 동적 임포트"""
    import sys
    storage_db_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "data", "packages", "installed", "tools", "pc-manager"
    )
    if storage_db_path not in sys.path:
        sys.path.insert(0, storage_db_path)
    import storage_db
    return storage_db


@router.get("/analyze/scans")
async def list_scanned_volumes():
    """스캔된 폴더 목록 조회"""
    storage_db = _get_storage_db()
    result = storage_db.list_scans()
    return result


# 하위 호환성
@router.get("/analyze/volumes")
async def list_scanned_volumes_compat():
    """스캔된 볼륨 목록 조회 (하위 호환성)"""
    storage_db = _get_storage_db()
    result = storage_db.list_scans()
    return {"success": True, "volumes": result.get('scans', [])}


@router.post("/analyze/scan")
async def scan_path_for_analysis(path: str = Query(...)):
    """경로 스캔하여 분석 데이터 생성"""
    storage_db = _get_storage_db()
    result = storage_db.scan_directory(path)
    return result


@router.delete("/analyze/scan/{scan_id}")
async def delete_scan(scan_id: int):
    """스캔 데이터 삭제"""
    storage_db = _get_storage_db()
    result = storage_db.delete_scan(scan_id)
    return result


@router.get("/analyze/check")
async def check_scan_exists(path: str = Query(...)):
    """해당 경로의 스캔 데이터 존재 여부 확인"""
    storage_db = _get_storage_db()

    # 경로 정규화
    import unicodedata
    path = os.path.expanduser(path)
    path = os.path.abspath(path)
    path = unicodedata.normalize('NFC', path)

    # DB에서 확인
    result = storage_db.list_scans()
    for scan in result.get('scans', []):
        scan_path = unicodedata.normalize('NFC', scan.get('root_path', ''))
        if scan_path == path:
            return {
                "exists": True,
                "scan_id": scan['id'],
                "name": scan['name'],
                "file_count": scan['file_count'],
                "last_scan": scan['last_scan']
            }

    return {"exists": False}


@router.get("/analyze/summary")
async def get_analysis_summary(path: str = Query(...)):
    """분석 요약 정보"""
    storage_db = _get_storage_db()
    return storage_db.get_summary(path)


@router.get("/analyze/treemap")
async def get_treemap_data(path: str = Query(...)):
    """트리맵용 데이터 - 폴더별 용량"""
    storage_db = _get_storage_db()

    import unicodedata
    path = os.path.expanduser(path)
    path = os.path.abspath(path)
    path = unicodedata.normalize('NFC', path)

    # 스캔 찾기
    result = storage_db.list_scans()
    scan = None
    for s in result.get('scans', []):
        scan_path = unicodedata.normalize('NFC', s.get('root_path', ''))
        if scan_path == path:
            scan = s
            break

    if not scan:
        return {"success": False, "error": "스캔 데이터가 없습니다. 먼저 스캔을 실행하세요."}

    scan_id = scan['id']
    root_path = scan['root_path']

    # 스캔별 DB 연결
    conn = storage_db._get_connection(scan_id)
    cursor = conn.cursor()

    # 최상위 폴더별 용량 집계
    cursor.execute("SELECT path, size FROM files")

    folder_sizes = {}
    for row in cursor.fetchall():
        file_path = row['path']
        size = row['size']

        # root_path 이후의 첫 번째 폴더 추출
        rel_path = file_path[len(root_path):].lstrip('/')
        parts = rel_path.split('/')
        if len(parts) > 1:
            top_folder = parts[0]
        else:
            top_folder = "(루트 파일)"

        folder_sizes[top_folder] = folder_sizes.get(top_folder, 0) + size

    conn.close()

    # 트리맵 데이터 형식으로 변환
    treemap_data = []
    for name, size in sorted(folder_sizes.items(), key=lambda x: -x[1]):
        treemap_data.append({
            "name": name,
            "size": size,
            "size_mb": round(size / (1024 * 1024), 2)
        })

    return {"success": True, "data": treemap_data[:20]}  # 상위 20개


@router.get("/analyze/timeline")
async def get_timeline_data(path: str = Query(...)):
    """타임라인용 데이터 - 월별 파일 생성/수정 추이"""
    storage_db = _get_storage_db()

    import unicodedata
    path = os.path.expanduser(path)
    path = os.path.abspath(path)
    path = unicodedata.normalize('NFC', path)

    # 스캔 찾기
    result = storage_db.list_scans()
    scan = None
    for s in result.get('scans', []):
        scan_path = unicodedata.normalize('NFC', s.get('root_path', ''))
        if scan_path == path:
            scan = s
            break

    if not scan:
        return {"success": False, "error": "스캔 데이터가 없습니다. 먼저 스캔을 실행하세요."}

    scan_id = scan['id']

    # 스캔별 DB 연결
    conn = storage_db._get_connection(scan_id)
    cursor = conn.cursor()

    # 월별 집계
    cursor.execute("""
        SELECT
            substr(mtime, 1, 7) as month,
            COUNT(*) as file_count,
            SUM(size) as total_size
        FROM files
        WHERE mtime IS NOT NULL
        GROUP BY month
        ORDER BY month
    """)

    timeline_data = []
    for row in cursor.fetchall():
        timeline_data.append({
            "month": row['month'],
            "file_count": row['file_count'],
            "size_mb": round(row['total_size'] / (1024 * 1024), 2)
        })

    conn.close()
    return {"success": True, "data": timeline_data}


@router.get("/analyze/extensions")
async def get_extension_data(path: str = Query(...)):
    """확장자별 데이터 - 도넛 차트용"""
    storage_db = _get_storage_db()

    import unicodedata
    path = os.path.expanduser(path)
    path = os.path.abspath(path)
    path = unicodedata.normalize('NFC', path)

    # 스캔 찾기
    result = storage_db.list_scans()
    scan = None
    for s in result.get('scans', []):
        scan_path = unicodedata.normalize('NFC', s.get('root_path', ''))
        if scan_path == path:
            scan = s
            break

    if not scan:
        return {"success": False, "error": "스캔 데이터가 없습니다. 먼저 스캔을 실행하세요."}

    scan_id = scan['id']

    # 스캔별 DB 연결
    conn = storage_db._get_connection(scan_id)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            COALESCE(extension, '(없음)') as extension,
            COUNT(*) as file_count,
            SUM(size) as total_size
        FROM files
        GROUP BY extension
        ORDER BY total_size DESC
        LIMIT 15
    """)

    ext_data = []
    for row in cursor.fetchall():
        ext_data.append({
            "extension": row['extension'] or '(없음)',
            "count": row['file_count'],
            "size_mb": round(row['total_size'] / (1024 * 1024), 2)
        })

    conn.close()
    return {"success": True, "data": ext_data}


@router.get("/analyze/scatter")
async def get_scatter_data(path: str = Query(...)):
    """산점도용 데이터 - 파일 크기 vs 수정일"""
    storage_db = _get_storage_db()

    import unicodedata
    path = os.path.expanduser(path)
    path = os.path.abspath(path)
    path = unicodedata.normalize('NFC', path)

    # 스캔 찾기
    result = storage_db.list_scans()
    scan = None
    for s in result.get('scans', []):
        scan_path = unicodedata.normalize('NFC', s.get('root_path', ''))
        if scan_path == path:
            scan = s
            break

    if not scan:
        return {"success": False, "error": "스캔 데이터가 없습니다. 먼저 스캔을 실행하세요."}

    scan_id = scan['id']

    # 스캔별 DB 연결
    conn = storage_db._get_connection(scan_id)
    cursor = conn.cursor()

    # 크기가 큰 파일 위주로 샘플링 (상위 500개)
    cursor.execute("""
        SELECT filename, path, size, mtime, extension
        FROM files
        WHERE mtime IS NOT NULL
        ORDER BY size DESC
        LIMIT 500
    """)

    scatter_data = []
    for row in cursor.fetchall():
        scatter_data.append({
            "filename": row['filename'],
            "path": row['path'],
            "size_mb": round(row['size'] / (1024 * 1024), 2),
            "mtime": row['mtime'],
            "extension": row['extension'] or ''
        })

    conn.close()
    return {"success": True, "data": scatter_data}


@router.get("/analyze/timeline-zoom")
async def get_timeline_zoom_data(
    path: str = Query(...),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    limit: int = Query(1000)
):
    """
    줌 가능한 타임라인 데이터
    - start_date, end_date: YYYY-MM-DD 형식 (없으면 전체 범위)
    - limit: 반환할 파일 수 (줌인 시 개별 파일 표시용)

    반환:
    - time_range: 전체 시간 범위
    - density: 시간대별 파일 밀도 (히트맵용)
    - files: 개별 파일 목록 (줌인 시)
    - stats: 선택 범위 통계
    """
    storage_db = _get_storage_db()

    import unicodedata
    path = os.path.expanduser(path)
    path = os.path.abspath(path)
    path = unicodedata.normalize('NFC', path)

    # 스캔 찾기
    result = storage_db.list_scans()
    scan = None
    for s in result.get('scans', []):
        scan_path = unicodedata.normalize('NFC', s.get('root_path', ''))
        if scan_path == path:
            scan = s
            break

    if not scan:
        return {"success": False, "error": "스캔 데이터가 없습니다. 먼저 스캔을 실행하세요."}

    scan_id = scan['id']
    conn = storage_db._get_connection(scan_id)
    cursor = conn.cursor()

    # 1. 전체 시간 범위 조회
    cursor.execute("""
        SELECT MIN(mtime) as min_date, MAX(mtime) as max_date, COUNT(*) as total_files
        FROM files
        WHERE mtime IS NOT NULL
    """)
    range_row = cursor.fetchone()
    time_range = {
        "min_date": range_row['min_date'],
        "max_date": range_row['max_date'],
        "total_files": range_row['total_files']
    }

    # 2. 날짜 조건 생성 (mtime은 ISO 형식: 2002-08-15T10:30:00)
    date_condition = "mtime IS NOT NULL"
    if start_date:
        date_condition += f" AND substr(mtime, 1, 10) >= '{start_date}'"
    if end_date:
        date_condition += f" AND substr(mtime, 1, 10) <= '{end_date}'"

    # 3. 선택 범위 통계
    cursor.execute(f"""
        SELECT COUNT(*) as file_count,
               COALESCE(SUM(size), 0) as total_size,
               MIN(mtime) as range_start,
               MAX(mtime) as range_end
        FROM files
        WHERE {date_condition}
    """)
    stats_row = cursor.fetchone()
    stats = {
        "file_count": stats_row['file_count'],
        "total_size_mb": round(stats_row['total_size'] / (1024 * 1024), 2),
        "range_start": stats_row['range_start'],
        "range_end": stats_row['range_end']
    }

    # 4. 줌 레벨에 따른 밀도 데이터 (일/월/년 단위)
    # 선택 범위의 기간에 따라 자동 결정
    from datetime import datetime

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
        group_expr = "substr(mtime, 1, 10)"
        density_label = "day"
    elif days_diff <= 365:
        # 월 단위
        group_expr = "substr(mtime, 1, 7)"
        density_label = "month"
    else:
        # 년 단위
        group_expr = "substr(mtime, 1, 4)"
        density_label = "year"

    cursor.execute(f"""
        SELECT {group_expr} as period,
               COUNT(*) as file_count,
               SUM(size) as total_size
        FROM files
        WHERE {date_condition}
        GROUP BY period
        ORDER BY period
    """)

    density = []
    for row in cursor.fetchall():
        density.append({
            "period": row['period'],
            "file_count": row['file_count'],
            "size_mb": round(row['total_size'] / (1024 * 1024), 2)
        })

    # 5. 개별 파일 목록 (줌인 상태에서만 의미 있음)
    files = []
    print(f"[timeline-zoom] file_count={stats['file_count']}, limit={limit}, will_show={stats['file_count'] <= limit}")
    if stats['file_count'] <= limit:
        cursor.execute(f"""
            SELECT filename, path, size, mtime, extension
            FROM files
            WHERE {date_condition}
            ORDER BY mtime
            LIMIT {limit}
        """)
        for row in cursor.fetchall():
            files.append({
                "filename": row['filename'],
                "path": row['path'],
                "size_mb": round(row['size'] / (1024 * 1024), 2),
                "mtime": row['mtime'],
                "extension": row['extension'] or ''
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


@router.get("/analyze/folders")
async def get_folder_structure(path: str = Query(...)):
    """폴더 구조 + 주석 데이터"""
    storage_db = _get_storage_db()

    import unicodedata
    path = os.path.expanduser(path)
    path = os.path.abspath(path)
    path = unicodedata.normalize('NFC', path)

    # 스캔 찾기
    result = storage_db.list_scans()
    scan = None
    for s in result.get('scans', []):
        scan_path = unicodedata.normalize('NFC', s.get('root_path', ''))
        if scan_path == path:
            scan = s
            break

    if not scan:
        return {"success": False, "error": "스캔 데이터가 없습니다. 먼저 스캔을 실행하세요."}

    scan_id = scan['id']
    root_path = scan['root_path']

    # 스캔별 DB 연결
    conn = storage_db._get_connection(scan_id)
    cursor = conn.cursor()

    # 폴더별 파일 수와 용량
    cursor.execute("SELECT path, size FROM files")

    folder_stats = {}
    for row in cursor.fetchall():
        file_path = row['path']
        size = row['size']

        # 폴더 경로 추출
        folder = os.path.dirname(file_path)
        rel_folder = folder[len(root_path):].lstrip('/') or '(루트)'

        if rel_folder not in folder_stats:
            folder_stats[rel_folder] = {"count": 0, "size": 0}
        folder_stats[rel_folder]["count"] += 1
        folder_stats[rel_folder]["size"] += size

    # 주석 조회
    annotations = storage_db.get_annotations(root_path)
    ann_map = {a['folder_path']: a['note'] for a in annotations.get('annotations', [])}

    # 결과 구성
    folders = []
    for folder, stats in sorted(folder_stats.items(), key=lambda x: -x[1]['size'])[:50]:
        full_path = os.path.join(root_path, folder) if folder != '(루트)' else root_path
        folders.append({
            "path": folder,
            "full_path": full_path,
            "file_count": stats["count"],
            "size_mb": round(stats["size"] / (1024 * 1024), 2),
            "annotation": ann_map.get(full_path, "")
        })

    conn.close()
    return {"success": True, "data": folders}
