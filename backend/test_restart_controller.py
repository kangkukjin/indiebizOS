"""R1 장애 주입: 상태 기록 양쪽 사망/관측 불능/직렬화/의도적 종료. 외부 송신 없음."""
import copy
from pathlib import Path

import pytest
from restart_controller import Controller
from restart_protocol import atomic_json, code_manifest, control_dir, request


class Adapter:
    def __init__(self):
        self.running = True
        self.accepting = True
        self.unknown = False
        self.busy = 0
        self.boot_failure = False
        self.occupied = False
        self.spawns = 0
        self.stops = 0
        self.received = None

    def alive(self, ident):
        return self.running if ident else False

    def tree(self, ident):
        return [ident] if self.alive(ident) else []

    def status(self, state):
        if self.unknown:
            return {"ownership": "unknown"}
        return {"generation": state["generation"], "code_digest": state["code_digest"],
                "ownership": "known", "readiness": "failed" if self.boot_failure else "ready",
                "active_roots": self.busy, "active_children": 0, "pending_finalizers": 0,
                "accepting": self.accepting, "owners": [{"id": "work"}] if self.busy else []}

    def command(self, state, action):
        if self.unknown:
            raise TimeoutError("slow response")
        self.accepting = action == "activate"
        return {"accepting": self.accepting}

    def spawn(self, state):
        self.spawns += 1
        self.running = True
        self.received = {"pid": 12, "born": 2, "nonce": state["generation"]}

    def receipt(self, state):
        return self.received if self.running else None

    def permit(self, state):
        pass

    def helper(self, action, state):
        from restart_red import apply_job, verify_after_boot
        if action == "apply":
            value = apply_job(self.base, state["request"]["payload"]["job_path"])
        else:
            value = {"verified": verify_after_boot(self.base, state)}
        return {"ok": True, "result": value}, []

    def port_free(self):
        return not self.occupied

    def stop(self, state, force=False):
        self.stops += 1
        self.running = False

    def stopped(self, state):
        return not self.running


@pytest.fixture
def setup(tmp_path):
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend/app.py").write_text("value = 1\n")
    adapter = Adapter()
    adapter.base = tmp_path
    clock = [100.0]
    controller = Controller(tmp_path, tmp_path, adapter, clock=lambda: clock[0])
    manifest = code_manifest(tmp_path)
    controller.save(phase="ACTIVE", generation="g1", worker={"pid": 11, "born": 1},
                    code_digest=manifest["digest"], control_token="test")
    return controller, adapter, clock


def ticks(controller, count=15):
    for _ in range(count):
        controller.tick()


def submit(controller, **kw):
    return request(controller.base, "test", **kw)


def test_serial_idempotent_and_stale_generation(setup):
    ctl, adapter, _ = setup
    req = submit(ctl, request_id="same")
    ticks(ctl)
    assert adapter.spawns == 1 and ctl.state["last_result"]["outcome"] == "restarted"
    submit(ctl, request_id="same")
    ticks(ctl)
    assert adapter.spawns == 1
    submit(ctl, request_id="old", expected_generation="g1")
    ticks(ctl)
    assert ctl.state["last_result"]["outcome"] == "stale_generation"
    assert adapter.spawns == 1


def test_busy_deadline_restores_admission_without_cutting(setup):
    ctl, adapter, now = setup
    adapter.busy = 1
    submit(ctl, policy={"drain_timeout_s": 1, "force": False})
    ticks(ctl, 3)
    assert not adapter.accepting and ctl.state["phase"] == "DRAINING"
    now[0] += 2
    ticks(ctl, 3)
    assert adapter.accepting and not adapter.stops
    assert ctl.state["last_result"]["outcome"] == "deferred"
    assert ctl.state["last_owners"]["active_roots"] == 1


def test_slow_is_not_dead_and_unknown_drain_defers(setup):
    ctl, adapter, now = setup
    submit(ctl, policy={"drain_timeout_s": 1, "force": False})
    ticks(ctl, 2)
    adapter.unknown = True
    now[0] += 5
    ctl.tick()
    assert ctl.state["resume_pending"] and not adapter.stops
    adapter.unknown = False
    ticks(ctl, 2)
    assert adapter.accepting and ctl.state["last_result"]["outcome"] == "deferred"


def test_force_records_cut_only_after_actual_death(setup, monkeypatch):
    ctl, adapter, now = setup
    adapter.busy = 1
    records = []
    monkeypatch.setattr("restart_red.record_interrupted", lambda *args: records.append(args))
    submit(ctl, policy={"drain_timeout_s": 1, "force": True})
    ticks(ctl, 3)
    now[0] += 2
    ctl.tick()
    assert ctl.state["phase"] == "STOPPING" and not records and adapter.running
    original_stop = adapter.stop
    monkeypatch.setattr(adapter, "stop", lambda *args, **kw: None)
    ctl.tick()
    assert not records and adapter.running
    monkeypatch.setattr(adapter, "stop", original_stop)
    ctl.tick()
    assert records and not adapter.running
    assert ctl.state["effect_unknown"] and ctl.state["interrupted_owners"] == [{"id": "work"}]


