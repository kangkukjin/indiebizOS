"""문서앱 에피소드에서 드러난 수리 묶음·중단·검사 영수증의 공통 경계."""
import asyncio
import hashlib
import json
import subprocess
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

import boot_paths  # noqa: F401
import api_repair_continuation as continuation
import repair_continuation as journal
import runtime_work
from restart_protocol import atomic_json, read_json
from test_repair_staging import _grant, _load_handler, _make_repo, _ungrant
from test_repair_continuation import record, receipt, consumer  # noqa: F401
from tool_context import ToolContext


@pytest.fixture
def bundle(tmp_path, monkeypatch):
    repo = _make_repo(tmp_path / "repo")
    (repo / "frontend").mkdir()
    package = repo / "data/packages/installed/tools/example"
    package.mkdir(parents=True)
    (package / "handler.py").write_text("VALUE = 'original'\n")
    (package / "ibl_actions.yaml").write_text("op: old\n")
    handler = _load_handler()
    handler._REPO_ROOT = repo
    monkeypatch.setenv("INDIEBIZ_BASE_PATH", str(repo))
    monkeypatch.setenv("INDIEBIZ_REPAIR_NO_SPAWN", "1")
    key = _grant(handler)
    import supervision_bus
    from test_repair_staging import _ready_supervisor
    monkeypatch.setattr(supervision_bus, "current", lambda *a, **kw: _ready_supervisor())
    yield repo, package, handler, handler._staging_mod(), key
    _ungrant()


def test_code_and_package_declarations_apply_as_one_recoverable_bundle(bundle):
    repo, package, handler, staging, key = bundle
    changes = {repo / "backend/cognition/victim.py": "VALUE = 'new'\n",
               package / "handler.py": "VALUE = 'new'\n",
               package / "ibl_actions.yaml": "op: new\n",
               package / "new_module.py": "VALUE = 2\n"}
    originals = {p: p.read_bytes() if p.exists() else None for p in changes}
    for path, content in changes.items():
        staged = Path(handler._red_stage(str(path), for_write=True))
        assert staged != path
        staged.write_text(content)
        assert handler._red_stage(str(path), for_write=False) == str(staged)
        assert (path.read_bytes() if path.exists() else None) == originals[path]
    session = staging.read_session(str(repo), key)
    assert len(session["files"]) == 4
    result = staging.op_apply({"_repo_root": str(repo), "_grant_key": key})
    assert result["scheduled"] and not result["applied"]
    assert all((p.read_bytes() if p.exists() else None) == originals[p] for p in changes)
    result = staging.perform_scheduled_apply(str(repo), key, prepare=handler._red_write_prepare,
                                             finalize=lambda path: None)
    assert result["applied"] and result["verified"]
    assert all(p.read_text() == content for p, content in changes.items())
    backup = read_json(repo / "data/system_ai_state/red_backups" / key / "manifest.json")
    assert set(backup["files"]) == {str(p) for p in changes}
    from restart_red import recover_code
    assert recover_code(repo, {"request": {"operation": "red_verify", "payload": {
        "manifest_path": str(repo / "data/system_ai_state/red_backups" / key / "manifest.json")}}})
    assert all((p.read_bytes() if p.exists() else None) == originals[p] for p in changes)


def test_package_only_repair_defers_and_does_not_leak_on_staging_failure(bundle, monkeypatch):
    repo, package, handler, staging, key = bundle
    path = package / "handler.py"
    Path(handler._red_stage(str(path), True)).write_text("VALUE = 2\n")
    assert staging._reload_triggering(staging.read_session(str(repo), key))
    monkeypatch.setattr(staging, "stage_file", lambda *a: None)
    with pytest.raises(RuntimeError, match="라이브 쓰기"):
        handler._red_stage(str(path), True)
    assert path.read_text() == "VALUE = 'original'\n"


def test_package_sources_do_not_change_regular_data_or_nonrepair_writes(bundle):
    repo, package, handler, staging, key = bundle
    assert handler._red_stage(str(package / "customer_data.json"), True) != str(package / "customer_data.json")
    assert not (package / "customer_data.json").exists()
    foreign = repo.parent / "other/data/packages/installed/tools/example/handler.py"
    assert handler._red_stage(str(foreign), True) == str(foreign)
    _ungrant()
    assert handler._red_stage(str(package / "handler.py"), True) == str(package / "handler.py")


