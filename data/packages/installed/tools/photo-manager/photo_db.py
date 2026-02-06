"""
photo_db.py - 사진/동영상 메타데이터 DB 관리
폴더별 독립 DB 아키텍처 - 각 스캔 폴더마다 별도 DB 파일 사용

구조:
  data/packages/photo_scans/
  ├── scans.json          # 스캔 목록 (메타 정보)
  ├── scan_1.db           # 폴더 1 전용 DB
  ├── scan_2.db           # 폴더 2 전용 DB
  └── ...
"""

import os
import json
import sqlite3
import threading
import unicodedata
from datetime import datetime
from typing import Dict, List, Optional
import hashlib


def _normalize_path(path: str) -> str:
    """경로 유니코드 정규화 (macOS NFD -> NFC)"""
    return unicodedata.normalize('NFC', path) if path else path

# 스캔 데이터 저장 경로
# __file__ = .../data/packages/installed/tools/photo-manager/photo_db.py
# 4단계 상위 = .../data/packages/
SCANS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "photo_scans"
)
SCANS_JSON = os.path.join(SCANS_DIR, "scans.json")

# 스레드 안전을 위한 락
_scans_lock = threading.Lock()


def _ensure_dir():
    """스캔 디렉토리 생성"""
    os.makedirs(SCANS_DIR, exist_ok=True)


def _load_scans_json() -> List[Dict]:
    """scans.json 로드"""
    _ensure_dir()
    if not os.path.exists(SCANS_JSON):
        return []
    try:
        with open(SCANS_JSON, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return []


def _save_scans_json(scans: List[Dict]):
    """scans.json 저장"""
    _ensure_dir()
    with open(SCANS_JSON, 'w', encoding='utf-8') as f:
        json.dump(scans, f, ensure_ascii=False, indent=2)


def _get_db_path(scan_id: int) -> str:
    """스캔 ID에 해당하는 DB 파일 경로"""
    return os.path.join(SCANS_DIR, f"scan_{scan_id}.db")


def _get_connection(scan_id: int) -> sqlite3.Connection:
    """특정 스캔 DB에 연결 (WAL 모드)"""
    db_path = _get_db_path(scan_id)
    conn = sqlite3.connect(db_path, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def _init_scan_db(scan_id: int):
    """개별 스캔 DB 테이블 초기화"""
    conn = _get_connection(scan_id)
    cursor = conn.cursor()

    # 미디어 파일 테이블만 (스캔 정보는 scans.json에 저장)
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS media_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT UNIQUE NOT NULL,
            filename TEXT NOT NULL,
            extension TEXT,
            size INTEGER DEFAULT 0,
            mtime TEXT,
            md5_hash TEXT,
            media_type TEXT,
            width INTEGER,
            height INTEGER,
            taken_date TEXT,
            camera_make TEXT,
            camera_model TEXT,
            gps_lat REAL,
            gps_lon REAL,
            duration REAL,
            fps REAL,
            codec TEXT
        )
    """)

    # 인덱스
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_media_md5 ON media_files(md5_hash)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_media_type ON media_files(media_type)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_media_taken ON media_files(taken_date)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_media_ext ON media_files(extension)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_media_size ON media_files(size)")

    conn.commit()
    conn.close()


def _generate_scan_id() -> int:
    """새 스캔 ID 생성"""
    scans = _load_scans_json()
    if not scans:
        return 1
    return max(s.get('id', 0) for s in scans) + 1


# ============ 공개 API ============

def init_db():
    """DB 초기화 (호환성 유지용 - 실제로는 아무것도 안함)"""
    _ensure_dir()


def get_or_create_scan(name: str, root_path: str) -> int:
    """스캔 ID 가져오거나 생성"""
    # macOS NFD -> NFC 정규화
    root_path = _normalize_path(root_path)

    with _scans_lock:
        scans = _load_scans_json()

        # 기존 스캔 찾기 (정규화 후 비교)
        for scan in scans:
            stored_path = _normalize_path(scan.get('root_path', ''))
            if stored_path == root_path:
                return scan['id']

        # 새 스캔 생성
        scan_id = _generate_scan_id()
        new_scan = {
            "id": scan_id,
            "name": name,
            "root_path": root_path,  # 정규화된 경로 저장
            "last_scan": None,
            "photo_count": 0,
            "video_count": 0,
            "total_size": 0
        }
        scans.append(new_scan)
        _save_scans_json(scans)

        # DB 파일 생성 및 초기화
        _init_scan_db(scan_id)

        return scan_id


def save_media_batch(scan_id: int, media_list: List[Dict]):
    """미디어 파일 배치 저장"""
    if not media_list:
        return

    conn = _get_connection(scan_id)
    cursor = conn.cursor()

    cursor.executemany("""
        INSERT OR REPLACE INTO media_files
        (path, filename, extension, size, mtime, md5_hash, media_type,
         width, height, taken_date, camera_make, camera_model, gps_lat, gps_lon,
         duration, fps, codec)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [(
        m.get('path'),
        m.get('filename'),
        m.get('extension'),
        m.get('size', 0),
        m.get('mtime'),
        m.get('md5_hash'),
        m.get('media_type'),
        m.get('width'),
        m.get('height'),
        m.get('taken_date'),
        m.get('camera_make'),
        m.get('camera_model'),
        m.get('gps_lat'),
        m.get('gps_lon'),
        m.get('duration'),
        m.get('fps'),
        m.get('codec')
    ) for m in media_list])

    conn.commit()
    conn.close()


