"""상주 기반 시설은 대기 중 0, 실제 함수·저장·타임아웃 뒤 실행은 완료까지 소유."""
import boot_paths  # noqa: F401 — 직접 실행도 같은 층 경로를 사용한다.
import asyncio
import importlib.util
import threading
from pathlib import Path

import anyio
import pytest
import runtime_work as rw

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def work():
    previous = rw.registry()
    reg = rw.install("service-test")
    reg.gate("ACTIVE")
    rw.install_worker_tracking()
    yield reg
    rw._registry = previous


def count(reg):
    s = reg.snapshot()
    return sum(s[k] for k in ("active_roots", "active_children", "pending_finalizers"))


@pytest.fixture
def browser():
    path = ROOT / "data/packages/installed/tools/browser-action/browser_session.py"
    spec = importlib.util.spec_from_file_location("runtime_test_browser", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_anyio_idle_pool_is_not_work_and_reused_call_keeps_parent(work):
    async def run():
        workers = []
        for _ in range(2):
            with rw.scope("request") as request:
                parent, worker = await anyio.to_thread.run_sync(
                    lambda: (rw.parent_token(), threading.get_ident()))
                assert parent == request.parent
                workers.append(worker)
            assert count(work) == 0
        assert workers[0] == workers[1]
        work.gate("DRAINING")
        with pytest.raises(rw.AdmissionClosed):
            with rw.scope("new-request"):
                pass
    anyio.run(run)


def test_anyio_abandoned_running_function_survives_cancellation(work):
    started, finish, done = (threading.Event() for _ in range(3))
    def function():
        started.set()
        try:
            assert finish.wait(5)
        finally:
            done.set()
    async def run():
        with rw.scope("request"):
            task = asyncio.create_task(anyio.to_thread.run_sync(function, abandon_on_cancel=True))
            while not started.is_set():
                await asyncio.sleep(0)
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
        assert [e["label"] for e in work.snapshot()["owners"]] == ["anyio-worker"]
        work.gate("DRAINING")
        finish.set()
        for _ in range(1000):
            if count(work) == 0:
                break
            await asyncio.sleep(0.001)
        assert done.is_set() and count(work) == 0
    try:
        anyio.run(run)
    finally:
        finish.set()


def test_anyio_cancel_before_capacity_does_not_leak_or_execute(work):
    called = []
    async def run():
        limiter = anyio.CapacityLimiter(1)
        async with limiter:
            with rw.scope("request"):
                task = asyncio.create_task(anyio.to_thread.run_sync(
                    lambda: called.append(True), limiter=limiter))
                await asyncio.sleep(0)
                await asyncio.sleep(0)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            assert count(work) == 0
        await asyncio.sleep(0)
        assert called == []
    anyio.run(run)


def test_progress_monitor_is_service_but_same_named_thread_is_work(work):
    from tqdm._monitor import TMonitor
    class Progress:
        _instances = set()
        get_lock = threading.RLock
    with rw.scope("model-load"):
        monitor = TMonitor(Progress, 60)
    try:
        assert monitor.is_alive() and count(work) == 0
    finally:
        monitor.exit()
    finish = threading.Event()
    with rw.scope("actual-work"):
        thread = threading.Thread(target=finish.wait, name="tqdm_monitor", daemon=True)
        thread.start()
    try:
        assert count(work) == 1  # 이름만 보고 면제하지 않는다.
    finally:
        finish.set()
        thread.join(2)
    assert count(work) == 0


def test_tool_loop_stays_idle_but_timed_out_coroutine_remains_owned(work, monkeypatch):
    import system_tools as tools
    monkeypatch.setattr(tools, "_async_loop", None)
    monkeypatch.setattr(tools, "_async_thread", None)
    started, done = threading.Event(), threading.Event()
    async def slow():
        started.set()
        await asyncio.sleep(0.15)
        done.set()
        return 1
    try:
        with rw.scope("tool-request"):
            with pytest.raises(TimeoutError):
                tools._run_coroutine(slow(), timeout=0.02)
        assert started.is_set() and count(work) == 1
        assert all(e["label"] != "thread:tool-async-loop" for e in work.snapshot()["owners"])
        assert done.wait(2)
        # 결과 완료 콜백까지 loop를 한 번 통과시킨다.
        tools._run_coroutine(asyncio.sleep(0))
        assert count(work) == 0 and tools._async_thread.is_alive()
    finally:
        if tools._async_loop:
            tools._async_loop.call_soon_threadsafe(tools._async_loop.stop)
            tools._async_thread.join(2)
            tools._async_loop.close()


@pytest.mark.parametrize("cancel", [False, True])
def test_cross_loop_submission_owns_queue_before_loop_starts(work, cancel):
    loop = asyncio.new_event_loop()
    calls = []
    async def operation():
        calls.append(rw.parent_token())
        return 42
    with rw.scope("request") as root:
        future = rw.submit_coroutine_threadsafe(operation(), loop)
    assert count(work) == 1
    work.gate("DRAINING")
    if cancel:
        assert future.cancel()
        assert count(work) == 0
    try:
        # 루프가 늦게 시작돼도 종료된 요청의 자격을 잃지 않는다.
        loop.run_until_complete(asyncio.sleep(0))
        if cancel:
            assert calls == []
        else:
            assert future.result(timeout=1) == 42
            assert calls == [root.parent]
        assert count(work) == 0
    finally:
        loop.close()


def test_browser_timer_wait_is_free_but_storage_finalizer_is_owned(work, browser):
    async def run():
        session = browser.BrowserSession()
        session._timeout_seconds = 0.01
        entered, finish = asyncio.Event(), asyncio.Event()
        async def save():
            entered.set()
            await finish.wait()
        session.save_storage_state = save
        with rw.scope("browser-call"):
            session._reset_timer()
        cleanup = session._cleanup_task
        assert count(work) == 0
        await asyncio.wait_for(entered.wait(), 2)
        assert work.snapshot()["pending_finalizers"] == 1
        work.gate("DRAINING")
        finish.set()
        await cleanup
        assert not cleanup.cancelled() and count(work) == 0
    asyncio.run(run())


def test_browser_idle_timer_cannot_start_storage_during_drain(work, browser):
    async def run():
        session = browser.BrowserSession()
        session._timeout_seconds = 0.01
        calls = []
        async def save():
            calls.append(True)
        session.save_storage_state = save
        with rw.scope("browser-call"):
            session._reset_timer()
        work.gate("DRAINING")
        await session._cleanup_task
        assert calls == [] and count(work) == 0
    asyncio.run(run())


def test_real_browser_transport_idle_and_process_receipt(work, browser, monkeypatch, tmp_path):
    from runtime_utils import setup_playwright_browsers_path
    setup_playwright_browsers_path()
    monkeypatch.setenv("INDIEBIZ_BASE_PATH", str(tmp_path))
    monkeypatch.setattr(browser, "get_cookies_dir", lambda: tmp_path)
    async def run():
        session = browser.BrowserSession()
        try:
            with rw.scope("browser-call"):
                page = await session.ensure_browser()
                assert await page.evaluate("6 * 7") == 42
            assert count(work) == 0
            assert list((tmp_path / "data/restart_control/processes").glob("service-test-*.json"))
            with rw.scope("browser-call-2"):
                assert await page.evaluate("1 + 1") == 2
            assert count(work) == 0
        finally:
            with rw.scope("browser-close"):
                await session.close()
        assert count(work) == 0
    asyncio.run(run())


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