def test_vocabulary_source_joins_repair_bundle(bundle):
    repo, _, handler, staging, key = bundle
    path = repo / "data/ibl_nodes_src/self.yaml"
    path.parent.mkdir(parents=True)
    path.write_text("old: true\n")
    target = Path(handler._red_stage(str(path), True))
    target.write_text("new: true\n")
    assert path.read_text() == "old: true\n"
    assert staging._reload_triggering(staging.read_session(str(repo), key))


def test_package_write_edit_copy_move_delete_use_staging(bundle):
    repo, package, handler, staging, key = bundle
    def call(name, **args):
        return handler.execute(args, ToolContext(str(repo), name, agent_id="system_ai"))
    path = package / "handler.py"
    assert json.loads(call("write_file", path=str(path), content="VALUE = 2\n"))["staged"]
    assert "2" in call("read_file", path=str(path))
    assert "격리" in call("edit_file", path=str(path), old_string="2", new_string="3")
    assert path.read_text() == "VALUE = 'original'\n"
    copy = package / "copy.py"
    assert json.loads(call("copy_path", src=str(path), dest=str(copy)))["staged"]
    assert not copy.exists()
    assert Path(handler._red_stage(str(copy), False)).read_text() == "VALUE = 3\n"
    # 이동은 목적지가 보통 data여도 양쪽을 묶어야 한다.
    moved = repo / "data/moved.txt"
    assert json.loads(call("move_path", src=str(path), dest=str(moved)))["staged"]
    assert path.exists() and not moved.exists()
    assert Path(staging.staged_path(str(repo), key, str(moved))).read_text() == "VALUE = 3\n"
    assert "VALUE = 3" in call("read_file", path=str(moved))
    declaration = package / "ibl_actions.yaml"
    assert json.loads(call("delete_path", path=str(declaration)))["staged"]
    assert declaration.exists()
    records = staging.read_session(str(repo), key)["files"]
    assert records[str(path)]["op"] == records[str(declaration)]["op"] == "delete"
    assert staging.op_apply({"_repo_root": str(repo), "_grant_key": key})["scheduled"]
    assert staging.perform_scheduled_apply(str(repo), key, prepare=handler._red_write_prepare,
                                          finalize=lambda path: None)["applied"]
    assert moved.read_text() == "VALUE = 3\n" and not path.exists()
    backup = read_json(repo / "data/system_ai_state/red_backups" / key / "manifest.json")
    assert str(moved) in backup["files"] and backup["files"][str(moved)] is None


def test_package_delete_failure_cannot_fall_back_to_live(bundle, monkeypatch):
    _, package, handler, staging, _ = bundle
    monkeypatch.setattr(staging, "stage_delete", lambda *a: False)
    with pytest.raises(RuntimeError, match="라이브 삭제"):
        handler._red_stage_delete(str(package / "handler.py"))
    assert (package / "handler.py").exists()


def test_drain_keeps_real_supervision_and_project_cancellation(monkeypatch, tmp_path):
    from fastapi import FastAPI
    from api_runtime import RuntimeAdmission
    from api_supervision import router as supervision_router
    from api_agents import router as agents_router
    import supervision_bus
    row = record(tmp_path)
    monkeypatch.setenv("INDIEBIZ_BASE_PATH", str(tmp_path))
    monkeypatch.setattr("api_agents.agent_runners", {})
    controller = SimpleNamespace(context={}, owner="agent", task="task",
                                 tool=lambda payload: json.dumps({"evidence": payload["id"]}),
                                 boundary=lambda: "finish existing work")
    monkeypatch.setattr(supervision_bus, "current", lambda agent, task:
                        controller if (agent, task) == ("agent", "task") else None)
    previous = runtime_work.registry()
    reg = runtime_work.install("test")
    reg.gate("DRAINING")
    app = FastAPI()
    app.include_router(supervision_router, prefix="/ibl")
    app.include_router(agents_router)
    app.add_middleware(RuntimeAdmission)
    @app.post("/new-work")
    async def new_work():
        pytest.fail("재시작 대기 중 새 작업 실행")
    async def scenario():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
            body = {"agent_id": "agent", "task_id": "task", "payload": {"op": "evidence", "id": "proof"}}
            assert (await client.post("/ibl/supervision", json=body)).json() == {"evidence": "proof"}
            assert (await client.post("/ibl/supervision/boundary", json=body)).json()["active"]
            assert (await client.post("/ibl/supervision", json={**body, "task_id": "missing"})).json()["success"] is False
            assert (await client.post("/projects/project/cancel_all")).status_code == 200
            assert journal.cancelled(row, tmp_path)
            assert (await client.post("/projects/project/stop_all")).status_code == 200
            assert (await client.post("/new-work")).status_code == 503
            assert (await client.post("/ibl/execute", json={"code": "return 1", "edition": 2})).status_code == 503
    try:
        asyncio.run(scenario())
        assert not reg.snapshot()["owners"]
    finally:
        runtime_work._registry = previous


