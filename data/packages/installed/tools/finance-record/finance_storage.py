"""재무 기록 저장소 - SQLite 기반 재무 원장 (health-record storage 대칭)

다중 주체(owner) 지원 — 개인/회사 재무를 한 DB에서 주체 축으로 분리.
소비(transactions: 지출·수입 거래)와 소유(holdings: 자산·부채 스냅샷)의 두 축.
"""
import os
import sqlite3
import json
import uuid as _uuid
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

# === 동기화용 식별자 (health-record 선례 — 주체=이름 자연키라 결정적 uuid) ===
_SYNC_NS = _uuid.UUID("6f1b2c3d-0000-4000-8000-000000000002")


def _new_uuid() -> str:
    return str(_uuid.uuid4())


def _owner_uuid(name: str) -> str:
    return str(_uuid.uuid5(_SYNC_NS, f"finance-owner:{name}"))


def _now() -> str:
    return datetime.now().isoformat()


# 데이터 저장 경로 (health-record 선례 — INDIEBIZ_USERDATA 있으면 그 아래)
_PACKAGE_DIR = os.path.dirname(os.path.abspath(__file__))
_DATA_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(_PACKAGE_DIR))))
_USERDATA = (os.environ.get("INDIEBIZ_USERDATA") or "").strip()
DATA_DIR = os.path.join(_USERDATA, 'finance') if _USERDATA else os.path.join(_DATA_DIR, 'finance')
DB_PATH = os.path.join(DATA_DIR, 'finance_records.db')
FILES_DIR = os.path.join(DATA_DIR, 'files')   # ingest 원본(영수증 등) 보존


# 기본 주체 — 소스는 설치 데이터 data/finance/config.json 의 default_owner
# ('명사의 자리': 세계의 명사는 코드가 아니라 데이터에). 없으면 "나".
def _load_default_owner() -> str:
    try:
        with open(os.path.join(DATA_DIR, 'config.json'), encoding='utf-8') as f:
            name = (json.load(f).get('default_owner') or '').strip()
        if name:
            return name
    except (OSError, ValueError):
        pass
    return "나"

DEFAULT_OWNER = _load_default_owner()


def get_db_connection():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(FILES_DIR, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS owners (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            note TEXT,
            uuid TEXT,
            created_at TEXT
        )""")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            tx_type TEXT NOT NULL CHECK(tx_type IN ('expense','income')),
            amount REAL NOT NULL,
            category TEXT,
            counterparty TEXT,
            occurred_at TEXT,
            note TEXT,
            uuid TEXT,
            created_at TEXT,
            updated_at TEXT,
            deleted_at TEXT
        )""")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            owner_id INTEGER NOT NULL,
            kind TEXT NOT NULL CHECK(kind IN ('asset','liability')),
            asset_type TEXT,
            name TEXT NOT NULL,
            value REAL,
            as_of TEXT,
            note TEXT,
            uuid TEXT,
            created_at TEXT,
            updated_at TEXT,
            deleted_at TEXT
        )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_tx_owner_date ON transactions(owner_id, occurred_at)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_hold_owner_name ON holdings(owner_id, name)")
    # ── spend 흡수(2026-08-14 합병): 수거 채널 컬럼 + 중복 방지 + 수거 로그 ──
    cols = [r[1] for r in conn.execute("PRAGMA table_info(transactions)").fetchall()]
    if 'source' not in cols:
        conn.execute("ALTER TABLE transactions ADD COLUMN source TEXT")     # 하나카드/청주페이/수기 등
    if 'ext_id' not in cols:
        conn.execute("ALTER TABLE transactions ADD COLUMN ext_id TEXT")     # 알림 해시(수거 dedup)
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_tx_ext ON transactions(ext_id) WHERE ext_id IS NOT NULL")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sync_log (
            at INTEGER, fetched INTEGER, new INTEGER, skipped INTEGER
        )""")
    # 기본 주체 행 보장
    row = conn.execute("SELECT id FROM owners WHERE name = ?", (DEFAULT_OWNER,)).fetchone()
    if not row:
        conn.execute("INSERT INTO owners (name, note, uuid, created_at) VALUES (?, ?, ?, ?)",
                     (DEFAULT_OWNER, "기본 주체", _owner_uuid(DEFAULT_OWNER), _now()))
    conn.commit()
    return conn


def get_or_create_owner(conn, name: str) -> int:
    row = conn.execute("SELECT id FROM owners WHERE name = ?", (name,)).fetchone()
    if row:
        return row['id']
    cur = conn.execute("INSERT INTO owners (name, uuid, created_at) VALUES (?, ?, ?)",
                       (name, _owner_uuid(name), _now()))
    return cur.lastrowid


def owner_id_of(conn, owner: str = None) -> int:
    if not owner or owner == "나":
        owner = DEFAULT_OWNER
    return get_or_create_owner(conn, owner)


def list_owners() -> List[Dict]:
    with get_db_connection() as conn:
        rows = conn.execute("SELECT name, note FROM owners ORDER BY id").fetchall()
        return [dict(r) for r in rows]


def save_transaction(tx_type: str, amount: float, category: str = None,
                     counterparty: str = None, occurred_at: str = None,
                     note: str = None, owner: str = None) -> int:
    with get_db_connection() as conn:
        oid = owner_id_of(conn, owner)
        cur = conn.execute(
            """INSERT INTO transactions
               (owner_id, tx_type, amount, category, counterparty, occurred_at, note,
                uuid, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (oid, tx_type, amount, category, counterparty,
             occurred_at or datetime.now().strftime('%Y-%m-%d'),
             note, _new_uuid(), _now(), _now()))
        conn.commit()
        return cur.lastrowid


