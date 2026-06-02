"""
storage_db.py - 스토리지 인덱싱 DB 관리
파일 메타데이터와 사용자 주석을 SQLite에 저장/검색
폴더별 개별 DB 구조 (사진관리창과 동일)
"""

import os
import json
import sqlite3
import subprocess
import threading
import unicodedata
from datetime import datetime
from typing import List, Dict, Optional, Tuple
from pathlib import Path

# 스캔 데이터 저장 경로
SCANS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))),
    "storage_scans"
)

# 스캔 목록 JSON 파일
SCANS_JSON = os.path.join(SCANS_DIR, "scans.json")

# 스캔 목록 접근 락
_scans_lock = threading.Lock()

# 스캔 제외 폴더
EXCLUDE_DIRS = {
    'node_modules', '.git', '__pycache__', '.venv', 'venv',
    '.idea', '.vscode', '.DS_Store', 'dist', 'build',
    '.cache', '.npm', '.yarn', 'vendor', '.gradle'
}

# 제외 파일 패턴
EXCLUDE_FILES = {'.DS_Store', '.gitignore', 'Thumbs.db', 'desktop.ini'}


def _normalize_path(path: str) -> str:
    """macOS NFD -> NFC 정규화"""
    return unicodedata.normalize('NFC', path)


def _ensure_scans_dir():
    """스캔 디렉토리 생성"""
    os.makedirs(SCANS_DIR, exist_ok=True)


def _load_scans_json() -> List[Dict]:
    """스캔 목록 JSON 로드"""
    _ensure_scans_dir()
    if os.path.exists(SCANS_JSON):
        try:
            with open(SCANS_JSON, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
    return []


def _save_scans_json(scans: List[Dict]):
    """스캔 목록 JSON 저장"""
    _ensure_scans_dir()
    with open(SCANS_JSON, 'w', encoding='utf-8') as f:
        json.dump(scans, f, ensure_ascii=False, indent=2)


def _get_db_path(scan_id: int) -> str:
    """스캔 ID에 해당하는 DB 파일 경로"""
    return os.path.join(SCANS_DIR, f"scan_{scan_id}.db")


def _get_connection(scan_id: int) -> sqlite3.Connection:
    """스캔별 DB 연결"""
    db_path = _get_db_path(scan_id)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def _init_scan_db(scan_id: int):
    """스캔별 DB 테이블 초기화"""
    conn = _get_connection(scan_id)
    cursor = conn.cursor()

    # 파일 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT UNIQUE NOT NULL,
            filename TEXT NOT NULL,
            extension TEXT,
            size INTEGER DEFAULT 0,
            mtime TEXT
        )
    """)

    # 파일명 검색용 FTS 인덱스
    cursor.execute("""
        CREATE VIRTUAL TABLE IF NOT EXISTS files_fts USING fts5(
            filename, path,
            content='files',
            content_rowid='id'
        )
    """)

    # FTS 트리거 (INSERT)
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS files_ai AFTER INSERT ON files BEGIN
            INSERT INTO files_fts(rowid, filename, path)
            VALUES (new.id, new.filename, new.path);
        END
    """)

    # FTS 트리거 (DELETE)
    cursor.execute("""
        CREATE TRIGGER IF NOT EXISTS files_ad AFTER DELETE ON files BEGIN
            INSERT INTO files_fts(files_fts, rowid, filename, path)
            VALUES ('delete', old.id, old.filename, old.path);
        END
    """)

    # 폴더 주석 테이블
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS annotations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            folder_path TEXT NOT NULL,
            note TEXT NOT NULL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 인덱스
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_ext ON files(extension)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_files_size ON files(size)")

    conn.commit()
    conn.close()


def get_volume_uuid(path: str) -> Optional[str]:
    """macOS에서 볼륨 UUID 가져오기"""
    try:
        if path.startswith('/Volumes/'):
            result = subprocess.run(
                ['diskutil', 'info', path],
                capture_output=True, text=True
            )
            for line in result.stdout.split('\n'):
                if 'Volume UUID' in line or 'Disk / Partition UUID' in line:
                    return line.split(':')[-1].strip()
        return None
    except Exception:
        return None


