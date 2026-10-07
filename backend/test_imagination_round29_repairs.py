"""긴문장 29회차 수리 회귀(2026-10-07).

L29-1 부모 턴이 살아 있는 동안 도착한 자식 보고 — 러너가 붙들었다가 턴 뒤에 전달, 부모가 이미 읽어 간 보고는 새 턴 없이 닫음
L29-2 `$w = [try]{… return …}[catch]{… return …}` — 대입이 일어나지 않는 모양을 검사가 경고
L29-3 접수증·투영의 접수 기준 시계(accepted_at·elapsed_s)
L29-4 병렬로 겹친 도구 시간의 벽시계(wall_ms)
"""
import boot_paths  # noqa: F401
import json
import time

import pytest

import system_ai_memory as memory
import thread_context as tc
from test_delegation_tasks import world, PROJECT, AGENT_ID, AGENT_NAME  # noqa: F401 — 임시 저장소 대역


# ── L29-2 ─────────────────────────────────────────────────────────────────────

def _compile(code, inputs=None):
    from ibl_v2_compile import compile_program
    return compile_program(code, None, inputs)


@pytest.mark.parametrize("code", [
    '$w = [try] { return {a: 1} } [catch] { return {a: 2} }\nreturn {w: $w, extra: 1}',
    '$w = [if:$c] { return 1 } [else] { return 2 }\nreturn $w',
    '$w = [case:$c] { [when:true] { return 1 } [else] { return 2 } }\nreturn $w',
])
def test_binding_a_block_whose_every_path_returns_is_warned(code):
    plan = _compile(code, {"c": True})
    warning = next((w for w in plan.preflight["warnings"] if w["code"] == "BIND_RETURNS"), None)
    assert warning and "$w" in warning["message"] and "마지막 문장" in warning["hint"], plan.report()
    assert not plan.issues, plan.report()          # 결과가 같은 기존 프로그램(뒤가 return $w 뿐)을 막지 않는다


@pytest.mark.parametrize("code,expected", [
    ('$w = [try] { {a: 1} } [catch] { {a: 2} }\nreturn $w.a', 1),          # 블록의 값 = 마지막 문장
    ('$w = [if:$c] { return "일찍" } [else] { 2 }\nreturn $w', "일찍"),      # 한쪽만 return 인 이른 반환은 그대로
    ('[try] { return 1 } [catch] { return 2 }', 1),                         # 대입이 아니면 함수 반환으로 정상
])
def test_block_values_and_early_returns_still_work(code, expected):
    from ibl_v2_runtime import Runtime
    plan = _compile(code, {"c": True})
    assert not plan.issues and not any(w["code"] == "BIND_RETURNS" for w in plan.preflight["warnings"]), plan.report()
    out = Runtime(plan, {"c": True}).run()
    assert out["success"] and out["value"] == expected, out


# ── L29-4 ─────────────────────────────────────────────────────────────────────

def test_wall_time_counts_overlapping_calls_once():
    from ibl_v2_runtime import _covered_seconds
    assert _covered_seconds([(0.0, 15.0), (0.0, 15.0)]) == 15.0            # 병렬 대기 둘 = 15초
    assert _covered_seconds([(0.0, 2.0), (3.0, 4.0)]) == 3.0               # 순차는 합 그대로
    assert _covered_seconds([(0.0, 10.0), (2.0, 3.0), (9.0, 12.0)]) == 12.0
    assert _covered_seconds([]) == 0.0


_SELECT = '$rows=[{n:1}]\n$a=$rows >> [table:select]{columns:["n"]}\nreturn $a'


def test_serial_tool_lines_have_no_wall_ms():
    from ibl_v2_entry import handle_request
    out = handle_request({"edition": 2, "code": _SELECT, "inputs": {}})
    assert out["success"] and "wall_ms" not in out["usage"]["tool_ms_by_line"][0], out


def test_usage_rows_carry_wall_ms_when_calls_overlap(monkeypatch):
    import ibl_v2_runtime as R
    from ibl_v2_entry import handle_request
    original = R.Runtime._timed_invoke

    def overlapped(self, node, args, piped):
        value = original(self, node, args, piped)
        cell = self.tool_time[node.id]                                      # 같은 줄의 호출 둘이 15초씩 겹쳐 돌았다
        cell[0], cell[1], cell[3] = 2, 30.0, [(100.0, 115.0), (100.0, 115.0)]
        return value
    monkeypatch.setattr(R.Runtime, "_timed_invoke", overlapped)
    row = handle_request({"edition": 2, "code": _SELECT, "inputs": {}})["usage"]["tool_ms_by_line"][0]
    assert row["ms"] == 30_000 and row["wall_ms"] == 15_000 and row["calls"] == 2, row


# ── L29-3 ─────────────────────────────────────────────────────────────────────

