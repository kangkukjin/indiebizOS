"""세대 기반 제어자(G1·G2·G6): 저장→후보→교체, 교체 후 실패→직전 세대 복구, 수리 반영은 현역을 살린다.

외부 송신 없음. 프로세스는 test_restart_controller.Adapter 대역. 실제 프로세스 시험은 test_restart_process.
"""
import json
import os
from pathlib import Path

import pytest
import boot_paths  # noqa: F401
import generation_store as gens
import restart_candidates
from restart_controller import Controller
from restart_protocol import atomic_json, control_dir, read_json, request
from test_restart_controller import Adapter, ticks


@pytest.fixture
def setup(tmp_path, monkeypatch):
    monkeypatch.delenv("INDIEBIZ_PRODUCTION", raising=False)
    (tmp_path / "backend").mkdir()
    (tmp_path / "backend/app.py").write_text("value = 1\n")
    adapter = Adapter()
    adapter.base = tmp_path
    clock = [100.0]
    ctl = Controller(tmp_path, tmp_path, adapter, clock=lambda: clock[0])
    # 첫 세대: 정본에서 봉인해 ACTIVE 로 둔다(제어자 start 와 같은 경로).
    candidate = ctl.prepare_candidate("fixture")
    ctl.save(phase="ACTIVE", generation="g1", worker={"pid": 11, "born": 1}, control_token="test",
             code_digest=candidate["generation"], generation_dir=candidate["generation_dir"],
             source_digest=candidate["source_digest"])
    return ctl, adapter, clock


def advance(clock, seconds):
    clock[0] += seconds


def settle(ctl, clock):
    """감시가 변경을 관측하고(1차 재고) 정착(2초)까지 기다린 뒤 후보를 준비하는 두 번의 재고 — 가짜 시계라 시간을 손으로 민다."""
    advance(clock, 3); ticks(ctl, 1)
    advance(clock, 3); ticks(ctl, 1)


def test_saved_edit_becomes_next_generation_without_commit(setup):
    """G1: 저장 → 정착 → 봉인 후보 → 교체. 활성 세대 바이트는 봉인 때 그대로."""
    ctl, adapter, clock = setup
    first = ctl.state["generation_dir"]
    (ctl.base / "backend/app.py").write_text("value = 2\n")
    ticks(ctl, 2)                       # 변경 관측(정착 대기 시작)
    assert ctl.state["watch"]["digest"] and not ctl.state.get("candidate")
    advance(clock, 3)                   # 정착
    ticks(ctl, 1)
    assert ctl.state["candidate"]["kind"] == "development"
    sealed = ctl.state["candidate"]["generation_dir"]
    assert (Path(sealed) / "backend/app.py").read_text() == "value = 2\n"
    ticks(ctl, 8)
    assert ctl.state["phase"] == "ACTIVE" and ctl.state["last_result"]["outcome"] == "restarted"
    assert ctl.state["generation_dir"] == sealed and adapter.spawns == 1
    assert ctl.state["previous"]["generation_dir"] == first
    assert ctl.state["source_digest"] == gens.execution_inventory(ctl.base)["digest"]
    gens.verify(sealed)
    gens.verify(first)                  # 직전 세대는 복구용으로 보존된다


def test_syntax_error_keeps_active_and_is_not_retried_until_source_changes(setup):
    """G2: 교체 전 실패(사전검사)는 현역 유지. 같은 입력은 다시 시도하지 않는다."""
    ctl, adapter, clock = setup
    (ctl.base / "backend/app.py").write_text("if broken\n")
    ticks(ctl, 2); advance(clock, 3); ticks(ctl, 3)
    failed = ctl.state["failed_sources"]
    assert len(failed) == 1 and next(iter(failed.values()))["outcome"] == "check_failed"
    assert adapter.spawns == 0 and adapter.stops == 0 and ctl.state["phase"] == "ACTIVE"
    advance(clock, 5); ticks(ctl, 3)
    assert adapter.spawns == 0 and not ctl.state.get("candidate")
    (ctl.base / "backend/app.py").write_text("value = 3\n")   # 고치면 다음 후보가 된다
    settle(ctl, clock); ticks(ctl, 10)
    assert adapter.spawns == 1 and ctl.state["last_result"]["outcome"] == "restarted"


