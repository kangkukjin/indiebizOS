"""finance_ledger_sync.py — finance_records.db 폰↔PC 합집합(union) 머지: LWW + tombstone.

health_sync.py 의 동형 미러(의료기록 대신 재무 원장). 두 몸이 각자 원장을 갖게 된
뒤(2026-09-05 폰이 자기 포획소를 직접 수거) 갈라지는 것을 막는 짝이다.

★모듈 이름이 finance_sync 가 아닌 이유: 그 이름은 재무 패키지의 결제 알림 수거기가
이미 쓰고 있고 backend 모듈 이름은 평면(sys.modules 공유)이라 충돌한다.

차이점(health 대비):
- 이미지 없음 — 재무 원장은 텍스트뿐(영수증 원본은 data/finance/files, 동기화 밖).
- 자식 행에 부모 uuid 컬럼이 없다(owner_id 정수뿐) → **export 가 owner_uuid 를 파생**해
  동봉하고 merge 가 그것으로 로컬 owner_id 를 재해소한 뒤 버린다(스키마 변경 0).
- owners 는 updated_at 이 없어 created_at 이 LWW 시각 노릇을 한다(주체는 사실상 불변).

머지 = 레코드별 LWW CRDT(결합·교환·멱등):
- 식별: uuid. 같은 uuid 양쪽 → 시각 늦은 쪽 채택(deleted_at tombstone 포함). 한쪽만 → union.
- 자식(transactions·holdings)은 owner_uuid 로 로컬 owners.id 재해소(정수 rowid 는 기기마다 다름).
- ext_id 유니크 인덱스: 같은 결제가 두 몸에서 수거돼도 ext_id 가 같아(앱|제목|본문) 한 행으로 만난다.
"""
import os
import sqlite3

from runtime_utils import get_base_path

ENTITY_TABLES = ["owners"]
# 자식표 → (export 가 파생해 실어 보내는 부모 uuid 필드, 부모표, 로컬 부모 id 컬럼)
CHILD_TABLES = {
    "transactions": ("owner_uuid", "owners", "owner_id"),
    "holdings": ("owner_uuid", "owners", "owner_id"),
}
SYNC_TABLES = ENTITY_TABLES + list(CHILD_TABLES.keys())  # owners 먼저(자식 remap 가능)


def _finance_dir() -> str:
    """재무 데이터 디렉토리. INDIEBIZ_USERDATA 가 있으면 userdata/finance(폰=영속),
    없으면 data/finance(맥 기본). 패키지 finance_storage 의 DATA_DIR 와 같은 로직 —
    반드시 같은 경로를 가리켜야 sync 가 옳은 DB 를 읽는다."""
    ud = (os.environ.get("INDIEBIZ_USERDATA") or "").strip()
    return os.path.join(ud, "finance") if ud else os.path.join(str(get_base_path()), "data", "finance")


def _db_path() -> str:
    return os.path.join(_finance_dir(), "finance_records.db")


def _ensure_db():
    """finance-record 패키지 storage 를 1회 호출해 DB·스키마·마이그레이션 보장(맥·폰 공통).
    sync 가 self:finance 보다 먼저 돌아도 표가 있게 — 스키마 정의는 복제하지 않는다."""
    try:
        import importlib.util
        sp = os.path.join(str(get_base_path()), "data", "packages", "installed",
                          "tools", "finance-record", "finance_storage.py")
        spec = importlib.util.spec_from_file_location("_finance_storage", sp)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.get_db_connection().close()
    except Exception:
        pass  # 패키지 미가용(이론상) — _conn 의 OperationalError 가드가 graceful 처리


def _conn():
    c = sqlite3.connect(_db_path(), timeout=10)
    c.row_factory = sqlite3.Row
    return c


def _ts(d: dict) -> str:
    """LWW 시각 — updated_at 우선, 없으면 created_at(owners 는 updated_at 컬럼이 없다)."""
    if not isinstance(d, dict):
        return ""
    return (d.get("updated_at") or d.get("created_at") or "")


