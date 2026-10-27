"""R1 장애 주입: 상태 기록 양쪽 사망/관측 불능/직렬화/의도적 종료. 외부 송신 없음."""
import copy
import os
from pathlib import Path

import pytest
from restart_controller import Controller, log
from restart_process import controller_presence, identity
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


@pytest.mark.parametrize("previous_phase", ["STOPPED", "FAILED"])
def test_cold_start_publishes_new_owner_and_preparation_atomically(tmp_path, monkeypatch, previous_phase):
    from restart_protocol import read_json
    from test_remote_boot import probe
    monkeypatch.setattr("restart_controller.signal.signal", lambda *args: None)
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend/app.py").write_text("VALUE = 1\n")
    adapter = Adapter()
    adapter.base, adapter.running = tmp_path, False
    ctl = Controller(tmp_path, tmp_path, adapter)
    ctl.save(phase=previous_phase, generation="old", worker=None,
             controller={"pid": 99999999, "born": 1})
    class Death(BaseException):
        pass
    def prepare(*args, **kwargs):
        state = read_json(ctl.home / "state.json")
        assert state["controller"] == identity(os.getpid())
        assert state["phase"] == "STARTING" and state["generation"] is None
        assert probe.classify(state, state["controller"], None)["status"] == "waiting"
        raise Death()
    monkeypatch.setattr(ctl, "prepare_candidate", prepare)
    with pytest.raises(Death):
        ctl.run(start=True)
    # A new controller can finish the persisted preparation without spawning twice.
    recovered = Controller(tmp_path, tmp_path, adapter)
    ticks(recovered, 4)
    assert recovered.state["phase"] == "ACTIVE" and adapter.spawns == 1
    assert recovered.state["generation"] != "old"


def test_cold_start_preparation_failure_is_terminal_and_does_not_spawn(tmp_path, monkeypatch):
    adapter = Adapter()
    adapter.base, adapter.running = tmp_path, False
    ctl = Controller(tmp_path, tmp_path, adapter)
    ctl.save(phase="STARTING", generation=None, preparing_start=True)
    monkeypatch.setattr(ctl, "prepare_candidate", lambda *a, **k: (_ for _ in ()).throw(ValueError("bad source")))
    ctl.tick()
    assert ctl.state["phase"] == "FAILED" and adapter.spawns == 0
    assert ctl.state["last_result"]["outcome"] == "start_prepare_failed"
    assert "bad source" in ctl.state["last_result"]["error"]


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


def test_source_change_during_drain_does_not_defer_sealed_candidate(setup):
    """2026-10-27 세대 전환: 교체 대상은 봉인 사본이다. drain 중 정본이 바뀌어도 그 후보는 그대로 가고,
    바뀐 정본은 다음 후보가 된다(옛 계약 'artifact_changed_after_check → deferred' 은퇴)."""
    import generation_store as gens
    ctl, adapter, _ = setup
    submit(ctl)
    ticks(ctl, 2)
    assert ctl.state["phase"] == "DRAINING"
    sealed = ctl.state["candidate"]["generation_dir"]
    (ctl.base / "backend/app.py").write_text("value = 2\n")
    ticks(ctl, 6)
    assert ctl.state["phase"] == "ACTIVE" and ctl.state["last_result"]["outcome"] == "restarted"
    assert adapter.spawns == 1 and ctl.state["generation_dir"] == sealed
    # 활성 세대의 바이트는 봉인 때의 것이다 — 편집이 현역 바이트를 바꾸지 않는다(G1).
    assert (Path(sealed) / "backend/app.py").read_text() == "value = 1\n"
    gens.verify(sealed)
    # 바뀐 정본은 정착 뒤 다음 후보가 된다(G1: 저장 후 자동 반영).
    assert gens.execution_inventory(ctl.base)["digest"] != ctl.state["source_digest"]


def test_syntax_failure_keeps_active(setup):
    ctl, adapter, _ = setup
    (ctl.base / "backend/app.py").write_text("if broken syntax\n")
    submit(ctl, artifact_digest=code_manifest(ctl.base)["digest"])
    ticks(ctl, 2)
    assert ctl.state["last_result"]["outcome"] == "check_failed"
    assert not adapter.stops


