"""Provider-neutral completion boundary: waiting is code, never a model turn.

Only trusted Python handles enter this protocol. A tool's JSON containing a
business status such as 'running' is data, not authority to start polling.
"""
from concurrent.futures import Future
from dataclasses import dataclass
import time
from typing import Any, Callable

from common.spill import TICKET_MAX_WAIT_S


@dataclass(frozen=True)
class CompletionState:
    done: bool
    value: Any = None
    progress: Any = None


@dataclass(frozen=True)
class DeferredToolResult:
    task_id: str
    poll: Callable[[float], CompletionState]


class CompletionWaitError(RuntimeError):
    def __init__(self, task_id, reason):
        self.result = {
            'success': False, 'completion_wait': reason, 'task_id': task_id,
            'execution_status': 'unconfirmed',
            'error': f'작업 {task_id} 결과 대기 {reason}. 실행 종료는 확인되지 않았습니다. 같은 작업을 회수하고 다시 제출하지 마세요.',
        }
        super().__init__(self.result['error'])


def await_completion(value, *, cancel_check=None, timeout=TICKET_MAX_WAIT_S,
                     notify=None, clock=time.monotonic, pause=time.sleep):
    """Keep the result boundary closed until completion, cancellation or deadline.

    poll may wait at most its supplied interval. It retrieves the same task;
    submission/retry is deliberately absent from this interface. Failed *jobs*
    are terminal results too. A timeout/cancel only ends this wait, not the job.
    """
    if isinstance(value, Future):
        future = value
        def poll(seconds):
            from concurrent.futures import wait
            done, _ = wait([future], timeout=seconds)
            return CompletionState(bool(done), future.result() if done else None)
        value = DeferredToolResult('future-' + str(id(future)), poll)
    if not isinstance(value, DeferredToolResult):
        return value
    task = value
    started = clock()
    emit = notify or (lambda event: None)
    emit({'state': 'waiting', 'task_id': task.task_id})
    previous = None
    while True:
        if cancel_check and cancel_check():
            emit({'state': 'cancelled', 'task_id': task.task_id})
            raise CompletionWaitError(task.task_id, 'cancelled')
        remaining = timeout - (clock() - started)
        if remaining <= 0:
            emit({'state': 'deadline', 'task_id': task.task_id})
            raise CompletionWaitError(task.task_id, 'deadline')
        before = clock()
        state = task.poll(min(1.0, remaining))
        if not isinstance(state, CompletionState):
            raise TypeError('completion poll must return CompletionState')
        if state.done:
            emit({'state': 'finished', 'task_id': task.task_id,
                  'elapsed_s': round(clock() - started, 3)})
            return state.value
        # A disconnected transport may return instantly. Back off in code.
        idle = min(0.1, max(0, timeout - (clock() - started))) - (clock() - before)
        if idle > 0:
            pause(idle)
        if state.progress is not None and state.progress != previous:
            previous = state.progress
            emit({'state': 'progress', 'task_id': task.task_id, 'progress': previous})


def observe_wait(event):
    """The UI/trajectory can observe progress without feeding it to a model."""
    from episode_logger import record_trajectory_event
    record_trajectory_event('tool.completion_wait', event)
