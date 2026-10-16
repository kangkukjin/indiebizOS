"""Registered phone file transfer using the existing resident chunk protocol."""
import base64
from contextlib import contextmanager
import errno
import hashlib
import os
from pathlib import Path
import re
import sys
import time

CHUNK = 512 * 1024


def _rename_no_replace(source, destination):
    """Linux/Android atomic publication when SELinux disallows hardlinks.

    RENAME_NOREPLACE preserves the no-clobber contract including concurrent writers.
    Old bionic (API 28) has the kernel call but may not export the libc wrapper.
    Numbers are Linux UAPI __NR_renameat2 for the supported process architectures.
    """
    import ctypes
    import platform
    libc = ctypes.CDLL(None, use_errno=True)
    args = (ctypes.c_int(-100), ctypes.c_char_p(os.fsencode(source)),
            ctypes.c_int(-100), ctypes.c_char_p(os.fsencode(destination)), ctypes.c_uint(1))
    call = getattr(libc, "renameat2", None)
    if call is not None:
        call.restype = ctypes.c_int
        result = call(*args)
    else:
        number = {"aarch64": 276, "armv7l": 382, "armv8l": 382, "x86_64": 316}.get(platform.machine())
        if number is None:
            raise OSError(errno.ENOSYS, "atomic_no_replace_unsupported")
        libc.syscall.restype = ctypes.c_long
        result = libc.syscall(ctypes.c_long(number), *args)
    if result != 0:
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(destination))


def publish_download(partial, path):
    try:
        os.link(partial, path)
    except OSError as error:
        if sys.platform != "linux" or error.errno not in {errno.EPERM, errno.EACCES, errno.EOPNOTSUPP}:
            raise
        _rename_no_replace(partial, path)
    else:
        partial.unlink()


def digest(path, check=lambda: None):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(CHUNK), b""):
            check()
            h.update(chunk)
    return h.hexdigest()


def execute(client, command, cancelled):
    tid = command.get("transfer_id", "")
    if not isinstance(tid, str) or not re.fullmatch(r"[a-f0-9]{32}", tid):
        raise ValueError("invalid_transfer")
    raw = command.get("path")
    if not isinstance(raw, str) or not raw or "\0" in raw:
        raise ValueError("path_required")
    path = Path(raw).expanduser()
    if not path.is_absolute():
        from phone_remote_execution import workspace
        path = workspace() / path
    path = path.resolve()
    with _pin_run_file(path, tid):
        return _transfer(client, command, cancelled, tid, path)


@contextmanager
def _pin_run_file(path, tid):
    """Failed/in-flight uploads remain pinned across restarts; successful upload releases it."""
    runs = Path(os.environ.get("INDIEBIZ_USERDATA") or Path.home()) / "remote_runs"
    try:
        relative = path.relative_to(runs.resolve())
    except ValueError:
        yield
        return
    if len(relative.parts) < 2:
        raise ValueError("transfer_requires_file")
    import fcntl
    runs.mkdir(parents=True, exist_ok=True)
    with (runs / ".retention.lock").open("a") as lock:
        fcntl.lockf(lock, fcntl.LOCK_EX)
        marker = runs / relative.parts[0] / (".transfer-" + tid)
        marker.touch()  # Parent must exist: do not resurrect a pruned result.
        fcntl.lockf(lock, fcntl.LOCK_UN)
    yield
    marker.unlink(missing_ok=True)


def _transfer(client, command, cancelled, tid, path):
    deadline = time.monotonic() + command.get("timeout", 3600)

    def check():
        if cancelled.is_set() or client.stopped.is_set():
            raise InterruptedError("transfer_cancelled")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("transfer_timeout")
        return remaining

    def request(action, **values):
        remaining = check()
        return client._post("transfers/" + tid, {**client._auth(), "action": action, **values}, min(30, remaining))

    row = request("info")
    if row["direction"] == "from_pc":
        sha = digest(path, check)
        size = path.stat().st_size
        row = request("meta", size=size, sha256=sha)
        with path.open("rb") as stream:
            stream.seek(row["offset"])
            offset = row["offset"]
            for data in iter(lambda: stream.read(CHUNK), b""):
                row = request("write", offset=offset, data=base64.b64encode(data).decode("ascii"))
                if row["offset"] != offset + len(data):
                    raise ValueError("invalid_transfer_offset")
                offset = row["offset"]
        row = request("commit")
    elif row["direction"] == "to_pc":
        if row["state"] != "committed":
            raise ValueError("transfer_not_committed")
        if path.exists():
            if path.is_file() and digest(path, check) == row["sha256"]:
                return {"success": True, "path": str(path), "sha256": row["sha256"], "size": row["size"]}
            raise ValueError("destination_exists")
        path.parent.mkdir(parents=True, exist_ok=True)
        partial = path.parent / (".indiebiz-" + tid + ".part")
        offset = partial.stat().st_size if partial.exists() else 0
        if offset > row["size"]:
            raise ValueError("partial_size_conflict")
        with partial.open("ab") as stream:
            while offset < row["size"]:
                piece = request("read", offset=offset, chunk_size=CHUNK)
                data = base64.b64decode(piece["data"], validate=True)
                if not data or piece["offset"] != offset + len(data) or piece["offset"] > row["size"]:
                    raise ValueError("invalid_transfer_chunk")
                stream.write(data)
                stream.flush()
                offset = piece["offset"]
            os.fsync(stream.fileno())
        if digest(partial, check) != row["sha256"]:
            raise ValueError("hash_mismatch")
        check()
        publish_download(partial, path)
    else:
        raise ValueError("invalid_transfer_direction")
    return {"success": True, "path": str(path), "sha256": row["sha256"],
            "size": row["size"], "transfer_id": tid}