def _table_columns(cur, t) -> list:
    return [r[1] for r in cur.execute(f"PRAGMA table_info({t})").fetchall()]


def export_finance_db() -> dict:
    """동기화 대상 3표를 dict 로 내보냄(tombstone 포함). 자식 행엔 owner_uuid 를 파생해 동봉."""
    _ensure_db()
    conn = _conn()
    cur = conn.cursor()
    out = {}
    owner_uuid_by_id = {}
    try:
        for r in cur.execute("SELECT id, uuid FROM owners").fetchall():
            owner_uuid_by_id[r["id"]] = r["uuid"]
    except sqlite3.OperationalError:
        pass
    for t in SYNC_TABLES:
        try:
            cur.execute(f"SELECT * FROM {t}")
            rows = [dict(r) for r in cur.fetchall()]
        except sqlite3.OperationalError:
            rows = []
        if t in CHILD_TABLES:
            for r in rows:
                r["owner_uuid"] = owner_uuid_by_id.get(r.get("owner_id"))
        out[t] = rows
    conn.close()
    return out


def _insert_row(cur, t, row: dict, cols: list, parent_id_col, local_parent_id):
    use = [c for c in cols if c != "id"]
    vals = [local_parent_id if c == parent_id_col else row.get(c) for c in use]
    cur.execute(f"INSERT OR IGNORE INTO {t} ({','.join(use)}) VALUES ({','.join('?' * len(use))})", vals)
    return cur.rowcount > 0  # ext_id 유니크 충돌 = 이미 있는 결제(양쪽에서 수거됨)


def _update_row(cur, t, key_col, key_val, row: dict, cols: list, parent_id_col, local_parent_id):
    setc = [c for c in cols if c not in ("id", key_col)]
    sets = ",".join(f"{c}=?" for c in setc)
    vals = [local_parent_id if c == parent_id_col else row.get(c) for c in setc]
    vals.append(key_val)
    cur.execute(f"UPDATE {t} SET {sets} WHERE {key_col}=?", vals)


def merge_finance_db(remote: dict) -> dict:
    """remote(다른 기기의 export_finance_db 결과)를 로컬 finance_records.db 에 합집합 머지.
    멱등·교환법칙: 같은 remote 재머지·A↔B 순서 무관 동일(LWW).
    반환: {table:{added,updated,skipped,collided}}. collided = ext_id 가 이미 있어 접힌 행."""
    _ensure_db()
    conn = _conn()
    cur = conn.cursor()
    stats = {}
    for t in SYNC_TABLES:
        cols = _table_columns(cur, t)
        parent_field, parent_table, parent_id_col = CHILD_TABLES.get(t, (None, None, None))
        st = {"added": 0, "updated": 0, "skipped": 0, "collided": 0}
        for r in remote.get(t, []) or []:
            ruuid = (r or {}).get("uuid")
            if not ruuid:
                st["skipped"] += 1
                continue
            r = dict(r)
            local_parent_id = None
            if parent_field:
                puuid = r.pop(parent_field, None)  # 스키마에 없는 파생 필드 — 재해소 후 버린다
                if puuid:
                    pr = cur.execute(f"SELECT id FROM {parent_table} WHERE uuid = ?",
                                     (puuid,)).fetchone()
                    local_parent_id = pr[0] if pr else None
                if local_parent_id is None:
                    st["skipped"] += 1  # 주체가 로컬에 없음 → 이 머지선 보류
                    continue
            local = cur.execute(f"SELECT * FROM {t} WHERE uuid = ?", (ruuid,)).fetchone()
            if local is None:
                if _insert_row(cur, t, r, cols, parent_id_col, local_parent_id):
                    st["added"] += 1
                else:
                    st["collided"] += 1  # 같은 결제를 두 몸이 각자 수거 — ext_id 가 접었다
            elif _ts(r) > _ts(dict(local)):
                _update_row(cur, t, "uuid", ruuid, r, cols, parent_id_col, local_parent_id)
                st["updated"] += 1
            else:
                st["skipped"] += 1
        stats[t] = st

    conn.commit()
    conn.close()
    return stats
