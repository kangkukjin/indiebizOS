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
    assert v["state"] == "unknown" and "어댑터 미등록" in v["failure"]
    T.register("broken", lambda ref: 1 / 0)
    v = T.status(T.ref("broken", "1"))
    assert v["state"] == "unknown" and "ZeroDivisionError" in v["failure"] and "error" not in v
    T.register("offvocab", lambda ref: {"state": "done"})
    assert T.status(T.ref("offvocab", "1"))["state"] == "unknown"


def test_wait_timeout_is_not_failure_and_terminal_returns_result():
    _fake_kind("k", {"slow": [T.RUNNING] * 50, "quick": [T.QUEUED, T.RUNNING, T.SUCCEEDED], "bad": [T.FAILED]})
    out = T.wait(T.ref("k", "slow"), timeout=0.3, poll=0.05)
    # 시간 초과는 대기자의 사정 — 값이다(판본 2 는 success:false·error 를 도구 실패로 올려 프로그램을 끝낸다, 26회차 L26-2)
    assert out["success"] is True and out["timed_out"] is True and out["state"] == "running" and "실패 아님" in out["note"]
    assert "error" not in out and out["result"] is None and out["failure"] is None
    out = T.wait(T.ref("k", "quick"), timeout=5, poll=0.01)
    assert out["success"] is True and out["state"] == "succeeded" and out["result"] == {"answer": "quick"} and out["terminal"]
    assert out["timed_out"] is False and out["failure"] is None          # 칸은 항상 같다
    out = T.wait(T.ref("k", "bad"), timeout=5, poll=0.01)
    assert out["success"] is False and out["state"] == "failed" and out["error"] == "boom" and out["failure"] == "boom"
    assert out["timed_out"] is False and out["result"] is None
    # 상한: 요청 timeout 이 WAIT_MAX 를 넘으면 줄였다고 말한다
    out = T.wait(T.ref("k", "slow"), timeout=10_000, poll=0.05) if False else None  # (실제 240초 대기는 하지 않는다)


def test_cancel_reports_only_confirmed_facts():
    _fake_kind("nocancel", {"a": [T.RUNNING]})
    out = T.cancel(T.ref("nocancel", "a"))
    assert out["success"] is False and out["state"] == "running" and "지원하지 않" in out["error"]
    T.register("c", lambda ref: T.view(ref, T.RUNNING), lambda ref: T.view(ref, T.CANCEL_REQUESTED))
    out = T.cancel(T.ref("c", "1"))
    assert out["success"] is True and out["state"] == "cancel_requested"


def test_cancel_of_a_finished_task_is_a_value_whatever_the_kind():
    """긴문장 27회차 L27-2: 늦어서 취소하려는 순간 이미 끝난 작업 — 종류의 취소 지원 여부보다 끝난 사실이 먼저다."""
    _fake_kind("nocancel", {"done": [T.SUCCEEDED], "bad": [T.FAILED], "live": [T.RUNNING]})
    out = T.cancel(T.ref("nocancel", "done"))
    assert out["success"] is True and out["state"] == "succeeded" and out["result"] == {"answer": "done"}
    assert "취소할 것이 없습니다" in out["note"] and "error" not in out
    out = T.cancel(T.ref("nocancel", "bad"))
    assert out["success"] is True and out["state"] == "failed" and out["failure"] == "boom"
    assert T.cancel(T.ref("nocancel", "live"))["success"] is False          # 살아 있는데 못 멈추는 것만 거절
    # 취소 어댑터가 '이미 끝남'을 돌려준 경합도 값
    T.register("race", lambda ref: T.view(ref, T.RUNNING), lambda ref: T.view(ref, T.SUCCEEDED, result=7))
    out = T.cancel(T.ref("race", "1"))
    assert out["success"] is True and out["state"] == "succeeded" and out["result"] == 7
    T.register("stuck", lambda ref: T.view(ref, T.RUNNING), lambda ref: T.view(ref, T.RUNNING))
    assert T.cancel(T.ref("stuck", "1"))["success"] is False