def test_boot_failure_rolls_back_to_previous_generation_and_marks_source(setup):
    """G2: 교체 후 실패는 직전 정상 세대 복구. 실패한 원천은 변경 전까지 재시도하지 않는다."""
    ctl, adapter, clock = setup
    first = ctl.state["generation_dir"]
    (ctl.base / "backend/app.py").write_text("value = 2\n")
    ticks(ctl, 2); advance(clock, 3); ticks(ctl, 1)
    bad = ctl.state["candidate"]
    adapter.boot_failure = True
    spawned = []
    original = adapter.spawn
    def spawn(state):
        spawned.append(state["generation_dir"])
        adapter.boot_failure = state["generation_dir"] == bad["generation_dir"]
        original(state)
    adapter.spawn = spawn
    ticks(ctl, 14)
    assert ctl.state["phase"] == "ACTIVE", ctl.state["phase"]
    assert ctl.state["last_result"]["outcome"] == "rolled_back"
    assert ctl.state["generation_dir"] == first and spawned == [bad["generation_dir"], first]
    assert bad["source_digest"] in ctl.state["failed_sources"]
    assert ctl.state["failed_candidate"]["code_digest"] == bad["generation"]
    # 고장난 원천은 다시 후보가 되지 않는다; 정본이 바뀌어야 한다.
    advance(clock, 5); ticks(ctl, 4)
    assert not ctl.state.get("candidate") and len(spawned) == 2


def test_second_failure_after_rollback_is_failed_not_loop(setup):
    ctl, adapter, clock = setup
    (ctl.base / "backend/app.py").write_text("value = 2\n")
    ticks(ctl, 2); advance(clock, 3); ticks(ctl, 1)
    adapter.boot_failure = True
    ticks(ctl, 20)
    assert ctl.state["phase"] == "FAILED" and ctl.state["last_result"]["outcome"] == "recovery_unavailable"
    assert adapter.spawns == 2


def test_crash_relaunches_same_sealed_generation(setup):
    ctl, adapter, clock = setup
    gen = ctl.state["generation_dir"]
    (ctl.base / "backend/app.py").write_text("value = 2\n")   # 정본은 바뀌었지만
    adapter.running = False
    ticks(ctl, 8)
    assert ctl.state["phase"] == "ACTIVE" and ctl.state["generation_dir"] == gen
    assert (Path(gen) / "backend/app.py").read_text() == "value = 1\n"   # 크래시 복구는 검증된 같은 세대


def test_edits_during_swap_become_next_candidate_not_a_cancel(setup):
    ctl, adapter, clock = setup
    (ctl.base / "backend/app.py").write_text("value = 2\n")
    ticks(ctl, 2); advance(clock, 3); ticks(ctl, 3)
    assert ctl.state["phase"] in {"CHECKING", "DRAINING"}
    sealed = ctl.state["candidate"]["generation_dir"]
    (ctl.base / "backend/app.py").write_text("value = 3\n")       # 교체 중 또 저장
    ticks(ctl, 8)
    assert ctl.state["generation_dir"] == sealed and ctl.state["last_result"]["outcome"] == "restarted"
    settle(ctl, clock); ticks(ctl, 10)
    assert (Path(ctl.state["generation_dir"]) / "backend/app.py").read_text() == "value = 3\n"
    assert adapter.spawns == 2


def test_production_mode_does_not_watch_files(setup, monkeypatch):
    ctl, adapter, clock = setup
    monkeypatch.setenv("INDIEBIZ_PRODUCTION", "1")
    (ctl.base / "backend/app.py").write_text("value = 2\n")
    ticks(ctl, 2); advance(clock, 3); ticks(ctl, 5)
    assert adapter.spawns == 0 and not ctl.state.get("candidate")


def _schedule_job(ctl, applied=True):
    from restart_red import reservation
    job_path = ctl.base / "data/system_ai_state/repair_sessions/task.apply.json"
    job = {"repo": str(ctl.base), "key": "task", "task_id": "task", "scheduled_at": "first", "readiness_hash": "ready"}
    atomic_json(job_path, job)
    atomic_json(job_path.with_name("task.json"), {"status": "apply_scheduled", "scheduled_at": "first", "root_task_id": "task"})
    return job_path, job, reservation(job)


