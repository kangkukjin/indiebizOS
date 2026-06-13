"""
건강 기록 저장소 - SQLite 기반 건강 데이터 관리
다중 사용자(환자) 지원
"""
import os
import sqlite3
import json
import uuid as _uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

# === 폰↔PC 동기화용 식별자 (business.db 선례 — backend/business_sync.py) ===
# 정수 rowid 는 기기마다 충돌 → uuid 로 레코드 동일성 판정. 인물은 이름 자연키라 결정적 uuid
# (양 기기의 "강국진"이 같은 식별자로 수렴 → 중복 인물 방지). 자식 기록은 무작위 uuid.
_SYNC_NS = _uuid.UUID("6f1b2c3d-0000-4000-8000-000000000001")  # business_manager 와 동일 네임스페이스


def _new_uuid() -> str:
    return _uuid.uuid4().hex


def _person_uuid(name: str) -> str:
    return _uuid.uuid5(_SYNC_NS, "person:" + (name or "")).hex


def _now() -> str:
    return datetime.now().isoformat()

# 데이터 저장 경로
# 패키지 위치: data/packages/installed/tools/health-record
# 저장 위치: data/health
_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
# installed/tools/health-record → installed/tools → installed → packages → data
_DATA_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(_PACKAGE_DIR))))
DATA_DIR = os.path.join(_DATA_DIR, 'health')
DB_PATH = os.path.join(DATA_DIR, 'health_records.db')
IMAGES_DIR = os.path.join(DATA_DIR, 'images')

# 기본 사용자 (명시하지 않을 경우)
DEFAULT_PERSON = "강국진"


