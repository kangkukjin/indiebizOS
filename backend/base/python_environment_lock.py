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
import re
from urllib.parse import unquote, urlparse


def fingerprint(source_root, *, details=False, search_paths=None, modules=None):
    h = hashlib.sha256(sys.version.encode())
    # Distribution.metadata reparses METADATA on every access (including
    # Distribution.version). Read it once per observation, never across calls:
    # installs, removals and editable source changes must remain visible.
    observed = (metadata.distributions() if search_paths is None else
                metadata.distributions(path=search_paths))
    # 같은 설치 경로의 별칭/중복 sys.path는 설치 변경이 아니다. 서로 다른 설치는
    # 모두 유지하며 동명이 배포판의 순서도 경로로 고정한다.
    unique = {str(Path(dist._path).resolve()): dist for dist in observed}
    distributions = [(path, dist, dist.metadata) for path, dist in unique.items()]
    if modules is not None:
        wanted = set(modules)
        def provides(dist, info):
            names = set((dist.read_text('top_level.txt') or '').split())
            names.add(info.get('Name', '').replace('-', '_'))
            if not names & wanted:
                names.update(str(p).split('/')[0].split('.')[0] for p in (dist.files or []))  # path-ok: wheel file/module name
            return bool(names & wanted)
        normalized = lambda name: re.sub(r'[-_.]+', '-', name).lower()
        selected = {normalized(info.get('Name', '')) for _, d, info in distributions if provides(d, info)}
        # Imported distributions depend on other distributions even when this
        # program does not import those names directly (e.g. requests/urllib3).
        while True:
            previous = set(selected)
            for _, _, info in distributions:
                if normalized(info.get('Name', '')) in selected:
                    for requirement in info.get_all('Requires-Dist', []):
                        match = re.match(r'[\w.-]+', requirement)
                        if match:
                            selected.add(normalized(match.group()))
            if selected == previous:
                break
        distributions = [(p, d, info) for p, d, info in distributions if normalized(info.get('Name', '')) in selected]
    for location, dist, info in sorted(distributions, key=lambda item: (item[2].get('Name', ''), item[0])):
        h.update((info.get('Name', '') + '=' + info['Version']).encode())
        base = Path(location)
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
    environment = h.hexdigest()
    for path in sorted(Path(source_root).glob('*.py')):
        h.update(path.read_bytes())
    combined = h.hexdigest()
    return {'combined': combined, 'environment': environment} if details else combined