def test_repair_publish_keeps_worker_then_swaps_to_candidate_with_commit(setup, monkeypatch):
    """§5.3: 반영·각인 → 그 정본으로 후보 → 교체. 반영 중 현역은 계속 서비스한다."""
    ctl, adapter, clock = setup
    job_path, job, res = _schedule_job(ctl)
    phases = []
    def helper(action, state):
        phases.append((action, state["phase"], adapter.running, adapter.accepting))
        if action == "apply":
            (ctl.base / "backend/app.py").write_text("value = 'repaired'\n")
            atomic_json(job_path, {**job, "controller_apply": {"applied": True}})
            return {"ok": True, "result": {"applied": True, "verified": True, "success": True,
                                           "commit": {"success": True, "commit": "abc123"},
                                           "published_files": {"backend/app.py": gens._sha(ctl.base / "backend/app.py")}}}, []
        return {"ok": True, "result": {"verified": True}}, []
    monkeypatch.setattr(adapter, "helper", helper)
    request(ctl.base, "red_apply", operation="red_apply", payload={"job_path": str(job_path), "reservation": res})
    ticks(ctl, 3)
    assert phases[0] == ("apply", "PUBLISHING", True, True)
    assert adapter.stops == 0
    ticks(ctl, 10)
    assert ctl.state["phase"] == "ACTIVE" and ctl.state["last_result"]["outcome"] == "restarted"
    assert (Path(ctl.state["generation_dir"]) / "backend/app.py").read_text() == "value = 'repaired'\n"
    assert ("verify", "STARTING", True, False) in phases or any(p[0] == "verify" for p in phases)
    manifest = gens.read_manifest(ctl.state["generation_dir"])
    assert manifest["extra"]["commit"] == "abc123" and manifest["extra"]["reason"] == "red_apply"
    import repair_root
    assert repair_root.projection(ctl.base, 'task')['stage'] == 'activate'
    assert ctl.state['red_job_path'] is None


def test_repair_publish_conflict_after_commit_keeps_active_without_swap(setup, monkeypatch):
    ctl, adapter, clock = setup
    job_path, job, res = _schedule_job(ctl)
    def helper(action, state):
        (ctl.base / "backend/app.py").write_text("value = 'repaired'\n")
        sha = gens._sha(ctl.base / "backend/app.py")
        (ctl.base / "backend/app.py").write_text("value = 'someone else'\n")   # 반영 뒤 타인이 같은 경로를 바꿈
        return {"ok": True, "result": {"applied": True, "commit": {"success": True, "commit": "abc"},
                                       "published_files": {"backend/app.py": sha}}}, []
    monkeypatch.setattr(adapter, "helper", helper)
    request(ctl.base, "red_apply", operation="red_apply", payload={"job_path": str(job_path), "reservation": res})
    ticks(ctl, 6)
    assert ctl.state["phase"] == "ACTIVE" and ctl.state["last_result"]["outcome"] == "publish_conflict"
    assert adapter.spawns == 0 and adapter.stops == 0


@pytest.mark.parametrize('case', ['commit_failed', 'file_missing', 'deleted_reappears'])
def test_rejected_publication_keeps_active_and_watcher_cannot_bypass_it(setup, monkeypatch, case):
    ctl, adapter, clock = setup
    original = ctl.state['generation_dir']
    job_path, job, res = _schedule_job(ctl)
    def helper(action, state):
        assert action == 'apply'
        path = ctl.base / 'backend/app.py'
        path.write_text('value = 2\n')
        out = {'applied': True, 'commit': {'success': True, 'commit': 'abc'},
               'published_files': {'backend/app.py': gens._sha(path)}, 'deleted_files': []}
        if case == 'commit_failed':
            out['commit'] = {'success': False, 'error': 'index locked'}
        elif case == 'file_missing':
            path.unlink()
        else:
            out.update(published_files={}, deleted_files=['backend/app.py'])
        return {'ok': True, 'result': out}, []
    monkeypatch.setattr(adapter, 'helper', helper)
    request(ctl.base, 'red_apply', operation='red_apply', payload={'job_path': str(job_path), 'reservation': res})
    ticks(ctl, 6)
    expected = 'publish_commit_failed' if case == 'commit_failed' else 'publish_conflict'
    assert ctl.state['last_result']['outcome'] == expected
    settle(ctl, clock)
    ticks(ctl, 12)
    assert ctl.state['phase'] == 'ACTIVE' and ctl.state['generation_dir'] == original
    assert adapter.stops == adapter.spawns == 0
    import repair_root
    view = repair_root.projection(ctl.base, 'task')
    assert view['repair_outcome'] == expected and view['service_health'] == 'unchanged_active'
    assert view['resume_condition']


