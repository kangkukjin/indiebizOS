#!/usr/bin/env python3
"""Run an explicit argv plan on the target PC; preserve steps across reconnects.

This is a CLI on the target, not a remote transport. Submit it once with guestpc
and observe the existing task_ref. No shell fragments are interpreted.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import boot_paths  # noqa: F401,E402

import argparse
from contextlib import contextmanager
import hashlib
import json
import math
import os
import platform
import re
import signal
import subprocess
import time


def atomic_json(path, value):
    tmp = path.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)


@contextmanager
def exclusive(path):
    """OS lock releases on death; stale journal entries never imply safe replay."""
    with path.open("a+b") as stream:
        if os.name == "nt":
            import msvcrt
            if stream.tell() == 0:
                stream.write(b"0")
                stream.flush()
            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        try:
            yield
        finally:
            if os.name == "nt":
                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(stream, fcntl.LOCK_UN)


def validate(plan):
    if not isinstance(plan, dict) or plan.get("version") != 1:
        raise ValueError("plan version must be 1")
    if not isinstance(plan.get("run_id"), str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", plan["run_id"]):
        raise ValueError("invalid run_id")
    if not isinstance(plan.get("cwd"), str):
        raise ValueError("cwd must be a path string")
    root = Path(plan.get("cwd", ""))
    if not root.is_absolute() or not root.is_dir():
        raise ValueError("cwd must be an existing absolute directory on the target")
    if not isinstance(plan.get("env", {}), dict) or any(
            not isinstance(k, str) or not isinstance(v, str) or not k or "=" in k
            or "\0" in k or "\0" in v for k, v in plan.get("env", {}).items()):
        raise ValueError("env must contain strings")
    steps = plan.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("steps required")
    names = set()
    for step in steps:
        if not isinstance(step, dict):
            raise ValueError("each step must be an object")
        name = step.get("id", "")
        if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", name) or name in names:
            raise ValueError("step ids must be unique safe names")
        names.add(name)
        for key in ("argv", "verify"):
            argv = step.get(key)
            if key == "verify" and argv is None:
                continue
            if not isinstance(argv, list) or not argv or any(not isinstance(a, str) or "\0" in a for a in argv) or not argv[0]:
                raise ValueError(f"{name}: {key} must be a nonempty argv list")
        seconds = step.get("timeout", 1800)
        if isinstance(seconds, bool) or not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or not 0 < seconds <= 86400:
            raise ValueError("timeout must be 0..86400 seconds")
        if "cwd" in step and not isinstance(step["cwd"], str):
            raise ValueError("step cwd must be a path string")
        cwd = Path(step.get("cwd", root))
        if not cwd.is_absolute():
            raise ValueError("step cwd must be absolute")
    return root.resolve()


def execute(argv, cwd, env, timeout, log):
    """A command's exit code cannot be replaced by a later echo/tail result."""
    started = time.time()
    with log.open("wb") as stream:
        try:
            process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                       stdout=stream, stderr=subprocess.STDOUT,
                                       start_new_session=os.name != "nt")
        except OSError as exc:
            stream.write(str(exc).encode("utf-8"))
            return {"status": "failed", "exit": None, "error": str(exc), "log": str(log)}
        timed_out = False
        try:
            code = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                               stdout=stream, stderr=stream, check=False)
            else:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            code = process.wait()
    return {"status": "succeeded" if code == 0 and not timed_out else "failed",
            "exit": code, "timeout": timed_out, "log": str(log),
            "started_at": started, "ended_at": time.time()}