def save_holding(kind: str, name: str, value: float = None, asset_type: str = None,
                 as_of: str = None, note: str = None, owner: str = None) -> int:
    """소유 스냅샷 — 같은 name 을 다시 저장하면 새 시점 평가액(이력이 추이가 된다)."""
    with get_db_connection() as conn:
        oid = owner_id_of(conn, owner)
        cur = conn.execute(
            """INSERT INTO holdings
               (owner_id, kind, asset_type, name, value, as_of, note,
                uuid, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (oid, kind, asset_type, name, value,
             as_of or datetime.now().strftime('%Y-%m-%d'),
             note, _new_uuid(), _now(), _now()))
        conn.commit()
        return cur.lastrowid


def merge_synced_rows(rows: list, owner: str = None) -> list:
    """수거된 결제 알림 행들 → 거래 병합 (ext_id dedup — 여러 번 수거해도 안전).

    approve=지출(+) / cancel=지출(−, 환불 차감) / charge(충전)=이체라 원장 제외.
    파싱 실패(amount 0)도 원문을 note 로 보존해 넣는다(침묵 실패 금지 — 합계 무영향).
    returns 새로 들어간 행 목록."""
    new_rows = []
    with get_db_connection() as conn:
        oid = owner_id_of(conn, owner)
        for r in rows:
            if r.get('type') == 'charge':
                continue
            sign = -1 if r.get('type') == 'cancel' else 1
            note_bits = []
            if r.get('type') == 'cancel':
                note_bits.append('취소·환불')
            if not r.get('parsed'):
                note_bits.append((r.get('body') or r.get('title') or '')[:200])
            occurred = datetime.fromtimestamp((r.get('ts') or 0) / 1000).strftime('%Y-%m-%d') \
                if r.get('ts') else datetime.now().strftime('%Y-%m-%d')
            # OR IGNORE = ext_id 부분 유니크 인덱스 위반 시 조용히 건너뜀
            # (부분 인덱스는 ON CONFLICT(ext_id) 타깃으로 못 잡는다 — 실측)
            cur = conn.execute(
                """INSERT OR IGNORE INTO transactions
                   (owner_id, tx_type, amount, category, counterparty, occurred_at, note,
                    source, ext_id, uuid, created_at, updated_at)
                   VALUES (?, 'expense', ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (oid, sign * (r.get('amount') or 0), r.get('merchant') or None,
                 occurred, ' · '.join(note_bits) or None,
                 r.get('source'), r['ext_id'], _new_uuid(), _now(), _now()))
            if cur.rowcount > 0:
                new_rows.append(r)
        conn.execute("INSERT INTO sync_log (at, fetched, new, skipped) VALUES (?,?,?,?)",
                     (int(datetime.now().timestamp()), len(rows), len(new_rows), 0))
        conn.commit()
    return new_rows


def last_sync_label() -> str:
    with get_db_connection() as conn:
        row = conn.execute("SELECT MAX(at) FROM sync_log").fetchone()
    if not row or not row[0]:
        return "아직 없음"
    return datetime.fromtimestamp(row[0]).strftime('%m/%d %H:%M')


def _owner_clause(conn, owner):
    """owner 지정 시 해당 주체만, 미지정=기본 주체 (건강 person 축과 동일 의미)."""
    return owner_id_of(conn, owner)


def get_transactions(owner: str = None, month: str = None, days: int = None,
                     tx_type: str = None, keyword: str = None, source: str = None,
                     limit: int = 200) -> List[Dict]:
    with get_db_connection() as conn:
        oid = _owner_clause(conn, owner)
        q = "SELECT * FROM transactions WHERE owner_id = ? AND deleted_at IS NULL"
        args: List[Any] = [oid]
        if month:
            q += " AND occurred_at LIKE ?"
            args.append(f"{month}%")
        elif days:
            since = (datetime.now() - timedelta(days=int(days))).strftime('%Y-%m-%d')
            q += " AND occurred_at >= ?"
            args.append(since)
        if tx_type in ('expense', 'income'):
            q += " AND tx_type = ?"
            args.append(tx_type)
        if source:
            q += " AND source = ?"
            args.append(source)
        if keyword:
            q += " AND (category LIKE ? OR counterparty LIKE ? OR note LIKE ?)"
            args += [f"%{keyword}%"] * 3
        q += " ORDER BY occurred_at DESC, id DESC LIMIT ?"
        args.append(int(limit))
        return [dict(r) for r in conn.execute(q, args).fetchall()]


def get_holdings(owner: str = None, kind: str = None, latest_only: bool = True) -> List[Dict]:
    """소유 목록 — latest_only=True 면 이름별 최신 스냅샷만(현재 보유 상태)."""
    with get_db_connection() as conn:
        oid = _owner_clause(conn, owner)
        q = "SELECT * FROM holdings WHERE owner_id = ? AND deleted_at IS NULL"
        args: List[Any] = [oid]
        if kind in ('asset', 'liability'):
            q += " AND kind = ?"
            args.append(kind)
        q += " ORDER BY as_of DESC, id DESC"
        rows = [dict(r) for r in conn.execute(q, args).fetchall()]
    if not latest_only:
        return rows
    seen, latest = set(), []
    for r in rows:  # as_of 내림차순 → 이름별 첫 행=최신
        key = (r['kind'], r['name'])
        if key not in seen:
            seen.add(key)
            latest.append(r)
    return latest


def holding_history(owner: str = None, name: str = None) -> List[Dict]:
    with get_db_connection() as conn:
        oid = _owner_clause(conn, owner)
        rows = conn.execute(
            "SELECT * FROM holdings WHERE owner_id=? AND name=? AND deleted_at IS NULL "
            "ORDER BY as_of ASC, id ASC", (oid, name)).fetchall()
        return [dict(r) for r in rows]


def get_summary(owner: str = None, month: str = None) -> Dict[str, Any]:
    month = month or datetime.now().strftime('%Y-%m')
    txs = get_transactions(owner=owner, month=month, limit=1000)
    expense = sum(t['amount'] for t in txs if t['tx_type'] == 'expense')
    income = sum(t['amount'] for t in txs if t['tx_type'] == 'income')
    by_cat: Dict[str, float] = {}
    by_source: Dict[str, float] = {}
    merchants: Dict[str, Dict] = {}
    for t in txs:
        if t['tx_type'] == 'expense':
            by_cat[t['category'] or '미분류'] = by_cat.get(t['category'] or '미분류', 0) + t['amount']
            if t.get('source'):
                by_source[t['source']] = by_source.get(t['source'], 0) + t['amount']
            if t['amount'] > 0:   # 취소(−)는 상위 가맹점 집계 밖
                key = t.get('counterparty') or t.get('category') or '(미분류)'
                m = merchants.setdefault(key, {'merchant': key, 'count': 0, 'amount': 0})
                m['count'] += 1
                m['amount'] += t['amount']
    top_cats = sorted(by_cat.items(), key=lambda x: -x[1])[:5]
    top_merchants = sorted(merchants.values(), key=lambda x: -x['amount'])[:15]
    holds = get_holdings(owner=owner, latest_only=True)
    asset_total = sum(h['value'] or 0 for h in holds if h['kind'] == 'asset')
    liab_total = sum(h['value'] or 0 for h in holds if h['kind'] == 'liability')
    return {
        'owner': owner or DEFAULT_OWNER, 'month': month,
        'expense': expense, 'income': income, 'net': income - expense,
        'tx_count': len(txs), 'top_categories': top_cats,
        'top_merchants': top_merchants, 'by_source': by_source,
        'holdings': holds, 'asset_total': asset_total,
        'liability_total': liab_total, 'net_worth': asset_total - liab_total,
        'last_sync': last_sync_label(),
    }


def search_records(keyword: str, owner: str = None) -> Dict[str, List[Dict]]:
    with get_db_connection() as conn:
        oid = _owner_clause(conn, owner)
        like = f"%{keyword}%"
        txs = conn.execute(
            "SELECT * FROM transactions WHERE owner_id=? AND deleted_at IS NULL AND "
            "(category LIKE ? OR counterparty LIKE ? OR note LIKE ?) "
            "ORDER BY occurred_at DESC LIMIT 30", (oid, like, like, like)).fetchall()
        holds = conn.execute(
            "SELECT * FROM holdings WHERE owner_id=? AND deleted_at IS NULL AND "
            "(name LIKE ? OR asset_type LIKE ? OR note LIKE ?) "
            "ORDER BY as_of DESC LIMIT 30", (oid, like, like, like)).fetchall()
        return {'transactions': [dict(r) for r in txs], 'holdings': [dict(r) for r in holds]}


def soft_delete_record(record_type: str, record_id: int, owner: str = None) -> bool:
    table = {'transaction': 'transactions', 'holding': 'holdings'}.get(record_type)
    if not table:
        return False
    with get_db_connection() as conn:
        q = f"UPDATE {table} SET deleted_at = ? WHERE id = ? AND deleted_at IS NULL"
        args: List[Any] = [_now(), int(record_id)]
        if owner:
            q += " AND owner_id = ?"
            args.append(owner_id_of(conn, owner))
        cur = conn.execute(q, args)
        conn.commit()
        return cur.rowcount > 0
