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
import tempfile
import unicodedata
from runtime_utils import expand_body_path  # 경로 펼침 단일 해소점 (~workspace/·~)
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
_scans_lock = threading.RLock()

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


def _abs(path: str, base: Optional[str] = None) -> str:
    """몸 토큰을 풀고 상대 경로는 호출한 프로젝트(base) 기준으로 — 프로세스 현재 폴더 기준이면
    `path:"."`·`"여행사진"` 메모가 백엔드 폴더 같은 엉뚱한 곳을 가리킨다(74회차 후속)."""
    expanded = expand_body_path(path)
    if base and not os.path.isabs(expanded):
        expanded = os.path.join(base, expanded)
    return _normalize_path(os.path.abspath(expanded))


def _ensure_scans_dir():
    """스캔 디렉토리 생성"""
    os.makedirs(SCANS_DIR, exist_ok=True)


def _load_scans_json() -> List[Dict]:
    """스캔 목록 JSON 로드"""
    _ensure_scans_dir()
    if not os.path.exists(SCANS_JSON):
        return []
    try:
        with open(SCANS_JSON, encoding='utf-8') as f:
            scans = json.load(f)
    except (ValueError, OSError) as exc:
        raise ValueError(f"스캔 원장 읽기 실패 — 원본을 보존합니다: {exc}") from exc
    if not isinstance(scans, list) or any(
            not isinstance(row, dict) or type(row.get('id')) is not int
            or not isinstance(row.get('root_path'), str)
            or not isinstance(row.get('name'), str) for row in scans):
        raise ValueError("스캔 원장 형식 오류 — 원본을 보존합니다.")
    return scans


def _save_scans_json(scans: List[Dict]):
    """완성된 JSON만 원자 교체해 동시 읽기·중간 실패로 원장이 깨지지 않게 한다."""
    _ensure_scans_dir()
    fd, temp = tempfile.mkstemp(dir=SCANS_DIR, suffix='.json')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(scans, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, SCANS_JSON)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def _get_db_path(scan_id: int) -> str:
    """스캔 ID에 해당하는 DB 파일 경로"""
    return os.path.join(SCANS_DIR, f"scan_{scan_id}.db")


def _get_connection(scan_id: int) -> sqlite3.Connection:
    """스캔별 DB 연결"""
    db_path = _get_db_path(scan_id)
    conn = sqlite3.connect(db_path, timeout=10)
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
    root_path = expand_body_path(root_path)
    root_path = os.path.abspath(root_path)
    root_path = _normalize_path(root_path)

    if not os.path.isdir(root_path):
        return {"success": False, "error": f"디렉토리가 아닙니다: {root_path}"}

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
        # 완성된 DB가 있을 때만 원장에 공개한다.
        _init_scan_db(scan_id)
        scans.append(new_scan)
        _save_scans_json(scans)

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
    """파일 색인만 지운다. 폴더 주석은 재스캔 이후에도 보존한다."""
    conn = _get_connection(scan_id)
    try:
        with conn:
            conn.execute("DELETE FROM files")
    finally:
        conn.close()


def save_file_batch(scan_id: int, file_list: List[Dict], connection=None):
    """파일 배치 저장"""
    if not file_list:
        return

    conn = connection or _get_connection(scan_id)
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

    if connection is None:
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


def scan_directory(path: str, scan_name: Optional[str] = None, progress_callback=None,
                   base: Optional[str] = None) -> Dict:
    """스캔과 원장 갱신을 직렬화해 뒤늦은 통계가 새 색인을 덮지 않게 한다."""
    with _scans_lock:
        return _scan_directory(path, scan_name, progress_callback, base)


