"""모델 호출의 부모·역할·목적. 같은 응답의 관측과 청구는 별개로 기록한다."""
import contextvars
import inspect
import time
import threading
import uuid
from contextlib import contextmanager
from functools import wraps

_call = contextvars.ContextVar("model_call", default=None)
_registry = {}
_lock = threading.RLock()
_purpose = contextvars.ContextVar("model_call_purpose", default="")


def observe_usage(usage, *, snapshot=False, response_id=None):
    value = _call.get()
    if value and (snapshot or not value.get("_snapshot_seen")):
        if usage.get("input") or not value.get("_last_usage"):
            value["_last_usage"] = dict(usage)
        value["_snapshot_seen"] = snapshot
        if snapshot and response_id:
            row = value.setdefault("_responses", {}).setdefault(response_id, {})
            for key, count in usage.items():
                if isinstance(count, (int, float)):
                    row[key] = max(row.get(key, 0), count)


@contextmanager
def adopt_call_context(agent, task):
    from providers.base import _turn_token_ledger
    ledger = _turn_token_ledger.get() or {}
    with _lock:
        stack = _registry.get((agent, task), [])
        if not stack and agent in ledger.get("scope_aliases", []):
            stack = _registry.get((ledger.get("scope_owner"), task), [])
        value = stack[-1] if stack else None
    token = _call.set(value)
    try:
        yield
    finally:
        _call.reset(token)


def mark_partial():
    value = _call.get()
    if value is not None:
        value["usage_partial"] = True


def set_purpose(value):
    return _purpose.set(value)


def reset_purpose(token):
    _purpose.reset(token)


def fields(*, next_round=False):
    value = _call.get()
    if not value:
        return {}
    if next_round:
        value["round_index"] += 1
    return {k: v for k, v in value.items() if not k.startswith("_")}


@contextmanager
def call_scope(provider):
    from providers.base import turn_limit_reason
    stop = turn_limit_reason()
    if stop:
        from episode_logger import record_trajectory_event
        record_trajectory_event("model.hard_limit", stop)
        raise RuntimeError(stop["reason"])
    parent = _call.get()
    if parent and parent.get("_provider") == id(provider):
        yield  # process_message가 자신의 stream을 호출하는 어댑터는 한 호출이다.
        return
    from episode_logger import _current_role, record_trajectory_event
    role = _current_role.get("") or getattr(provider, "agent_role", "execution") or "execution"
    value = {"call_id": uuid.uuid4().hex, "parent_call_id": (parent or {}).get("call_id"),
             "role": role, "phase": _purpose.get() or ("execute" if role == "execution" else role),
             "provider": type(provider).__name__.removesuffix("Provider"),
             "model": getattr(provider, "model", ""), "round_index": 0,
             "_provider": id(provider)}
    from thread_context import get_current_agent_id, get_current_task_id
    key = (get_current_agent_id(), get_current_task_id())
    with _lock:
        if all(key):
            _registry.setdefault(key, []).append(value)
    token = _call.set(value)
    started = time.monotonic()
    requests_before = provider.metrics.total_requests
    record_trajectory_event("model.call_started", fields())
    try:
        yield
    finally:
        snapshots = value.get("_responses", {})
        if snapshots and provider.metrics.total_requests == requests_before:
            usage = {k: sum(row.get(k, 0) for row in snapshots.values()) for k in ("input", "output", "cache_read", "cache_create", "reasoning")}
            value["usage_partial"] = True
            provider.metrics.record_usage((time.monotonic() - started) * 1000, {
                "input_tokens": max(0, usage["input"] - usage["cache_read"] - usage["cache_create"]),
                "output_tokens": usage["output"], "cache_read_input_tokens": usage["cache_read"],
                "cache_creation_input_tokens": usage["cache_create"],
                "output_tokens_details": {"reasoning_tokens": usage["reasoning"]}})
        record_trajectory_event("model.call_finished", {**fields(), "elapsed_ms": round((time.monotonic() - started) * 1000),
                                "accounting": "boundary_only"})
        if value.get("_last_usage"):
            provider._last_prompt_usage = value["_last_usage"]
        with _lock:
            if all(key):
                stack = _registry.get(key, [])
                stack[:] = [entry for entry in stack if entry is not value]
                if not stack:
                    _registry.pop(key, None)
        _call.reset(token)


def trace_provider_method(method):
    if inspect.isgeneratorfunction(method):
        @wraps(method)
        def stream(self, *args, **kwargs):
            from providers.base import turn_limit_reason
            if "cancel_check" in inspect.signature(method).parameters:
                bound = inspect.signature(method).bind_partial(self, *args, **kwargs)
                previous_check = bound.arguments.get("cancel_check")
                def cancelled():
                    stop = turn_limit_reason()
                    if stop:
                        from episode_logger import record_trajectory_event
                        if not getattr(cancelled, "recorded", False):
                            record_trajectory_event("model.hard_limit", {**fields(), **stop})
                            cancelled.recorded = True
                        return True
                    return bool(previous_check and previous_check())
                bound.arguments["cancel_check"] = cancelled
                args, kwargs = bound.args[1:], bound.kwargs
            with call_scope(self):
                yield from method(self, *args, **kwargs)
        return stream
    @wraps(method)
    def call(self, *args, **kwargs):
        with call_scope(self):
            return method(self, *args, **kwargs)
    return call


def count_execution_rounds(rows):
    """새 원장은 호출 내 사건 번호, 옛 원장은 라운드 리셋별 최댓값을 합산한다."""
    observed, legacy_total, previous = set(), 0, 0
    for row in rows:
        if row.get("event") != "round" or (row.get("role") or "execution") != "execution":
            continue
        n = int(row.get("round") or 0)
        if row.get("call_id") and row.get("round_index"):
            observed.add((row["call_id"], row["round_index"]))
        else:
            if n <= previous:
                legacy_total += previous
                previous = 0
            previous = n
    return len(observed) + legacy_total + previous
