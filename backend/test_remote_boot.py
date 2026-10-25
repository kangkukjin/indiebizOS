"""Boot observations are bound to controller birth, generation and target root."""
import boot_paths  # noqa: F401
import importlib.util
import io
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("remote_boot", ROOT / "scripts/remote_boot.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def receipt(tmp_path, phase="ACTIVE"):
    return {"controller": {"pid": 42, "born": 100}, "generation": "new", "phase": phase,
            "worker": {"pid": 43, "born": 101}, "code_digest": "digest"}


def test_old_failed_receipt_cannot_fail_new_boot(tmp_path):
    state = receipt(tmp_path, "FAILED")
    expected = {"pid": 42, "born": 200}  # PID reused by the OS
    assert probe.classify(state, expected, None)["status"] == "waiting"
    assert probe.classify(state, state["controller"], "other")["status"] == "waiting"
    assert probe.classify(state, state["controller"], "new")["status"] == "failed"


@pytest.mark.parametrize("change", ["root", "generation", "digest", "ownership", "readiness"])
def test_health_200_alone_cannot_certify_boot(tmp_path, change):
    state = receipt(tmp_path)
    runtime = {"generation": "new", "code_digest": "digest", "ownership": "known", "readiness": "ready"}
    health = {"status": "healthy", "base_path": str(tmp_path)}
    assert probe.classify(state, state["controller"], "new", runtime, health, tmp_path)["status"] == "succeeded"
    if change == "root":
        health["base_path"] = str(tmp_path / "another")
    else:
        runtime[{"digest": "code_digest"}.get(change, change)] = "wrong"
    assert probe.classify(state, state["controller"], "new", runtime, health, tmp_path)["status"] == "waiting"


class Adapter:
    def __init__(self, root, state):
        self.root, self.state, self.calls = root, state, 0
        self.opener = self

    def alive(self, ident):
        return bool(ident)

    def status(self, state):
        self.calls += 1
        return {"generation": "new", "code_digest": "digest", "ownership": "known", "readiness": "ready"}

    def open(self, *args, **kwargs):
        return io.BytesIO(json.dumps({"status": "healthy", "base_path": str(self.root)}).encode())


def persist(root, state):
    p = root / "data/restart_control/state.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state), encoding="utf-8")


def test_current_failure_stops_without_health_poll_or_sleep(tmp_path):
    state = receipt(tmp_path, "FAILED")
    persist(tmp_path, state)
    adapter = Adapter(tmp_path, state)
    result = probe.wait_for_boot(tmp_path, ROOT, state["controller"], adapter=adapter,
                                 sleep=lambda _: pytest.fail("waited after definite failure"))
    assert result["status"] == "failed" and adapter.calls == 0


def test_new_starting_after_old_failure_then_verified_active(tmp_path):
    state = receipt(tmp_path)
    old = {**state, "phase": "FAILED", "controller": {"pid": 41, "born": 1}}
    persist(tmp_path, old)
    tick = [0]
    def sleep(_):
        tick[0] += 1
        persist(tmp_path, {**state, "phase": "STARTING" if tick[0] == 1 else "ACTIVE"})
    result = probe.wait_for_boot(tmp_path, ROOT, state["controller"], adapter=Adapter(tmp_path, state),
                                 clock=lambda: tick[0], sleep=sleep, timeout=10)
    assert result["status"] == "succeeded" and tick[0] == 2


def test_restart_during_http_observation_invalidates_success(tmp_path):
    state = receipt(tmp_path)
    persist(tmp_path, state)
    adapter = Adapter(tmp_path, state)
    original = adapter.open
    def opening(*args, **kwargs):
        persist(tmp_path, {**state, "generation": "next", "phase": "STARTING"})
        return original(*args, **kwargs)
    adapter.open = opening
    tick = [0]
    result = probe.wait_for_boot(tmp_path, ROOT, state["controller"], adapter=adapter, timeout=1,
                                 clock=lambda: tick[0], sleep=lambda _: tick.__setitem__(0, 2))
    assert result["status"] == "timeout" and result["reason"] == "state_changed_during_probe"


def test_spawned_windows_launcher_can_bind_its_actual_controller(tmp_path):
    state = receipt(tmp_path)
    persist(tmp_path, state)
    launcher = {'pid': 40, 'born': 99}
    adapter = Adapter(tmp_path, state)
    adapter.tree = lambda ident: [launcher, state['controller'], state['worker']]
    out = probe.wait_for_boot(tmp_path, ROOT, launcher, launcher=launcher, adapter=adapter,
                              sleep=lambda _: pytest.fail('verified child was not recognized'))
    assert out['status'] == 'succeeded' and out['controller'] == state['controller']


@pytest.mark.parametrize('other', [{'pid': 42, 'born': 99}, {'pid': 77, 'born': 100}])
def test_launcher_never_adopts_reused_or_unrelated_controller(tmp_path, other):
    state = receipt(tmp_path)
    persist(tmp_path, state)
    launcher = {'pid': 40, 'born': 99}
    adapter = Adapter(tmp_path, state)
    adapter.tree = lambda ident: [launcher, other]
    tick = [0]
    out = probe.wait_for_boot(tmp_path, ROOT, launcher, launcher=launcher, adapter=adapter,
                              timeout=1, clock=lambda: tick[0], sleep=lambda _: tick.__setitem__(0, 2))
    assert out['status'] == 'timeout' and out['reason'] == 'different_controller'
    assert adapter.calls == 0


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
