"""병렬 가지의 컨텍스트 승계 회귀 — 리허설 표식이 스레드를 건넌다 (2026-08-23)

재현한 결함(실측):
  `origin: "training"` 으로 실행해도 **병렬 가지만** 건강 원장에 `source='usage'` 로 쌓였다.
      [sense:stock]{op:"quote", ticker:"ZZZZINVALID"} & [sense:weather]{city:"수원"}
        → usage / usage      ← 누수
      [sense:stock]{op:"quote", ticker:"ZZZZINVALID"}          (단일)  → training ✓
      … ?? …  ·  [table:each]{…}  ·  [try]{…}                          → training ✓
  훈련 창 실측: 44행이 usage 로 기록(그중 실패 5건). E28-3('리허설은 삶이 아니다')이
  막으려던 사고가 병렬 통로로만 계속 샜다 — E28-3 주석 자체가 "actor_context 가
  each·폴백·병렬 가지까지 전파한다" 고 적어 뒀는데 **병렬은 사실이 아니었다.**

원인(단일 지점):
  `workflow_parallel._execute_parallel` 이 자식 스레드로 넘길 컨텍스트를 **손으로 5칸만
  열거**했다(task_id·agent_id·agent_name·project_id·allowed_nodes). 뒤에 추가된
  `task_origin`(= `in_rehearsal()` 이 읽는 칸)이 목록에 없었다. `threading.local` 은
  스레드를 안 건너므로 병렬 가지에서만 표식이 증발했다.

처방:
  호출부마다 플래그를 나르는 땜질이 아니라 **경계 한 지점**에서 컨텍스트를 통째 승계
  (`thread_context.snapshot()/restore()`). 같은 저장소의 다른 스레드 경계 둘
  (`ibl_engine._run_router_safely`, `ibl_routing` 워커)이 이미 쓰던 관용에 맞춘 것이다.
  열거 목록은 반드시 뒤처지므로, 통째 승계라야 다음 칸이 생겨도 자동으로 건너간다.

실행: .venv/bin/python -m pytest backend/test_parallel_context_inherit.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import boot_paths  # noqa: F401


import pytest


@pytest.fixture(autouse=True)
def restore_parent_context():
    import thread_context
    snap = thread_context.snapshot()
    try:
        yield
    finally:
        thread_context.restore(snap)


def _branches():
    return [{"node": "sense", "action": "probe_a"}, {"node": "sense", "action": "probe_b"}]


def _run_and_capture(monkeypatch):
    """병렬 가지 안에서 본 (in_rehearsal, task_origin, project_id) 를 걷어 온다."""
    import ibl_engine
    import thread_context
    import workflow_parallel as wp

    seen = []

    def _fake_execute(tool_input, project_path=None):
        seen.append({
            "action": tool_input.get("action"),
            "in_rehearsal": thread_context.in_rehearsal(),
            "origin": thread_context.get_task_origin(),
            "project_id": thread_context.get_current_project_id(),
        })
        return {"items": [{"x": 1}]}

    monkeypatch.setattr(ibl_engine, "execute_ibl", _fake_execute)
    wp._execute_parallel(_branches(), None, "")
    return seen


def test_R1_리허설_표식이_병렬_가지로_건너간다(monkeypatch):
    """이 시험이 이번 수리의 본체다 — 옛 코드(5칸 열거)에서는 실패한다."""
    import thread_context
    with thread_context.actor_context(origin="training"):
        assert thread_context.in_rehearsal(), "부모 스레드부터 리허설이어야 시험이 성립한다"
        seen = _run_and_capture(monkeypatch)
    assert len(seen) == 2, f"두 가지가 다 돌아야 한다: {seen}"
    for row in seen:
        assert row["in_rehearsal"] is True, f"병렬 가지에서 리허설 표식이 사라졌다: {row}"
        assert row["origin"] == "training"


def test_R2_실사용은_리허설로_물들지_않는다(monkeypatch):
    """반대 방향 — 격리가 과하게 걸려 실사용까지 훈련으로 찍히면 안 된다."""
    import thread_context
    thread_context.clear_all_context()
    seen = _run_and_capture(monkeypatch)
    assert len(seen) == 2
    for row in seen:
        assert row["in_rehearsal"] is False, f"실사용이 리허설로 찍혔다: {row}"


def test_R3_옛_5칸도_여전히_건너간다(monkeypatch):
    """통째 승계로 바꾸면서 원래 나르던 칸을 떨어뜨리지 않았는지 — 회귀 방지."""
    import thread_context
    thread_context.clear_all_context()
    thread_context.set_current_project_id("부동산")
    seen = _run_and_capture(monkeypatch)
    for row in seen:
        assert row["project_id"] == "부동산", f"기존에 나르던 칸이 유실됐다: {row}"


@pytest.mark.parametrize("boundary", ["parallel", "offload", "timeout", "tool-thread"])
def test_R4_경계는_열거가_아니라_통째_승계여야_한다(monkeypatch, boundary):
    """새 thread-local 칸과 새 ContextVar도 소비자 수정 없이 건너가야 한다."""
    import asyncio
    import contextvars
    import thread_context as tc
    import ibl_engine
    from ibl_routing import _run_sync_with_timeout
    from workflow_parallel import _execute_parallel
    from execution_workers import create_executor

    marker = contextvars.ContextVar("future_worker_marker", default=None)
    marker.set("parent-ledger")
    tc.restore({**tc.snapshot(), "future_task_field": "parent-task"})

    def observe(*args, **kwargs):
        return {"items": [{"task": tc.snapshot().get("future_task_field"),
                            "ledger": marker.get()}]}

    expected = observe()
    if boundary == "parallel":
        monkeypatch.setattr(ibl_engine, "execute_ibl", observe)
        result = _execute_parallel(_branches(), None, "")
        assert len(result) == 2
        assert all(row["items"] == expected["items"] for row in result)
    elif boundary == "tool-thread":
        import system_tools
        monkeypatch.setattr(system_tools, "_execute_tool_inner", observe)
        assert system_tools._execute_tool_with_cancel("probe", {}, "", "test", lambda: False) == expected
    elif boundary == "timeout":
        assert _run_sync_with_timeout(observe, (), 2, "probe") == expected
    else:
        with create_executor("test-offload", max_workers=1) as pool:
            monkeypatch.setattr(ibl_engine, "_offload_pool", pool)

            async def on_loop():
                return ibl_engine._run_router_safely(observe)

            assert asyncio.run(on_loop()) == expected


def test_R5_예외_뒤에도_워커_문맥을_복원한다():
    """생성자와 무관한 경계 함수도 worker의 이전 상태를 복원해야 한다."""
    import contextvars
    import thread_context as tc
    from concurrent.futures import ThreadPoolExecutor
    from execution_workers import bind_context

    marker = contextvars.ContextVar("worker_restore_marker", default="empty")
    marker.set("parent")
    tc.restore({**tc.snapshot(), "future_task_field": "parent"})

    def fail():
        assert marker.get() == "parent"
        assert tc.snapshot()["future_task_field"] == "parent"
        marker.set("leaked")
        tc.restore({"future_task_field": "leaked", "new_worker_field": True})
        raise ValueError("worker failure")

    with ThreadPoolExecutor(max_workers=1) as pool:
        pool.submit(tc.restore, {"future_task_field": "worker-before"}).result()
        with pytest.raises(ValueError, match="worker failure"):
            pool.submit(bind_context(fail)).result()
        state = pool.submit(tc.snapshot).result()
        assert state["future_task_field"] == "worker-before"
        assert "new_worker_field" not in state
        assert pool.submit(marker.get).result() == "empty"
    assert tc.snapshot()["future_task_field"] == "parent"
    assert marker.get() == "parent"


def test_pool_captures_each_submission_and_separates_nested_pools():
    import contextvars
    import threading
    import thread_context as tc
    from execution_workers import create_executor

    marker = contextvars.ContextVar("submission_marker", default="empty")
    release = threading.Event()

    def observe():
        return tc.get_current_task_id(), marker.get()

    with create_executor("parent", max_workers=1) as pool:
        blocked = pool.submit(release.wait, 3)
        try:
            tc.set_current_task_id("task-a")
            marker.set("ledger-a")
            a = pool.submit(observe)
            tc.set_current_task_id("task-b")
            marker.set("ledger-b")
            b = pool.submit(observe)
        finally:
            release.set()
        blocked.result(timeout=2)
        assert a.result(timeout=2) == ("task-a", "ledger-a")
        assert b.result(timeout=2) == ("task-b", "ledger-b")

        def nested():
            with create_executor("child", max_workers=1) as child:
                assert child is not pool
                return child.submit(observe).result(timeout=2)

        assert pool.submit(nested).result(timeout=3) == ("task-b", "ledger-b")


if __name__ == "__main__":                      # 러너는 하나 — pytest (2026-08-23)
    import sys as _sys
    try:
        import pytest as _pytest
    except ImportError:
        raise SystemExit("pytest 가 없습니다 — .venv/bin/python -m pytest 로 실행하세요")
    raise SystemExit(_pytest.main([__file__] + _sys.argv[1:]))
