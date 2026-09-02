r"""스키마 버전 레지스트리 — 옛 몸이 부팅만으로 따라잡는다 (2026-09-02, ② E)

    T1. version 0 DB 에 옛 액션명 행 → apply 후 치환·user_version=1
    T2. 재적용은 멱등(다시 apply 해도 변화 0, 버전 그대로)
    T3. 실패하는 마이그레이션은 롤백되고 예외 — user_version 은 오르지 않는다
    T4. world_pulse v1 은 옛 액션명 행만 지운다(다른 행 보존), 테이블이 없으면 조용히 통과
    T5. 등록되지 않은 DB 이름은 예외(오타를 '적용할 것 없음'으로 눙치지 않는다)

실행: python3 -m pytest backend/test_schema_migrations.py
"""
import sqlite3
import sys

import pytest

sys.path.insert(0, __file__.rsplit('/', 1)[0])
import boot_paths  # noqa: F401

import schema_migrations as sm


def _usage_db():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE ibl_examples (id INTEGER PRIMARY KEY, intent TEXT, ibl_code TEXT)")
    conn.executemany("INSERT INTO ibl_examples (intent, ibl_code) VALUES (?, ?)", [
        ("a", '[self:storage_scan]{path: "/x"}'),
        ("b", "[sense:cctv_nearby]"),
        ("c", '[self:folder_annotations]{}'),
        ("d", '[self:storage]{op: "scan"}'),      # 이미 새 이름
    ])
    conn.commit()
    return conn


def test_t1_rewrites_and_stamps_version():
    conn = _usage_db()
    assert sm.current_version(conn) == 0
    assert sm.apply(conn, "ibl_usage") == 1
    codes = [r[0] for r in conn.execute("SELECT ibl_code FROM ibl_examples ORDER BY id")]
    assert codes == ['[self:storage]{op: "scan", path: "/x"}', '[sense:cctv]{op: "nearby"}',
                     '[self:folder_note]{op: "get"}', '[self:storage]{op: "scan"}']
    assert sm.current_version(conn) == 1


def test_t2_reapply_is_idempotent():
    conn = _usage_db()
    sm.apply(conn, "ibl_usage")
    before = list(conn.execute("SELECT ibl_code FROM ibl_examples ORDER BY id"))
    assert sm.apply(conn, "ibl_usage") == 1
    assert list(conn.execute("SELECT ibl_code FROM ibl_examples ORDER BY id")) == before


def test_t3_failed_step_rolls_back_and_raises(monkeypatch):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE t (v INTEGER)")
    conn.commit()

    def bad(c):
        c.execute("INSERT INTO t VALUES (1)")
        raise RuntimeError("boom")

    monkeypatch.setitem(sm.MIGRATIONS, "_probe", [(1, "터짐", bad)])
    with pytest.raises(sm.SchemaMigrationError) as ei:
        sm.apply(conn, "_probe")
    assert "_probe v1" in str(ei.value) and "boom" in str(ei.value)
    assert sm.current_version(conn) == 0
    assert conn.execute("SELECT count(*) FROM t").fetchone()[0] == 0   # 롤백됨


def test_t4_world_pulse_deletes_only_retired_rows():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE action_health (action TEXT, ok INTEGER)")
    conn.executemany("INSERT INTO action_health VALUES (?, 1)", [("cctv_search",), ("storage",), ("volumes",)])
    conn.commit()
    sm.apply(conn, "world_pulse")
    assert [r[0] for r in conn.execute("SELECT action FROM action_health")] == ["storage"]
    empty = sqlite3.connect(":memory:")
    assert sm.apply(empty, "world_pulse") == 1     # 테이블 없음 = 통과


def test_t5_unknown_db_name_raises():
    with pytest.raises(sm.SchemaMigrationError):
        sm.apply(sqlite3.connect(":memory:"), "nope")


if __name__ == "__main__":
    # 직접 실행도 pytest 로 위임 — 두 번째 러너는 드리프트한다(test_single_runner R2)
    import pytest as _pytest
    sys.exit(_pytest.main([__file__]))