def _scan_directory(path: str, scan_name: Optional[str] = None, progress_callback=None,
                    base: Optional[str] = None) -> Dict:
    """전체 순회가 성공한 파일 색인만 교체한다. 주석과 실패 전 색인은 보존한다."""
    path = _abs(path, base)
    if not os.path.isdir(path):
        return {"success": False, "error": f"디렉토리가 아닙니다: {path}"}
    result = create_scan(path, scan_name)
    if not result['success']:
        return result
    scan_id = result['scan_id']
    file_count = total_size = 0
    batch = []
    conn = _get_connection(scan_id)

    errors = []
    def walk_error(exc):
        errors.append({"path": getattr(exc, "filename", None), "error": str(exc)})

    try:
        # 삭제·배치 적재 전체가 한 트랜잭션. 독자는 직전 완성본을 본다.
        with conn:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM files")
            for root, dirs, files in os.walk(path, onerror=walk_error):
                dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS and not d.startswith('.')]
                for filename in files:
                    if filename in EXCLUDE_FILES or filename.startswith('.'):
                        continue
                    filepath = os.path.join(root, filename)
                    try:
                        # lstat — 링크는 링크 자체로 센다. 대상 추종은 깨진 링크를 접근 실패로,
                        # 살아 있는 링크를 대상 크기의 이중 계상으로 만든다(74회차 B74-3 ③).
                        stat = os.lstat(filepath)
                    except OSError as exc:
                        walk_error(exc)
                        continue
                    batch.append({
                        'path': filepath, 'filename': filename,
                        'extension': os.path.splitext(filename)[1].lower().lstrip('.'),
                        'size': stat.st_size,
                        'mtime': datetime.fromtimestamp(stat.st_mtime).isoformat(),
                    })
                    file_count += 1
                    total_size += stat.st_size
                    if len(batch) >= 5000:
                        save_file_batch(scan_id, batch, connection=conn)
                        batch = []
                    if progress_callback and file_count % 1000 == 0:
                        progress_callback(file_count)
            save_file_batch(scan_id, batch, connection=conn)
    except Exception as exc:
        return {"success": False, "error": f"스캔 실패 — 이전 색인·주석 보존: {exc}",
                "scan_id": scan_id}
    finally:
        conn.close()
    update_scan_stats(scan_id, file_count, total_size)
    scans = _load_scans_json()
    for scan in scans:
        if scan["id"] == scan_id:
            scan["source_complete"] = not errors
            scan["scan_errors"] = errors
    _save_scans_json(scans)
    return {"success": True, "scan_id": scan_id, "name": result.get('name'),
            "file_count": file_count, "total_size_mb": round(total_size / (1024 * 1024), 2),
            "error_count": len(errors), "errors": errors, "source_complete": not errors}


def get_summary_all() -> Dict:
    """모든 스캔 볼륨의 통합 요약 (root_path 미지정 시 기본 동작)."""
    scans = _load_scans_json()
    if not scans:
        return {"success": False,
                "error": "스캔된 볼륨이 없습니다. [self:storage]{op:scan, path:...}로 먼저 스캔하세요."}

    volumes = []
    total_files = 0
    total_size = 0
    for s in scans:
        fc = s.get('file_count', 0)
        ts = s.get('total_size', 0)
        total_files += fc
        total_size += ts
        volumes.append({
            "name": s['name'],
            "root_path": s['root_path'],
            "file_count": fc,
            "total_size_mb": round(ts / (1024 * 1024), 2),
            "last_scan": s.get('last_scan'),
        })

    states = [_scan_completeness(s) for s in scans]
    errors = [e for _, errs in states for e in errs]
    return {
        "success": True,
        "source_complete": all(ok for ok, _ in states),
        "errors": errors,
        **({"message": _incomplete_note(errors)} if errors else {}),
        "volume_count": len(scans),
        "total_file_count": total_files,
        "total_size_mb": round(total_size / (1024 * 1024), 2),
        "volumes": volumes,
        # F8-storage (2026-08-16 6회차): 볼륨 행=자연 items — "볼륨별 용량 표로/정렬"이
        # 파이프에 서게 병기(원형 volumes 보존).
        "items": volumes,
        "count": len(volumes),
    }


