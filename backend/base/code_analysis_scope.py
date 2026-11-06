"""Trusted launcher binding shared by workspace, IPC and analysis. Never model input."""
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

_scope = ContextVar('code_analysis_scope', default=None)


def current_scope():
    return _scope.get()


@contextmanager
def bind(root, *, writable=False, generation=''):
    target = Path(root).resolve(strict=True)
    outer = _scope.get()
    if outer and not target.is_relative_to(outer['root']):
        raise PermissionError('작업 사본의 경계를 넓힐 수 없습니다')
    token = _scope.set({'root': str(target), 'writable': writable and (not outer or outer['writable']),
                        'generation': generation})
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
