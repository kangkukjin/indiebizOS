"""건강 문서의 이미지 참조는 실행 세대가 정리된 뒤에도 유효해야 한다."""
import importlib.util
import json
import shutil
import sys
from pathlib import Path

import pytest


PACKAGE = (Path(__file__).resolve().parents[1] / "data" / "packages" /
           "installed" / "tools" / "health-record")


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize("userdata", [False, True])
def test_generation_document_survives_removal(tmp_path, monkeypatch, userdata):
    live = tmp_path / "live" / "health"
    live.mkdir(parents=True)
    generation = tmp_path / "generation"
    package = generation / "data/packages/installed/tools/health-record"
    package.mkdir(parents=True)
    shutil.copy2(PACKAGE / "health_storage.py", package / "health_storage.py")
    shutil.copy2(PACKAGE / "handler.py", package / "handler.py")
    alias = generation / "data/health"
    alias.symlink_to(live, target_is_directory=True)
    if userdata:
        monkeypatch.setenv("INDIEBIZ_USERDATA", str(generation / "data"))
    else:
        monkeypatch.delenv("INDIEBIZ_USERDATA", raising=False)
    storage = _load(package / "health_storage.py", "test_generation_health_storage")
    monkeypatch.setitem(sys.modules, "health_storage", storage)
    monkeypatch.syspath_prepend(str(package))
    handler = _load(package / "handler.py", "test_generation_health_handler")
    source = tmp_path / "prescription.jpg"
    source.write_bytes(b"prescription image bytes")

    result = json.loads(handler.save_health_info({
        "info_type": "document", "person": "test-person",
        "data": {"category": "prescription", "image_path": str(source)},
    }))
    assert result["success"], result
    with storage.get_db_connection() as conn:
        path = conn.execute("SELECT image_path FROM documents").fetchone()[0]
    assert Path(path).parent == live / "images"
    assert Path(storage.DB_PATH).parent == live

    # 코드·연결만 없애고 영속 파일은 그대로 둔다(세대 정리와 같은 경계).
    alias.unlink()
    shutil.rmtree(generation)
    assert Path(path).read_bytes() == source.read_bytes()


def test_document_storage_canonicalizes_caller_alias(tmp_path, monkeypatch):
    monkeypatch.setenv("INDIEBIZ_USERDATA", str(tmp_path / "userdata"))
    storage = _load(PACKAGE / "health_storage.py", "test_alias_health_storage")
    image = tmp_path / "image.jpg"
    image.write_bytes(b"original")
    alias = tmp_path / "temporary-link.jpg"
    alias.symlink_to(image)
    record_id = storage.save_document("prescription", image_path=str(alias))
    empty_id = storage.save_document("text-only")
    alias.unlink()
    with storage.get_db_connection() as conn:
        row = conn.execute("SELECT image_path FROM documents WHERE id=?", (record_id,)).fetchone()
        empty = conn.execute("SELECT image_path FROM documents WHERE id=?", (empty_id,)).fetchone()
    assert row[0] == str(image)
    assert Path(row[0]).read_bytes() == b"original"
    assert empty[0] is None
