"""Publish completed files with an explicit collision policy; never erase first."""
import errno
import os
from pathlib import Path
import tempfile
import sys


def collision_policy(value, default='fail'):
    policy = default if value is None else value
    if policy not in ('fail', 'overwrite', 'rename'):
        raise ValueError('if_exists는 fail·overwrite·rename 중 하나입니다.')
    return policy


def rename_no_replace(source, destination):
    """Publish a completed sibling file atomically, without replacing any target.

    No empty reservation is exposed. Unsupported filesystems fail with the source
    intact, rather than falling back to a check-then-replace race.
    """
    if sys.platform == 'win32':
        os.rename(source, destination)  # Windows rename fails if destination exists.
        return
    import ctypes
    libc = ctypes.CDLL(None, use_errno=True)
    src, dst = ctypes.c_char_p(os.fsencode(source)), ctypes.c_char_p(os.fsencode(destination))
    if sys.platform == 'darwin':
        call = getattr(libc, 'renamex_np', None)
        if call is None:
            raise OSError(errno.ENOSYS, 'atomic_no_replace_unsupported')
        call.restype = ctypes.c_int
        result = call(src, dst, ctypes.c_uint(4))  # RENAME_EXCL, <sys/stdio.h>
    elif sys.platform == 'linux':
        args = (ctypes.c_int(-100), src, ctypes.c_int(-100), dst, ctypes.c_uint(1))
        call = getattr(libc, 'renameat2', None)
        if call is not None:
            call.restype = ctypes.c_int
            result = call(*args)  # RENAME_NOREPLACE
        else:
            # Android API 28 may have the kernel call without the libc wrapper.
            import platform
            number = {'aarch64': 276, 'armv7l': 382, 'armv8l': 382, 'x86_64': 316}.get(platform.machine())
            if number is None:
                raise OSError(errno.ENOSYS, 'atomic_no_replace_unsupported')
            libc.syscall.restype = ctypes.c_long
            result = libc.syscall(ctypes.c_long(number), *args)
    else:
        raise OSError(errno.ENOSYS, 'atomic_no_replace_unsupported')
    if result != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(destination))


def publish_exclusive(temp, target):
    """Publish complete bytes; caller cleans temp if link publication retains it."""
    try:
        os.link(temp, target)
        return
    except (PermissionError, OSError) as error:
        if isinstance(error, FileExistsError):
            raise
        if getattr(error, 'errno', None) not in (errno.EPERM, errno.EACCES, errno.EXDEV, errno.EOPNOTSUPP, errno.ENOTSUP):
            raise
    rename_no_replace(temp, target)


def publish_file(destination, writer, *, if_exists='fail', guard=None):
    """writer(temp) finishes before a link/replace publishes bytes in the same directory.

    Rename/fail never overwrite a racing writer. Overwrite is explicit and atomic
    per file, not a transaction over a directory or a whole workflow.
    """
    policy = collision_policy(if_exists)
    requested = Path(destination).absolute()

    def check(path):
        if guard:
            error = guard(str(path))
            if error:
                raise ValueError(str(error))
        if path.is_symlink() and policy != 'rename':
            raise ValueError('출력 대상의 심볼릭 링크는 교체하지 않습니다.')
        if path.is_dir():
            raise ValueError('파일 출력 대상이 폴더입니다.')

    check(requested)
    if policy == 'fail' and requested.exists():
        raise FileExistsError(f'output 파일이 이미 있습니다: {requested}. if_exists를 명시하세요.')
    requested.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.publish-', suffix=requested.suffix, dir=requested.parent)
    os.close(fd)
    temp = Path(name)
    try:
        value = writer(temp)
        if not temp.is_file() or temp.is_symlink():
            raise ValueError('작성기가 정상 결과 파일을 만들지 않았습니다.')
        with temp.open('rb') as stream:
            os.fsync(stream.fileno())
        target, index = requested, 1
        while True:
            check(target)
            replaced = target.exists()
            try:
                if policy == 'overwrite':
                    os.replace(temp, target)
                else:
                    publish_exclusive(temp, target)
                break
            except FileExistsError:
                if policy != 'rename':
                    raise
                index += 1
                target = requested.with_name(f'{requested.stem} ({index}){requested.suffix}')
        return value, {'path': str(target), 'requested_path': str(requested),
                       'if_exists': policy, 'replaced_existing': replaced,
                       'renamed': str(target) != str(requested)}
    finally:
        temp.unlink(missing_ok=True)