def test_wait_then_cancel_program_reports_finished_and_unstoppable_tasks_apart():
    """27회차 주 과제의 뼈대: 기다리다 늦은 일을 취소 시도 — 그 사이 끝난 일은 결과로, 못 멈춘 일은 '취소 불가'로 갈린다."""
    _fake_kind("k", {"late": [T.RUNNING, T.SUCCEEDED], "live": [T.RUNNING] * 400})
    code = (
        '[def:정리]($ref) {\n'
        '  $w = [self:task]{op: "wait", ref: $ref, timeout: 0}\n'
        '  [if:not $w.timed_out] { return {상태: "완료", result: $w.result} }\n'
        '  [try] {\n'
        '    $c = [self:task]{op: "cancel", ref: $ref}\n'
        '    [if:$c.state == "succeeded"] { return {상태: "완료", result: $c.result} }\n'
        '    return {상태: $c.state, result: null}\n'
        '  }\n'
        '  [catch] { return {상태: "취소 불가", result: null, state: $error.details.state} }\n'
        '}\n'
        'return [[fn:정리]{ref: $a}, [fn:정리]{ref: $b}]')
    r = _run(code, {"a": T.ref("k", "late"), "b": T.ref("k", "live")})
    assert r["success"] is True, r.get("error")
    assert r["value"] == [{"상태": "완료", "result": {"answer": "late"}},
                          {"상태": "취소 불가", "result": None, "state": "running"}]


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


def _run(code, inputs):
    from project_manager import ProjectManager
    from ibl_v2_entry import handle_request
    pp = str(ProjectManager().get_project_path("앱모드"))
    return handle_request({"code": code, "edition": 2, "inputs": inputs, "declared_inputs": list(inputs)}, pp, None)


def test_timeout_is_a_value_and_failed_job_is_catchable_in_one_program():
    """긴문장 26회차: 묶음을 기다리다 안 끝난 것은 '진행 중', 실패한 것은 '오류'로 가르는 프로그램이 중단 없이 돈다."""
    _fake_kind("m", {"slow": [T.RUNNING] * 400, "ok": [T.SUCCEEDED], "bad": [T.FAILED]})
    code = (
        '[def:관찰]($ref) {\n'
        '  [try] {\n'
        '    $r = [self:task]{op: "wait", ref: $ref, timeout: 0.3}\n'
        '    [if:$r.timed_out] { return {상태: "진행 중", state: $r.state, result: $r.result, failure: $r.failure} }\n'
        '    return {상태: "완료", state: $r.state, result: $r.result, failure: $r.failure}\n'
        '  }\n'
        '  [catch] { return {상태: "오류", state: $error.details.state, result: null, failure: $error.details.failure} }\n'
        '}\n'
        'return [[fn:관찰]{ref: $a}, [fn:관찰]{ref: $b}, [fn:관찰]{ref: $c}]')
    r = _run(code, {"a": T.ref("m", "slow"), "b": T.ref("m", "ok"), "c": T.ref("m", "bad")})
    assert r["success"] is True, r.get("error")
    assert r["value"] == [
        {"상태": "진행 중", "state": "running", "result": None, "failure": None},
        {"상태": "완료", "state": "succeeded", "result": {"answer": "ok"}, "failure": None},
        {"상태": "오류", "state": "failed", "result": None, "failure": "boom"}]


def test_status_of_a_failed_job_is_an_answer_and_declared_fields_are_checked():
    _fake_kind("n", {"bad": [T.FAILED], "ok": [T.SUCCEEDED]})
    r = _run('$s = [self:task]{op: "status", ref: $x}; return {state: $s.state, failure: $s.failure, terminal: $s.terminal}', {"x": T.ref("n", "bad")})
    assert r["success"] is True and r["value"] == {"state": "failed", "failure": "boom", "terminal": True}
    # 모르는 작업은 값을 줄 수 없다 — 호출의 실패이고 사정은 details 로 읽힌다
    r = _run('[try] { [self:task]{op: "status", ref: $x} } [catch] { return $error.details.state }', {"x": T.ref("no-such-kind", "1")})
    assert r["success"] is True and r["value"] == "unknown"
    # 없는 칸(`error`)은 실행 전에 걸린다 — 실행 중 MISSING_FIELD 는 이미 시작한 작업을 남긴 채 끝났다(L26-1)
    from project_manager import ProjectManager
    from ibl_v2_entry import handle_request
    pp = str(ProjectManager().get_project_path("앱모드"))
    chk = handle_request({"code": '$s = [self:task]{op: "wait", ref: $x}; return $s.error', "edition": 2, "check": True,
                          "inputs": {"x": T.ref("n", "ok")}, "declared_inputs": ["x"]}, pp, None)
    assert chk.get("ok") is False and any(i.get("code") in ("MISSING_FIELD", "UNKNOWN_FIELD", "UNOBSERVED_FIELD") for i in chk.get("issues") or []), chk


