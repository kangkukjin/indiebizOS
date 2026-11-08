"""Trusted launcher binding shared by workspace, IPC and analysis. Never model input."""
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

_scope = ContextVar('code_analysis_scope', default=None)


def current_scope():
    return _scope.get()


@contextmanager
def bind(root, *, writable=False, generation='', execution=None):
    target = Path(root).resolve(strict=True)
    outer = _scope.get()
    if outer and not target.is_relative_to(outer['root']):
        raise PermissionError('작업 사본의 경계를 넓힐 수 없습니다')
    token = _scope.set({'root': str(target), 'writable': writable and (not outer or outer['writable']),
                        'generation': generation, 'execution': execution or (outer or {}).get('execution')})
    try:
        yield
    finally:
        _scope.reset(token)


def check(root, *, write=False):
    from principal import is_owner
    if not is_owner():
        raise PermissionError('코드 작업 공간은 소유자만 사용할 수 있습니다')
    scope = _scope.get()
    if scope and (not Path(root).resolve().is_relative_to(scope['root']) or write and not scope['writable']):
        raise PermissionError('발행된 작업 사본·작업 범위를 벗어났습니다')
    return scope


def working_directory(requested, default):
    """A location narrows existing authority; it never creates authority."""
    from runtime_utils import expand_body_path
    path = Path(expand_body_path(requested)) if requested is not None else Path(default)
    if not path.is_absolute():
        path = Path(default) / path
    target = path.resolve(strict=True)
    if not target.is_dir():
        raise ValueError('cwd는 디렉터리여야 합니다')
    check(target, write=True)
    return target
