"""One job per Android process; app UID, bounded diagnostics, explicit JSON result."""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import traceback

PREVIEW = 64 * 1024
LOG_LIMIT = 8 * 1024 * 1024


class Output:
    encoding = "utf-8"

    def __init__(self, root):
        self.root = root
        self.size = 0
        self.truncated = False
        self.lock = threading.Lock()

    def write(self, name, data):
        if isinstance(data, str):
            data = data.encode("utf-8", errors="replace")
        with self.lock:
            remaining = max(0, LOG_LIMIT - self.size)
            if len(data) > remaining:
                self.truncated = True
            data = data[:remaining]
            with (self.root / (name + ".log")).open("ab") as stream:
                stream.write(data)
            self.size += len(data)

    def stream(self, name):
        owner = self

        class Stream:
            encoding = "utf-8"

            def write(self, text):
                owner.write(name, text)
                return len(text)

            def flush(self):
                pass

            def isatty(self):
                return False

        return Stream()


def artifact(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(512 * 1024), b""):
            digest.update(chunk)
    return {"path": str(path), "size": path.stat().st_size, "sha256": digest.hexdigest()}


def diagnostics(root):
    result = {"artifacts": []}
    for name in ("stdout", "stderr"):
        path = root / (name + ".log")
        if path.exists():
            with path.open("rb") as stream:
                result[name] = stream.read(PREVIEW).decode("utf-8", errors="replace")
            result["artifacts"].append(artifact(path))
        else:
            result[name] = ""
    return result


@contextlib.contextmanager
def capture_native_output(output):
    """Capture os.write, native file descriptors and inherited subprocess output too."""
    saved = []
    readers = []
    try:
        for fd, name in ((1, "stdout"), (2, "stderr")):
            read_fd, write_fd = os.pipe()
            saved.append((fd, os.dup(fd)))
            os.dup2(write_fd, fd)
            os.close(write_fd)

            def read(pipe=read_fd, stream=name):
                with os.fdopen(pipe, "rb", buffering=0) as source:
                    for chunk in iter(lambda: source.read(8192), b""):
                        output.write(stream, chunk)

            thread = threading.Thread(target=read, daemon=True)
            thread.start()
            readers.append(thread)
        yield
    finally:
        for fd, backup in saved:
            os.dup2(backup, fd)
            os.close(backup)
        for thread in readers:
            thread.join(2)
        output.incomplete = any(thread.is_alive() for thread in readers)


def run_shell(command, output):
    process = subprocess.Popen(
        ["/system/bin/sh" if sys.platform == "android" or os.path.exists("/system/bin/sh") else "/bin/sh",
         "-c", command["cmd"]], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, env={**os.environ, **command.get("env", {})}, start_new_session=True)

    def read(stream, name):
        with stream:
            for chunk in iter(lambda: stream.read(8192), b""):
                output.write(name, chunk)

    def feed():
        try:
            with process.stdin:
                process.stdin.write(command.get("stdin", "").encode())
        except (BrokenPipeError, OSError):
            pass

    readers = [threading.Thread(target=read, args=(process.stdout, "stdout"), daemon=True),
               threading.Thread(target=read, args=(process.stderr, "stderr"), daemon=True)]
    for thread in readers:
        thread.start()
    threading.Thread(target=feed, daemon=True).start()
    try:
        code = process.wait(timeout=command["timeout"])
        return {"success": code == 0, "exit_code": code,
                **({"error": "shell_exit_nonzero"} if code else {})}
    finally:
        # The job owns its children; a detached shell daemon is not a completed job.
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait()
        for thread in readers:
            thread.join(2)


def run(request_path):
    request = json.loads(Path(request_path).read_text())
    root = Path(request_path).parent
    os.environ["INDIEBIZ_BASE_PATH"] = request["base_path"]
    os.environ["INDIEBIZ_PROFILE"] = "phone"
    os.environ["INDIEBIZ_USERDATA"] = str(Path(request["workspace"]).parent)
    sys.path.insert(0, str(Path(request["base_path"]) / "backend"))
    import boot_paths  # noqa: F401
    from phone_execution_contract import validate
    from thread_context import ISOLATED_ORIGINS, actor_context
    output = Output(root)
    started = time.monotonic()
    result = {"success": False, "exit_code": None}
    try:
        command = validate(request["command"])
        cwd = Path(command.get("cwd") or request["workspace"]).expanduser()
        if not cwd.is_absolute():
            cwd = Path(request["workspace"]) / cwd
        cwd = cwd.resolve(strict=True)
        os.chdir(cwd)
        result.update(runtime=command["op"], cwd=str(cwd), identity="app", uid=os.getuid())
        origin = command.get("origin")
        origin = origin if isinstance(origin, str) and origin in ISOLATED_ORIGINS else None
        result["origin"] = origin
        with actor_context(agent_id="phone_execution", origin=origin), capture_native_output(output), contextlib.redirect_stdout(output.stream("stdout")), contextlib.redirect_stderr(output.stream("stderr")):
            if command["op"] == "shell":
                result.update(run_shell(command, output))
            else:
                namespace = {"__name__": "__main__", "__file__": str(root / "program.py"),
                             "inputs": command.get("inputs", {}), "result": None}
                (root / "program.py").write_text(command["code"], encoding="utf-8")
                exec(compile(command["code"], str(root / "program.py"), "exec"), namespace)
                value = json.dumps(namespace["result"], ensure_ascii=False, allow_nan=False).encode()
                if len(value) <= PREVIEW:
                    result.update(success=True, value=namespace["result"])
                else:
                    path = root / "value.json"
                    path.write_bytes(value)
                    result.update(success=True, value_ref=artifact(path))
    except BaseException as exc:
        output.write("stderr", traceback.format_exc())
        result.update(success=False, error=str(exc) or type(exc).__name__, exception_type=type(exc).__name__)
        if isinstance(exc, subprocess.TimeoutExpired):
            result.update(timeout=True, error="execution_timeout")
    result.update(diagnostics(root), elapsed_ms=int((time.monotonic() - started) * 1000),
                  output_truncated=output.truncated, diagnostics_incomplete=getattr(output, "incomplete", False))
    dest = root / "result.json"
    tmp = root / "result.tmp"
    tmp.write_text(json.dumps(result, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    os.replace(tmp, dest)
    return str(dest)
