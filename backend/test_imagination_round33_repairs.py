"""긴문장 33회차 수리 회귀 — 다단계 BOM 전개 훈련에서 발견한 세 가지.

L33-2 제자리에서 바뀐 파일을 `reuse` 가 옛 영수증으로 읽던 결함(신선도 지문),
L33-3 프로젝트 문맥 없는 요청의 검사 단계 사전경고,
L33-1 값으로 정한 레코드 키의 구문 안내.
정본: docs/experiments/long_sentence_imagination/round_33/report.md
"""
import json
import os
import time

import boot_paths  # noqa: F401
import pytest
from ibl_v2_ir import unpack
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime
from ibl_v2_adapters import Adapter
from ibl_run_journal import Journal, reusable_receipts, resource_state


def file_registry(calls):
    def read(rt, args):
        calls.append(("read", args["path"]))
        with open(args["path"], encoding="utf-8") as fh:
            return {"data": json.load(fh)}
    contract = {"version": 1, "params": {"path": "Text"}, "result": "Record", "effects": ["read_external"],
                "implementation_fingerprint": "impl-1", "read_resources": {"file": "path"}}
    return {"t:read": Adapter(contract, read)}


def _run(source, registry, root, reuse_id=None):
    plan = compile_program(source, registry)
    with Journal(root, "ctx") as journal:
        out = Runtime(plan, journal=journal, reusable=reusable_receipts(root, reuse_id) if reuse_id else None,
                      reuse_run=reuse_id).run()
        return journal.run_id, out


def _touch(path, payload):
    # mtime 해상도가 거친 파일시스템에서도 지문이 달라지도록 크기·시각을 함께 바꾼다
    time.sleep(0.01)
    path.write_text(json.dumps(payload))


def test_reuse_rereads_file_changed_in_place(tmp_path):
    """L33-2: 같은 경로의 파일이 바뀌면 옛 영수증을 빌리지 않고 새로 읽는다(사유 resource_changed·바뀐 경로)."""
    calls = []
    data = tmp_path / "orders.json"
    data.write_text(json.dumps([{"qty": 102}]))
    source = f'#!ibl edition=2\n$d = [t:read]{{path:"{data}"}}\nreturn $d.data[0].qty'
    first_id, first = _run(source, file_registry(calls), tmp_path)
    assert first["success"] and unpack(first["value_wire"]["data"]) == 102
    receipts = reusable_receipts(tmp_path, first_id)
    assert len(receipts) == 1 and next(iter(receipts.values()))["resource_state"][0][0] == os.path.realpath(data)

    _touch(data, [{"qty": 204}])
    calls.clear()
    _, second = _run(source + " * 1", file_registry(calls), tmp_path, reuse_id=first_id)
    assert second["success"] and unpack(second["value_wire"]["data"]) == 204, "바뀐 파일은 새 값으로 읽어야 한다"
    assert calls == [("read", str(data))]
    reuse = second["reuse"]
    assert reuse["reused_calls"] == 0 and reuse["skipped"][0]["reason"] == "resource_changed"
    assert reuse["skipped"][0]["changed_resources"] == [os.path.realpath(data)]


def test_reuse_keeps_borrowing_unchanged_file(tmp_path):
    """L33-2 보존: 파일이 그대로면 종전처럼 영수증을 빌린다(읽기 0회)."""
    calls = []
    data = tmp_path / "parts.json"
    data.write_text(json.dumps([{"n": 1}]))
    source = f'#!ibl edition=2\n$d = [t:read]{{path:"{data}"}}\nreturn len($d.data)'
    first_id, first = _run(source, file_registry(calls), tmp_path)
    assert first["success"]
    calls.clear()
    _, second = _run(source + " + 0", file_registry(calls), tmp_path, reuse_id=first_id)
    assert second["success"] and unpack(second["value_wire"]["data"]) == 1
    assert calls == [] and second["reuse"]["reused_calls"] == 1


def test_reuse_refuses_old_receipt_without_freshness(tmp_path):
    """L33-2: 지문이 없는 옛 영수증은 빌리지 않고 사유를 밝힌다(freshness_unknown)."""
    calls = []
    data = tmp_path / "stock.json"
    data.write_text(json.dumps([{"n": 1}]))
    source = f'#!ibl edition=2\n$d = [t:read]{{path:"{data}"}}\nreturn len($d.data)'
    first_id, _ = _run(source, file_registry(calls), tmp_path)
    old = reusable_receipts(tmp_path, first_id)
    for receipt in old.values():
        receipt.pop("resource_state")
    calls.clear()
    plan = compile_program(source + " + 0", file_registry(calls))
    out = Runtime(plan, reusable=old, reuse_run=first_id).run()
    assert out["success"] and calls == [("read", str(data))]
    assert out["reuse"]["reused_calls"] == 0 and out["reuse"]["skipped"][0]["reason"] == "freshness_unknown"


def test_resource_state_shape():
    assert resource_state(None) is None and resource_state([]) is None
    assert resource_state([["db", "x", None]]) is None
    state = resource_state([["file", "/nonexistent/round33", None]])
    assert state == [["/nonexistent/round33", None, None, None]]


def test_check_warns_when_project_context_is_missing(tmp_path, monkeypatch):
    """L33-3: 프로젝트 경로가 필요한 액션을 쓰는데 요청에 문맥이 없으면 검사가 PROJECT_CONTEXT 경고를 낸다."""
    from ibl_v2_entry import handle_request
    import thread_context
    monkeypatch.setattr(thread_context, "get_current_project_id", lambda: None)
    code = '#!ibl edition=2\n$d = [self:read]{path:"x.json"}\nreturn $d'
    checked = handle_request({"code": code, "check": True}, project_path=".")
    assert checked["ok"], checked.get("issues")
    warning = [w for w in checked["warnings"] if w.get("code") == "PROJECT_CONTEXT"]
    assert warning and "self:read" in warning[0]["actions"] and "project_id" in warning[0]["hint"]

    with_path = handle_request({"code": code, "check": True}, project_path=str(tmp_path))
    assert not [w for w in with_path["warnings"] if w.get("code") == "PROJECT_CONTEXT"]

    pure = handle_request({"code": '#!ibl edition=2\nreturn [{a:1}] >> [table:filter]{where:($r)=>$r.a > 0}', "check": True},
                          project_path=".")
    assert pure["ok"] and not [w for w in pure["warnings"] if w.get("code") == "PROJECT_CONTEXT"]


def test_record_computed_key_is_explained():
    """L33-1: {[$k]: 값} 은 '이름이 필요합니다' 대신 지원하지 않는 모양과 대안을 말한다."""
    from ibl_v2_entry import handle_request
    out = handle_request({"code": '#!ibl edition=2\n$k = "a"\nreturn {[$k]: 1}', "check": True}, project_path=".")
    assert not out["ok"]
    message = out["issues"][0]["message"]
    assert "값으로 정한 키" in message and "keys/values/entries" in message


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
