"""store_waste_audit 관문 — 빈 vec0 청크·미회수 프리페이지를 실제로 잡는가.

★붉은 적 없는 관문은 관문이 아니다: 2026-09-07 수리 직후 감사가 초록이라
  "잡는다"를 초록으로 확인할 수 없다. 그래서 잔재의 **디스크 모양**을 픽스처로
  세워 붉게 만든다 (vec0 그림자 테이블은 평범한 테이블이라 손으로 세울 수 있다).
"""
import sqlite3

import boot_paths  # noqa: F401
import store_waste_audit as SW


def _make_vec_db(path, chunks, live_per_chunk, chunk_size=1024, dim=768):
    """vec0 그림자 테이블의 디스크 모양을 그대로 세운다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(str(path))
    c.execute("CREATE TABLE t_chunks(chunk_id INTEGER PRIMARY KEY, size INTEGER NOT NULL, "
              "validity BLOB NOT NULL, rowids BLOB NOT NULL)")
    c.execute("CREATE TABLE t_vector_chunks00(rowid PRIMARY KEY, vectors BLOB NOT NULL)")
    blob = b"\0" * (chunk_size * dim * 4)
    for i in range(chunks):
        n = live_per_chunk[i]
        bits = (1 << n) - 1
        validity = bits.to_bytes(chunk_size // 8, "little")
        c.execute("INSERT INTO t_chunks VALUES (?,?,?,?)", (i + 1, chunk_size, validity, b""))
        c.execute("INSERT INTO t_vector_chunks00 VALUES (?,?)", (i + 1, blob))
    c.commit()
    c.close()


def _scan(tmp_path, monkeypatch):
    monkeypatch.setattr(SW, "_ROOT", tmp_path)
    (tmp_path / "data").mkdir(exist_ok=True)
    return SW.measure()


def test_빈_청크_잔재를_깃발한다(tmp_path, monkeypatch):
    # 청크 3개인데 살아있는 벡터는 첫 청크에 10개뿐 = 점유 0.3%
    _make_vec_db(tmp_path / "data" / "leaky.db", 3, [10, 0, 0])
    r = _scan(tmp_path, monkeypatch)
    kinds = [f["kind"] for f in r["flags"]]
    assert "vec_chunk_residue" in kinds, f"잔재를 못 잡았다: {r}"
    f = [f for f in r["flags"] if f["kind"] == "vec_chunk_residue"][0]
    assert f["chunks"] == 3 and f["live"] == 10
    assert f["reclaim_mb"] > 8, f"회수량 추정이 이상하다: {f}"


def test_청크_1개는_구조적_최소라_깃발_아니다(tmp_path, monkeypatch):
    # 벡터 1개여도 청크는 통째로 잡힌다 — 재구성해도 안 줄어드니 부채가 아니다.
    _make_vec_db(tmp_path / "data" / "tiny.db", 1, [1])
    r = _scan(tmp_path, monkeypatch)
    assert not r["flags"], f"구조적 최소치를 깃발했다: {r['flags']}"
    assert len(r["structural"]) == 1


def test_꽉_찬_청크는_깃발_아니다(tmp_path, monkeypatch):
    _make_vec_db(tmp_path / "data" / "full.db", 2, [1024, 900])
    r = _scan(tmp_path, monkeypatch)
    assert not r["flags"], f"정상 점유를 깃발했다: {r['flags']}"


def test_미회수_프리페이지를_깃발한다(tmp_path, monkeypatch):
    p = tmp_path / "data" / "free.db"
    p.parent.mkdir(exist_ok=True)
    c = sqlite3.connect(str(p))
    c.execute("CREATE TABLE t(id INTEGER PRIMARY KEY, b BLOB)")
    c.executemany("INSERT INTO t(b) VALUES (?)", [(b"\0" * 100_000,) for _ in range(400)])
    c.commit()
    c.execute("DELETE FROM t")          # VACUUM 없이 삭제 = 프리페이지로 남는다
    c.commit()
    c.close()
    r = _scan(tmp_path, monkeypatch)
    assert any(f["kind"] == "freelist" for f in r["flags"]), f"프리페이지를 못 잡았다: {r}"


def test_백업_폴더는_감사하지_않는다(tmp_path, monkeypatch):
    d = tmp_path / "data" / "_backups"
    d.mkdir(parents=True)
    _make_vec_db(d / "old.db", 3, [10, 0, 0])
    r = _scan(tmp_path, monkeypatch)
    assert not r["flags"], f"백업을 감사했다: {r['flags']}"


def test_열_수_없는_파일은_깨끗함이_아니라_미검사다(tmp_path, monkeypatch):
    p = tmp_path / "data" / "broken.db"
    p.parent.mkdir(exist_ok=True)
    p.write_bytes(b"this is not a sqlite file" * 100)
    r = _scan(tmp_path, monkeypatch)
    assert r["unchecked"], "손상 파일을 조용히 통과시켰다"


if __name__ == "__main__":
    import sys

    import pytest
    sys.exit(pytest.main([__file__, "-v"]))