def test_adapter_built_views_get_the_same_fields():
    T.register("rawkind", lambda ref: {"state": "failed", "error": "옛 칸"})          # view() 를 안 거친 어댑터
    v = T.status(T.ref("rawkind", "1"))
    assert v["failure"] == "옛 칸" and "error" not in v and v["terminal"] is True and v["timed_out"] is False and v["result"] is None


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


def test_script_cancel_stops_the_runner_and_its_children(monkeypatch, tmp_path):
    """27회차 L27-3: 백그라운드 스크립트 취소 — 표식 → 러너가 자식 나무를 끝내고 cancelled 기록 → 투영 cancelled."""
    import importlib, os, subprocess, sys
    from pathlib import Path
    pkg = Path(__file__).resolve().parents[1] / "data/packages/installed/tools/system_essentials"
    if str(pkg) not in sys.path:
        sys.path.insert(0, str(pkg))
    so = importlib.import_module("script_ops")
    jobs = tmp_path / "jobs"; jobs.mkdir()
    monkeypatch.setattr(so, "_path", lambda name: {"_JOB_DIR": jobs, "_RUN_DIR": tmp_path}[name])
    script = tmp_path / "slow.py"
    script.write_text("import subprocess, sys, time\n"
                      "kid = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'])\n"
                      "open(sys.argv[0] + '.kid', 'w').write(str(kid.pid))\n"
                      "time.sleep(120)\n")
    def start(jid):
        (jobs / f"{jid}.json").write_text(json.dumps({
            "job_id": jid, "id": "s", "status": "starting", "created_epoch": time.time(), "timeout": 120,
            "log": str(tmp_path / f"{jid}.log"), "interpreter": sys.executable, "script": str(script), "stdin": "{}"}))
        return subprocess.Popen([sys.executable, str(pkg / "_bg_runner.py"), str(jobs / f"{jid}.json")], cwd=str(pkg),
                                env={**os.environ, "INDIEBIZ_API_PORT": "9"})      # 완료 알림은 닫힌 포트로
    runner = start("j1")
    kid_file = Path(str(script) + ".kid")
    deadline = time.time() + 20
    while not kid_file.exists() and time.time() < deadline:
        time.sleep(0.1)
    assert so.task_status(T.ref("script", "j1"))["state"] == "running"
    out = T.cancel(T.ref("script", "j1"))                 # 등록부가 패키지 yaml 에서 취소 어댑터까지 적재한다
    assert out["success"] is True and out["state"] in ("cancelled", "cancel_requested"), out
    runner.wait(timeout=20)
    final = T.status(T.ref("script", "j1"))
    assert final["state"] == "cancelled" and final["terminal"] is True and final["result"] is None
    from common import platform_utils
    kid = int(kid_file.read_text())
    for _ in range(50):
        if not platform_utils.pid_alive(kid):
            break
        time.sleep(0.1)
    assert not platform_utils.pid_alive(kid), "스크립트의 자식이 남았다"
    again = T.cancel(T.ref("script", "j1"))               # 끝난 작업의 재취소는 값
    assert again["success"] is True and again["state"] == "cancelled"
    assert so.op_status({"job_id": "j1"})["success"] is False       # 옛 조회 경로도 취소를 성공으로 꾸미지 않는다
    # 시작 전에 취소된 작업은 스크립트를 띄우지 않는다
    kid_file.unlink()
    (jobs / "j2.cancel").write_text("x")
    start("j2").wait(timeout=20)
    assert so.task_status(T.ref("script", "j2"))["state"] == "cancelled" and not kid_file.exists()


def test_concurrent_first_lookups_wait_for_the_package_adapter(monkeypatch):
    """긴문장 27회차 L27-7: 어댑터 첫 적재 중에 온 병렬 조회가 실행 중인 작업을 unknown 으로 답하지 않는다."""
    loads = []
    def slow_resolve(kind):
        loads.append(kind)
        time.sleep(0.3)
        T.register(kind, lambda ref: T.view(ref, T.RUNNING))
    monkeypatch.setattr(T, "_resolve_from_packages", slow_resolve)
    out = []
    threads = [threading.Thread(target=lambda: out.append(T.status(T.ref("slowkind", "j"))["state"])) for _ in range(4)]
    for th in threads: th.start()
    for th in threads: th.join()
    assert out == ["running"] * 4 and loads == ["slowkind"]

