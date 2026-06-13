"""health_sync.py — health_records.db 폰↔PC 합집합(union) 머지: LWW + tombstone + 이미지 전송.

backend/business_sync.py 의 동형 미러(주소록 대신 의료기록). 차이점:
- `bm` 객체 대신 DB 경로를 직접 해소(get_base_path()/data/health/health_records.db) — 맥·폰 공통.
- **documents 이미지 파일까지 동기화**: export 가 각 문서 이미지를 base64 로 동봉, merge 가 로컬
  IMAGES_DIR 에 기록(없을 때만) + image_path 를 로컬 경로로 재작성(절대경로는 기기마다 달라 basename
  으로 번역). 이미지 내용은 불변이라 존재 체크만으로 충분.

머지 = 레코드별 LWW CRDT(결합·교환·멱등):
- 식별: persons=결정적 uuid(이름 자연키 → 양 기기 수렴), 자식4=무작위 uuid + person_uuid(부모 재해소).
- 같은 uuid 양쪽 → updated_at 늦은 쪽 채택(deleted=1 tombstone 포함). 한쪽만 → union.
- 자식은 person_uuid 로 로컬 persons.id 재해소(정수 rowid 는 기기마다 다름). 머지 순서=persons 먼저.
- 삭제=tombstone(현재 하드삭제 경로 없음 — 전향적). storage.py 마이그레이션이 컬럼·backfill 보장.
"""
import os
import sqlite3
import base64

from runtime_utils import get_base_path

# persons=부모(uuid 식별). 자식4=uuid 식별 + person_uuid 로 로컬 부모 id 재해소.
ENTITY_TABLES = ["persons"]
CHILD_TABLES = {
    "measurements": ("person_uuid", "persons", "person_id"),
    "symptoms": ("person_uuid", "persons", "person_id"),
    "medications": ("person_uuid", "persons", "person_id"),
    "documents": ("person_uuid", "persons", "person_id"),
}
SYNC_TABLES = ENTITY_TABLES + list(CHILD_TABLES.keys())  # persons 먼저(자식 remap 가능)
_MAX_IMG = 8 * 1024 * 1024  # 개별 이미지 8MB 상한(초과=메타만 동기화, 경고)


def _db_path() -> str:
    return os.path.join(str(get_base_path()), "data", "health", "health_records.db")


def _images_dir() -> str:
    return os.path.join(str(get_base_path()), "data", "health", "images")


def _ensure_db():
    """health-record 패키지 storage 의 get_db_connection 을 1회 호출해 DB 생성·스키마·마이그레이션
    보장(맥·폰 공통). sync 가 self:health 보다 먼저 돌아도 테이블이 있게. 스키마 정의 DRY(미복제)."""
    try:
        import importlib.util
        sp = os.path.join(str(get_base_path()), "data", "packages", "installed",
                          "tools", "health-record", "storage.py")
        spec = importlib.util.spec_from_file_location("_health_storage", sp)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.get_db_connection().close()
    except Exception:
        pass  # 패키지 미가용(이론상) — _conn 의 OperationalError 가드가 graceful 처리


def _conn():
    c = sqlite3.connect(_db_path())
    c.row_factory = sqlite3.Row
    return c


def export_health_db() -> dict:
    """동기화 대상 5테이블 + documents 이미지(base64, basename 키)를 dict 로 내보냄(tombstone 포함)."""
    _ensure_db()
    conn = _conn()
    cur = conn.cursor()
    out = {}
    for t in SYNC_TABLES:
        try:
            cur.execute(f"SELECT * FROM {t}")
            out[t] = [dict(r) for r in cur.fetchall()]
        except sqlite3.OperationalError:
            out[t] = []
    conn.close()

    # 이미지 동봉: documents.image_path 파일을 basename 키로 base64 (로컬 IMAGES_DIR 에서 해소)
    images, warnings = {}, []
    idir = _images_dir()
    for r in out.get("documents", []):
        p = r.get("image_path")
        if not p:
            continue
        bn = os.path.basename(p)
        if bn in images:
            continue
        local = p if (os.path.isabs(p) and os.path.exists(p)) else os.path.join(idir, bn)
        try:
            if os.path.exists(local):
                sz = os.path.getsize(local)
                if sz > _MAX_IMG:
                    warnings.append(f"{bn}: {sz}B 상한 초과 — 메타만 동기화")
                    continue
                with open(local, "rb") as f:
                    images[bn] = base64.b64encode(f.read()).decode("ascii")
        except Exception as e:
            warnings.append(f"{bn}: {e.__class__.__name__}")
    out["images"] = images
    if warnings:
        out["image_warnings"] = warnings
    return out


