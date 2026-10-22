"""Bounded, context-inherited admission; executors remain owned by their caller.

A caller executes one branch itself and borrows only immediately available slots.
Waiting parents release admission, so nesting never waits while owning capacity.
Queued roots take precedence over speculative fan-out. A lease lasts until the
actual callable exits, including cancellation/timeout cleanup.
"""
from collections import deque
from concurrent.futures import FIRST_COMPLETED, Future, wait
from contextlib import contextmanager
from contextvars import ContextVar
from threading import Condition

from execution_workers import create_executor


class Capacity:
    def __init__(self, limit=8):
        if type(limit) is not int or limit < 1:
            raise ValueError("capacity must be a positive integer")
        self.limit = limit
        self.active = 0
        self.peak = 0
        self.condition = Condition()
        self.waiters = deque()

    def acquire(self, root, *, blocking=True):
        with self.condition:
            if not blocking:
                if self.waiters or self.active >= self.limit or root.active >= root.limit:
                    return False
            else:
                ticket = object()
                self.waiters.append(ticket)
                try:
                    self.condition.wait_for(lambda: self.waiters[0] is ticket
                                            and self.active < self.limit
                                            and root.active < root.limit)
                finally:
                    self.waiters.remove(ticket)
                    self.condition.notify_all()
            self.active += 1
            root.active += 1
            self.peak = max(self.peak, self.active)
            root.peak = max(root.peak, root.active)
            return True

    def release(self, root):
        with self.condition:
            self.active -= 1
            root.active -= 1
            self.condition.notify_all()


class Root:
    def __init__(self, capacity, limit):
        self.capacity, self.limit = capacity, limit
        self.active = self.peak = 0


BODY = Capacity()
_root = ContextVar("execution_capacity_root", default=None)


@contextmanager
def scope(*, capacity=None, limit=8):
    """Join the inherited root, or admit a new root (also useful in tests)."""
    if _root.get() is not None:
        yield _root.get()
        return
    root = Root(capacity or BODY, max(1, limit))
    root.capacity.acquire(root)
    token = _root.set(root)
    try:
        yield root
    finally:
        _root.reset(token)
        root.capacity.release(root)


@contextmanager
def suspended():
    """Release this execution's slot only while synchronously waiting."""
    root = _root.get()
    if root is None:
        yield
        return
    root.capacity.release(root)
    try:
        yield
    finally:
        root.capacity.acquire(root)


@contextmanager
def _executor(role, workers):
    pool = create_executor(role, max_workers=max(1, workers - 1))
    try:
        yield pool
    finally:
        with suspended():
            pool.shutdown(wait=True)


def fanout(count, workers, run, accept, *, role="fanout"):
    """accept(index, future) returns False to stop new starts; always drain starts.

Exceptions from accept also drain the pool before escaping. No result is retried.
Only extra threads borrow admission; the inline branch uses its caller's slot.
"""
    with scope() as root:
        def borrowed(index):
            try:
                return run(index)
            finally:
                root.capacity.release(root)

        with _executor(role, workers) as pool:
            pending, next_i, stopped = {}, 0, False
            while pending or (not stopped and next_i < count):
                # Observe failures before admitting more work.
                for future in list(pending):
                    if future.done():
                        if not accept(pending.pop(future), future):
                            stopped = True
                while (not stopped and next_i + 1 < count
                       and len(pending) < workers - 1
                       and root.capacity.acquire(root, blocking=False)):
                    try:
                        pending[pool.submit(borrowed, next_i)] = next_i
                    except BaseException:
                        root.capacity.release(root)
                        raise
                    next_i += 1
                if not stopped and next_i < count:
                    future = Future()
                    try:
                        future.set_result(run(next_i))
                    except BaseException as exc:
                        future.set_exception(exc)
                    if not accept(next_i, future):
                        stopped = True
                    next_i += 1
                elif pending:
                    with suspended():
                        wait(pending, return_when=FIRST_COMPLETED)
