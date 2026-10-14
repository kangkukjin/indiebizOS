"""Warehouse snapshot provenance survives empty, failed and partial polling."""
import boot_paths  # noqa: F401
import sqlite3

import pytest

import warehouse_feed as wf
import warehouse_ops as wo
from ibl_v2_adapters import decode_envelope
from ibl_v2_ir import Fault

URL = "https://warehouse.example"
ADAPTER = {"protocol": "legacy-envelope", "value_path": ""}


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(wf, "DB_PATH", tmp_path / "warehouse.db")
    monkeypatch.setattr(wf, "_seed_scores_from_favorites", lambda: None)
    monkeypatch.setattr(wf, "_reconcile_identity", lambda *args: None)
    return tmp_path


def fetched(monkeypatch, files=(), **metadata):
    monkeypatch.setattr(wf, "_fetch_with_auth", lambda *args: ({"files": list(files), **metadata}, "native"))


def browse(path=""):
    return wo.warehouse_op({"op": "browse", "url": URL, "path": path})


def test_unpolled_and_confirmed_empty_are_distinct(store, monkeypatch):
    unknown = browse()
    assert unknown["files"] == [] and unknown["source"]["state"] == "unpolled"
    with pytest.raises(Fault) as error:
        decode_envelope(unknown, ADAPTER)
    assert error.value.code == "PARTIAL_SOURCE"
    assert error.value.partial["source"]["state"] == "unpolled"
    fetched(monkeypatch)
    result = wo.warehouse_op({"op": "poll", "url": URL})
    assert result["success"] and result["source_complete"]
    empty = browse()
    assert empty["files"] == [] and empty["source_complete"]
    assert empty["source"]["state"] == "ready"
    assert empty["source"]["last_success"] == empty["source"]["last_poll"]
    decode_envelope(empty, ADAPTER)


def test_failed_poll_is_failure_and_old_files_remain_partial(store, monkeypatch):
    fetched(monkeypatch, [{"name": "folder/event.json", "mtime": "2026-10-15", "bytes": 12}])
    wf.poll_warehouse(URL)
    before = browse("folder")

    def unavailable(*args):
        raise RuntimeError("503 unavailable")

    monkeypatch.setattr(wf, "_fetch_with_auth", unavailable)
    failed = wo.warehouse_op({"op": "poll", "url": URL})
    assert failed["success"] is False and "503" in failed["error"]
    with pytest.raises(Fault) as error:
        decode_envelope(failed, ADAPTER)
    assert error.value.code == "TOOL"
    stale = browse("folder")
    assert stale["files"] == before["files"]
    assert stale["source"]["last_success"] == before["source"]["last_success"]
    assert stale["source"]["state"] == "stale" and not stale["source_complete"]
    with pytest.raises(Fault) as error:
        decode_envelope(stale, ADAPTER)
    assert error.value.code == "PARTIAL_SOURCE"
    assert error.value.partial["files"][0]["path"] == "folder/event.json"


def test_first_poll_failure_does_not_look_like_empty_success(store, monkeypatch):
    def unavailable(*args):
        raise RuntimeError("503 unavailable")
    monkeypatch.setattr(wf, "_fetch_with_auth", unavailable)
    wf.poll_warehouse(URL)
    result = browse()
    assert result["source"]["state"] == "failed"
    assert result["total"] == 0 and not result["source_complete"]


def test_truncated_poll_retains_rows_and_persists_incomplete_provenance(store, monkeypatch):
    fetched(monkeypatch, [{"name": "keep.json", "mtime": "2026-10-14"}])
    wf.poll_warehouse(URL)
    fetched(monkeypatch, [], truncated=True)
    poll = wo.warehouse_op({"op": "poll", "url": URL})
    assert poll["success"] and not poll["source_complete"]
    with pytest.raises(Fault) as error:
        decode_envelope(poll, ADAPTER)
    assert error.value.code == "PARTIAL_SOURCE"
    result = browse()
    assert result["source"]["state"] == "partial" and result["source"]["truncated"] is True
    assert [r["path"] for r in result["files"]] == ["keep.json"]
    with pytest.raises(Fault):
        decode_envelope(result, ADAPTER)
    fetched(monkeypatch, [])
    wf.poll_warehouse(URL)
    result = browse()
    assert result["files"] == [] and result["source_complete"]


def test_poll_all_preserves_successes_and_reports_partial_failure(store, monkeypatch):
    rows = [{"ok": True, "url": URL, "source_complete": True},
            {"ok": False, "url": URL + "/down", "error": "503"}]
    monkeypatch.setattr(wf, "poll_all", lambda: rows)
    response = wo.warehouse_op({"op": "poll"})
    with pytest.raises(Fault) as error:
        decode_envelope(response, ADAPTER)
    assert error.value.code == "PARTIAL_SOURCE"
    assert error.value.partial["items"] == rows


def test_legacy_cache_migration_does_not_invent_completeness(store, monkeypatch):
    with sqlite3.connect(wf.DB_PATH) as db:
        db.execute("CREATE TABLE poll_status(wh_url TEXT PRIMARY KEY, last_poll TEXT, ok INTEGER, error TEXT, "
                   "file_count INTEGER, title TEXT, has_restricted INTEGER)")
        db.execute("INSERT INTO poll_status VALUES(?, '2026-10-01', 1, NULL, 0, 'legacy', 0)", (URL,))
    result = browse()
    assert result["source"]["last_success"] == "2026-10-01"
    assert result["source"]["truncated"] is None
    assert result["source"]["state"] == "unknown" and not result["source_complete"]
    fetched(monkeypatch)
    wf.poll_warehouse(URL)
    assert browse()["source_complete"]


def test_ibl_browse_keeps_incomplete_snapshot_in_catch(store, monkeypatch):
    import ibl_routing
    import routing_system
    from ibl_v2_entry import handle_request

    monkeypatch.setattr(ibl_routing, "_SYSTEM_CAPS", dict(ibl_routing._SYSTEM_CAPS))
    routing_system.register_all()
    ibl_routing.register_system_capabilities({"warehouse_op": wo.warehouse_op})
    code = '''#!ibl edition=2
[try] { return [others:warehouse]{op:"browse",url:"https://warehouse.example"} }
[catch] { return {code:$error.code,source:$error.partial.source,files:$error.partial.files} }
'''
    response = handle_request({"code": code, "edition": 2, "origin": "training"}, str(store), None)
    assert response["success"], response
    assert response["value"]["code"] == "PARTIAL_SOURCE"
    assert response["value"]["source"]["state"] == "unpolled"
    assert response["value"]["files"] == []
    assert response["source_complete"] is False


def test_http_browser_receives_same_warning_and_preserved_files(store, monkeypatch):
    import asyncio
    import api_warehouse_feed

    monkeypatch.setattr(api_warehouse_feed, "_name_map", lambda: {URL: "시험 창고"})
    result = asyncio.run(api_warehouse_feed.browse(URL))
    assert result["source"]["state"] == "unpolled"
    assert result["source_complete"] is False and result["warning"]
    assert result["neighbor_name"] == "시험 창고"


if __name__ == "__main__":
    import sys
    sys.exit(pytest.main([__file__] + sys.argv[1:]))
