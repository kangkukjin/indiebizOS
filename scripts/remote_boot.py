#!/usr/bin/env python3
"""Observe one controller identity/generation; never launch, stop or retry it."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
import boot_paths  # noqa: F401,E402

import argparse
import json
import time

from restart_process import ProcessAdapter, identity
from restart_protocol import control_dir, read_json


def classify(state, controller, generation, runtime=None, health=None, base=None):
    """Old receipts cannot fail or certify a new boot. No credentials in output."""
    if state.get("controller") != controller:
        return {"status": "waiting", "reason": "different_controller"}
    if generation and state.get("generation") != generation:
        return {"status": "waiting", "reason": "different_generation"}
    phase = state.get("phase")
    observed = {"phase": phase, "generation": state.get("generation"),
                "controller": controller, "worker": state.get("worker")}
    if phase in {"FAILED", "STOPPED"}:
        return {**observed, "status": "failed", "reason": "controller_" + phase.lower()}
    if phase != "ACTIVE":
        return {**observed, "status": "waiting", "reason": "not_active"}
    runtime = runtime or {}
    if (not state.get("generation") or runtime.get("generation") != state["generation"]
            or runtime.get("code_digest") != state.get("code_digest")
            or runtime.get("ownership") != "known"
            or runtime.get("readiness") not in {"ready", "degraded"}):
        return {**observed, "status": "waiting", "reason": "runtime_not_verified"}
    health = health or {}
    if (health.get("status") != "healthy" or not health.get("base_path")
            or Path(health["base_path"]).resolve() != Path(base).resolve()):
        return {**observed, "status": "waiting", "reason": "health_root_not_verified"}
    return {**observed, "status": "succeeded", "readiness": runtime["readiness"],
            "scope": "backend boot; models and Electron require separate checks"}


def wait_for_boot(base, code_root, controller, *, generation=None, port=8765, timeout=300,
                  interval=1, adapter=None, clock=time.monotonic, sleep=time.sleep,
                  launcher=None):
    base = Path(base)
    adapter = adapter or ProcessAdapter(base, code_root, port)
    start = clock()
    last = {"status": "waiting", "reason": "no_state"}
    while clock() - start < timeout:
        if not adapter.alive(controller):
            return {"status": "failed", "reason": "controller_exited", "controller": controller}
        state = read_json(control_dir(base) / "state.json", {})
        # Windows venv python.exe can be a redirector. Only adopt the recorded
        # controller when it belongs to the process tree we actually spawned.
        # A live but unrelated controller or a reused PID remains untrusted.
        if launcher and controller == launcher:
            candidate = state.get("controller")
            if candidate and candidate != controller and candidate in adapter.tree(launcher):
                controller = candidate
        last = classify(state, controller, generation)
        if last["status"] == "failed":
            return last
        if last["reason"] == "runtime_not_verified":
            runtime = adapter.status(state)
            try:
                with adapter.opener.open(f"http://127.0.0.1:{port}/health", timeout=3) as response:
                    health = json.load(response)
            except (OSError, ValueError):
                health = {}
            last = classify(state, controller, generation, runtime, health, base)
            # Re-read after the HTTP calls: a concurrent restart invalidates this observation.
            latest = read_json(control_dir(base) / "state.json", {})
            if any(latest.get(k) != state.get(k) for k in ("controller", "generation", "phase", "worker")):
                last = {"status": "waiting", "reason": "state_changed_during_probe"}
            elif last["status"] == "succeeded" and adapter.alive(controller) and adapter.alive(state.get("worker")):
                return last
        sleep(interval)
    return {**last, "status": "timeout", "seconds": clock() - start}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--controller-pid", type=int, required=True)
    parser.add_argument("--generation")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--timeout", type=float, default=300)
    args = parser.parse_args()
    if args.timeout <= 0 or not 1 <= args.port <= 65535:
        parser.error("positive timeout and port 1..65535 required")
    try:
        result = wait_for_boot(args.root, args.root, identity(args.controller_pid),
                               generation=args.generation, port=args.port, timeout=args.timeout)
    except Exception as exc:
        result = {"status": "failed", "reason": type(exc).__name__}
    print(json.dumps(result, ensure_ascii=True))
    return 0 if result["status"] == "succeeded" else 2


if __name__ == "__main__":
    raise SystemExit(main())
