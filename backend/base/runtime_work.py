"""단일 현역의 접수와 실제 실행 수명. 소켓/취소 요청은 완료가 아니다.

워크 등록과 drain은 같은 잠금을 쓴다. 부모 자격은 서버가 발행한 난수 capability이며
agent/task/episode ID로 재구성하지 않는다. install() 이전(폰/독립 도구)은 기존 동작.
"""
import asyncio
import contextvars
import inspect
import secrets
import threading
import time
from contextlib import contextmanager
from functools import wraps

_current = contextvars.ContextVar("runtime_parent", default=None)
_registry = None
NOTICE = "재기동을 위해 새 작업 접수를 잠시 중단했습니다. 이 작업은 실행되지 않았습니다. 잠시 후 다시 요청해 주세요."


class AdmissionClosed(RuntimeError):
    pass


class WorkRegistry:
    def __init__(self, generation):
        self.generation = generation
        self.lock = threading.RLock()
        self.accepting = False
        self.phase = "STARTING"
        self.groups = {}
        self.entries = {}
        self.errors = []

    def reserve(self, label, parent=None, kind=None, bootstrap=False):
        with self.lock:
            if parent is not None and parent not in self.groups:
                raise AdmissionClosed("종료되었거나 다른 세대의 부모 실행입니다")
            if parent is None:
                if not self.accepting and not (bootstrap and self.phase == "STARTING"):
                    raise AdmissionClosed(NOTICE)
                parent = secrets.token_hex(32)
                self.groups[parent] = set()
                kind = kind or "root"
            else:
                kind = kind or "child"
            key = secrets.token_hex(16)
            self.groups[parent].add(key)
            self.entries[key] = {"id": key, "kind": kind, "label": label,
                                 "started_at": time.time(), "thread": None}
            return Lease(self, key, parent)

    def release(self, lease):
        with self.lock:
            self.entries.pop(lease.key, None)
            members = self.groups.get(lease.parent)
            if members is not None:
                members.discard(lease.key)
                if not members:
                    del self.groups[lease.parent]

    def gate(self, phase):
        with self.lock:
            self.phase = phase
            self.accepting = phase == "ACTIVE"
            return self.snapshot()

    def snapshot(self):
        with self.lock:
            owners = [dict(e) for e in self.entries.values()]
            return {"generation": self.generation, "phase": self.phase,
                    "accepting": self.accepting, "ownership": "unknown" if self.errors else "known",
                    "errors": list(self.errors),
                    "active_roots": sum(e["kind"] == "root" for e in owners),
                    "active_children": sum(e["kind"] == "child" for e in owners),
                    "pending_finalizers": sum(e["kind"] == "finalizer" for e in owners),
                    "owners": owners, "observed_at": time.time()}


class Lease:
    def __init__(self, registry, key, parent):
        self.registry, self.key, self.parent = registry, key, parent

    @contextmanager
    def activate(self):
        token = _current.set(self.parent)
        with self.registry.lock:
            entry = self.registry.entries.get(self.key)
            if entry is not None:
                entry["thread"] = threading.get_ident()
        try:
            yield self
        finally:
            _current.reset(token)

    def close(self):
        self.registry.release(self)


class NullLease:
    parent = None

    @contextmanager
    def activate(self):
        yield self

    def close(self):
        pass


def install(generation):
    global _registry
    _registry = WorkRegistry(generation)
    return _registry


def registry():
    return _registry


def parent_token():
    return _current.get() if _registry else None


def reserve(label, *, parent=None, kind=None):
    if _registry is None:
        return NullLease()
    return _registry.reserve(label, parent if parent is not None else _current.get(), kind)


@contextmanager
def scope(label, *, parent=None, kind=None):
    lease = reserve(label, parent=parent, kind=kind)
    try:
        with lease.activate():
            yield lease
    finally:
        lease.close()


@contextmanager
def service_scope():
    """상주 서비스/외부 재기동 수행자는 요청 작업의 자식 수명을 갖지 않는다."""
    token = _current.set(None)
    try:
        yield
    finally:
        _current.reset(token)


def tracked(label, *, defer=False, kind=None, bypass=None):
    """실제 본체와 finally를 감싼다. 폴러는 접수 전 보류해 다음 틱에 다시 읽는다."""
    def decorate(fn):
        if inspect.isasyncgenfunction(fn):
            raise TypeError("async generator는 transport에서 수명을 등록하세요")
        if inspect.isgeneratorfunction(fn):
            @wraps(fn)
            def gen(*a, **kw):
                with scope(label, kind=kind):
                    yield from fn(*a, **kw)
            return gen
        if inspect.iscoroutinefunction(fn):
            @wraps(fn)
            async def async_call(*a, **kw):
                with scope(label, kind=kind):
                    return await fn(*a, **kw)
            return async_call
        @wraps(fn)
        def call(*a, **kw):
            if bypass is not None and bypass(*a, **kw):
                return fn(*a, **kw)
            try:
                lease = reserve(label, kind=kind)
            except AdmissionClosed:
                if defer:
                    return None
                raise
            try:
                with lease.activate():
                    return fn(*a, **kw)
            finally:
                lease.close()
        return call
    return decorate


