"""Trusted task ownership for temporary code; this is not a sandbox."""
from contextlib import contextmanager
from contextvars import ContextVar
from hashlib import sha256
from pathlib import Path
import json
import os
import uuid

_scope = ContextVar('file_script_scope', default=None)


def authorize():
    import principal
    from thread_context import get_allowed_nodes
    if not principal.is_owner() or get_allowed_nodes() is not None:
        raise PermissionError('임시 Script는 임의 로컬 코드 실행이 허용된 제한 없는 주인 문맥 전용입니다.')


@contextmanager
def request_scope(project, agent=None, resume=None, stored_scope=None):
    """A real task spans tool calls; a taskless API request gets its own scope."""
    import principal
    from thread_context import get_current_task_id, get_current_agent_id
    previous = _scope.get()
    if previous is not None:
        yield
        return
    task = get_current_task_id()
    if not task:
        task = 'request:' + (str((resume or {}).get('run_id') or uuid.uuid4().hex))
    key = [principal.cache_key(), str(Path(project).resolve()),
           agent or get_current_agent_id() or '', task]
    token = _scope.set(stored_scope or sha256(json.dumps(key, ensure_ascii=False).encode()).hexdigest())
    try:
        yield
    finally:
        _scope.reset(token)


def storage_root():
    from runtime_utils import get_base_path
    return get_base_path() / 'data' / 'script_runs' / 'transient'


def current_scope():
    return _scope.get()


def workspace():
    authorize()
    scope = _scope.get()
    if scope is None:
        raise PermissionError('~turn은 IBL 실행 문맥 안에서 사용하세요.')
    return storage_root() / scope / 'work'


def expand(path):
    root = workspace().resolve()
    relative = path[len('~turn'):].lstrip('/\\')
    target = (root / relative).resolve()
    if not target.is_relative_to(root):
        raise PermissionError('~turn 경로는 현재 턴 작업 폴더 안에 있어야 합니다.')
    return str(target)


def source_path(raw):
    from runtime_utils import expand_body_path
    root = workspace().resolve()
    path = Path(expand_body_path(raw))
    path = (path if path.is_absolute() else root / path).resolve()
    if not path.is_relative_to(root) or path.suffix != '.py' or not path.is_file():
        raise PermissionError('path는 현재 ~turn 작업 폴더 안의 실존 Python 파일이어야 합니다.')
    if path.stat().st_nlink != 1:
        raise PermissionError('임시 Script 진입 파일의 하드 링크는 지원하지 않습니다.')
    return path


def prepare_path(path):
    """Called only by file mutation, never by compiler/path observation."""
    if _scope.get() is None:
        return
    root = (storage_root() / _scope.get() / 'work').resolve()
    if Path(path).resolve().is_relative_to(root):
        authorize()
        root.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        os.chmod(root.parent, 0o700)
        root.mkdir(exist_ok=True, mode=0o700)
        os.chmod(root, 0o700)
        import time
        from file_script import atomic_json
        atomic_json(root.parent / 'scope.json', {'protocol': 'file-workspace/1', 'updated': time.time()})
