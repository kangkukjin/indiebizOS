"""Atomic file replacement anchored to directory handles on POSIX."""
import os
import tempfile
import uuid
from pathlib import Path


def replace(path, data, mode):
    path = Path(path)
    if os.open not in os.supports_dir_fd:
        # Windows analysis is local-owner only; confined workers are unavailable there.
        if data is None:
            path.unlink(missing_ok=True)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix='.coding-save-', dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as out:
                out.write(data); out.flush(); os.fsync(out.fileno())
            os.chmod(name, mode)
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)
        return
    parent = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY)
    temporary = '.coding-save-' + uuid.uuid4().hex
    try:
        for part in path.parts[1:-1]:
            try:
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            except FileNotFoundError:
                if data is None:
                    return
                try:
                    os.mkdir(part, dir_fd=parent)
                except FileExistsError:
                    pass
                child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent)
            os.close(parent); parent = child
        if data is None:
            try:
                os.unlink(path.name, dir_fd=parent)
            except FileNotFoundError:
                pass
        else:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode, dir_fd=parent)
            try:
                with os.fdopen(fd, 'wb') as out:
                    out.write(data); out.flush(); os.fchmod(out.fileno(), mode); os.fsync(out.fileno())
                os.replace(temporary, path.name, src_dir_fd=parent, dst_dir_fd=parent)
            finally:
                try:
                    os.unlink(temporary, dir_fd=parent)
                except FileNotFoundError:
                    pass
        os.fsync(parent)
    finally:
        os.close(parent)