@pytest.mark.parametrize("moment", ["before_check", "during_drain", "drain_completion"])
def test_superseded_red_reservation_never_stops_active_worker(setup, moment, monkeypatch):
    from restart_red import reservation
    ctl, adapter, _ = setup
    job_path = ctl.base / "data/system_ai_state/repair_sessions/task.apply.json"
    job = {"repo": str(ctl.base), "key": "task", "task_id": "task",
           "scheduled_at": "first", "readiness_hash": "ready"}
    atomic_json(job_path, job)
    atomic_json(job_path.with_name("task.json"), {"status": "apply_scheduled", "scheduled_at": "first"})
    submit(ctl, operation="red_apply", payload={"job_path": str(job_path), "reservation": reservation(job)})
    if moment != "before_check":
        ticks(ctl, 2)
        # 2026-10-27: red_apply 는 현역을 살려 둔 채 PUBLISHING 에서 정본 반영부터 한다(drain 은 그 뒤).
        assert ctl.state["phase"] == "PUBLISHING"
    if moment == "drain_completion":
        helper = adapter.helper
        def reschedule(action, state):
            if action == "apply":
                atomic_json(job_path, {**job, "scheduled_at": "second"})
            return helper(action, state)
        monkeypatch.setattr(adapter, "helper", reschedule)
    else:
        atomic_json(job_path, {**job, "scheduled_at": "second"})
    ticks(ctl)
    assert not adapter.stops and not adapter.spawns and adapter.accepting
    assert ctl.state["phase"] == "ACTIVE"
    # 교체된 예약은 적용 전에 거절된다 — 현역 유지(G2), 수리 세션은 보존.
    assert ctl.state["last_result"]["outcome"] in {"check_failed", "apply_rejected"}


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


def test_rejected_apply_without_live_write_keeps_new_worker_active(setup, monkeypatch):
    """L97-6b(긴문장 97회차): 쓰기 직전 재검증 실패(라이브 무변경)는 복구 불가가 아니라 거절이다 — 작업자를 죽이지 않는다."""
    ctl, adapter, _ = setup
    rejection = {"applied": False, "verified": False, "success": False,
                 "error": "쓰기 직전 재검증 실패(workspace_ready) — 라이브 무변경"}
    def helper(action, state):
        return ({"ok": True, "result": rejection} if action == "apply"
                else {"ok": True, "result": {"verified": False}}), []
    monkeypatch.setattr(adapter, "helper", helper)
    from restart_red import reservation
    job_path = ctl.base / "data/system_ai_state/repair_sessions/task.apply.json"
    job = {"repo": str(ctl.base), "key": "task", "task_id": "task",
           "scheduled_at": "first", "readiness_hash": "ready"}
    atomic_json(job_path, job)
    atomic_json(job_path.with_name("task.json"), {"status": "apply_scheduled", "scheduled_at": "first"})
    submit(ctl, operation="red_apply", payload={"job_path": str(job_path), "reservation": reservation(job)})
    ticks(ctl, 30)
    assert ctl.state["phase"] == "ACTIVE", ctl.state
    assert ctl.state["last_result"]["outcome"] == "apply_rejected"
    assert ctl.state["red_outcome"] == rejection
    # 거절은 현역을 건드리지 않는다 — 정지도 재기동도 없다(G2: 교체 전 실패는 현역 유지).
    assert adapter.running and adapter.accepting and adapter.spawns == 0 and adapter.stops == 0


@pytest.mark.parametrize('operation,outcome', [
    ('red_apply', None), ('red_apply', {}), ('red_apply', {'applied': None}),
    ('red_apply', {'applied': True}), ('red_verify', None),
    ('red_verify', {'applied': False}),
])
def test_failed_verify_without_explicit_apply_rejection_still_recovers(setup, monkeypatch, operation, outcome):
    """미관측 적용·이미 쓴 코드의 검증 실패를 '무변경 거절'로 승격하지 않는다."""
    ctl, adapter, _ = setup
    ctl.start_generation(code_manifest(ctl.code_root))
    ctl.save(request={'operation': operation, 'request_id': 'verify-probe'}, red_outcome=outcome)
    adapter.spawn(ctl.state)
    adapter.accepting = False
    monkeypatch.setattr(adapter, 'helper', lambda *a: ({'ok': True, 'result': {'verified': False}}, []))
    ctl.tick()
    assert ctl.state['phase'] == 'RECOVERING'
    assert ctl.state['recovery_reason'] == 'red_verification_failed'
    assert not adapter.accepting


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))


def test_update_shutdown_drains_work_before_stopping(setup):
    ctl, adapter, _ = setup
    adapter.busy = 1
    submit(ctl, operation='shutdown', policy={'drain_before_shutdown': True, 'drain_timeout_s': 60, 'force': False})
    ticks(ctl, 5)
    assert ctl.state['phase'] == 'DRAINING' and adapter.stops == 0
    assert not (ctl.base / 'data/.intentional_shutdown').exists()
    adapter.busy = 0
    ticks(ctl, 5)
    assert ctl.state['phase'] == 'STOPPED'
    assert ctl.state['last_result']['outcome'] == 'intentional_shutdown'
    assert ctl.state['last_result']['effect_unknown'] is False
    assert adapter.spawns == 0


