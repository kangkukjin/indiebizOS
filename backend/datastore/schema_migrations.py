"""schema_migrations.py — SQLite 스키마 버전의 단일 레지스트리 (2026-09-02, ② E)

그동안 컬럼 추가는 파일마다 `try: ALTER TABLE … except: pass` 로 흩어져 있었고, 액션명
개편은 `backend/migrate_*.py` 일회성 스크립트를 **사람이** 돌려야 했다. 그 스크립트를
안 돌린 몸(옛 설치본)은 영원히 옛 이름을 안고 산다. 여기서는 `PRAGMA user_version` 으로
DB 마다 적용 위치를 기록하고, 부팅 때 자동으로 따라잡는다.

규약:
- 각 DB 모듈의 `_init_db` 가 CREATE TABLE(=version 0 바닥, 멱등) 뒤에 `apply(conn, "<이름>")` 을 부른다.
- 새 컬럼·데이터 개편은 여기 MIGRATIONS 에 (version, 설명, fn) 으로만 추가한다. fn(conn) 은 멱등해야 한다.
- 한 버전은 한 트랜잭션 — 실패하면 롤백되고 예외가 난다(반쯤 적용된 DB 로 뜨지 않는다).
  예외는 호출한 서브시스템의 초기화 실패로 기록된다(boot_status → /health degraded) — 정직.
- 옛 `migrate_storage_action.py`·`migrate_cctv_action.py` 의 DB 부분은 v1 로 흡수됐다(스크립트 은퇴).
"""
import re
import sqlite3
from typing import Callable, Dict, List, Tuple


class SchemaMigrationError(RuntimeError):
    pass


# ── ibl_usage.db v1: storage/folder/cctv 액션명 통합 (옛 스크립트 2개의 usage_db 부분) ──

_ACTION_RENAMES = [
    # (node, old, new, op) — 긴 이름 먼저(prefix 충돌 방지: folder_annotations → folder_annotate)
    ("self", "storage_summary", "storage", "summary"),
    ("self", "storage_scan", "storage", "scan"),
    ("self", "volumes", "storage", "volumes"),
    ("self", "folder_annotations", "folder_note", "get"),
    ("self", "folder_annotate", "folder_note", "set"),
    ("sense", "cctv_search", "cctv", "search"),
    ("sense", "cctv_nearby", "cctv", "nearby"),
]


def rewrite_retired_action_names(code: str) -> str:
    if not code:
        return code
    for node, old, new, op in _ACTION_RENAMES:
        code = code.replace(f'[{node}:{old}]{{}}', f'[{node}:{new}]{{op: "{op}"}}')
        code = re.sub(r'\[' + node + ':' + old + r'\]\{', f'[{node}:{new}]{{op: "{op}", ', code)
        code = re.sub(r'\[' + node + ':' + old + r'\](?!\{)', f'[{node}:{new}]{{op: "{op}"}}', code)
    return code


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone() is not None


def _ibl_usage_v1(conn: sqlite3.Connection) -> None:
    if not _has_table(conn, "ibl_examples"):
        return
    like = " OR ".join(["ibl_code LIKE ?"] * len(_ACTION_RENAMES))
    params = [f"%{n}:{old}%" for n, old, _, _ in _ACTION_RENAMES]
    rows = conn.execute(f"SELECT id, ibl_code FROM ibl_examples WHERE {like}", params).fetchall()
    for rid, code in rows:
        new = rewrite_retired_action_names(code)
        if new != code:
            conn.execute("UPDATE ibl_examples SET ibl_code=? WHERE id=?", (new, rid))


def _world_pulse_v1(conn: sqlite3.Connection) -> None:
    olds = [old for _, old, _, _ in _ACTION_RENAMES]
    ph = ",".join("?" * len(olds))
    for table in ("action_health", "self_checks"):
        if _has_table(conn, table):
            conn.execute(f"DELETE FROM {table} WHERE action IN ({ph})", olds)