_LEGACY_SCAN_NOTE = ("이 스캔은 접근 실패 기록(2026-09-29) 이전에 만들어져 누락 여부를 알 수 없습니다 "
                     "(보호 폴더를 건너뛰고도 완전하다고 기록됐을 수 있음). 같은 경로를 다시 스캔하세요.")


def _scan_completeness(scan):
    """(완전 여부, 오류 표본). 완전성을 기록하지 않은 옛 스캔은 '완전'이 아니라 '미상'이다 —
    `/` 스캔이 보호 폴더(~/Downloads)를 통째로 빠뜨리고도 그 아래 요약을 0건·완전으로 답했다."""
    if "source_complete" not in scan:
        return False, [{"path": scan.get("root_path"), "error": _LEGACY_SCAN_NOTE}]
    return bool(scan["source_complete"]), list(scan.get("scan_errors") or [])


def _incomplete_note(errors):
    return f"스캔이 접근하지 못한 항목 {len(errors)}건 — 집계는 읽은 파일만 셉니다. 첫 사유: {errors[0].get('error')}"


def _under(path, root):
    """NFC 기준 포함 관계. 색인 경로는 파일시스템 원형(NFD 한글 폴더 포함)으로 저장돼 있다."""
    path = _normalize_path(path)
    return path == root or path.startswith(root.rstrip(os.sep) + os.sep)


def _resolve_scan(root_path, base=None):
    """Resolve a name, path token, or subtree to the most specific scan."""
    scans = _load_scans_json()
    named = [x for x in scans if x['name'] == root_path]
    if len(named) > 1:
        raise ValueError("같은 이름의 스캔이 여러 개입니다. root_path를 지정하세요.")
    path = named[0]['root_path'] if named else _abs(root_path, base)
    enclosing = [x for x in scans if os.path.commonpath([x['root_path'], path]) == x['root_path']]
    return (max(enclosing, key=lambda x: len(x['root_path'])) if enclosing else None), path


def get_summary(root_path: str, base: Optional[str] = None) -> Dict:
    """Complete extension and immediate-folder totals, including subtree queries."""
    scan, path = _resolve_scan(root_path, base)
    if not scan:
        return {"success": False, "error": "이 경로를 품은 스캔이 없습니다. 먼저 상위 폴더를 스캔하세요."}
    conn = _get_connection(scan['id'])
    try:
        # Prefix matching in Python avoids SQL LIKE metacharacter surprises.
        rows = [dict(row) for row in conn.execute('SELECT path, extension, size FROM files')
                if _under(row['path'], path)]
    finally:
        conn.close()
    extensions, folders = {}, {}
    for row in rows:
        ext = row['extension'] or '(없음)'
        relative = os.path.relpath(_normalize_path(row['path']), path)
        folder = relative.split(os.sep)[0] if os.sep in relative else '.'
        for groups, key in ((extensions, ext), (folders, folder)):
            item = groups.setdefault(key, {'count': 0, 'total_size': 0})
            item['count'] += 1
            item['total_size'] += row['size']
    def totals(groups, field):
        return [{field: k, **v, 'total_size_mb': round(v['total_size'] / 1048576, 2)}
                for k, v in sorted(groups.items(), key=lambda kv: (-kv[1]['total_size'], kv[0]))]
    ext_stats, folder_stats = totals(extensions, 'extension'), totals(folders, 'folder')
    complete, errors = _scan_completeness(scan)
    if errors and path != scan['root_path']:
        # 하위 경로 요약은 그 아래에서 난 실패만 불완전으로 센다(옛 스캔의 '미상'은 루트 표지라 늘 남는다).
        # 실패 경로가 조회 경로의 안쪽이거나 조상(잠긴 폴더의 안쪽을 물은 경우)이면 불완전이다.
        errors = [e for e in errors if not e.get('path') or e['path'] == scan['root_path']
                  or _under(e['path'], path) or _under(path, _normalize_path(e['path']))]
        complete = not errors
    return {'success': True, 'scan_id': scan['id'], 'name': scan['name'], 'root_path': path,
            'last_scan': scan.get('last_scan'), 'file_count': len(rows),
            'total_size_mb': round(sum(x['size'] for x in rows) / 1048576, 2),
            'top_extensions': ext_stats, 'folders': folder_stats, 'items': ext_stats,
            'count': len(ext_stats), 'truncated': False,  # truncation-scope: selection — 실제 반환 행 수와 전체 수 비교; 상한이 없으면 전량
            'source_complete': complete, 'errors': errors,
            **({'message': _incomplete_note(errors)} if errors else {})}


