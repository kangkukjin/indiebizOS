"""Managed Python installs and library workers share one environment lease."""
from contextlib import contextmanager
from pathlib import Path
import os
import time


@contextmanager
def environment_lease(*, write=False, check=lambda: None, timeout=300):
    from runtime_utils import get_base_path
    path = Path(get_base_path()) / 'data' / 'runtime' / 'python-environment.lock'
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name == 'nt':
        # Windows fallback is exclusive; correctness before concurrent workers.
        from filelock import FileLock
        with FileLock(str(path), timeout=timeout, thread_local=False):
            check()
            yield
        return
    import fcntl
    with path.open('a') as stream:
        until = time.monotonic() + timeout
        while True:
            check()
            try:
                fcntl.flock(stream, (fcntl.LOCK_EX if write else fcntl.LOCK_SH) | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() > until:
                    raise TimeoutError('Python 실행/설치 환경 잠금 대기 시간 초과')
                time.sleep(.05)
        try:
            yield
        finally:
            fcntl.flock(stream, fcntl.LOCK_UN)
