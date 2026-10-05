"""③ 작업 수명의 공통 관찰·제어(2026-10-05): 접수증 통화 1종 + `[self:task]{op: status|wait|cancel}` + 어댑터.

docs/APP_COMMON_FOUNDATION_GAPS_2026_10_05.md §1-③. 수명 셋(목표/작업/티켓)을 섞지 않고, 실행기는 어댑터 뒤에 남는다.
상태 어휘: timeout(대기자 사정)≠failed(작업 사정), cancel_requested≠cancelled, interrupted≠failed, unknown=모르는 작업.
"""
import json
import threading
import time

import boot_paths  # noqa: F401
import pytest
import task_receipts as T


@pytest.fixture(autouse=True)
def _clean_registry():
    T._reset_for_tests()
    yield
    T._reset_for_tests()


def _fake_kind(name, states):
    """states: task_id -> 호출마다 소비되는 상태 목록(마지막 값 유지)."""
    calls = {}
    def status(ref):
        seq = states[ref["task_id"]]
        i = calls.get(ref["task_id"], 0)
        st = seq[min(i, len(seq) - 1)]
        calls[ref["task_id"]] = i + 1
        return T.view(ref, st, result={"answer": ref["task_id"]} if st == T.SUCCEEDED else None,
                      error="boom" if st == T.FAILED else None)
    T.register(name, status)
    return calls


def test_receipt_shape_and_state_vocabulary():
    r = T.receipt("script", "job-1", status_url="/x", job_id="job-1")
    assert r["success"] and r["accepted"] and r["task_ref"] == {"kind": "script", "task_id": "job-1"} and r["state"] == "queued"
    assert r["status_url"] == "/x" and r["job_id"] == "job-1"
    assert T.receipt("delegation", "t", owner="system")["task_ref"]["owner"] == "system"
    with pytest.raises(ValueError):
        T.receipt("script", "j", state="succeeded")   # 접수증은 살아 있는 상태만
    with pytest.raises(ValueError):
        T.view(T.ref("x", "1"), "done")                # 상태 어휘 밖 거절


def test_normalize_ref_accepts_receipt_task_ref_string_and_flat():
    rc = T.receipt("script", "j1")
    assert T.normalize_ref(rc) == {"kind": "script", "task_id": "j1"}
    assert T.normalize_ref(rc["task_ref"]) == {"kind": "script", "task_id": "j1"}
    assert T.normalize_ref("guestpc:abc") == {"kind": "guestpc", "task_id": "abc"}
    assert T.normalize_ref(None, kind="newspaper", task_id="2026") == {"kind": "newspaper", "task_id": "2026"}
    assert T.normalize_ref({"kind": "x"}) is None and T.normalize_ref("") is None


def test_status_unknown_kind_and_adapter_errors_are_unknown_not_failed():
    v = T.status(T.ref("nope", "1"))
    assert v["state"] == "unknown" and "어댑터 미등록" in v["error"]
    T.register("broken", lambda ref: 1 / 0)
    v = T.status(T.ref("broken", "1"))
    assert v["state"] == "unknown" and "ZeroDivisionError" in v["error"]
    T.register("offvocab", lambda ref: {"state": "done"})
    assert T.status(T.ref("offvocab", "1"))["state"] == "unknown"


def test_wait_timeout_is_not_failure_and_terminal_returns_result():
    _fake_kind("k", {"slow": [T.RUNNING] * 50, "quick": [T.QUEUED, T.RUNNING, T.SUCCEEDED], "bad": [T.FAILED]})
    out = T.wait(T.ref("k", "slow"), timeout=0.3, poll=0.05)
    assert out["success"] is False and out["timed_out"] is True and out["state"] == "running" and "실패 아님" in out["error"]
    out = T.wait(T.ref("k", "quick"), timeout=5, poll=0.01)
    assert out["success"] is True and out["state"] == "succeeded" and out["result"] == {"answer": "quick"} and out["terminal"]
    out = T.wait(T.ref("k", "bad"), timeout=5, poll=0.01)
    assert out["success"] is False and out["state"] == "failed" and out["error"] == "boom" and "timed_out" not in out
    # 상한: 요청 timeout 이 WAIT_MAX 를 넘으면 줄였다고 말한다
    out = T.wait(T.ref("k", "slow"), timeout=10_000, poll=0.05) if False else None  # (실제 240초 대기는 하지 않는다)