def update_scan_stats(scan_id: int, photo_count: int, video_count: int, total_size: int):
    """스캔 통계 업데이트"""
    with _scans_lock:
        scans = _load_scans_json()

        for scan in scans:
            if scan['id'] == scan_id:
                scan['last_scan'] = datetime.now().isoformat()
                scan['photo_count'] = photo_count
                scan['video_count'] = video_count
                scan['total_size'] = total_size
                break

        _save_scans_json(scans)


def clear_scan_data(scan_id: int):
    """스캔 데이터 초기화 (재스캔용) - 해당 DB의 모든 미디어 파일 삭제"""
    db_path = _get_db_path(scan_id)
    if not os.path.exists(db_path):
        _init_scan_db(scan_id)
        return

    conn = _get_connection(scan_id)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM media_files")
    conn.commit()
    conn.close()


def delete_scan(scan_id: int) -> Dict:
    """스캔 완전 삭제 - DB 파일 및 메타 정보 제거"""
    with _scans_lock:
        scans = _load_scans_json()

        # 스캔 찾기
        target_scan = None
        for scan in scans:
            if scan['id'] == scan_id:
                target_scan = scan
                break

        if not target_scan:
            return {"success": False, "error": "스캔을 찾을 수 없습니다."}

        scan_name = target_scan['name']
        root_path = target_scan['root_path']

        # 목록에서 제거
        scans = [s for s in scans if s['id'] != scan_id]
        _save_scans_json(scans)

    # DB 파일 삭제
    db_path = _get_db_path(scan_id)
    deleted_files = 0

    if os.path.exists(db_path):
        try:
            # 삭제 전 파일 개수 확인
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM media_files")
            deleted_files = cursor.fetchone()[0]
            conn.close()
        except:
            pass

        # DB 파일 삭제
        os.remove(db_path)

        # WAL 파일들도 삭제
        for ext in ['-wal', '-shm']:
            wal_path = db_path + ext
            if os.path.exists(wal_path):
                os.remove(wal_path)

    return {
        "success": True,
        "deleted_scan": scan_name,
        "deleted_path": root_path,
        "deleted_files": deleted_files
    }


def list_scans() -> Dict:
    """모든 스캔 목록"""
    _ensure_dir()
    scans = _load_scans_json()

    result = []
    for scan in scans:
        result.append({
            "id": scan['id'],
            "name": scan['name'],
            "root_path": scan['root_path'],
            "last_scan": scan.get('last_scan'),
            "photo_count": scan.get('photo_count', 0),
            "video_count": scan.get('video_count', 0),
            "total_size_mb": round(scan.get('total_size', 0) / (1024 * 1024), 2)
        })

    return {"success": True, "scans": result}