def get_db_connection():
    """DB 연결 및 초기화"""
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(IMAGES_DIR, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row

    # 테이블 생성 — 동기화 컬럼(uuid/updated_at/deleted, 자식 person_uuid) 포함(신규 DB).
    # 기존 DB 는 _migrate_sync_columns 가 ALTER 로 소급 추가 + backfill.
    conn.executescript('''
        -- 사용자(환자) 테이블
        CREATE TABLE IF NOT EXISTS persons (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            birth_date DATE,
            gender TEXT,
            note TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            uuid TEXT,
            updated_at TEXT,
            deleted INTEGER DEFAULT 0
        );

        -- 측정값 (혈압, 혈당, 체중 등)
        CREATE TABLE IF NOT EXISTS measurements (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id INTEGER NOT NULL DEFAULT 1,
            category TEXT NOT NULL,
            value_json TEXT NOT NULL,
            measured_at DATETIME NOT NULL,
            note TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            person_uuid TEXT,
            uuid TEXT,
            updated_at TEXT,
            deleted INTEGER DEFAULT 0,
            FOREIGN KEY (person_id) REFERENCES persons(id)
        );

        -- 증상/이벤트 (감기, 두통, 배탈 등)
        CREATE TABLE IF NOT EXISTS symptoms (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id INTEGER NOT NULL DEFAULT 1,
            category TEXT NOT NULL,
            description TEXT,
            severity TEXT,
            started_at DATE NOT NULL,
            ended_at DATE,
            note TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            person_uuid TEXT,
            uuid TEXT,
            updated_at TEXT,
            deleted INTEGER DEFAULT 0,
            FOREIGN KEY (person_id) REFERENCES persons(id)
        );

        -- 투약 기록
        CREATE TABLE IF NOT EXISTS medications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id INTEGER NOT NULL DEFAULT 1,
            name TEXT NOT NULL,
            dosage TEXT,
            frequency TEXT,
            reason TEXT,
            started_at DATE NOT NULL,
            ended_at DATE,
            is_active INTEGER DEFAULT 1,
            note TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            person_uuid TEXT,
            uuid TEXT,
            updated_at TEXT,
            deleted INTEGER DEFAULT 0,
            FOREIGN KEY (person_id) REFERENCES persons(id)
        );

        -- 문서/이미지 (검사결과, 처방전 등)
        CREATE TABLE IF NOT EXISTS documents (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            person_id INTEGER NOT NULL DEFAULT 1,
            doc_type TEXT NOT NULL,
            image_path TEXT,
            extracted_data TEXT,
            description TEXT,
            recorded_at DATE NOT NULL,
            note TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            person_uuid TEXT,
            uuid TEXT,
            updated_at TEXT,
            deleted INTEGER DEFAULT 0,
            FOREIGN KEY (person_id) REFERENCES persons(id)
        );

        -- 인덱스
        CREATE INDEX IF NOT EXISTS idx_measurements_person ON measurements(person_id);
        CREATE INDEX IF NOT EXISTS idx_measurements_category ON measurements(category);
        CREATE INDEX IF NOT EXISTS idx_measurements_date ON measurements(measured_at);
        CREATE INDEX IF NOT EXISTS idx_symptoms_person ON symptoms(person_id);
        CREATE INDEX IF NOT EXISTS idx_symptoms_category ON symptoms(category);
        CREATE INDEX IF NOT EXISTS idx_symptoms_date ON symptoms(started_at);
        CREATE INDEX IF NOT EXISTS idx_medications_person ON medications(person_id);
        CREATE INDEX IF NOT EXISTS idx_medications_active ON medications(is_active);
        CREATE INDEX IF NOT EXISTS idx_documents_person ON documents(person_id);
    ''')

    # 기존 DB 동기화 컬럼 소급 + backfill (멱등, 첫 호출 1회만 실질 작업)
    _migrate_sync_columns(conn)

    # 기본 사용자 생성 (없으면) — 결정적 uuid + updated_at 스탬프
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM persons WHERE name = ?", (DEFAULT_PERSON,))
    if not cursor.fetchone():
        cursor.execute("INSERT INTO persons (name, note, uuid, updated_at) VALUES (?, ?, ?, ?)",
                      (DEFAULT_PERSON, "기본 사용자", _person_uuid(DEFAULT_PERSON), _now()))

    conn.commit()
    return conn


_sync_migrated = False  # 프로세스당 1회만 backfill 검사 (get_db_connection 매 호출 비용 절감)


def _migrate_sync_columns(conn):
    """기존 health_records.db 에 동기화 컬럼 소급 추가 + 기존 행 backfill. 멱등.
    persons.uuid=결정적(이름), 자식 uuid=무작위 + person_uuid(부모 결정적 uuid)."""
    global _sync_migrated
    cur = conn.cursor()

    def colnames(t):
        return [r[1] for r in cur.execute(f"PRAGMA table_info({t})").fetchall()]

    child = ["measurements", "symptoms", "medications", "documents"]
    # 1) ADD COLUMN (없을 때만 — 신규 DB 는 이미 있어 스킵)
    for t in ["persons"] + child:
        c = colnames(t)
        if "uuid" not in c: cur.execute(f"ALTER TABLE {t} ADD COLUMN uuid TEXT")
        if "updated_at" not in c: cur.execute(f"ALTER TABLE {t} ADD COLUMN updated_at TEXT")
        if "deleted" not in c: cur.execute(f"ALTER TABLE {t} ADD COLUMN deleted INTEGER DEFAULT 0")
        if t in child and "person_uuid" not in c:
            cur.execute(f"ALTER TABLE {t} ADD COLUMN person_uuid TEXT")

    if _sync_migrated:
        return  # 컬럼 보장만 하고 backfill 스캔은 프로세스당 1회

    # 2) persons backfill: 결정적 uuid + updated_at (uuid 없는 행만)
    for r in cur.execute("SELECT id, name, created_at FROM persons WHERE uuid IS NULL OR updated_at IS NULL").fetchall():
        cur.execute("UPDATE persons SET uuid=COALESCE(uuid, ?), updated_at=COALESCE(updated_at, ?, ?), deleted=COALESCE(deleted, 0) WHERE id=?",
                    (_person_uuid(r["name"]), r["created_at"], _now(), r["id"]))

    pmap = {r["id"]: r["uuid"] for r in cur.execute("SELECT id, uuid FROM persons").fetchall()}

    # 3) 자식 backfill: uuid(무작위) + person_uuid(부모 결정적) + updated_at (미설정 행만)
    date_field = {"measurements": "measured_at", "symptoms": "started_at",
                  "medications": "started_at", "documents": "recorded_at"}
    for t in child:
        df = date_field[t]
        for r in cur.execute(f"SELECT id, person_id, created_at, {df} AS df FROM {t} WHERE uuid IS NULL OR person_uuid IS NULL OR updated_at IS NULL").fetchall():
            cur.execute(
                f"UPDATE {t} SET uuid=COALESCE(uuid, ?), person_uuid=COALESCE(person_uuid, ?), "
                f"updated_at=COALESCE(updated_at, ?, ?, ?), deleted=COALESCE(deleted, 0) WHERE id=?",
                (_new_uuid(), pmap.get(r["person_id"]), r["created_at"], r["df"], _now(), r["id"]))

    conn.commit()
    _sync_migrated = True


def get_or_create_person(name: str) -> int:
    """사용자 ID 조회 또는 생성"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id FROM persons WHERE name = ?", (name,))
    row = cursor.fetchone()

    if row:
        person_id = row['id']
    else:
        cursor.execute("INSERT INTO persons (name, uuid, updated_at) VALUES (?, ?, ?)",
                       (name, _person_uuid(name), _now()))
        person_id = cursor.lastrowid
        conn.commit()

    conn.close()
    return person_id


def list_persons() -> List[Dict]:
    """등록된 사용자 목록"""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM persons ORDER BY id")
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_person_id(person: str = None) -> int:
    """사용자 이름으로 ID 조회 (없으면 기본 사용자)"""
    if not person or person == "나":
        person = DEFAULT_PERSON
    return get_or_create_person(person)


def save_measurement(category: str, value: dict, measured_at: str = None,
                     note: str = None, person: str = None) -> int:
    """측정값 저장"""
    conn = get_db_connection()
    cursor = conn.cursor()

    person_id = get_person_id(person)

    if not measured_at:
        measured_at = datetime.now().isoformat()

    prow = conn.execute("SELECT uuid FROM persons WHERE id=?", (person_id,)).fetchone()
    puuid = prow["uuid"] if prow else None
    cursor.execute('''
        INSERT INTO measurements (person_id, category, value_json, measured_at, note, person_uuid, uuid, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (person_id, category, json.dumps(value, ensure_ascii=False), measured_at, note, puuid, _new_uuid(), _now()))

    record_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return record_id


def save_symptom(category: str, description: str = None, severity: str = None,
                 started_at: str = None, ended_at: str = None, note: str = None,
                 person: str = None) -> int:
    """증상/이벤트 저장"""
    conn = get_db_connection()
    cursor = conn.cursor()

    person_id = get_person_id(person)

    if not started_at:
        started_at = datetime.now().strftime('%Y-%m-%d')

    prow = conn.execute("SELECT uuid FROM persons WHERE id=?", (person_id,)).fetchone()
    puuid = prow["uuid"] if prow else None
    cursor.execute('''
        INSERT INTO symptoms (person_id, category, description, severity, started_at, ended_at, note, person_uuid, uuid, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (person_id, category, description, severity, started_at, ended_at, note, puuid, _new_uuid(), _now()))

    record_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return record_id


def save_medication(name: str, dosage: str = None, frequency: str = None,
                    reason: str = None, started_at: str = None, ended_at: str = None,
                    note: str = None, person: str = None) -> int:
    """투약 기록 저장"""
    conn = get_db_connection()
    cursor = conn.cursor()

    person_id = get_person_id(person)

    if not started_at:
        started_at = datetime.now().strftime('%Y-%m-%d')

    is_active = 1 if not ended_at else 0

    prow = conn.execute("SELECT uuid FROM persons WHERE id=?", (person_id,)).fetchone()
    puuid = prow["uuid"] if prow else None
    cursor.execute('''
        INSERT INTO medications (person_id, name, dosage, frequency, reason, started_at, ended_at, is_active, note, person_uuid, uuid, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (person_id, name, dosage, frequency, reason, started_at, ended_at, is_active, note, puuid, _new_uuid(), _now()))

    record_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return record_id


def save_document(doc_type: str, image_path: str = None, extracted_data: dict = None,
                  description: str = None, recorded_at: str = None, note: str = None,
                  person: str = None) -> int:
    """문서/이미지 저장"""
    conn = get_db_connection()
    cursor = conn.cursor()

    person_id = get_person_id(person)

    if not recorded_at:
        recorded_at = datetime.now().strftime('%Y-%m-%d')

    extracted_json = json.dumps(extracted_data, ensure_ascii=False) if extracted_data else None

    prow = conn.execute("SELECT uuid FROM persons WHERE id=?", (person_id,)).fetchone()
    puuid = prow["uuid"] if prow else None
    cursor.execute('''
        INSERT INTO documents (person_id, doc_type, image_path, extracted_data, description, recorded_at, note, person_uuid, uuid, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (person_id, doc_type, image_path, extracted_json, description, recorded_at, note, puuid, _new_uuid(), _now()))

    record_id = cursor.lastrowid
    conn.commit()
    conn.close()
    return record_id


def get_measurements(category: str = None, days: int = 30, limit: int = 50,
                     person: str = None) -> List[Dict]:
    """측정값 조회"""
    conn = get_db_connection()
    cursor = conn.cursor()

    person_id = get_person_id(person)
    since_date = (datetime.now() - timedelta(days=days)).isoformat()

    if category:
        cursor.execute('''
            SELECT * FROM measurements
            WHERE person_id = ? AND category = ? AND measured_at >= ?
            ORDER BY measured_at DESC LIMIT ?
        ''', (person_id, category, since_date, limit))
    else:
        cursor.execute('''
            SELECT * FROM measurements
            WHERE person_id = ? AND measured_at >= ?
            ORDER BY measured_at DESC LIMIT ?
        ''', (person_id, since_date, limit))

    rows = cursor.fetchall()
    conn.close()

    results = []
    for row in rows:
        r = dict(row)
        r['value'] = json.loads(r['value_json'])
        del r['value_json']
        results.append(r)
    return results


def get_symptoms(category: str = None, days: int = 30, include_ended: bool = True,
                 person: str = None) -> List[Dict]:
    """증상 조회"""
    conn = get_db_connection()
    cursor = conn.cursor()

    person_id = get_person_id(person)
    since_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

    query = 'SELECT * FROM symptoms WHERE person_id = ? AND started_at >= ?'
    params = [person_id, since_date]

    if category:
        query += ' AND category = ?'
        params.append(category)

    if not include_ended:
        query += ' AND ended_at IS NULL'

    query += ' ORDER BY started_at DESC'

    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def get_active_medications(person: str = None) -> List[Dict]:
    """현재 복용 중인 약물 조회"""
    conn = get_db_connection()
    cursor = conn.cursor()

    person_id = get_person_id(person)

    cursor.execute('''
        SELECT * FROM medications WHERE person_id = ? AND is_active = 1
        ORDER BY started_at DESC
    ''', (person_id,))

    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_medications(days: int = 90, active_only: bool = False, person: str = None) -> List[Dict]:
    """투약 기록 조회"""
    conn = get_db_connection()
    cursor = conn.cursor()

    person_id = get_person_id(person)
    since_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

    if active_only:
        cursor.execute('''
            SELECT * FROM medications WHERE person_id = ? AND is_active = 1
            ORDER BY started_at DESC
        ''', (person_id,))
    else:
        cursor.execute('''
            SELECT * FROM medications WHERE person_id = ? AND started_at >= ?
            ORDER BY started_at DESC
        ''', (person_id, since_date))

    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


def get_documents(doc_type: str = None, days: int = 90, person: str = None) -> List[Dict]:
    """문서 조회"""
    conn = get_db_connection()
    cursor = conn.cursor()

    person_id = get_person_id(person)
    since_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')

    if doc_type:
        cursor.execute('''
            SELECT * FROM documents WHERE person_id = ? AND doc_type = ? AND recorded_at >= ?
            ORDER BY recorded_at DESC
        ''', (person_id, doc_type, since_date))
    else:
        cursor.execute('''
            SELECT * FROM documents WHERE person_id = ? AND recorded_at >= ?
            ORDER BY recorded_at DESC
        ''', (person_id, since_date))

    rows = cursor.fetchall()
    conn.close()

    results = []
    for row in rows:
        r = dict(row)
        if r['extracted_data']:
            r['extracted_data'] = json.loads(r['extracted_data'])
        results.append(r)
    return results


def search_records(keyword: str, person: str = None) -> Dict[str, List[Dict]]:
    """키워드로 전체 기록 검색"""
    conn = get_db_connection()
    cursor = conn.cursor()

    person_id = get_person_id(person)
    results = {'measurements': [], 'symptoms': [], 'medications': [], 'documents': []}
    keyword_pattern = f'%{keyword}%'

    # 측정값 검색
    cursor.execute('''
        SELECT * FROM measurements WHERE person_id = ? AND (category LIKE ? OR note LIKE ?)
        ORDER BY measured_at DESC LIMIT 20
    ''', (person_id, keyword_pattern, keyword_pattern))
    for row in cursor.fetchall():
        r = dict(row)
        r['value'] = json.loads(r['value_json'])
        del r['value_json']
        results['measurements'].append(r)

    # 증상 검색
    cursor.execute('''
        SELECT * FROM symptoms WHERE person_id = ? AND (category LIKE ? OR description LIKE ? OR note LIKE ?)
        ORDER BY started_at DESC LIMIT 20
    ''', (person_id, keyword_pattern, keyword_pattern, keyword_pattern))
    results['symptoms'] = [dict(row) for row in cursor.fetchall()]

    # 투약 검색
    cursor.execute('''
        SELECT * FROM medications WHERE person_id = ? AND (name LIKE ? OR reason LIKE ? OR note LIKE ?)
        ORDER BY started_at DESC LIMIT 20
    ''', (person_id, keyword_pattern, keyword_pattern, keyword_pattern))
    results['medications'] = [dict(row) for row in cursor.fetchall()]

    # 문서 검색
    cursor.execute('''
        SELECT * FROM documents WHERE person_id = ? AND (doc_type LIKE ? OR description LIKE ? OR note LIKE ?)
        ORDER BY recorded_at DESC LIMIT 20
    ''', (person_id, keyword_pattern, keyword_pattern, keyword_pattern))
    for row in cursor.fetchall():
        r = dict(row)
        if r['extracted_data']:
            r['extracted_data'] = json.loads(r['extracted_data'])
        results['documents'].append(r)

    conn.close()
    return results


def get_health_summary(days: int = 30, person: str = None) -> Dict[str, Any]:
    """건강 상태 전체 요약"""
    person_name = person or DEFAULT_PERSON

    summary = {
        'person': person_name,
        'period': f'최근 {days}일',
        'generated_at': datetime.now().isoformat(),
        'measurements': {},
        'active_symptoms': [],
        'current_medications': [],
        'recent_documents': []
    }

    # 최근 측정값 요약
    measurements = get_measurements(days=days, person=person)
    for m in measurements:
        cat = m['category']
        if cat not in summary['measurements']:
            summary['measurements'][cat] = {
                'latest': m,
                'count': 1
            }
        else:
            summary['measurements'][cat]['count'] += 1

    # 진행 중인 증상
    symptoms = get_symptoms(days=days, include_ended=False, person=person)
    summary['active_symptoms'] = symptoms

    # 현재 복용 약물
    summary['current_medications'] = get_active_medications(person=person)

    # 최근 검사 문서
    documents = get_documents(days=days, person=person)
    summary['recent_documents'] = documents[:5]  # 최근 5개만

    return summary


def end_symptom(symptom_id: int, ended_at: str = None) -> bool:
    """증상 종료 처리"""
    conn = get_db_connection()
    cursor = conn.cursor()

    if not ended_at:
        ended_at = datetime.now().strftime('%Y-%m-%d')

    cursor.execute('UPDATE symptoms SET ended_at = ?, updated_at = ? WHERE id = ?', (ended_at, _now(), symptom_id))
    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected > 0


def end_medication(medication_id: int = None, name: str = None, ended_at: str = None,
                   person: str = None) -> bool:
    """투약 종료 처리"""
    conn = get_db_connection()
    cursor = conn.cursor()

    if not ended_at:
        ended_at = datetime.now().strftime('%Y-%m-%d')

    if medication_id:
        cursor.execute('''
            UPDATE medications SET ended_at = ?, is_active = 0, updated_at = ? WHERE id = ?
        ''', (ended_at, _now(), medication_id))
    elif name and person:
        person_id = get_person_id(person)
        cursor.execute('''
            UPDATE medications SET ended_at = ?, is_active = 0, updated_at = ?
            WHERE person_id = ? AND name LIKE ? AND is_active = 1
        ''', (ended_at, _now(), person_id, f'%{name}%'))
    elif name:
        cursor.execute('''
            UPDATE medications SET ended_at = ?, is_active = 0, updated_at = ?
            WHERE name LIKE ? AND is_active = 1
        ''', (ended_at, _now(), f'%{name}%'))

    conn.commit()
    affected = cursor.rowcount
    conn.close()
    return affected > 0
