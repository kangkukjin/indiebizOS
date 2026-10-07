"""Durable, task-scoped cancellation requests; never stop a resident runner."""
import hashlib
import os
from pathlib import Path


def _path(owner, task_id):
    from runtime_utils import get_base_path
    root = Path(os.environ.get('INDIEBIZ_RUNTIME_STATE_DIR') or get_base_path() / 'data')
    key = hashlib.sha256(f'{owner}\0{task_id}'.encode()).hexdigest()
    return root / 'task_cancellations' / key


def request(owner, task_id):
    path = _path(owner, task_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch(mode=0o600)


def requested(owner, task_id):
    return bool(task_id) and _path(owner, task_id).is_file()