def get_gallery(root_path: str, page: int = 1, limit: int = 50,
                media_type: Optional[str] = None, sort_by: str = "taken_date") -> Dict:
    """갤러리 조회 (페이지네이션)"""
    # macOS NFD -> NFC 정규화
    root_path = _normalize_path(root_path)

    # 스캔 찾기
    scans = _load_scans_json()
    scan = None
    for s in scans:
        stored_path = _normalize_path(s.get('root_path', ''))
        if stored_path == root_path:
            scan = s
            break

    if not scan:
        return {"success": False, "error": "스캔 데이터가 없습니다. 먼저 스캔을 실행하세요."}

    scan_id = scan['id']
    db_path = _get_db_path(scan_id)

    if not os.path.exists(db_path):
        return {"success": False, "error": "스캔 DB가 없습니다. 먼저 스캔을 실행하세요."}

    conn = _get_connection(scan_id)
    cursor = conn.cursor()

    offset = (page - 1) * limit

    # 쿼리 구성
    where_clause = "WHERE 1=1"
    params = []

    if media_type in ('photo', 'video'):
        where_clause += " AND media_type = ?"
        params.append(media_type)

    # 정렬 (taken_date가 NULL인 경우 mtime 사용, 그것도 NULL이면 id 역순)
    order_by = {
        'taken_date': 'COALESCE(taken_date, mtime) DESC, id DESC',
        'mtime': 'mtime DESC, id DESC',
        'size': 'size DESC, id DESC',
        'filename': 'filename ASC, id ASC'
    }.get(sort_by, 'COALESCE(taken_date, mtime) DESC, id DESC')

    # 전체 개수
    cursor.execute(f"SELECT COUNT(*) as cnt FROM media_files {where_clause}", params)
    total = cursor.fetchone()['cnt']

    # 데이터 조회
    cursor.execute(f"""
        SELECT id, path, filename, extension, size, mtime, media_type,
               width, height, taken_date, camera_model
        FROM media_files
        {where_clause}
        ORDER BY {order_by}
        LIMIT ? OFFSET ?
    """, params + [limit, offset])

    items = []
    for row in cursor.fetchall():
        items.append({
            "id": row['id'],
            "path": row['path'],
            "filename": row['filename'],
            "extension": row['extension'],
            "size_mb": round(row['size'] / (1024 * 1024), 2) if row['size'] else 0,
            "mtime": row['mtime'],
            "media_type": row['media_type'],
            "width": row['width'],
            "height": row['height'],
            "taken_date": row['taken_date'],
            "camera": row['camera_model']
        })

    conn.close()

    return {
        "success": True,
        "total": total,
        "page": page,
        "limit": limit,
        "items": items
    }


def get_gps_photos(root_path: str) -> Dict:
    """GPS 정보가 있는 사진들 조회 (지도 표시용)"""
    # macOS NFD -> NFC 정규화
    root_path = _normalize_path(root_path)

    # 스캔 찾기
    scans = _load_scans_json()
    scan = None
    for s in scans:
        stored_path = _normalize_path(s.get('root_path', ''))
        if stored_path == root_path:
            scan = s
            break

    if not scan:
        return {"success": False, "error": "스캔 데이터가 없습니다.", "items": []}

    scan_id = scan['id']
    db_path = _get_db_path(scan_id)
    if not os.path.exists(db_path):
        return {"success": False, "error": "DB 파일이 없습니다.", "items": []}

    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # GPS 정보가 있는 사진만 조회
    cursor.execute("""
        SELECT id, path, filename, gps_lat, gps_lon, taken_date, mtime
        FROM media_files
        WHERE gps_lat IS NOT NULL AND gps_lon IS NOT NULL
          AND gps_lat != 0 AND gps_lon != 0
    """)

    items = []
    for row in cursor.fetchall():
        items.append({
            "id": row['id'],
            "path": row['path'],
            "filename": row['filename'],
            "lat": row['gps_lat'],
            "lon": row['gps_lon'],
            "taken_date": row['taken_date'],
            "mtime": row['mtime']
        })

    conn.close()

    return {
        "success": True,
        "total": len(items),
        "items": items
    }


def _calculate_md5(filepath: str, chunk_size: int = 65536) -> Optional[str]:
    """파일 MD5 해시 계산 (첫 64KB만 - 성능 최적화)"""
    try:
        md5 = hashlib.md5()
        with open(filepath, 'rb') as f:
            chunk = f.read(chunk_size)
            if chunk:
                md5.update(chunk)
        return md5.hexdigest()
    except (IOError, OSError):
        return None


def _update_file_hash(cursor, file_id: int, md5_hash: str):
    """파일 해시 업데이트"""
    cursor.execute("UPDATE media_files SET md5_hash = ? WHERE id = ?", (md5_hash, file_id))


