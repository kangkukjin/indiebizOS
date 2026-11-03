"""R1 접수 경쟁/실제 워커 수명/부모 capability. 외부 효과는 Event 어댑터."""
import asyncio
import threading
from concurrent.futures import ThreadPoolExecutor, TimeoutError

import pytest
import runtime_work as rw


@pytest.fixture
def work(monkeypatch):
    previous = rw.registry()
    reg = rw.install("test-generation")
    reg.gate("ACTIVE")
    rw.install_worker_tracking()
    yield reg
    rw._registry = previous


def count(reg):
    s = reg.snapshot()
    return s["active_roots"] + s["active_children"] + s["pending_finalizers"]


def test_admission_and_drain_are_one_boundary(work):
    barrier = threading.Barrier(3)
    accepted = []
    def enter():
        barrier.wait()
        try:
            accepted.append(work.reserve("racing"))
        except rw.AdmissionClosed:
            pass
    def drain():
        barrier.wait()
        work.gate("DRAINING")
    a, b = threading.Thread(target=enter), threading.Thread(target=drain)
    a.start(); b.start(); barrier.wait(); a.join(); b.join()
    assert count(work) == len(accepted)
    with pytest.raises(rw.AdmissionClosed):
        work.reserve("late")
    for lease in accepted:
        lease.close()
    assert count(work) == 0


def test_parent_capability_survives_root_while_child_lives(work):
    root = work.reserve("root")
    child = work.reserve("child", parent=root.parent)
    work.gate("DRAINING")
    root.close()
    continuation = work.reserve("MCP", parent=child.parent)
    child.close(); continuation.close()
    with pytest.raises(rw.AdmissionClosed):
        work.reserve("MCP", parent=root.parent)
    with pytest.raises(rw.AdmissionClosed):
        work.reserve("MCP", parent="task-guessed")


def test_timeout_does_not_release_running_tool(work):
    finish = threading.Event()
    started = threading.Event()
    def tool():
        started.set()
        finish.wait(5)
    with ThreadPoolExecutor(1) as pool:
        with rw.scope("http"):
            future = pool.submit(tool)
            assert started.wait(1)
            with pytest.raises(TimeoutError):
                future.result(timeout=0.01)
        work.gate("DRAINING")
        assert count(work) == 1
        assert not future.cancel() and count(work) == 1
        finish.set(); future.result(timeout=1)
    assert count(work) == 0


def test_queued_future_cancel_releases_only_that_reservation(work):
    finish = threading.Event()
    with ThreadPoolExecutor(1) as pool:
        with rw.scope("request"):
            running = pool.submit(finish.wait, 5)
            pending = pool.submit(lambda: None)
            assert pending.cancel()
        assert count(work) == 1
        finish.set(); running.result(timeout=1)
    assert count(work) == 0


def test_detached_thread_finally_is_counted(work):
    finish = threading.Event()
    with rw.scope("turn"):
        child = threading.Thread(target=lambda: finish.wait(5))
        child.start()
    assert count(work) == 1
    finish.set(); child.join(1)
    assert count(work) == 0


def test_async_cancel_before_first_step_and_unawaited_work(work):
    async def scenario():
        finish = asyncio.Event()
        with rw.scope("http"):
            child = asyncio.create_task(finish.wait())
            cancelled = asyncio.create_task(asyncio.sleep(10))
            cancelled.cancel()
        await asyncio.sleep(0)
        assert count(work) >= 1
        finish.set()
        await child
        await asyncio.sleep(0)
        assert count(work) == 0
    asyncio.run(scenario())


def test_queued_delegation_and_finalizer(work):
    queue = rw.WorkMessages()
    with rw.scope("parent"):
        queue.append({"content": "approved"})
        finalizer = rw.reserve("save", kind="finalizer")
    work.gate("DRAINING")
    assert count(work) == 2
    for message in rw.message_stream(lambda: queue.pop(0) if queue else None):
        assert message["content"] == "approved"
        with rw.scope("delegation-tool"):
            pass
    assert work.snapshot()["pending_finalizers"] == 1
    finalizer.close()
    assert count(work) == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


def test_transient_process_observation_retains_lease_then_recovers(work, monkeypatch):
    import runtime_work as module
    lease = work.reserve('real-process')
    calls = []
    monkeypatch.setattr(module.time, 'sleep', lambda delay: None)
    def observe():
        calls.append(1)
        assert work.snapshot()['active_roots'] == 1
        if len(calls) == 1:
            raise SystemError('temporary proc_cmdline failure')
        assert work.snapshot()['ownership'] == 'unknown'
    module._reap_until_observed(observe, work, lease)
    assert len(calls) == 2
    assert work.snapshot()['ownership'] == 'known'
    assert work.snapshot()['active_roots'] == 0


def test_recovered_process_receipt_clears_only_its_own_error(work):
    import runtime_work as module
    work.errors[:] = ['unrelated observation', 'receipt failure']
    lease = work.reserve('process')
    module._reap_until_observed(lambda: None, work, lease, 'receipt failure')
    assert work.errors == ['unrelated observation']