def test_receipt_and_view_carry_the_acceptance_clock():
    import task_receipts as T
    receipt = T.receipt("script", "j1")
    assert T._epoch(receipt["accepted_at"]) == pytest.approx(time.time(), abs=2)
    r = T.ref("script", "j1")
    started = time.time() - 20
    live = T.view(r, T.RUNNING, accepted_at=started)
    assert 19 <= live["elapsed_s"] <= 22 and T._epoch(live["accepted_at"]) == pytest.approx(started, abs=1)
    done = T.view(r, T.SUCCEEDED, result="ok", accepted_at=started, ended_at=started + 18)
    assert done["elapsed_s"] == 18.0                                       # 끝난 작업은 종료까지 — 조회 시각과 무관
    assert T.view(r, T.SUCCEEDED, result="ok", accepted_at=started)["elapsed_s"] is None   # 종료 시각을 모르면 지어내지 않는다
    unknown = T.view(r, T.RUNNING)
    assert unknown["accepted_at"] is None and unknown["elapsed_s"] is None  # 칸은 항상 있다
    naive = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(started))     # script job 의 지역 시각 표기
    assert 19 <= T.view(r, T.RUNNING, accepted_at=naive)["elapsed_s"] <= 22


def test_adapters_without_view_still_get_clock_columns():
    import task_receipts as T
    T.register("r29_plain", lambda ref: {"state": "running"})
    T.register("r29_stamped", lambda ref: {"state": "running", "accepted_at": time.time() - 5})
    try:
        plain = T.status(T.ref("r29_plain", "x"))
        assert plain["accepted_at"] is None and plain["elapsed_s"] is None
        assert 4 <= T.status(T.ref("r29_stamped", "x"))["elapsed_s"] <= 7
        waited = T.wait(T.ref("r29_stamped", "x"), timeout=0)
        assert waited["timed_out"] is True and waited["elapsed_s"] >= 4      # 대기 0초여도 접수 기준 시계는 흐른다
    finally:
        with T._LOCK:
            for kind in ("r29_plain", "r29_stamped"):
                T._STATUS.pop(kind, None)


def test_task_contract_declares_clock_columns():
    """닫힌 투영 계약에 두 칸이 있어 읽는 프로그램이 검사를 통과하고, 실패한 대기의 사정($error.details)에도 실린다."""
    from ibl_v2_entry import handle_request
    head = '$r=[self:task]{op:"status", ref:"script:r29_없는작업"}\n'
    ok = handle_request({"edition": 2, "code": head + 'return {e: $r.elapsed_s, a: $r.accepted_at}', "inputs": {}})
    assert ok["diagnostic"]["kind"] == "runtime", ok                       # 검사는 통과 — 없는 작업이라 실행에서 unknown
    assert {"accepted_at", "elapsed_s"} <= set(ok["diagnostic"]["details"])
    bad = handle_request({"edition": 2, "code": head + 'return $r.started', "inputs": {}})
    assert bad["executed"] is False and bad["issues"][0]["code"] == "MISSING_FIELD", bad


def test_delegation_view_counts_from_acceptance(world):
    import task_receipts as T
    memory.create_task("p_clock", "user@gui", "gui", "원요청")
    view = world.dt.task_status({"kind": "delegation", "owner": "system", "task_id": "p_clock"})
    assert view["state"] == T.RUNNING and 0 <= view["elapsed_s"] < 5 and view["accepted_at"]
    memory.complete_task("p_clock", "끝")
    done = world.dt.task_status({"kind": "delegation", "owner": "system", "task_id": "p_clock"})
    assert done["state"] == T.SUCCEEDED and 0 <= done["elapsed_s"] < 5


# ── L29-1 ─────────────────────────────────────────────────────────────────────

def _accept_async(world, parent):
    from routing_system import _delegate_unified
    out = _delegate_unified({"scope": "cross", "agent_id": f"{PROJECT}/{AGENT_ID}", "message": "요약"}, world.project_path)
    assert out["accepted"], out
    return out["child_task_id"]


def _child_reports(world, parent, child, text="요약 본문"):
    """보고기가 하는 순서 그대로 — 부모 원장 반영 뒤 자식 행을 닫는다."""
    recorded = memory.record_child_response(parent, {"child_task_id": child, "from_agent": AGENT_NAME, "response": text})
    world.db.complete_task(child, text)
    return recorded


def test_parent_turn_reading_child_marks_it_collected_and_others_do_not(world):
    memory.create_task("p1", "user@gui", "gui", "원요청")
    tc.set_current_task_id("p1")
    a, b = _accept_async(world, "p1"), _accept_async(world, "p1")
    assert memory.awaited_child_reports("p1") == {"total": 2, "pending": 2, "uncollected": 0, "status": "pending"}
    _child_reports(world, "p1", a)
    _child_reports(world, "p1", b)
    assert memory.awaited_child_reports("p1")["uncollected"] == 2           # 응답은 왔으나 부모가 아직 읽지 않았다
    ref = {"kind": "delegation", "owner": PROJECT, "task_id": a}
    tc.set_current_task_id("someone_else")                                  # 다른 작업·화면의 조회는 회수가 아니다
    assert world.dt.task_status(ref)["state"] == "succeeded"
    assert memory.awaited_child_reports("p1")["uncollected"] == 2
    tc.set_current_task_id("p1")                                            # 부모 자신의 턴이 읽었다
    assert world.dt.task_status(ref)["result"] == "요약 본문"
    assert memory.awaited_child_reports("p1")["uncollected"] == 1
    world.dt.task_status({"kind": "delegation", "owner": PROJECT, "task_id": b})
    assert memory.awaited_child_reports("p1") == {"total": 2, "pending": 0, "uncollected": 0, "status": "pending"}
    assert memory.awaited_child_reports("no_such") is None