def list_scans() -> Dict:
    """모든 스캔 목록"""
    scans = _load_scans_json()
    result = []
    for s in scans:
        result.append({
            "id": s['id'],
            "name": s['name'],
            "root_path": s['root_path'],
            "last_scan": s.get('last_scan'),
            "file_count": s.get('file_count', 0),
            "total_size_mb": round(s.get('total_size', 0) / (1024 * 1024), 2)
        })
    return {"success": True, "scans": result}


def create_scan(root_path: str, name: Optional[str] = None) -> Dict:
    """새 스캔 생성"""
    root_path = os.path.expanduser(root_path)
    root_path = os.path.abspath(root_path)
    root_path = _normalize_path(root_path)

    if not os.path.exists(root_path):
        return {"success": False, "error": f"경로가 존재하지 않습니다: {root_path}"}

    # 이름 자동 생성
    if not name:
        if root_path.startswith('/Volumes/'):
            parts = root_path.split('/')
            if len(parts) >= 4:
                name = f"{parts[2]}/{parts[-1]}"
            elif len(parts) == 3:
                name = parts[2]
            else:
                name = 'Unknown'
        else:
            name = os.path.basename(root_path) or 'LocalDisk'

    with _scans_lock:
        scans = _load_scans_json()

        # 중복 확인
        for s in scans:
            if _normalize_path(s.get('root_path', '')) == root_path:
                return {"success": True, "scan_id": s['id'], "name": s['name'], "exists": True}

        # 새 ID 생성
        scan_id = max([s['id'] for s in scans], default=0) + 1

        new_scan = {
            "id": scan_id,
            "name": name,
            "root_path": root_path,
            "uuid": get_volume_uuid(root_path),
            "last_scan": None,
            "file_count": 0,
            "total_size": 0
        }
        scans.append(new_scan)
        _save_scans_json(scans)

    # DB 초기화
    _init_scan_db(scan_id)

    return {"success": True, "scan_id": scan_id, "name": name, "exists": False}


def delete_scan(scan_id: int) -> Dict:
    """스캔 삭제"""
    with _scans_lock:
        scans = _load_scans_json()

        # 스캔 찾기
        scan = None
        for s in scans:
            if s['id'] == scan_id:
                scan = s
                break

        if not scan:
            return {"success": False, "error": f"스캔을 찾을 수 없습니다: {scan_id}"}

        # 목록에서 제거
        scans = [s for s in scans if s['id'] != scan_id]
        _save_scans_json(scans)

    # DB 파일 삭제
    db_path = _get_db_path(scan_id)
    if os.path.exists(db_path):
        os.remove(db_path)

    return {"success": True, "deleted_id": scan_id, "name": scan.get('name')}


def clear_scan_data(scan_id: int):
    """스캔 데이터 초기화 (재스캔용)"""
    db_path = _get_db_path(scan_id)
    if os.path.exists(db_path):
        os.remove(db_path)
    _init_scan_db(scan_id)


def save_file_batch(scan_id: int, file_list: List[Dict]):
    """파일 배치 저장"""
    if not file_list:
        return

    conn = _get_connection(scan_id)
    cursor = conn.cursor()

    cursor.executemany("""
        INSERT OR REPLACE INTO files
        (path, filename, extension, size, mtime)
        VALUES (?, ?, ?, ?, ?)
    """, [(
        f.get('path'),
        f.get('filename'),
        f.get('extension'),
        f.get('size', 0),
        f.get('mtime')
    ) for f in file_list])

    conn.commit()
    conn.close()


def update_scan_stats(scan_id: int, file_count: int, total_size: int):
    """스캔 통계 업데이트"""
    with _scans_lock:
        scans = _load_scans_json()
        for s in scans:
            if s['id'] == scan_id:
                s['last_scan'] = datetime.now().isoformat()
                s['file_count'] = file_count
                s['total_size'] = total_size
                break
        _save_scans_json(scans)