def get_duplicates(root_path: str) -> Dict:
    """중복 파일 조회 (크기 기반 필터링 + MD5 해시 확인)"""
    # macOS NFD -> NFC 정규화
    root_path = _normalize_path(root_path)

    # 스캔 찾기
    scans = _load_scans_json()
    scan = None
    for s in scans:
        stored_path = _normalize_path(s.get('root_path', ''))
        if stored_path == root_path:
            scan = s
            break

    if not scan:
        return {"success": False, "error": "스캔 데이터가 없습니다."}

    scan_id = scan['id']
    db_path = _get_db_path(scan_id)

    if not os.path.exists(db_path):
        return {"success": False, "error": "스캔 DB가 없습니다."}

    conn = _get_connection(scan_id)
    cursor = conn.cursor()

    # 1단계: 같은 크기를 가진 파일 그룹 찾기 (잠재적 중복)
    cursor.execute("""
        SELECT size, COUNT(*) as cnt
        FROM media_files
        WHERE size > 0
        GROUP BY size
        HAVING cnt > 1
        ORDER BY size DESC
    """)

    size_groups = cursor.fetchall()

    # 2단계: 같은 크기의 파일들에 대해서만 해시 계산/확인
    groups = []
    total_duplicates = 0
    total_wasted_size = 0
    hash_calculated = 0

    for size_row in size_groups:
        file_size = size_row['size']

        # 해당 크기의 모든 파일 조회
        cursor.execute("""
            SELECT id, path, filename, size, mtime, media_type, md5_hash
            FROM media_files
            WHERE size = ?
        """, (file_size,))

        files_with_same_size = cursor.fetchall()

        # 해시별로 그룹화
        hash_groups = {}
        for f in files_with_same_size:
            file_hash = f['md5_hash']

            # 해시가 없으면 계산
            if file_hash is None:
                file_hash = _calculate_md5(f['path'])
                if file_hash:
                    _update_file_hash(cursor, f['id'], file_hash)
                    hash_calculated += 1

            if file_hash:
                if file_hash not in hash_groups:
                    hash_groups[file_hash] = []
                hash_groups[file_hash].append({
                    "id": f['id'],
                    "path": f['path'],
                    "filename": f['filename'],
                    "size_mb": round(f['size'] / (1024 * 1024), 2) if f['size'] else 0,
                    "mtime": f['mtime'],
                    "media_type": f['media_type']
                })

        # 2개 이상인 해시 그룹만 중복으로 처리
        for md5_hash, files in hash_groups.items():
            if len(files) > 1:
                # 수정일 기준 정렬
                files.sort(key=lambda x: x['mtime'] or '', reverse=True)
                wasted = sum(f['size_mb'] for f in files[1:])
                total_wasted_size += wasted
                total_duplicates += len(files) - 1

                groups.append({
                    "hash": md5_hash[:8] + "...",
                    "count": len(files),
                    "wasted_mb": round(wasted, 2),
                    "files": files
                })

    # 변경사항 저장
    conn.commit()
    conn.close()

    return {
        "success": True,
        "total_groups": len(groups),
        "total_duplicates": total_duplicates,
        "total_wasted_mb": round(total_wasted_size, 2),
        "hash_calculated": hash_calculated,
        "groups": groups
    }


def get_stats(root_path: str) -> Dict:
    """통계 조회"""
    # macOS NFD -> NFC 정규화
    root_path = _normalize_path(root_path)

    # 스캔 찾기
    scans = _load_scans_json()
    scan = None
    for s in scans:
        stored_path = _normalize_path(s.get('root_path', ''))
        if stored_path == root_path:
            scan = s
            break

    if not scan:
        return {"success": False, "error": "스캔 데이터가 없습니다."}

    scan_id = scan['id']
    db_path = _get_db_path(scan_id)

    if not os.path.exists(db_path):
        return {"success": False, "error": "스캔 DB가 없습니다."}

    conn = _get_connection(scan_id)
    cursor = conn.cursor()

    # 확장자별 통계
    cursor.execute("""
        SELECT extension, COUNT(*) as cnt, SUM(size) as total_size
        FROM media_files
        GROUP BY extension ORDER BY cnt DESC
    """)

    ext_stats = []
    for row in cursor.fetchall():
        ext_stats.append({
            "extension": row['extension'] or '(없음)',
            "count": row['cnt'],
            "size_mb": round(row['total_size'] / (1024 * 1024), 2) if row['total_size'] else 0
        })

    # 카메라별 통계
    cursor.execute("""
        SELECT camera_model, COUNT(*) as cnt
        FROM media_files WHERE camera_model IS NOT NULL
        GROUP BY camera_model ORDER BY cnt DESC LIMIT 10
    """)

    camera_stats = []
    for row in cursor.fetchall():
        camera_stats.append({
            "camera": row['camera_model'],
            "count": row['cnt']
        })

    conn.close()

    return {
        "success": True,
        "name": scan['name'],
        "root_path": scan['root_path'],
        "last_scan": scan.get('last_scan'),
        "photo_count": scan.get('photo_count', 0),
        "video_count": scan.get('video_count', 0),
        "total_size_mb": round(scan.get('total_size', 0) / (1024 * 1024), 2),
        "extensions": ext_stats,
        "cameras": camera_stats
    }