def test_active_receipt_survives_death_before_journal_update(tmp_path, monkeypatch):
    command = "test-and-commit"
    proof = tmp_path / "data/system_ai_state/repair_check_outputs/durable.json"
    signature = hashlib.sha256(command.encode()).hexdigest()
    row = record(tmp_path, result={"outcome": "healthy", "active_verify_cmd": command},
                 active_verify={"state": "running", "output_path": str(proof), "command_sha256": signature})
    atomic_json(proof, {"exit_code": 0, "command_sha256": signature, "output_path": str(proof), "output": "passed"})
    monkeypatch.setattr("red_apply._run_post_verify", lambda *a, **kw: pytest.fail("완료한 검사·커밋 반복"))
    checked = continuation.active_check(row, tmp_path)
    assert checked["phase"] == "verify_remaining" and checked["active_verify"]["recovered"]
    assert continuation.active_check(journal.read(row["task_id"], tmp_path), tmp_path)["phase"] == "verify_remaining"


@pytest.mark.parametrize("wrong", ["command", "outside"])
def test_unrelated_receipt_does_not_prove_success(tmp_path, monkeypatch, wrong):
    proof = tmp_path / ("outside.json" if wrong == "outside" else "data/system_ai_state/repair_check_outputs/proof.json")
    signature = hashlib.sha256(b"check").hexdigest()
    atomic_json(proof, {"exit_code": 0, "command_sha256": "other" if wrong == "command" else signature})
    row = record(tmp_path, result={"outcome": "healthy", "active_verify_cmd": "check"},
                 active_verify={"state": "running", "output_path": str(proof), "command_sha256": signature})
    monkeypatch.setattr("red_apply._run_post_verify", lambda *a, **kw: pytest.fail("불확실한 실행 재시도"))
    assert continuation.active_check(row, tmp_path)["phase"] == "repair_active"


def test_timeout_preserves_partial_evidence_and_active_uses_separate_deadline(tmp_path, monkeypatch):
    import red_apply
    monkeypatch.setattr(red_apply, "_wait_healthy", lambda *a: True)
    calls = []
    def timeout(*args, **kwargs):
        calls.append(kwargs["timeout"])
        raise subprocess.TimeoutExpired("check", kwargs["timeout"], output=b"tests PASSED", stderr=b"commit started")
    monkeypatch.setattr("repair_process.run", timeout)
    row = record(tmp_path, result={"outcome": "healthy", "active_verify_cmd": "check"})
    checked = continuation.active_check(row, tmp_path)
    result = checked["active_verify"]["receipt"]
    assert calls == [red_apply.ACTIVE_VERIFY_TIMEOUT_S]
    assert red_apply.ACTIVE_VERIFY_TIMEOUT_S > red_apply.VERIFY_TIMEOUT_S
    assert result["effect_unknown"] and result["timed_out"]
    assert "tests PASSED" in result["output"] and "commit started" in result["output"]
    assert "tests PASSED" in read_json(result["output_path"])["output"]
    continuation.active_check(journal.read(row["task_id"], tmp_path), tmp_path)
    assert len(calls) == 1


def test_cancel_during_active_check_prevents_model_resume(tmp_path, monkeypatch, consumer):
    module, _, settled = consumer
    row = record(tmp_path)
    job = read_json(row["job_path"])
    atomic_json(row["job_path"], {**job, "active_verify_cmd": "check"})
    receipt(tmp_path)
    def check(*args, **kwargs):
        journal.cancel_pending("project", "agent", tmp_path)
        return {"exit_code": 0}
    monkeypatch.setattr("red_apply._run_post_verify", check)
    module.process_pending(tmp_path, "new", lambda row: pytest.fail("취소 후 모델 재개"))
    assert settled == ["cancelled"]


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