def bind_lease(fn, label="worker", kind=None):
    """제출 시 예약한다. 실행 전 취소/제출 실패는 bound.release()로 반환한다."""
    lease = reserve(label, kind=kind)
    @wraps(fn)
    def bound(*a, **kw):
        try:
            with lease.activate():
                return fn(*a, **kw)
        finally:
            lease.close()
    bound.release = lease.close
    return bound


def install_worker_tracking():
    """요청에서 파생된 stdlib 실행 경계. 설치는 워커 조립점에서 한 번만.

    ThreadPool의 상주 스레드가 아닌 각 제출을 센다. 취소된 Future만 미실행 예약을
    해제한다. Popen은 대기 timeout 뒤에도 실제 프로세스가 끝날 때까지 남는다.
    """
    import concurrent.futures
    import subprocess
    if getattr(threading.Thread, "_runtime_tracking", False):
        return
    threading.Thread._runtime_tracking = True
    original_start = threading.Thread.start
    original_submit = concurrent.futures.ThreadPoolExecutor.submit
    original_popen = subprocess.Popen.__init__
    original_task = asyncio.BaseEventLoop.create_task

    def submit(pool, fn, /, *a, **kw):
        if not parent_token():
            return original_submit(pool, fn, *a, **kw)
        bound = bind_lease(fn, "executor")
        try:
            # 신규 pool의 상주 worker 자체를 작업으로 세지 않는다.
            with service_scope():
                future = original_submit(pool, bound, *a, **kw)
        except BaseException:
            bound.release()
            raise
        future.add_done_callback(lambda f: bound.release() if f.cancelled() else None)
        return future

    def start(thread):
        if not parent_token():
            return original_start(thread)
        bound = bind_lease(thread.run, "thread:" + thread.name)
        thread.run = bound
        try:
            return original_start(thread)
        except BaseException:
            bound.release()
            raise

    def popen(proc, *a, **kw):
        if not parent_token():
            return original_popen(proc, *a, **kw)
        lease = reserve("process")
        try:
            original_popen(proc, *a, **kw)
        except BaseException:
            lease.close()
            raise
        with lease.registry.lock:
            lease.registry.entries[lease.key]["pid"] = proc.pid
        receipt = None
        import os
        if os.environ.get("INDIEBIZ_BASE_PATH"):
            try:
                from restart_process import tool_process_receipt
                receipt = tool_process_receipt(proc, os.environ["INDIEBIZ_BASE_PATH"], lease.registry.generation)
            except Exception as exc:
                # 등록 직후 아주 짧게 끝난 자식은 이미 완료. 살아 있는데 신원이 없으면 UNKNOWN.
                if proc.poll() is None:
                    with lease.registry.lock:
                        lease.registry.errors.append("process receipt: " + str(exc))
        def reap():
            try:
                if receipt:
                    from restart_process import wait_tool_process
                    wait_tool_process(proc, *receipt)
                else:
                    proc.wait()
            except Exception as exc:
                with lease.registry.lock:
                    lease.registry.errors.append("process observation: " + str(exc))
            finally:
                lease.close()
        watcher = threading.Thread(target=reap, daemon=True, name="runtime-process-reap")
        original_start(watcher)

    def create_task(loop, coro, **kwargs):
        if not parent_token():
            return original_task(loop, coro, **kwargs)
        lease = reserve("async-task")
        async def invoke():
            try:
                with lease.activate():
                    return await coro
            finally:
                lease.close()
        wrapped = invoke()
        try:
            task = original_task(loop, wrapped, **kwargs)
        except BaseException:
            wrapped.close()
            coro.close()
            lease.close()
            raise
        def completed(task):
            if task.cancelled():
                # 실행 전 취소된 coroutine도 닫는다. 실행 중 취소면 finally가 이미 완료.
                coro.close()
                lease.close()
        task.add_done_callback(completed)
        return task

    asyncio.BaseEventLoop.create_task = create_task
    concurrent.futures.ThreadPoolExecutor.submit = submit
    threading.Thread.start = start
    subprocess.Popen.__init__ = popen


class WorkMessages(list):
    """메모리 위임 큐도 승인 시점부터 drain 대상이다."""
    def append(self, message):
        if isinstance(message, dict) and "_runtime_lease" not in message:
            message = dict(message, _runtime_lease=reserve("delegation-queue"))
        super().append(message)

    def clear(self):
        for message in self:
            if isinstance(message, dict) and message.get("_runtime_lease"):
                message["_runtime_lease"].close()
        super().clear()


def message_stream(pop):
    while True:
        message = pop()
        if message is None:
            return
        if not isinstance(message, dict):
            continue
        lease = message.pop("_runtime_lease", None) or reserve("delegation")
        try:
            with lease.activate():
                yield message
        finally:
            lease.close()


def bind_boot(fn, label="boot", service_children=False):
    """부팅이 제출한 유한 작업도 등록한다. 상주 서비스 자체는 작업 카운터 밖이다."""
    lease = (_registry.reserve(label, parent=_current.get(), kind="finalizer", bootstrap=True)
             if _registry else NullLease())
    @wraps(fn)
    def bound(*a, **kw):
        try:
            with lease.activate():
                if service_children:
                    with service_scope():
                        return fn(*a, **kw)
                return fn(*a, **kw)
        finally:
            lease.close()
    return bound