def scan_directory(path: str, scan_name: Optional[str] = None, progress_callback=None) -> Dict:
    """디렉토리 스캔하여 파일 메타데이터 수집"""
    path = os.path.expanduser(path)
    path = os.path.abspath(path)
    path = _normalize_path(path)

    if not os.path.exists(path):
        return {"success": False, "error": f"경로가 존재하지 않습니다: {path}"}

    # 스캔 생성 또는 기존 스캔 찾기
    result = create_scan(path, scan_name)
    if not result['success']:
        return result

    scan_id = result['scan_id']

    # 기존 데이터 삭제 (재스캔)
    clear_scan_data(scan_id)

    # 스캔 시작
    file_count = 0
    total_size = 0
    error_count = 0
    batch = []
    BATCH_SIZE = 5000

    for root, dirs, files in os.walk(path):
        # 제외 폴더 필터링
        dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith('.')]

        for filename in files:
            if filename in EXCLUDE_FILES or filename.startswith('.'):
                continue

            filepath = os.path.join(root, filename)
            try:
                stat = os.stat(filepath)
                ext = os.path.splitext(filename)[1].lower().lstrip('.')
                mtime = datetime.fromtimestamp(stat.st_mtime).isoformat()

                batch.append({
                    'path': filepath,
                    'filename': filename,
                    'extension': ext,
                    'size': stat.st_size,
                    'mtime': mtime
                })
                file_count += 1
                total_size += stat.st_size

                # 배치 저장
                if len(batch) >= BATCH_SIZE:
                    save_file_batch(scan_id, batch)
                    batch = []

                # 진행 콜백
                if progress_callback and file_count % 1000 == 0:
                    progress_callback(file_count)

            except (OSError, PermissionError):
                error_count += 1

    # 남은 배치 처리
    if batch:
        save_file_batch(scan_id, batch)

    # 통계 업데이트
    update_scan_stats(scan_id, file_count, total_size)

    return {
        "success": True,
        "scan_id": scan_id,
        "name": result.get('name'),
        "file_count": file_count,
        "total_size_mb": round(total_size / (1024 * 1024), 2),
        "error_count": error_count
    }


def query_files(
    root_path: str,
    search_term: Optional[str] = None,
    extension: Optional[str] = None,
    min_size_mb: Optional[float] = None,
    page: int = 1,
    limit: int = 100
) -> Dict:
    """파일 검색"""
    root_path = _normalize_path(os.path.abspath(os.path.expanduser(root_path)))

    # 스캔 찾기
    scans = _load_scans_json()
    scan = None
    for s in scans:
        if _normalize_path(s.get('root_path', '')) == root_path:
            scan = s
            break

    if not scan:
        return {"success": False, "error": "스캔 데이터가 없습니다."}

    scan_id = scan['id']
    db_path = _get_db_path(scan_id)

    if not os.path.exists(db_path):
        return {"success": False, "error": "DB 파일이 없습니다."}

    conn = _get_connection(scan_id)
    cursor = conn.cursor()

    offset = (page - 1) * limit

    # 검색어가 있으면 FTS 사용
    if search_term:
        query = """
            SELECT f.*
            FROM files f
            JOIN files_fts fts ON f.id = fts.rowid
            WHERE files_fts MATCH ?
        """
        params = [f'"{search_term}"*']
    else:
        query = "SELECT * FROM files WHERE 1=1"
        params = []

    if extension:
        query += " AND extension = ?"
        params.append(extension.lower().lstrip('.'))

    if min_size_mb:
        query += " AND size >= ?"
        params.append(int(min_size_mb * 1024 * 1024))

    # 전체 개수
    count_query = query.replace("SELECT f.*", "SELECT COUNT(*) as cnt").replace("SELECT *", "SELECT COUNT(*) as cnt")
    cursor.execute(count_query, params)
    total = cursor.fetchone()['cnt']

    # 데이터 조회
    query += " ORDER BY size DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cursor.execute(query, params)
    rows = cursor.fetchall()

    results = []
    for row in rows:
        results.append({
            "id": row['id'],
            "path": row['path'],
            "filename": row['filename'],
            "extension": row['extension'],
            "size_mb": round(row['size'] / (1024 * 1024), 2),
            "mtime": row['mtime']
        })

    conn.close()

    return {
        "success": True,
        "total": total,
        "page": page,
        "limit": limit,
        "files": results
    }