def _ts(d: dict) -> str:
    return (d.get("updated_at") or "") if isinstance(d, dict) else ""


def _table_columns(cur, t) -> list:
    return [r[1] for r in cur.execute(f"PRAGMA table_info({t})").fetchall()]


def _insert_row(cur, t, row: dict, cols: list, parent_id_col, local_parent_id):
    use = [c for c in cols if c != "id"]
    vals = [local_parent_id if c == parent_id_col else row.get(c) for c in use]
    cur.execute(f"INSERT INTO {t} ({','.join(use)}) VALUES ({','.join('?' * len(use))})", vals)


def _update_row(cur, t, key_col, key_val, row: dict, cols: list, parent_id_col, local_parent_id):
    setc = [c for c in cols if c not in ("id", key_col)]
    sets = ",".join(f"{c}=?" for c in setc)
    vals = [local_parent_id if c == parent_id_col else row.get(c) for c in setc]
    vals.append(key_val)
    cur.execute(f"UPDATE {t} SET {sets} WHERE {key_col}=?", vals)


def _write_images(remote: dict) -> int:
    """remote 이미지(base64)를 로컬 IMAGES_DIR 에 기록(없을 때만 — 내용 불변). 반환: 기록 수."""
    imgs = remote.get("images") or {}
    if not imgs:
        return 0
    d = _images_dir()
    os.makedirs(d, exist_ok=True)
    n = 0
    for bn, b64 in imgs.items():
        path = os.path.join(d, os.path.basename(bn))
        if os.path.exists(path):
            continue
        try:
            with open(path, "wb") as f:
                f.write(base64.b64decode(b64))
            n += 1
        except Exception:
            pass
    return n


def merge_health_db(remote: dict) -> dict:
    """remote(다른 기기의 export_health_db 결과)를 로컬 health_records.db 에 합집합 머지.
    멱등·교환법칙: 같은 remote 재머지·A↔B 순서 무관 동일(LWW). 반환: {table:{added,updated,skipped}}."""
    _ensure_db()
    # 0) 이미지 먼저 기록(문서 행이 가리킬 파일 확보)
    img_written = _write_images(remote)
    local_images = _images_dir()

    conn = _conn()
    cur = conn.cursor()
    stats = {}
    for t in SYNC_TABLES:
        cols = _table_columns(cur, t)
        parent_field, parent_table, parent_id_col = CHILD_TABLES.get(t, (None, None, None))
        st = {"added": 0, "updated": 0, "skipped": 0}
        for r in remote.get(t, []):
            ruuid = r.get("uuid")
            if not ruuid:
                st["skipped"] += 1
                continue
            r = dict(r)
            # documents: image_path 를 로컬 IMAGES_DIR 기준으로 번역(기기마다 절대경로 다름)
            if t == "documents" and r.get("image_path"):
                r["image_path"] = os.path.join(local_images, os.path.basename(r["image_path"]))
            # 자식: 부모 uuid → 로컬 정수 id 재해소
            local_parent_id = None
            if parent_field:
                puuid = r.get(parent_field)
                if puuid:
                    pr = cur.execute(f"SELECT id FROM {parent_table} WHERE uuid = ?", (puuid,)).fetchone()
                    local_parent_id = pr[0] if pr else None
                if local_parent_id is None:
                    st["skipped"] += 1  # 부모가 로컬에 없음 → 이 머지선 보류
                    continue
            local = cur.execute(f"SELECT * FROM {t} WHERE uuid = ?", (ruuid,)).fetchone()
            if local is None:
                _insert_row(cur, t, r, cols, parent_id_col, local_parent_id)
                st["added"] += 1
            elif _ts(r) > _ts(dict(local)):
                _update_row(cur, t, "uuid", ruuid, r, cols, parent_id_col, local_parent_id)
                st["updated"] += 1
            else:
                st["skipped"] += 1
        stats[t] = st

    conn.commit()
    conn.close()
    stats["__images_written__"] = img_written
    return stats
