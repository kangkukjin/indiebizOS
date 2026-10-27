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
_obligations = ContextVar("observation_obligations", default=None)


class ObservationActions(dict):
    """Keep existing observation producers on the same scope-owned mapping."""
    def __init__(self, scope):
        super().__init__()
        self.scope = scope

    def __setitem__(self, key, action):
        with self.scope.lock:
            current = _obligations.get()
            if current:
                self.scope.obligations[key] = frozenset(current)
                self.scope.origins[key] = dict(current)
            else:
                self.scope.obligations.pop(key, None)
                self.scope.origins.pop(key, None)
            super().__setitem__(key, action)


class CommitScope:
    def __init__(self):
        self.lock = RLock()
        self.state = {}
        self.obligations = {}
        self.origins = {}
        self.certified = set()
        self.certified_evidence = {}
        self.actions = ObservationActions(self)
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

    def stage(self, key, action, *, obligations):
        """Opt in a local observation to named runtime completion duties."""
        if not obligations or any(not isinstance(v, str) for v in obligations):
            raise ValueError('관측 확정에는 의무 id가 필요합니다.')
        with self.lock:
            self.actions[key] = action
            self.obligations[key] = frozenset(obligations)

    def commit(self, *, satisfied=None, evidence=None, allow_unscoped=False):
        with self.lock:
            self.commit_failed = False
            global_commit = satisfied is None
            if global_commit:
                satisfied, evidence = self.certified, self.certified_evidence
            for key, action in list(self.actions.items()):
                if key in self.obligations:
                    if not self.obligations[key] <= satisfied:
                        continue
                elif not (global_commit or allow_unscoped):
                    continue
                if satisfied is not None and any(origin not in (evidence or {}).get(name, ())
                                                 for name, origin in self.origins.get(key, {}).items()):
                    continue
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
def bind_scope(scope, observed_at=None, *, obligations=None):
    token = _current.set(scope)
    clock_token = _observed_at.set(observed_at)
    obligation_token = _obligations.set(obligations)
    try:
        yield scope
    finally:
        _current.reset(token)
        _observed_at.reset(clock_token)
        _obligations.reset(obligation_token)


def observation_timestamp():
    return _observed_at.get()


def committed_program(fn):
    @wraps(fn)
    def wrapped(*args, **kwargs):
        inherited = current_scope()
        scope = inherited or CommitScope()
        with bind_scope(scope):
            result = fn(*args, **kwargs)
            if inherited is None and result.get("success"):
                if result.get("source_complete", True):
                    scope.commit()
                elif scope.certified:
                    scope.commit(satisfied=scope.certified, evidence=scope.certified_evidence)
            scope.report(result, owner=inherited is None)
            return result
    return wrapped
