"""현재 실행의 신원과 MCP 재진입 문맥. 종료되면 폐기하며 작업 내용은 저장하지 않는다."""
import contextvars
import threading
from dataclasses import dataclass, field

_current = contextvars.ContextVar("execution_turn", default=None)
_sessions = {}
_lock = threading.RLock()


@dataclass
class Binding:
    runner: object
    agent: str
    task: str
    aliases: set = field(default_factory=set)
    context: dict = field(default_factory=lambda: __import__("thread_context").snapshot())
    conversation: object = field(default_factory=lambda: __import__("conversation_sessions").current())


def current():
    return _current.get()


def enter(runner, enabled=True):
    from thread_context import get_current_agent_id, get_current_task_id
    config = getattr(runner, "config", {}) or {}
    agent = get_current_agent_id() or config.get("id") or getattr(runner, "agent_id", None)
    task = get_current_task_id()
    b = Binding(runner, str(agent), str(task)) if enabled and agent and task else None
    if b:
        provider = getattr(getattr(runner, "ai", None), "_provider", None)
        b.aliases = {b.agent, str(getattr(provider, "agent_id", "") or "")} - {""}
        with _lock:
            if b.task in _sessions:
                raise ValueError("이미 실행 중인 task_id입니다")
            _sessions[b.task] = b
    return _current.set(b)


def leave(token):
    b = current()
    if b:
        with _lock:
            if _sessions.get(b.task) is b:
                del _sessions[b.task]
    _current.reset(token)


def resolve_session(agent, task=None):
    with _lock:
        hits = [b for b in _sessions.values() if agent in b.aliases and task == b.task]
    if len(hits) != 1:
        raise ValueError("활성 실행 신원이 없거나 모호합니다. agent_id/task_id를 확인하세요")
    return hits[0]