def test_unrelated_restart_does_not_reopen_completed_repair(setup):
    import repair_root
    ctl, adapter, clock = setup
    job_path, job, res = _schedule_job(ctl)
    repair_root.close(ctl.base, 'task', complete=True, reason='verified')
    before = repair_root.read(ctl.base, 'task')
    # 상태 파일에 옛 경로가 남은 제어자도 다음 일반 재기동에서 회수해야 한다.
    ctl.save(red_job_path=str(job_path))
    request(ctl.base, 'ordinary restart')
    ticks(ctl, 12)
    assert ctl.state['last_result']['outcome'] == 'restarted'
    assert repair_root.read(ctl.base, 'task') == before


def test_helper_death_during_publish_keeps_worker_and_recovers_canonical(setup, monkeypatch):
    ctl, adapter, clock = setup
    job_path, job, res = _schedule_job(ctl)
    monkeypatch.setattr(adapter, "helper", lambda action, state: ({"ok": False, "error": "RED 수행자 사망; 자동 재실행하지 않음"}, []))
    monkeypatch.setattr("restart_red.recover_code", lambda base, state: True)
    request(ctl.base, "red_apply", operation="red_apply", payload={"job_path": str(job_path), "reservation": res})
    ticks(ctl, 6)
    assert ctl.state["phase"] == "ACTIVE" and ctl.state["last_result"]["outcome"] == "apply_interrupted_recovered"
    assert adapter.running and adapter.spawns == 0 and adapter.stops == 0


def test_intentional_shutdown_during_publish_stops_without_new_generation(setup, monkeypatch):
    ctl, adapter, clock = setup
    job_path, job, res = _schedule_job(ctl)
    monkeypatch.setattr(adapter, "helper", lambda action, state: (None, []))   # 수행자 진행 중
    request(ctl.base, "red_apply", operation="red_apply", payload={"job_path": str(job_path), "reservation": res})
    ticks(ctl, 2)
    assert ctl.state["phase"] == "PUBLISHING"
    atomic_json(ctl.base / "data/.intentional_shutdown", {})
    ticks(ctl, 3)
    assert ctl.state["phase"] == "STOPPED" and adapter.spawns == 0


def test_repair_boot_failure_rolls_back_but_keeps_committed_canonical(setup, monkeypatch):
    """각인된 수리의 활성 실패: 서비스는 직전 세대, 정본 커밋은 되감지 않는다(후속 커밋의 몫)."""
    ctl, adapter, clock = setup
    first = ctl.state["generation_dir"]
    job_path, job, res = _schedule_job(ctl)
    def helper(action, state):
        if action == "apply":
            (ctl.base / "backend/app.py").write_text("value = 'bad repair'\n")
            return {"ok": True, "result": {"applied": True, "commit": {"success": True, "commit": "abc"},
                                           "published_files": {"backend/app.py": gens._sha(ctl.base / "backend/app.py")}}}, []
        return {"ok": True, "result": {"verified": False}}, []
    monkeypatch.setattr(adapter, "helper", helper)
    restored = []
    monkeypatch.setattr("restart_red.recover_code", lambda base, state: restored.append(1) or True)
    request(ctl.base, "red_apply", operation="red_apply", payload={"job_path": str(job_path), "reservation": res})
    ticks(ctl, 25)
    assert ctl.state["phase"] == "ACTIVE" and ctl.state["last_result"]["outcome"] == "rolled_back"
    assert ctl.state["generation_dir"] == first and not restored
    assert (ctl.base / "backend/app.py").read_text() == "value = 'bad repair'\n"
    assert ctl.state["canonical_recovered"] is None


