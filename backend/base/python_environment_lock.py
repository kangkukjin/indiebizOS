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


# Metadata only: dependency checks must not import a registered script or library.
import hashlib
import importlib.metadata as metadata
import json
import sys
from urllib.parse import unquote, urlparse


def fingerprint(source_root):
    h = hashlib.sha256(sys.version.encode())
    for dist in sorted(metadata.distributions(), key=lambda d: d.metadata.get('Name', '')):
        h.update((dist.metadata.get('Name', '') + '=' + dist.version).encode())
        base = Path(dist._path)
        for name in ('METADATA', 'RECORD', 'direct_url.json'):
            path = base / name
            if path.is_file():
                st = path.stat()
                h.update(f'{path}:{st.st_size}:{st.st_mtime_ns}'.encode())
        direct = dist.read_text('direct_url.json')
        if direct:
            entry = json.loads(direct)
            if entry.get('dir_info', {}).get('editable'):
                root = Path(unquote(urlparse(entry['url']).path))
                for path in sorted(root.rglob('*.py')):
                    if '.venv' not in path.parts and '.git' not in path.parts:
                        h.update(str(path).encode()); h.update(path.read_bytes())
    for path in sorted(Path(source_root).glob('*.py')):
        h.update(path.read_bytes())
    return h.hexdigest()

