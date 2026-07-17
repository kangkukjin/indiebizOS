"""business_sync.py — business.db 폰↔PC 합집합(union) 머지: last-write-wins + tombstone.

설계 결정(사용자 합의):
- **자동응답은 PC 전용**(상시 켜진 단일 응답자). 폰은 읽기/작성만 → 이중 자동응답 없음.
- **메시지/글 내용**은 Nostr 릴레이·Gmail 이 진실원 → 양 기기가 같은 키로 같은 릴레이 구독하면
  공짜로 수렴(머지 대상 아님, messages/channel_settings 제외).
- **DB 머지**는 외부 진실원이 없는 '주소록 메타데이터'만: 이웃·연락처·사업·아이템·문서·지침.

머지 = 레코드별 LWW CRDT (결합·교환법칙 성립 → 어느 쪽서 먼저 sync 해도 결과 동일):
- 식별: 엔티티/자식은 `uuid`, 문서·지침은 `level`(고정 0-4 싱글턴).
- 같은 식별자가 양쪽에 있으면 `updated_at` 늦은 쪽 채택(`deleted=1` tombstone 포함).
- 한쪽에만 있으면 합침(union). 새 uuid 는 그대로 추가.
- 삭제는 행 제거가 아니라 tombstone → 합집합서 부활 방지(순수 union 의 유일한 함정 해소).
- 자식(contacts/business_items)은 `parent_uuid` 로 로컬 부모 정수 id 를 재해소(정수 rowid 는
  기기마다 달라 신뢰 불가). 머지 순서=부모(이웃·사업) 먼저 → 자식.

함정: `updated_at` 비교는 ISO 문자열 사전식. 우리 write-path 는 전부 datetime.isoformat()('...T...')
이라 일관. 단 오래된 contacts 의 backfill 값이 SQLite CURRENT_TIMESTAMP('... ...', 공백) 포맷일 수
있는데, 공백(0x20)<'T'(0x54) 라 '편집된 행(T포맷)이 항상 이김' = 생성후 편집이므로 대개 옳음.
"""

# 엔티티(부모) — uuid 로 식별
ENTITY_TABLES = ["neighbors", "businesses"]
# 자식 — uuid 식별 + parent_uuid 로 로컬 부모 id 재해소. {table: (parent_uuid_field, parent_table, parent_id_col)}
CHILD_TABLES = {
    "contacts": ("neighbor_uuid", "neighbors", "neighbor_id"),
    "business_items": ("business_uuid", "businesses", "business_id"),
}
# level 싱글턴(0-4) — level 로 식별
LEVEL_TABLES = ["business_documents", "work_guidelines"]
# 맥 전용 컬럼(개인 포털 인증) — 폰엔 포털이 없으므로 머지에서 제외한다. 이 컬럼들을
# 덮어쓰면 폰의 이웃 편집(이름·레벨)이 LWW 로 이겼을 때 포털 로그인·열쇠가 NULL 로 지워진다.
PORTAL_LOCAL_COLS = {"portal_login_id", "portal_pw", "portal_key",
                     "portal_revoked", "portal_joined_at", "portal_last_used"}
# 머지/내보내기 순서 (부모 먼저여야 자식 remap 가능)
SYNC_TABLES = ENTITY_TABLES + list(CHILD_TABLES.keys()) + LEVEL_TABLES


def export_business_db(bm) -> dict:
    """동기화 대상 테이블 전체를 dict 로 내보냄 (삭제 tombstone 포함 — 삭제 전파에 필요)."""
    conn = bm._get_connection()
    cur = conn.cursor()
    out = {}
    for t in SYNC_TABLES:
        cur.execute(f"SELECT * FROM {t}")
        rows = [dict(r) for r in cur.fetchall()]
        if t == "neighbors":  # 맥 전용 포털 인증(비밀번호 해시 포함)은 폰으로 내보내지 않는다
            for r in rows:
                for c in PORTAL_LOCAL_COLS:
                    r.pop(c, None)
        out[t] = rows
    conn.close()
    return out