def test_force_never_converts_unknown_to_zero(setup):
    ctl, adapter, now = setup
    submit(ctl, policy={"drain_timeout_s": 1, "force": True})
    ticks(ctl, 2)
    adapter.unknown = True
    now[0] += 2
    ctl.tick()
    assert ctl.state["resume_pending"] and not adapter.stops


def test_failed_red_post_verification_never_reports_healthy(tmp_path, monkeypatch):
    from restart_protocol import read_json
    from restart_red import verify_after_boot
    from types import SimpleNamespace
    manifest = tmp_path / "data/system_ai_state/red_backups/test/manifest.json"
    job = tmp_path / "data/system_ai_state/repair_sessions/test.apply.json"
    atomic_json(manifest, {"files": {"backend/app.py": "before.py"}})
    atomic_json(job, {"repo": str(tmp_path), "key": "test", "verify_cmd": "false"})
    monkeypatch.setattr("red_apply._run_post_verify", lambda *a: {"ran": True, "exit_code": 1})
    staging = SimpleNamespace(task_key=lambda x: x, write_followup=lambda *a: None)
    monkeypatch.setattr("red_apply._load_handler", lambda *a: SimpleNamespace(_staging_mod=lambda: staging))
    state = {"generation": "new", "request": {"operation": "red_apply", "payload": {
        "manifest_path": str(manifest), "job_path": str(job)}}}
    assert verify_after_boot(tmp_path, state) is False
    result = read_json(manifest.with_name("result.json"))
    assert result["outcome"] == "verification_failed" and result["recovered"] is False


def test_manifest_drift_requires_new_check(setup):
    ctl, adapter, _ = setup
    submit(ctl)
    ticks(ctl, 2)
    (ctl.base / "backend/app.py").write_text("value = 2\n")
    ticks(ctl, 2)
    assert ctl.state["last_result"]["outcome"] == "deferred"
    assert not adapter.stops and adapter.accepting


def test_syntax_failure_keeps_active(setup):
    ctl, adapter, _ = setup
    (ctl.base / "backend/app.py").write_text("if broken syntax\n")
    submit(ctl, artifact_digest=code_manifest(ctl.base)["digest"])
    ticks(ctl, 2)
    assert ctl.state["last_result"]["outcome"] == "check_failed"
    assert not adapter.stops


def test_crash_does_not_replay_user_work(setup):
    ctl, adapter, _ = setup
    ctl.save(last_owners={"active_roots": 1, "live_episode_ids": []})
    adapter.running = False
    ticks(ctl)
    assert adapter.spawns == 1 and ctl.state["phase"] == "ACTIVE"
    # 제어자가 워커 세대만 복구하며 어떠한 사용자 실행 요청도 발급하지 않는다.
    assert not list((ctl.home / "requests").glob("*.json"))


def test_intentional_shutdown_at_starting_never_resurrects(setup):
    ctl, adapter, _ = setup
    submit(ctl)
    ticks(ctl, 4)
    atomic_json(ctl.base / "data/.intentional_shutdown", {"reason": "all_windows_closed"})
    ticks(ctl)
    assert ctl.state["phase"] == "STOPPED" and not adapter.running
    assert not adapter.spawns


def test_port_occupant_is_not_killed(setup):
    ctl, adapter, _ = setup
    submit(ctl)
    ticks(ctl, 4)
    adapter.occupied = True
    ctl.tick()
    assert ctl.state["phase"] == "FAILED" and not adapter.spawns


def test_boot_failure_without_compatible_backup_is_failed(setup):
    ctl, adapter, _ = setup
    submit(ctl)
    ticks(ctl, 4)
    adapter.boot_failure = True
    ticks(ctl)
    assert ctl.state["phase"] == "FAILED" and not adapter.running


@pytest.mark.parametrize("edge", ["before", "after"])
@pytest.mark.parametrize("phase", ["CHECKING", "DRAINING", "STOPPING", "STARTING", "ACTIVE", "RECOVERING", "FAILED", "STOPPED"])
def test_controller_death_around_state_write(setup, edge, phase):
    ctl, adapter, _ = setup
    submit(ctl)
    crashed = []
    class Death(BaseException):
        pass
    def fault(at, stage):
        if at == edge and stage == phase and not crashed:
            crashed.append(True)
            raise Death()
    ctl.fault = fault
    if phase in {"RECOVERING", "FAILED"}:
        adapter.boot_failure = True
    if phase == "STOPPED":
        atomic_json(ctl.base / "data/.intentional_shutdown", {})
    try:
        ticks(ctl)
    except Death:
        ctl = Controller(ctl.base, ctl.code_root, adapter, clock=ctl.clock)
        ticks(ctl)
    assert crashed, (edge, phase)
    assert ctl.state["phase"] in {"ACTIVE", "FAILED", "STOPPED"}
    assert adapter.spawns <= 1
    if ctl.state["phase"] == "ACTIVE":
        assert adapter.accepting and adapter.running


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