def add_annotation(root_path: str, folder_path: str, note: str, base: Optional[str] = None) -> Dict:
    """Set one current note per existing folder, inside the selected scan."""
    with _scans_lock:
        scan, _ = _resolve_scan(root_path, base)
        folder_path = _abs(folder_path, base)
        if not scan or os.path.commonpath([scan['root_path'], folder_path]) != scan['root_path']:
            return {'success': False, 'error': '주석 폴더는 선택한 스캔 안에 있어야 합니다.'}
        if not os.path.isdir(folder_path):
            return {'success': False, 'error': f'존재하는 폴더가 아닙니다: {folder_path}'}
        conn = _get_connection(scan['id'])
        try:
            with conn:
                # Also consolidate historical duplicates after path normalization.
                for row in conn.execute('SELECT id, folder_path FROM annotations').fetchall():
                    old = _abs(row['folder_path'])
                    if old == folder_path:
                        conn.execute('DELETE FROM annotations WHERE id = ?', (row['id'],))
                conn.execute('INSERT INTO annotations (folder_path, note) VALUES (?, ?)', (folder_path, note))
        finally:
            conn.close()
    return {'success': True, 'folder_path': folder_path, 'note': note}


def get_annotations_all() -> Dict:
    """모든 스캔 볼륨의 폴더 주석 통합 조회 (root_path 미지정 시 기본 동작)."""
    scans = _load_scans_json()
    if not scans:
        return {"success": True, "annotations": []}

    annotations = []
    for s in scans:
        try:
            conn = _get_connection(s['id'])
            cursor = conn.cursor()
            cursor.execute("""
                SELECT folder_path, note, created_at
                FROM annotations ORDER BY created_at DESC
            """)
            for row in cursor.fetchall():
                annotations.append({
                    "volume": s['name'],
                    "root_path": s['root_path'],
                    "folder_path": row['folder_path'],
                    "note": row['note'],
                    "created_at": row['created_at'],
                })
            conn.close()
        except Exception:
            continue

    return {"success": True, "annotations": annotations, "items": annotations, "count": len(annotations)}


def get_annotations(root_path: str, base: Optional[str] = None) -> Dict:
    """폴더 주석 조회 — 준 경로 아래의 주석만. 하위 폴더로 물으면 품은 스캔의 전부가 아니라 그 폴더 아래."""
    scan, root_path = _resolve_scan(root_path, base)

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
        # 옛 행은 받은 토큰 원문(~workspace/…)으로 저장돼 있다 — 보여 줄 때도 한 해소점으로 푼다.
        folder = _abs(row['folder_path'])
        if not _under(folder, root_path):
            continue
        annotations.append({
            "folder_path": folder,
            "note": row['note'],
            "created_at": row['created_at']
        })

    conn.close()
    return {"success": True, "annotations": annotations, "items": annotations, "count": len(annotations)}


# 하위 호환성을 위한 별칭
def list_volumes() -> Dict:
    """볼륨 목록 (하위 호환성)"""
    result = list_scans()
    return {"success": True, "volumes": result.get('scans', [])}
