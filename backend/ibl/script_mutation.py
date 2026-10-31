"""Conditional registration at the existing script owner, shared by every writer."""
import hashlib
import json
import threading
from contextlib import contextmanager
from pathlib import Path
from filelock import FileLock

_LOCK = threading.RLock()
FIELDS = ('file', 'interpreter', 'description', 'timeout', 'callable_contract')


def revision(entry, directory):
    if entry is None:
        return ''
    path = Path(directory) / entry.get('file', '')
    data = {k: entry.get(k) for k in FIELDS}
    data['source'] = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


@contextmanager
def transaction(path):
    path = Path(path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK, FileLock(str(path) + '.lock', timeout=30):
        yield


def check_expected(params, entry, directory):
    current = revision(entry, directory)
    if 'expected_revision' in params and params['expected_revision'] != current:
        raise ValueError('스크립트 판본 충돌: 목록을 다시 읽고 변경하세요.')
    return current


def publish(root, path, directory, write, before, after, sid):
    from capability_consumers import validate_script_change
    import function_store
    impact = validate_script_change(root, path, before, after, sid, function_store.storage_root())
    write(after)
    return {'revision': revision(after.get(sid), directory),
            'callers': [r['location'] for r in impact['callers']], 'unknown': impact['unknown']}