def _ibl_usage_v2(conn: sqlite3.Connection) -> None:
    """이름 붙은 용례의 호출 서명 백필 (2026-09-06).

    서명은 이제 원장 문(add_example)이 실행기의 계약으로 계산해 넣지만, 그 문이 생기기 전에 태어난
    행은 비어 있다. 그 행들이 바로 어긋난 서명을 가르쳤다 — 표시가 `${…}` 정규식이던 시절의 유산이라
    45건 중 10건이 실행 요구와 달랐고, 5건은 표시가 빈 `{}` 라 가르친 대로 부르면 100% 거절됐다.
    해마 DB 는 릴리스에 실려 다른 몸으로 가므로, 사람이 스크립트를 돌리는 대신 여기서 따라잡는다.

    서명을 못 구하는 행(파서 없는 몸·파스 불가)은 NULL 로 둔다 — 표시 쪽이 '미상'으로 말한다.
    멱등: 이미 값이 있는 행은 건드리지 않는다."""
    if not _has_table(conn, "ibl_examples"):
        return
    cols = {r[1] for r in conn.execute("PRAGMA table_info(ibl_examples)").fetchall()}
    if "signature" not in cols:
        conn.execute("ALTER TABLE ibl_examples ADD COLUMN signature TEXT")
    if "alias" not in cols:
        return
    from ibl_signature_slot import signature_of as _signature_of
    rows = conn.execute("SELECT id, ibl_code FROM ibl_examples "
                        "WHERE COALESCE(alias,'') != '' AND signature IS NULL").fetchall()
    for rid, code in rows:
        sig = _signature_of(code)
        if sig is not None:
            conn.execute("UPDATE ibl_examples SET signature=? WHERE id=?", (sig, rid))


MIGRATIONS: Dict[str, List[Tuple[int, str, Callable[[sqlite3.Connection], None]]]] = {
    "ibl_usage": [
        (1, "storage/folder/cctv 액션명 통합 — ibl_examples.ibl_code 치환", _ibl_usage_v1),
        (2, "이름 붙은 용례의 호출 서명 백필 — 표시 서명 = 실행 요구", _ibl_usage_v2),
    ],
    "world_pulse": [
        (1, "storage/folder/cctv 옛 액션명 행 삭제 — action_health/self_checks", _world_pulse_v1),
    ],
    # 나머지 DB 는 version 0 바닥만 (CREATE TABLE IF NOT EXISTS + 모듈 내 idempotent ALTER).
    # 새 개편은 여기에 (version, 설명, fn) 으로 추가한다.
    "conversation": [], "business": [], "multi_chat": [], "guide_usage": [],
    "forage_memory": [], "system_ai_memory": [],
}


def current_version(conn: sqlite3.Connection) -> int:
    return int(conn.execute("PRAGMA user_version").fetchone()[0])


def latest_version(db_name: str) -> int:
    steps = MIGRATIONS.get(db_name) or []
    return max((v for v, _, _ in steps), default=0)


def apply(conn: sqlite3.Connection, db_name: str) -> int:
    """등록된 마이그레이션을 현재 user_version 다음부터 차례로 적용. 반환 = 적용 후 버전.

    한 버전 = 한 트랜잭션. 실패는 롤백 후 SchemaMigrationError(어느 DB 의 몇 번이 왜)."""
    if db_name not in MIGRATIONS:
        raise SchemaMigrationError(f"등록되지 않은 DB 이름: {db_name}")
    cur = current_version(conn)
    for version, desc, fn in sorted(MIGRATIONS[db_name], key=lambda t: t[0]):
        if version <= cur:
            continue
        try:
            conn.execute("BEGIN")
            fn(conn)
            conn.execute(f"PRAGMA user_version={int(version)}")
            conn.commit()
        except Exception as e:
            try:
                conn.rollback()
            except Exception:
                pass
            raise SchemaMigrationError(f"{db_name} v{version} ({desc}) 실패: {e}") from e
        cur = version
    return cur
