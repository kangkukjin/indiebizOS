"""Shared observed usage and model admission for a task tree.

Reservations are estimates, not vendor billing measurements. Native CLI internal
requests are outside the API round scheduler; observed usage still joins the tree.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import threading
import time

from execution_capacity import Capacity, Root

MODELS = Capacity(8)
_current = ContextVar('task_tree_budget', default=None)


class Tree:
    def __init__(self, limit=None, deadline=None, used=0, record=None):
        self.limit, self.deadline, self.used = limit, deadline, used
        self.reserved = 0
        self.record = record
        self.lock = threading.RLock()
        self.models = Root(MODELS, 8)

    def reason(self):
        with self.lock:
            if self.deadline and time.time() >= self.deadline:
                return {'kind': 'task_deadline', 'reason': '부모·자식 전체 작업 시간 한도에 도달했습니다'}
            if self.limit and self.used >= self.limit:
                return {'kind': 'task_budget', 'reason': '부모·자식 전체 관측 토큰 한도에 도달했습니다'}

    def reserve(self, estimate):
        with self.lock:
            if self.reason() or self.limit and self.used + self.reserved + estimate > self.limit:
                raise RuntimeError('위임 트리의 남은 모델 예산이 부족합니다')
            self.reserved += estimate

    def observe(self, amount):
        with self.lock:
            self.used += amount
            if self.record:
                self.record(amount)


def current():
    tree = _current.get()
    if tree is None:
        # A root can acquire its tree during a tool call on another thread; the
        # inherited turn ledger is a shared object, unlike ContextVar assignment.
        from providers.base import _turn_token_ledger
        tree = (_turn_token_ledger.get() or {}).get('tree')
    return tree


@contextmanager
def scope(tree):
    token = _current.set(tree)
    try:
        yield
    finally:
        _current.reset(token)


def start_round(call):
    finish_round(call)
    if call.get('_native_tools'):
        return
    tree = current()
    root = tree.models if tree else Root(MODELS, 8)
    # No tool or parent execution slot is held during this model admission.
    root.capacity.acquire(root)
    estimate = max(1, call.get('_token_estimate', 1))
    try:
        if tree:
            tree.reserve(estimate)
    except BaseException:
        root.capacity.release(root)
        raise
    call['_model_lease'] = root, tree, estimate


def finish_round(call):
    lease = call.pop('_model_lease', None) if call else None
    if lease:
        root, tree, estimate = lease
        if tree:
            with tree.lock:
                tree.reserved -= estimate
        root.capacity.release(root)


def observe(amount):
    tree = current()
    if tree:
        tree.observe(amount)
