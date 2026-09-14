"""졸업 ZIP의 실제 저장·회상 호환성. 경로는 전부 pytest 임시 폴더."""
import importlib.util
import json
import sqlite3
import zipfile
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("member_import", Path(__file__).parents[1] / "scripts/import_member_archive.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def archive(path, extra=None):
    tables = {"conversations": [{"id": "t", "user": "PRIVATE-A 취향은 보리차", "assistant": "기억했습니다"}],
              "memories": [{"id": "m", "content": "PRIVATE-A 취향은 보리차"}],
              "episodes": [{"id": "t", "data": "{}"}], "forage": [], "hippocampus_examples": [],
              "sentences": [{"id": "f", "code": '[self:read]{path:"a.txt"}'}],
              "scripts": [{"id": "hello", "path": "programs/0/main.py", "interpreter": "python3",
                           "resources": ["programs/0/data.txt"], "dependencies": ["example-package==1.0"]}]}
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("manifest.json", json.dumps({"format": "indiebiz-member", "version": 1, "tables": tables}))
        z.writestr("programs/0/main.py", "raise RuntimeError('MUST NEVER EXECUTE DURING IMPORT')")
        z.writestr("programs/0/data.txt", "resource")
        if extra:
            z.writestr(extra, "escape")


def test_graduation_is_portable_and_idempotent(tmp_path, monkeypatch):
    z = tmp_path / "member.zip"
    archive(z)
    base = tmp_path / "independent"
    out = module.import_archive(z, base)
    assert out["success"] and out["memories"] == 1
    assert module.import_archive(z, base)["already_imported"]
    with sqlite3.connect(base / "data/system_ai_memory.db") as db:
        assert db.execute("SELECT count(*) FROM conversations").fetchone()[0] == 2
    # 소유주 시스템의 정본 심층 기억 읽기로 이식된 표식을 찾는다.
    import memory_db
    rows = memory_db._search_like(str(base / "data/system_ai_state/memory_system_ai.db"), "보리차")
    assert "PRIVATE-A" in str(rows)
    assert (Path(out["path"]) / "programs/0/data.txt").read_text() == "resource"
    assert "dependencies" in (base / "data/scripts/registry.yaml").read_text()
    assert not list(tmp_path.rglob("*MUST NEVER*"))


@pytest.mark.parametrize("bad", ["../outside.txt", "/outside.txt", "programs/../../outside.txt", "programs\\outside"])
def test_graduation_rejects_path_escape(tmp_path, bad):
    z = tmp_path / "member.zip"
    archive(z, bad)
    with pytest.raises(ValueError):
        module.import_archive(z, tmp_path / "independent")


def test_worker_preserves_member_turn(tmp_path):
    import principal as p
    import member_runtime as mr
    import thread_context as tc
    import threading
    from concurrent.futures import ThreadPoolExecutor
    old = tc.snapshot()
    with p.narrow(p.member("A", 4, "devA")), mr.turn_scope(tmp_path, "devA", "t", threading.Event(), {}):
        snap = tc.snapshot()
        def work():
            try:
                tc.restore(snap)
                assert p.current().key() == "member:A"
                assert mr.current()["device_id"] == "devA"
                from common.spill import spill_dir
                assert Path(spill_dir()).is_relative_to(tmp_path)
            finally:
                tc.restore(old)
        with ThreadPoolExecutor() as pool:
            pool.submit(work).result()


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