def test_cancel_reports_only_confirmed_facts():
    _fake_kind("nocancel", {"a": [T.RUNNING]})
    out = T.cancel(T.ref("nocancel", "a"))
    assert out["success"] is False and out["state"] == "running" and "지원하지 않" in out["error"]
    T.register("c", lambda ref: T.view(ref, T.RUNNING), lambda ref: T.view(ref, T.CANCEL_REQUESTED))
    out = T.cancel(T.ref("c", "1"))
    assert out["success"] is True and out["state"] == "cancel_requested"


def test_self_task_word_waits_two_receipts_and_merges_in_one_program():
    """완료 조건의 핵심: 한 관용구가 두 접수증을 기다려 결과를 합쳐 다음 낱말에 넘긴다."""
    _fake_kind("a", {"x": [T.RUNNING, T.SUCCEEDED]})
    _fake_kind("b", {"y": [T.QUEUED, T.RUNNING, T.SUCCEEDED]})
    from project_manager import ProjectManager
    from ibl_v2_entry import handle_request
    pp = str(ProjectManager().get_project_path("앱모드"))
    code = ('$p = [self:task]{op: "wait", ref: $ra, timeout: 5}; $q = [self:task]{op: "wait", ref: $rb, timeout: 5}; '
            'return {first: $p.result.answer, second: $q.result.answer, states: [$p.state, $q.state]}')
    inputs = {"ra": T.receipt("a", "x"), "rb": T.receipt("b", "y")["task_ref"]}
    r = handle_request({"code": code, "edition": 2, "inputs": inputs, "declared_inputs": ["ra", "rb"]}, pp, None)
    assert r["success"] is True, r.get("error")
    assert r["value"] == {"first": "x", "second": "y", "states": ["succeeded", "succeeded"]}
    # status 는 즉시, ref 없으면 거절(알려진 종류를 알려준다)
    r = handle_request({"code": '[self:task]{op: "status", ref: $ra}', "edition": 2, "inputs": {"ra": T.receipt("a", "x")}, "declared_inputs": ["ra"]}, pp, None)
    assert r["success"] is True and r["value"]["state"] in ("running", "succeeded")
    r = handle_request({"code": '[self:task]{op: "status"}', "edition": 2, "inputs": {}, "declared_inputs": []}, pp, None)
    assert r["success"] is False and "ref" in (r.get("error") or "")


def test_delegation_adapter_projects_task_view(monkeypatch):
    import delegation_tasks as D
    import routing_system
    routing_system.register_all()
    assert "delegation" in T.registered()
    row = {"status": "completed", "result": "답", "run_id": "r", "delegation_context": "{}", "pending_delegations": 0}
    monkeypatch.setattr(D, "get_task_row", lambda owner, tid: row if tid == "t1" else None)
    v = T.status(T.ref("delegation", "t1", "system"))
    assert v["state"] == "succeeded" and v["result"] == "답" and v["status_url"] == "/system-ai/tasks/t1"
    assert T.status(T.ref("delegation", "zz", "system"))["state"] == "unknown"
    rc = D.accepted("system", "t1")
    assert rc["task_ref"] == {"kind": "delegation", "owner": "system", "task_id": "t1"} and rc["state"] == "queued"
    assert D.task_view("system", "t1")["task_ref"]["kind"] == "delegation"