def test_update_shutdown_timeout_preserves_work_and_reopens_admission(setup):
    ctl, adapter, clock = setup
    adapter.busy = 1
    submit(ctl, operation='shutdown', policy={'drain_before_shutdown': True, 'drain_timeout_s': 1, 'force': False})
    ticks(ctl, 3)
    clock[0] += 2
    ticks(ctl, 5)
    assert ctl.state['phase'] == 'ACTIVE' and adapter.accepting
    assert adapter.stops == 0
    assert ctl.state['last_result']['outcome'] == 'deferred'
    assert not (ctl.base / 'data/.intentional_shutdown').exists()


def test_controller_log_survives_broken_stdout(tmp_path, monkeypatch):
    """2026-10-26: 제어자의 유일한 출력이 print 였고 stdout 은 시작 주체마다 달랐다. 닫힌 파이프가
    tick 예외 보고를 죽음으로 바꾸면 안 되고, 기록은 stdout 과 무관하게 controller.log 에 남아야 한다."""
    class Broken:
        def write(self, _):
            raise BrokenPipeError(32, "Broken pipe")
        def flush(self):
            raise BrokenPipeError(32, "Broken pipe")
    monkeypatch.setattr("sys.stdout", Broken())
    home = control_dir(tmp_path)
    log(home, "tick 예외 보고")
    text = (home / "controller.log").read_text(encoding="utf-8")
    assert "tick 예외 보고" in text and f"pid={os.getpid()}" in text


def test_controller_presence_distinguishes_missing_from_stopped(tmp_path):
    """status·/health 가 공유하는 판정: 죽은 pid 는 그대로 보여 주지 않고 '제어자 부재'로 말한다."""
    import subprocess
    import sys
    gone = subprocess.Popen([sys.executable, "-c", "pass"])
    dead = identity(gone.pid)
    gone.wait()
    me = identity(os.getpid())
    base = tmp_path
    state = {"phase": "ACTIVE", "controller": dead, "worker": me, "updated_at": 50.0, "generation": "g"}
    missing = controller_presence(base, state, now=100.0)
    assert missing["verdict"] == "controller_missing" and missing["revive"] is True
    assert missing["worker_alive"] is True and missing["controller_alive"] is False
    assert missing["state_age_s"] == 50.0
    assert controller_presence(base, dict(state, controller=me))["verdict"] == "controller_alive"
    assert controller_presence(base, dict(state, phase="STOPPED"))["verdict"] == "stopped"
    atomic_json(base / "data/.intentional_shutdown", {})
    assert controller_presence(base, state)["revive"] is False
    assert controller_presence(base, {})["verdict"] == "no_state"


def test_real_boot_verifier_accepts_rejected_session_as_rejection(setup, monkeypatch):
    """거절 뒤 staging인 실제 예약 원장을 통과한다. verify 결과를 가짜로 주지 않는다."""
    from restart_red import reservation, verify_after_boot
    ctl, adapter, _ = setup
    job_path = ctl.base / 'data/system_ai_state/repair_sessions/task.apply.json'
    job = {'repo': str(ctl.base), 'key': 'task', 'task_id': 'task',
           'scheduled_at': 'first', 'readiness_hash': 'ready'}
    atomic_json(job_path, job)
    atomic_json(job_path.with_name('task.json'), {'status': 'apply_scheduled', 'scheduled_at': 'first'})
    rejection = {'applied': False, 'verified': False, 'success': False, 'error': 'input conflict'}
    def helper(action, state):
        if action == 'apply':
            atomic_json(job_path.with_name('task.json'), {'status': 'staging'})
            atomic_json(job_path, {**job, 'controller_apply': rejection})
            return {'ok': True, 'result': rejection}, []
        return {'ok': True, 'result': {'verified': verify_after_boot(ctl.base, state)}}, []
    monkeypatch.setattr(adapter, 'helper', helper)
    submit(ctl, operation='red_apply', payload={'job_path': str(job_path), 'reservation': reservation(job)})
    ticks(ctl, 30)
    assert ctl.state['phase'] == 'ACTIVE' and adapter.running and adapter.accepting
    assert ctl.state['last_result']['outcome'] == 'apply_rejected'
    from restart_protocol import read_json
    assert read_json(job_path)['done_at'] is not None
    # 같은 경로의 다른 예약은 거절 영수증을 빌려 쓸 수 없다.
    state = {**ctl.state, 'request': {'operation': 'red_apply',
             'payload': {'job_path': str(job_path), 'reservation': {**reservation(job), 'scheduled_at': 'other'}}}}
    with pytest.raises(ValueError, match='판본'):
        verify_after_boot(ctl.base, state)
