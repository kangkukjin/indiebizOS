"""적용 예약의 교체·취소가 대기 중인 옛 수행자와 제어자까지 전달되는가."""
import sys
from pathlib import Path

import pytest
import boot_paths  # noqa: F401
import red_apply
import restart_protocol
from restart_protocol import atomic_json, read_json


@pytest.fixture
def scheduled(tmp_path, monkeypatch):
    path = tmp_path / "data/system_ai_state/repair_sessions/task.apply.json"
    job = {"repo": str(tmp_path), "key": "task", "task_id": "task",
           "scheduled_at": "first", "readiness_hash": "ready", "episode_id": 1}
    atomic_json(path, job)
    atomic_json(path.with_name("task.json"), {"status": "apply_scheduled", "scheduled_at": "first"})
    atomic_json(tmp_path / "data/restart_control/state.json", {"generation": "g1"})
    monkeypatch.setattr(sys, "argv", ["red_apply.py", str(path)])
    monkeypatch.setattr(restart_protocol, "code_manifest", lambda _: {"digest": "code"})
    requests = []
    monkeypatch.setattr(restart_protocol, "request", lambda *a, **k:
                        requests.append(k) or {"request_id": k["request_id"]})
    return path, job, requests


@pytest.mark.parametrize("replacement", ["rescheduled", "cancelled", "finished"])
def test_old_waiter_never_overwrites_or_submits_changed_reservation(scheduled, monkeypatch, replacement):
    path, job, requests = scheduled
    def wait(*a, **k):
        if replacement == "rescheduled":
            atomic_json(path, {**job, "scheduled_at": "second", "new_evidence": "preserve"})
            atomic_json(path.with_name("task.json"), {"status": "apply_scheduled", "scheduled_at": "second"})
        elif replacement == "cancelled":
            atomic_json(path.with_name("task.json"), {"status": "staging"})
        else:
            atomic_json(path, {**job, "done_at": 123, "applied": True})
        return "observed"
    monkeypatch.setattr(red_apply, "wait_turn_closed", wait)
    assert red_apply.main() == 0
    assert not requests
    current = read_json(path)
    assert "restart_request_id" not in current
    if replacement == "rescheduled":
        assert current["scheduled_at"] == "second" and current["new_evidence"] == "preserve"
    if replacement == "finished":
        assert current["done_at"] == 123


def test_handoff_publishes_identity_without_writing_job_after_request(scheduled, monkeypatch):
    path, job, requests = scheduled
    monkeypatch.setattr(red_apply, "wait_turn_closed", lambda *a, **k: "observed")
    def request(*a, **kw):
        requests.append(kw)
        atomic_json(path, {**job, "controller_apply": {"applied": True}, "done_at": 123})
        return {"request_id": kw["request_id"]}
    monkeypatch.setattr(restart_protocol, "request", request)
    assert red_apply.main() == 0
    assert read_json(path)["done_at"] == 123
    assert requests[0]["payload"]["reservation"]["scheduled_at"] == "first"


def test_controller_rejects_replacement_after_submission(scheduled, monkeypatch):
    from restart_red import inspect_job, apply_job
    path, job, _ = scheduled
    identity = {k: job[k] for k in ("key", "task_id", "scheduled_at", "readiness_hash")}
    atomic_json(path, {**job, "scheduled_at": "second"})
    monkeypatch.setattr(red_apply, "_load_handler", lambda *a: pytest.fail("낡은 예약 적용"))
    with pytest.raises(ValueError, match="판본"):
        inspect_job(path.parents[3], path, identity)
    with pytest.raises(ValueError, match="판본"):
        apply_job(path.parents[3], path, identity)


def test_current_request_cannot_apply_cancelled_session(scheduled):
    from restart_red import inspect_job, reservation
    path, job, _ = scheduled
    atomic_json(path.with_name("task.json"), {"status": "staging"})
    with pytest.raises(ValueError, match="판본"):
        inspect_job(path.parents[3], path, reservation(job))


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
