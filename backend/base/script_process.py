"""File-process lifecycle shared by registered scripts and transient files.

No IBL dependencies. The caller owns codecs, authority, and durable receipts.
"""
import os
import signal
import subprocess
import tempfile
import time


def stop_tree(proc):
    """Stop the owned child and descendants on every supported desktop OS."""
    import psutil
    try:
        children = psutil.Process(proc.pid).children(recursive=True)
    except (psutil.NoSuchProcess, psutil.AccessDenied, PermissionError):
        children = []
    if os.name != 'nt':
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    for child in reversed(children):
        try:
            child.kill()
        except psutil.NoSuchProcess:
            pass
    if proc.poll() is None:
        proc.kill()
    proc.wait()
    psutil.wait_procs(children, timeout=2)


def run_process(argv, stdin, *, cwd, env, timeout, check=None,
                stdout_file=None, stderr_file=None, started=None,
                terminate_descendants=False):
    """Keep raw streams separate; check may raise the host's cancellation fault.

Files avoid pipe deadlocks and unbounded in-memory diagnostics. Even a host
exception waits for child termination before returning to its receipt owner.
"""
    from thread_context import get_repair_workspace
    workspace = get_repair_workspace()
    if workspace and not (env or {}).get("INDIEBIZ_REPAIR_CHILD"):
        from repair_process import prepare
        argv, env = prepare(argv, workspace, env=env)
    from contextlib import ExitStack
    with ExitStack() as stack:
        inp = stack.enter_context(tempfile.TemporaryFile())
        inp.write(stdin)
        inp.seek(0)
        out = stack.enter_context(open(stdout_file, 'w+b') if stdout_file else tempfile.TemporaryFile())
        err = stack.enter_context(open(stderr_file, 'w+b') if stderr_file else tempfile.TemporaryFile())
        if check:
            check()
        proc = subprocess.Popen(argv, stdin=inp, stdout=out, stderr=err,
                                cwd=cwd, env=env, start_new_session=os.name != 'nt')
        deadline = time.monotonic() + timeout
        timed_out = False
        try:
            if started:
                started(proc.pid)
            while proc.poll() is None:
                if check:
                    check()
                if time.monotonic() >= deadline:
                    timed_out = True
                    stop_tree(proc)
                    break
                time.sleep(.05)
        except BaseException:
            stop_tree(proc)
            raise
        # Transient files own their synchronous children; registered scripts keep
        # the historical successful-exit behavior (some start external services).
        if terminate_descendants:
            stop_tree(proc)
        out.flush()
        err.flush()
        result = {'exit_code': proc.returncode, 'timed_out': timed_out}
        if stdout_file is None:
            out.seek(0)
            result['stdout'] = out.read().decode('utf-8', errors='replace')
        if stderr_file is None:
            err.seek(0)
            result['stderr'] = err.read().decode('utf-8', errors='replace')
        return result