def get_summary(root_path: str) -> Dict:
    """스캔 요약 정보"""
    root_path = _normalize_path(os.path.abspath(os.path.expanduser(root_path)))

    # 스캔 찾기
    scans = _load_scans_json()
    scan = None
    for s in scans:
        if _normalize_path(s.get('root_path', '')) == root_path:
            scan = s
            break

    if not scan:
        return {"success": False, "error": "스캔 데이터가 없습니다."}

    scan_id = scan['id']
    db_path = _get_db_path(scan_id)

    if not os.path.exists(db_path):
        return {"success": False, "error": "DB 파일이 없습니다."}

    conn = _get_connection(scan_id)
    cursor = conn.cursor()

    # 확장자별 통계
    cursor.execute("""
        SELECT extension, COUNT(*) as count, SUM(size) as total_size
        FROM files
        GROUP BY extension ORDER BY total_size DESC LIMIT 20
    """)
    ext_stats = []
    for row in cursor.fetchall():
        ext_stats.append({
            "extension": row['extension'] or '(없음)',
            "count": row['count'],
            "total_size_mb": round((row['total_size'] or 0) / (1024 * 1024), 2)
        })

    conn.close()

    return {
        "success": True,
        "scan_id": scan['id'],
        "name": scan['name'],
        "root_path": scan['root_path'],
        "last_scan": scan.get('last_scan'),
        "file_count": scan.get('file_count', 0),
        "total_size_mb": round(scan.get('total_size', 0) / (1024 * 1024), 2),
        "top_extensions": ext_stats
    }


def add_annotation(root_path: str, folder_path: str, note: str) -> Dict:
    """폴더에 주석 추가"""
    root_path = _normalize_path(os.path.abspath(os.path.expanduser(root_path)))

    # 스캔 찾기
    scans = _load_scans_json()
    scan = None
    for s in scans:
        if _normalize_path(s.get('root_path', '')) == root_path:
            scan = s
            break

    if not scan:
        return {"success": False, "error": "스캔 데이터가 없습니다."}

    conn = _get_connection(scan['id'])
    cursor = conn.cursor()

    cursor.execute("""
        INSERT INTO annotations (folder_path, note)
        VALUES (?, ?)
    """, (folder_path, note))

    conn.commit()
    conn.close()

    return {"success": True, "folder_path": folder_path, "note": note}


def get_annotations(root_path: str) -> Dict:
    """폴더 주석 조회"""
    root_path = _normalize_path(os.path.abspath(os.path.expanduser(root_path)))

    # 스캔 찾기
    scans = _load_scans_json()
    scan = None
    for s in scans:
        if _normalize_path(s.get('root_path', '')) == root_path:
            scan = s
            break

    if not scan:
        return {"success": False, "error": "스캔 데이터가 없습니다.", "annotations": []}

    conn = _get_connection(scan['id'])
    cursor = conn.cursor()

    cursor.execute("""
        SELECT folder_path, note, created_at
        FROM annotations ORDER BY created_at DESC
    """)

    annotations = []
    for row in cursor.fetchall():
        annotations.append({
            "folder_path": row['folder_path'],
            "note": row['note'],
            "created_at": row['created_at']
        })

    conn.close()
    return {"success": True, "annotations": annotations}


# 하위 호환성을 위한 별칭
def list_volumes() -> Dict:
    """볼륨 목록 (하위 호환성)"""
    result = list_scans()
    return {"success": True, "volumes": result.get('scans', [])}