def get_timeline(root_path: str) -> Dict:
    """타임라인 (월별 촬영 통계)"""
    # macOS NFD -> NFC 정규화
    root_path = _normalize_path(root_path)

    # 스캔 찾기
    scans = _load_scans_json()
    scan = None
    for s in scans:
        stored_path = _normalize_path(s.get('root_path', ''))
        if stored_path == root_path:
            scan = s
            break

    if not scan:
        return {"success": False, "error": "스캔 데이터가 없습니다."}

    scan_id = scan['id']
    db_path = _get_db_path(scan_id)

    if not os.path.exists(db_path):
        return {"success": False, "error": "스캔 DB가 없습니다."}

    conn = _get_connection(scan_id)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT
            substr(COALESCE(taken_date, mtime), 1, 7) as month,
            media_type,
            COUNT(*) as cnt,
            SUM(size) as total_size
        FROM media_files
        GROUP BY month, media_type
        ORDER BY month DESC
    """)

    # 월별로 그룹화
    timeline = {}
    for row in cursor.fetchall():
        month = row['month']
        if month not in timeline:
            timeline[month] = {"month": month, "photos": 0, "videos": 0, "size_mb": 0}

        if row['media_type'] == 'photo':
            timeline[month]['photos'] = row['cnt']
        else:
            timeline[month]['videos'] = row['cnt']

        timeline[month]['size_mb'] += round(row['total_size'] / (1024 * 1024), 2) if row['total_size'] else 0

    conn.close()

    return {
        "success": True,
        "data": list(timeline.values())
    }


def get_media_detail(media_id: int, root_path: str = None) -> Dict:
    """미디어 상세 정보"""
    # macOS NFD -> NFC 정규화
    if root_path:
        root_path = _normalize_path(root_path)

    # root_path가 없으면 모든 스캔에서 찾기
    scans = _load_scans_json()

    if root_path:
        scan = None
        for s in scans:
            stored_path = _normalize_path(s.get('root_path', ''))
            if stored_path == root_path:
                scan = s
                break
        if scan:
            scans = [scan]

    for scan in scans:
        scan_id = scan['id']
        db_path = _get_db_path(scan_id)

        if not os.path.exists(db_path):
            continue

        conn = _get_connection(scan_id)
        cursor = conn.cursor()

        cursor.execute("SELECT * FROM media_files WHERE id = ?", (media_id,))
        row = cursor.fetchone()
        conn.close()

        if row:
            return {
                "success": True,
                "data": {
                    "id": row['id'],
                    "path": row['path'],
                    "filename": row['filename'],
                    "extension": row['extension'],
                    "size_mb": round(row['size'] / (1024 * 1024), 2) if row['size'] else 0,
                    "mtime": row['mtime'],
                    "media_type": row['media_type'],
                    "width": row['width'],
                    "height": row['height'],
                    "taken_date": row['taken_date'],
                    "camera_make": row['camera_make'],
                    "camera_model": row['camera_model'],
                    "gps_lat": row['gps_lat'],
                    "gps_lon": row['gps_lon'],
                    "duration": row['duration'],
                    "fps": row['fps'],
                    "codec": row['codec'],
                    "md5_hash": row['md5_hash'][:16] + "..." if row['md5_hash'] else None
                }
            }

    return {"success": False, "error": "파일을 찾을 수 없습니다."}


# ============ 호환성을 위한 get_connection (레거시) ============

def get_connection() -> sqlite3.Connection:
    """
    호환성 유지용 - 더 이상 사용하지 마세요.
    새 코드에서는 _get_connection(scan_id)를 사용하세요.
    """
    raise NotImplementedError(
        "get_connection()은 폴더별 DB 아키텍처에서 더 이상 지원되지 않습니다. "
        "특정 스캔의 DB에 접근하려면 해당 기능의 API를 사용하세요."
    )
