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

    def commit(self):
        with self.lock:
            for action in self.actions.values():
                action()
            self.actions.clear()


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
            return result
    return wrapped
