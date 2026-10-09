"""Commit deferred local observations only after a complete successful program.

This is not a transaction over remote effects. Failed delivery remains retryable;
remote consumers still need their own idempotency keys for exactly-once delivery.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from threading import RLock

_current = ContextVar("execution_commit", default=None)
_observed_at = ContextVar("observation_timestamp", default=None)


class CommitScope:
    def __init__(self):
        self.lock = RLock()
        self.state = {}
        self.actions = {}
        self.committed = 0
        self.commit_failed = False

    def report(self, result, *, owner=True):
        total = self.committed + len(self.actions)
        if total:
            result["state_commit"] = {
                "status": ("failed" if self.commit_failed else "committed" if self.committed == total else "pending" if not owner
                           else "partial" if self.committed else "not_committed"),
                "actions": total, "committed": self.committed,
                "reason": ("commit_failed" if self.commit_failed else "" if self.committed == total else "outer_program" if not owner
                           else "partial_source" if not result.get("source_complete", True)
                           else "program_failed"),
            }

    def commit(self):
        with self.lock:
            self.commit_failed = False
            for key, action in list(self.actions.items()):
                try:
                    action()
                except Exception:
                    # 한 action 내부에서도 앞 쓰기가 반영됐을 수 있다. 미확정과 구별한다.
                    self.commit_failed = True
                    raise
                self.committed += 1
                del self.actions[key]


def current_scope():
    return _current.get()


@contextmanager
def bind_scope(scope, observed_at=None):
    token = _current.set(scope)
    clock_token = _observed_at.set(observed_at)
    try:
        yield scope
    finally:
        _current.reset(token)
        _observed_at.reset(clock_token)


def observation_timestamp():
    return _observed_at.get()


def committed_program(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        inherited = current_scope()
        scope = inherited or CommitScope()
        with bind_scope(scope):
            result = fn(*args, **kwargs)
            if inherited is None and result.get("success") and result.get("source_complete", True):
                scope.commit()
            scope.report(result, owner=inherited is None)
            return result
    return wrapped