def test_red_verify_boot_failure_restores_uncommitted_canonical(setup, monkeypatch):
    ctl, adapter, clock = setup
    (ctl.base / "backend/app.py").write_text("value = 'direct write'\n")
    restored = []
    monkeypatch.setattr("restart_red.recover_code", lambda base, state: restored.append(state["request"]["operation"]) or True)
    request(ctl.base, "red_verify", operation="red_verify", payload={"manifest_path": str(ctl.base / "data/system_ai_state/red_backups/x/manifest.json")})
    adapter.boot_failure = True
    original = adapter.spawn
    def spawn(state):
        adapter.boot_failure = state.get("rollback_attempted") is False
        original(state)
    adapter.spawn = spawn
    ticks(ctl, 25)
    assert ctl.state["last_result"]["outcome"] == "rolled_back" and restored == ["red_verify"]


@pytest.mark.parametrize("edge", ["before", "after"])
def test_controller_death_around_publishing_write(setup, edge):
    ctl, adapter, clock = setup
    job_path, job, res = _schedule_job(ctl)
    def helper(action, state):
        if action == "apply":
            (ctl.base / "backend/app.py").write_text("value = 'repaired'\n")
            return {"ok": True, "result": {"applied": True, "commit": {"success": True, "commit": "abc"},
                                           "published_files": {"backend/app.py": gens._sha(ctl.base / "backend/app.py")}}}, []
        return {"ok": True, "result": {"verified": True}}, []
    adapter.helper = helper
    request(ctl.base, "red_apply", operation="red_apply", payload={"job_path": str(job_path), "reservation": res})
    crashed = []
    class Death(BaseException):
        pass
    def fault(at, stage):
        if at == edge and stage == "PUBLISHING" and not crashed:
            crashed.append(True)
            raise Death()
    ctl.fault = fault
    try:
        ticks(ctl, 20)
    except Death:
        ctl = Controller(ctl.base, ctl.code_root, adapter, clock=ctl.clock)
        ticks(ctl, 20)
    assert crashed and ctl.state["phase"] == "ACTIVE"
    assert adapter.spawns <= 1 and adapter.running and adapter.accepting


def test_state_compact_and_results_carry_generation_identity(setup):
    ctl, adapter, clock = setup
    request(ctl.base, "cli", request_id="r1")
    ticks(ctl, 10)
    result = read_json(control_dir(ctl.base) / "results/r1.json")
    assert result["code_digest"] == ctl.state["code_digest"] and result["generation_dir"] == ctl.state["generation_dir"]
    from restart_controller import compact_status
    out = compact_status(ctl.state)
    assert "generation_dir" in out and isinstance(out.get("failed_sources", {}), dict)


def test_generation_prune_keeps_active_previous_and_pending(setup):
    ctl, adapter, clock = setup
    dirs = [ctl.state["generation_dir"]]
    for n in range(2, 7):
        (ctl.base / "backend/app.py").write_text(f"value = {n}\n")
        settle(ctl, clock); ticks(ctl, 12)
        assert ctl.state["phase"] == "ACTIVE" and ctl.state["last_result"]["outcome"] == "restarted"
        dirs.append(ctl.state["generation_dir"])
    store = restart_candidates.store_dir(ctl.base)
    existing = {p.name for p in store.iterdir() if p.is_dir()}
    assert Path(ctl.state["generation_dir"]).name in existing
    assert Path(ctl.state["previous"]["generation_dir"]).name in existing
    assert len(existing) <= 4


def test_control_base_snapshot_verify_and_select(tmp_path):
    """G6: 정본의 제어 파일을 기반으로 봉인·검증하고, 실패한 기반은 이전 승인 기반으로 대신한다."""
    import control_base
    repo = Path(__file__).resolve().parents[1]
    base = tmp_path / "data"
    base.mkdir()
    cid, note = control_base.ensure(repo, tmp_path, support_root=repo)
    assert cid and note in {"promoted", "current"}
    chosen, chosen_id, _ = control_base.select(repo, tmp_path, support_root=repo)
    assert chosen_id == cid and (chosen / "VERIFIED").exists()
    assert (chosen / "backend/services/restart_controller.py").is_file()
    assert control_base.running_from(chosen / "backend/base/control_base.py") == cid
    # 실패 표시된 기반은 선택되지 않고 이전 기반이 남는다.
    control_base.mark_failed(tmp_path, cid, "boot failed")
    current = control_base.read_current(tmp_path)
    assert current["current"] is None and cid in current["failed"]


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
