"""File-process lifecycle shared by registered scripts and transient files.

No IBL dependencies. The caller owns codecs, authority, and durable receipts.
"""
from contextlib import contextmanager
from contextvars import ContextVar
import os
import signal
import subprocess
import tempfile
import time

_invocation_check = ContextVar("registered_script_check", default=None)


@contextmanager
def invocation_scope(check):
    token = _invocation_check.set(check)
    try:
        yield
    finally:
        _invocation_check.reset(token)


def check_invocation():
    check = _invocation_check.get()
    if check:
        check()


def stop_tree(proc, *, grace=0):
    """Attempt every owned termination; cleanup cannot replace the primary result."""
    import psutil
    errors = []
    def attempt(stage, operation):
        try:
            return operation()
        except (ProcessLookupError, psutil.NoSuchProcess):
            return None
        except (OSError, psutil.Error, subprocess.TimeoutExpired) as exc:
            errors.append({'phase': 'cleanup', 'operation': stage,
                           'errno': getattr(exc, 'errno', None), 'error': str(exc)})
    try:
        children = psutil.Process(proc.pid).children(recursive=True)
    except psutil.NoSuchProcess:
        children = []
    except (psutil.AccessDenied, PermissionError) as exc:
        children = []
        errors.append({'phase': 'cleanup', 'operation': 'descendants',
                       'errno': getattr(exc, 'errno', None), 'error': str(exc)})
    if grace and proc.poll() is None:
        attempt('terminate', lambda: os.killpg(proc.pid, signal.SIGTERM) if os.name != 'nt' else proc.terminate())
        try:
            proc.wait(timeout=grace)
        except subprocess.TimeoutExpired:
            pass
    if os.name != 'nt':
        attempt('group', lambda: os.killpg(proc.pid, signal.SIGKILL))
    for child in reversed(children):
        attempt('child', child.kill)
    if proc.poll() is None:
        attempt('parent', proc.kill)
    attempt('wait', lambda: proc.wait(timeout=2))
    remaining = attempt('wait_children', lambda: psutil.wait_procs(children, timeout=2))
    return {'confirmed': not errors and proc.poll() is not None and not (remaining and remaining[1]),
            'scope': 'process_group_and_observed_descendants',
            'diagnostics': errors, 'remaining_pids': [p.pid for p in remaining[1]] if remaining else []}


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
        cleanup = None
        failure = None
        try:
            if started:
                started(proc.pid)
            while proc.poll() is None:
                if check:
                    check()
                if time.monotonic() >= deadline:
                    timed_out = True
                    break
                time.sleep(.05)
        except BaseException as exc:
            failure = exc
        # Transient files own their synchronous children; registered scripts keep
        # the historical successful-exit behavior (some start external services).
        if terminate_descendants or timed_out or failure is not None:
            cleanup = stop_tree(proc)
        out.flush()
        err.flush()
        result = {'exit_code': proc.returncode, 'timed_out': timed_out}
        if cleanup is not None:
            result['cleanup'] = cleanup
        if stdout_file is None:
            out.seek(0)
            result['stdout'] = out.read().decode('utf-8', errors='replace')
        if stderr_file is None:
            err.seek(0)
            result['stderr'] = err.read().decode('utf-8', errors='replace')
        if failure is not None:
            failure.process_result = result
            raise failure
        return result