def run(plan, *, retry=None, inspect=False):
    root = validate(plan)
    if retry and retry not in {s["id"] for s in plan["steps"]}:
        raise ValueError("retry must name a failed step")
    fingerprint = hashlib.sha256(json.dumps(plan, sort_keys=True).encode()).hexdigest()
    home = root / "data" / "runtime" / "remote_steps"
    folder = home / plan["run_id"]
    journal = folder / "state.json"
    identity = {"host": platform.node(), "root": str(root), "fingerprint": fingerprint}
    if inspect:
        if not journal.exists():
            return {"status": "not_started", "run_id": plan["run_id"]}
        state = json.loads(journal.read_text(encoding="utf-8"))
        if state["identity"] != identity:
            raise ValueError("plan or target changed; use a new run_id")
        return {**state, "observation": "last_persisted_state", "process_liveness": "not_checked"}
    folder.mkdir(parents=True, exist_ok=True)
    # All plans against this checkout share one lock, not just one run_id.
    with exclusive(home / "execution.lock"):
        if journal.exists():
            state = json.loads(journal.read_text(encoding="utf-8"))
            if state["identity"] != identity:
                raise ValueError("plan or target changed; use a new run_id")
        else:
            state = {"version": 1, "run_id": plan["run_id"], "identity": identity,
                     "status": "running", "steps": {}}
        env = {**os.environ, **plan.get("env", {})}

        def save():
            state["updated_at"] = time.time()
            atomic_json(journal, state)

        for step in plan["steps"]:
            name = step["id"]
            old = state["steps"].get(name, {})
            if old.get("status") in {"running", "interrupted"}:
                old["status"] = "interrupted"
                state.update(status="blocked", blocked_step=name,
                             reason="Execution outcome unknown; inspect processes/effects before a new plan. No automatic replay.")
                save()
                return state
            if old.get("status") == "succeeded":
                # Revalidate effects on resume without repeating installation.
                if step.get("verify"):
                    result = execute(step["verify"], step.get("cwd", str(root)), env,
                                     step.get("timeout", 1800), folder / f"{name}-recheck-{time.time_ns()}.log")
                    old["recheck"] = result
                    if result["status"] != "succeeded":
                        state.update(status="blocked", blocked_step=name, reason="Completed step no longer verifies; inspect before a new plan")
                        save()
                        return state
                continue
            if old.get("status") == "failed" and retry != name:
                state.update(status="failed", blocked_step=name, reason="Explicit --retry STEP required after reviewing failure")
                save()
                return state
            attempt = len(old.get("attempts", [])) + 1
            row = {"status": "running", "attempts": old.get("attempts", []), "attempt": attempt,
                   "log": str(folder / f"{name}-{attempt}.log")}
            state["steps"][name] = row
            state.update(status="running", current_step=name)
            state.pop("blocked_step", None)
            state.pop("reason", None)
            save()  # durable before any side effect
            print(json.dumps({"step": name, "status": "running", "attempt": attempt}), flush=True)
            last = row["attempts"][-1] if row["attempts"] else {}
            if last.get("command_ok") and step.get("verify"):
                result = {k: v for k, v in last.items() if k != "verification"}
                result.update(status="succeeded", reused_command=True)
            else:
                result = execute(step["argv"], step.get("cwd", str(root)), env,
                                 step.get("timeout", 1800), Path(row["log"]))
                result["command_ok"] = result["status"] == "succeeded"
            if result["status"] == "succeeded" and step.get("verify"):
                row["log"] = str(folder / f"{name}-{attempt}-verify.log")
                save()
                result["verification"] = execute(step["verify"], step.get("cwd", str(root)), env,
                                                 step.get("timeout", 1800), Path(row["log"]))
                if result["verification"]["status"] != "succeeded":
                    result["status"] = "failed"
            row["attempts"].append(result)
            row["status"] = result["status"]
            save()
            print(json.dumps({"step": name, **result}), flush=True)
            if row["status"] != "succeeded":
                state.update(status="failed", blocked_step=name)
                save()
                return state
        state.update(status="succeeded", current_step=None)
        state.pop("blocked_step", None)
        state.pop("reason", None)
        save()
        return state


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("plan", type=Path)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--retry", help="Retry only this terminal failed step; never an interrupted step")
    args = parser.parse_args()
    try:
        state = run(json.loads(args.plan.read_text(encoding="utf-8")), retry=args.retry, inspect=args.status)
        print(json.dumps(state, ensure_ascii=False))
        return 0 if args.status or state["status"] == "succeeded" else 1
    except (OSError, ValueError) as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
