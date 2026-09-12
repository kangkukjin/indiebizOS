"""상주 라이브러리 스레드와 그 위의 유한 호출을 분리하는 실행 경계.

스레드 이름/daemon 여부로 면제하지 않는다. 알려진 풀·모니터의 생성 경계만
분리하며, AnyIO asyncio 백엔드는 각 제출을 실제 함수의 finally까지 소유한다.
"""
import threading
from functools import wraps

import runtime_work as work


class _Submission:
    """취소와 실행 시작 사이의 경쟁도 같은 잠금으로 닫는다."""
    def __init__(self, fn):
        self.fn = fn
        self.lease = work.reserve("anyio-worker")
        self.lock = threading.Lock()
        self.state = "pending"

    def __call__(self, *args):
        with self.lock:
            if self.state != "pending":
                return None  # 접수 대기 중 취소된 함수는 뒤늦게 실행하지 않는다.
            self.state = "running"
        try:
            with self.lease.activate():
                return self.fn(*args)
        finally:
            with self.lock:
                self.state = "done"
                self.lease.close()

    def cancel_pending(self):
        with self.lock:
            if self.state == "pending":
                self.state = "cancelled"
                self.lease.close()


def _service_thread(cls):
    original = cls.start

    @wraps(original)
    def start(self, *args, **kwargs):
        with work.service_scope():
            return original(self, *args, **kwargs)

    cls.start = start


def install_library_tracking():
    # FastAPI/Starlette가 미리 import한 run_sync 별칭도 같은 백엔드 경계를 지난다.
    try:
        from anyio._backends._asyncio import AsyncIOBackend, WorkerThread
    except ImportError:
        pass  # AnyIO가 없는 독립 몸에는 이 경계가 없다.
    else:
        if not getattr(AsyncIOBackend, "_runtime_tracking", False):
            original = AsyncIOBackend.run_sync_in_worker_thread.__func__

            @classmethod
            @wraps(original)
            async def run_sync(cls, func, args, *options, **kwargs):
                if not work.parent_token():
                    return await original(cls, func, args, *options, **kwargs)
                call = _Submission(func)
                try:
                    return await original(cls, call, args, *options, **kwargs)
                finally:
                    # abandon_on_cancel은 기다리는 요청만 끝낸다. 실행 중인 함수의
                    # 예약은 이곳에서 반환하지 않고 worker의 finally가 반환한다.
                    call.cancel_pending()

            _service_thread(WorkerThread)
            AsyncIOBackend.run_sync_in_worker_thread = run_sync
            AsyncIOBackend._runtime_tracking = True

    try:
        from tqdm._monitor import TMonitor
    except ImportError:
        pass
    else:
        if not TMonitor.__dict__.get("_runtime_service", False):
            _service_thread(TMonitor)
            TMonitor._runtime_service = True