def _ts(d: dict) -> str:
    return (d.get("updated_at") or "") if isinstance(d, dict) else ""


def _table_columns(cur, t) -> list:
    return [r[1] for r in cur.execute(f"PRAGMA table_info({t})").fetchall()]


def _insert_row(cur, t, row: dict, cols: list, parent_id_col, local_parent_id):
    """remote row 를 로컬에 삽입. id(autoincrement)는 제외, 자식 parent_id 는 로컬 id 로 치환."""
    use = [c for c in cols if c != "id"]
    vals = [local_parent_id if c == parent_id_col else row.get(c) for c in use]
    cur.execute(f"INSERT INTO {t} ({','.join(use)}) VALUES ({','.join('?' * len(use))})", vals)


def _update_row(cur, t, key_col, key_val, row: dict, cols: list, parent_id_col, local_parent_id):
    """로컬 행을 remote 값으로 덮어씀(LWW 승자). id 와 식별키는 건드리지 않음.
    맥 전용 포털 인증 컬럼은 제외 — 폰 편집이 이겨도 로컬 포털 로그인을 보존한다."""
    setc = [c for c in cols if c not in ("id", key_col) and c not in PORTAL_LOCAL_COLS]
    sets = ",".join(f"{c}=?" for c in setc)
    vals = [local_parent_id if c == parent_id_col else row.get(c) for c in setc]
    vals.append(key_val)
    cur.execute(f"UPDATE {t} SET {sets} WHERE {key_col}=?", vals)


def merge_business_db(bm, remote: dict) -> dict:
    """remote(다른 기기의 export_business_db 결과)를 로컬 business.db 에 합집합 머지.

    반환: {table: {added, updated, skipped}} 통계.
    멱등·교환법칙: 같은 remote 를 두 번 머지해도, A↔B 순서를 바꿔도 동일 결과(LWW).
    """
    conn = bm._get_connection()
    cur = conn.cursor()
    stats = {}

    # 1) 엔티티 + 자식 (uuid 식별)
    for t in ENTITY_TABLES + list(CHILD_TABLES.keys()):
        cols = _table_columns(cur, t)
        parent_field, parent_table, parent_id_col = CHILD_TABLES.get(t, (None, None, None))
        st = {"added": 0, "updated": 0, "skipped": 0}
        for r in remote.get(t, []):
            ruuid = r.get("uuid")
            if not ruuid:
                st["skipped"] += 1
                continue
            # 자식: 로컬 부모 id 재해소 (부모 uuid → 로컬 정수 id)
            local_parent_id = None
            if parent_field:
                puuid = r.get(parent_field)
                if puuid:
                    pr = cur.execute(f"SELECT id FROM {parent_table} WHERE uuid = ?", (puuid,)).fetchone()
                    local_parent_id = pr[0] if pr else None
                if local_parent_id is None:
                    st["skipped"] += 1  # 부모가 로컬에 없음 → 이 머지에선 보류
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

    # 2) level 싱글턴 (level 식별, parent 없음)
    for t in LEVEL_TABLES:
        cols = _table_columns(cur, t)
        st = {"added": 0, "updated": 0, "skipped": 0}
        for r in remote.get(t, []):
            lvl = r.get("level")
            if lvl is None:
                st["skipped"] += 1
                continue
            local = cur.execute(f"SELECT * FROM {t} WHERE level = ?", (lvl,)).fetchone()
            if local is None:
                _insert_row(cur, t, r, cols, None, None)
                st["added"] += 1
            elif _ts(r) > _ts(dict(local)):
                _update_row(cur, t, "level", lvl, r, cols, None, None)
                st["updated"] += 1
            else:
                st["skipped"] += 1
        stats[t] = st

    conn.commit()
    conn.close()
    return stats
