"""작업 제출 경계의 문맥 승계. 풀의 크기·수명·타임아웃은 호출자가 소유한다."""
import contextvars
from concurrent.futures import ThreadPoolExecutor
from functools import wraps

import thread_context


def bind_context(fn):
    """현재 문맥을 캡처한 1회 호출을 만든다. 동시 제출마다 새로 바인딩한다.

    thread-local 신원과 contextvars(비용 원장·궤적 등)를 함께 나른다.
    참조 객체는 원래 계약대로 공유하며, 종료/예외 때 워커의 이전 문맥을 복원한다.
    """
    snapshot = thread_context.snapshot()
    context = contextvars.copy_context()

    def invoke(*args, **kwargs):
        previous = thread_context.snapshot()
        try:
            thread_context.restore(snapshot)
            return fn(*args, **kwargs)
        finally:
            thread_context.restore(previous)

    @wraps(fn)
    def bound(*args, **kwargs):
        return context.run(invoke, *args, **kwargs)

    return bound


class ContextThreadPoolExecutor(ThreadPoolExecutor):
    """생성 시점이 아닌 각 submit 시점의 작업 문맥을 승계하는 풀."""

    def submit(self, fn, /, *args, **kwargs):
        return super().submit(bind_context(fn), *args, **kwargs)


def create_executor(role: str, max_workers=None, **kwargs):
    """역할별 새 풀. 전역 공유/캐시하지 않아 중첩 작업의 독립 풀을 보존한다."""
    kwargs.setdefault("thread_name_prefix", role)
    return ContextThreadPoolExecutor(max_workers=max_workers, **kwargs)