def test_running_child_is_not_collected(world):
    memory.create_task("p2", "user@gui", "gui", "원요청")
    tc.set_current_task_id("p2")
    child = _accept_async(world, "p2")
    assert world.dt.task_status({"kind": "delegation", "owner": PROJECT, "task_id": child})["terminal"] is False
    assert memory.awaited_child_reports("p2")["pending"] == 1
    assert memory.mark_child_collected("p2", child) is False                # 응답이 없으면 적을 것이 없다


def test_task_busy_covers_model_turn_and_surface_hold():
    import steer_inbox as S
    assert S.task_busy("t_r29") is False and S.task_busy(None) is False
    with S.turn_hold("t_r29"):
        with S.turn_hold("t_r29"):
            assert S.task_busy("t_r29")
        assert S.task_busy("t_r29")                                          # 겹친 수명의 안쪽이 끝나도 바깥이 쥐고 있다
        with S.task_scope(("system_ai",), "t_r29"):
            assert S.task_busy("t_r29")
    assert S.task_busy("t_r29") is False
    with S.task_scope(("system_ai",), "t_r29b"):
        assert S.task_busy("t_r29b") and not S.task_busy("t_r29")
    assert S.task_busy("t_r29b") is False


@pytest.fixture
def runner(monkeypatch):
    import runtime_work
    from system_ai_runner import SystemAIRunner
    monkeypatch.setattr(SystemAIRunner, "internal_messages", runtime_work.WorkMessages())
    monkeypatch.setattr(SystemAIRunner, "held_reports", [])
    inst = SystemAIRunner.__new__(SystemAIRunner)
    yield inst, SystemAIRunner
    SystemAIRunner.internal_messages.clear()


def test_runner_holds_report_while_parent_turn_is_alive_and_requeues_after(runner):
    import steer_inbox as S
    inst, cls = runner
    report = {"content": "[task:p_live] 완료.\n요약", "from_agent": "홈페이지", "task_id": None}
    other = {"content": "새 일", "from_agent": "앱", "task_id": "p_other"}
    with S.task_scope(("system_ai",), "p_live"):
        assert inst._hold_while_turn_alive(report) is True                   # 새 턴을 열지 않고 붙든다(옛: RuntimeError·유실)
        assert inst._hold_while_turn_alive(other) is False                   # 다른 작업은 그대로 처리
        inst._release_held_reports()
        assert cls.held_reports == [report] and not cls.internal_messages    # 턴이 살아 있으면 계속 붙든다
    inst._release_held_reports()
    assert cls.held_reports == [] and [m["content"] for m in cls.internal_messages] == [report["content"]]
    assert inst._hold_while_turn_alive(dict(report)) is False                # 턴이 끝났으니 전달된다


def test_runner_skips_only_reports_the_closed_parent_already_read(world, runner):
    inst, _ = runner
    memory.create_task("p3", "user@gui", "gui", "원요청")
    tc.set_current_task_id("p3")
    child = _accept_async(world, "p3")
    _child_reports(world, "p3", child)
    assert inst._nothing_awaited("p3") is False                              # 읽어 가지 않은 응답 — 보고가 새 턴으로 전달돼야 한다
    memory.complete_task("p3", "부모 답")
    assert inst._report_already_collected("p3") is False                     # 닫혔어도 읽지 않은 응답은 버리지 않는다
    memory.create_task("p4", "user@gui", "gui", "원요청")
    tc.set_current_task_id("p4")
    child = _accept_async(world, "p4")
    _child_reports(world, "p4", child)
    world.dt.task_status({"kind": "delegation", "owner": PROJECT, "task_id": child})   # 부모 턴이 wait 로 읽음
    assert inst._nothing_awaited("p4") is True
    assert inst._report_already_collected("p4") is False                     # 아직 열린 작업 — 표면이 보고를 기다린다
    memory.complete_task("p4", "부모 답")
    assert inst._report_already_collected("p4") is True                      # 닫혔고 다 읽었다 — 새 턴 없음
    memory.create_task("p5", "user@gui", "gui", "위임 없는 작업")
    assert inst._nothing_awaited("p5") is False and inst._report_already_collected("p5") is False


def test_sync_children_are_never_awaited_as_reports(world):
    memory.create_task("p6", "user@gui", "gui", "원요청")
    ctx = {"delegations": [{"child_task_id": "c_sync", "mode": "sync"}], "responses": []}
    memory.update_task_delegation("p6", json.dumps(ctx), increment_pending=True)
    memory.record_child_response("p6", {"child_task_id": "c_sync", "from_agent": "x", "response": "r"})
    assert memory.awaited_child_reports("p6") == {"total": 1, "pending": 0, "uncollected": 0, "status": "pending"}


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