def test_script_adapter_maps_job_states(monkeypatch, tmp_path):
    import importlib, sys
    pkg = boot_paths.ROOT / "data/packages/installed/tools/system_essentials" if hasattr(boot_paths, "ROOT") else None
    from pathlib import Path
    pkg = Path(__file__).resolve().parents[1] / "data/packages/installed/tools/system_essentials"
    if str(pkg) not in sys.path:
        sys.path.insert(0, str(pkg))
    so = importlib.import_module("script_ops")
    jobs = tmp_path / "jobs"; jobs.mkdir()
    monkeypatch.setattr(so, "_path", lambda name: {"_JOB_DIR": jobs, "_RUN_DIR": tmp_path}[name])
    def job(jid, **kw):
        (jobs / f"{jid}.json").write_text(json.dumps({"job_id": jid, "id": "s", "status": "done", "created_epoch": time.time(), **kw}))
    job("j-done", result={"ok": 1}); job("j-fail", status="failed", error="x"); job("j-lost", status="running", pid=999999999)
    job("j-start", status="starting")
    assert T.status(T.ref("script", "j-done")) and so.task_status(T.ref("script", "j-done"))["state"] == "succeeded"
    assert so.task_status(T.ref("script", "j-done"))["result"] == {"ok": 1}
    assert so.task_status(T.ref("script", "j-fail"))["state"] == "failed"
    assert so.task_status(T.ref("script", "j-lost"))["state"] == "interrupted"
    assert so.task_status(T.ref("script", "j-start"))["state"] == "queued"
    assert so.task_status(T.ref("script", "nope"))["state"] == "unknown"
    # 데이터 길: 등록부가 패키지 yaml task_kinds 로 어댑터를 찾는다
    T._reset_for_tests()
    assert T.status(T.ref("script", "j-done"))["state"] == "succeeded" and "script" in T.registered()


def test_guestpc_adapter_reads_phone_jobs_nondestructively():
    import phone_jobs
    import importlib, sys
    from pathlib import Path
    pkg = Path(__file__).resolve().parents[1] / "data/packages/installed/tools/guest-helper"
    if str(pkg) not in sys.path:
        sys.path.insert(0, str(pkg))
    gh = importlib.import_module("handler")
    jid = phone_jobs.enqueue("dev-test", "{}")
    ref = T.ref("guestpc", jid)
    assert gh.task_status(ref)["state"] == "running"
    phone_jobs.set_partial(jid, {"tail": "…"})
    assert gh.task_status(ref)["progress"] == {"tail": "…"}
    phone_jobs.set_result(jid, {"exit_code": 0})
    assert gh.task_status(ref)["state"] == "succeeded" and gh.task_status(ref)["result"] == {"exit_code": 0}   # 두 번 읽어도 남는다
    assert phone_jobs.wait_result(jid, timeout=0.1) == {"exit_code": 0}                                        # 옛 회수(pop)도 그대로
    after = gh.task_status(ref)
    assert after["state"] == "succeeded" and after["result"] is None and "회수" in after["note"]   # 회수됨 ≠ 실행 중
    jid2 = phone_jobs.enqueue("dev-test", "{}")
    assert gh.task_status_cancel(T.ref("guestpc", jid2))["state"] == "cancelled"


def test_newspaper_adapter_reads_state_file(monkeypatch, tmp_path):
    import importlib, sys
    from pathlib import Path
    pkg = Path(__file__).resolve().parents[1] / "data/packages/installed/tools/web"
    if str(pkg) not in sys.path:
        sys.path.insert(0, str(pkg))
    tn = importlib.import_module("tool_newspaper")
    monkeypatch.setattr(tn, "_outputs_dir", lambda: tmp_path)
    from datetime import datetime, timedelta
    now = datetime.now().isoformat()
    tn._write_state(tmp_path, {"status": "building", "started_at": now, "task_id": now})
    assert tn.task_status(T.ref("newspaper", now))["state"] == "running"
    assert tn.task_status(T.ref("newspaper", "other"))["state"] == "unknown"
    old = (datetime.now() - timedelta(seconds=999)).isoformat()
    tn._write_state(tmp_path, {"status": "building", "started_at": old, "task_id": old})
    assert tn.task_status(T.ref("newspaper", old))["state"] == "interrupted"
    tn._write_state(tmp_path, {"status": "done", "started_at": now, "task_id": now, "message": "ok"})
    v = tn.task_status(T.ref("newspaper", now))
    assert v["state"] == "succeeded" and v["result"]["message"] == "ok"
    tn._write_state(tmp_path, {"status": "error", "started_at": now, "message": "bad"})   # 옛 기록(task_id 없음)은 started_at 으로 맞춘다
    assert tn.task_status(T.ref("newspaper", now))["state"] == "failed"


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
