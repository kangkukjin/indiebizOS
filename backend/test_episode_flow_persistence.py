"""실행 중단·부분 보완·검수 장애가 전체 과제와 증거를 지우지 않는지 검증한다."""
import base64
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest
import thread_context as tc
import repair_continuation as journal
from test_conscious_supervisor import supervisor, finish  # noqa: F401
from test_repair_continuation import consumer  # noqa: F401
from test_repair_task_state import authorize


@pytest.mark.parametrize("shift", [-2, 2])
def test_clock_shift_does_not_cancel_live_completion_channel(tmp_path, monkeypatch, shift):
    import completion_lease as lease
    from common.completion_contract import owner_alive, process_identity
    from restart_process import identity
    import os
    osx = pytest.importorskip("psutil._psosx", exc_type=ImportError)
    if not hasattr(osx, "INIT_BOOT_TIME"):
        pytest.skip("시계 보정 없는 psutil")
    monkeypatch.setenv("INDIEBIZ_BASE_PATH", str(tmp_path))
    token = lease.create_channel()
    before = process_identity()
    monkeypatch.setattr(osx, "INIT_BOOT_TIME", osx.boot_time() + shift)
    assert owner_alive(before) is True
    assert identity(os.getpid()) == before
    assert not lease.channel_cancelled(token)
    assert owner_alive({**before, "born": before["born"] - 10}) is False
    lease.cancel_channel(token)
    assert lease.channel_cancelled(token)


def evaluation(controller, criterion=None):
    manifest = controller.store.manifest()
    return json.dumps({"status": "REWORK" if criterion else "APPROVED", "reason": "남은 구현" if criterion else "전체 확인",
                       "response_version": manifest["version"], "response_hash": manifest["hash"],
                       "repair_scope": "research", "instruction": "다음 항목 구현",
                       "defects": [{"criterion_id": criterion, "evidence": "미구현", "repair": "구현"}] if criterion else []})


def test_partial_repair_continues_whole_goal_across_execution_rounds(supervisor, tmp_path, monkeypatch, consumer):
    from supervision_store import TurnStore
    authorize(supervisor, tmp_path, monkeypatch)
    supervisor.configure({"achievement_criteria": ["UI 연결", "실행자 실제 동작", "정본 적용"]}, repair=True)
    monkeypatch.setattr("final_evaluator.invoke", lambda c, *a, **kw: evaluation(c, "C1"))
    finish(supervisor, "UI 미완료")
    original_task = supervisor.task
    row = journal.read(original_task, tmp_path)
    assert tc.get_goal_eval_outcome()["status"] == "PENDING_EXECUTION"
    assert len(row["criteria_state"]) == 3 and row["status"] == "waiting_execution"
    worker, deliveries, settled = consumer
    for criterion in ("C2", None):
        monkeypatch.setattr("final_evaluator.invoke", lambda c, *a, **kw: evaluation(c, criterion))
        def execute(item):
            supervisor.task = item["resume_task_id"]
            with tc.actor_context(agent_id=supervisor.owner, task_id=supervisor.task, origin="user"):
                supervisor.store = TurnStore(tmp_path / "data/spill/supervision" / supervisor.task)
                supervisor.configure(journal.inherited_framing(item["goal"]), repair=True)
                assert len(supervisor._final_criteria_contract["criteria"]) == 3
                final = finish(supervisor, "남은 기준 실행 결과")[-1]["content"]
                return {"response": final, "evaluation": tc.get_goal_eval_outcome()}
        worker.process_pending(tmp_path, "same-generation", execute)
    assert settled == ["completed"] and not deliveries
    completed = journal.read(original_task, tmp_path)
    assert completed["status"] == "completed"
    assert all(c["status"] == "met" for c in completed["criteria_state"])


def test_repeated_no_progress_blocks_without_losing_goal(supervisor, tmp_path, monkeypatch):
    authorize(supervisor, tmp_path, monkeypatch)
    from supervision_store import TurnStore
    for _ in range(3):
        supervisor.store = TurnStore(tmp_path / "data/spill/supervision" / str(_))
        supervisor.store.put_response("변하는 보고 문구 " + str(_))
        supervisor._evaluation_snapshot = {"files": {}}
        row = journal.review_checkpoint(supervisor, {"context": {"criteria_contract": {
            "criteria": [{"id": "C1", "text": "실제 구현"}]}}}, {"files": {}}, tmp_path)
        journal.finish_review(supervisor, json.loads(evaluation(supervisor, "C1")), tmp_path)
    saved = journal.read(row["task_id"], tmp_path)
    assert saved["status"] == "blocked" and "3회" in saved["reason"]
    assert saved["criteria_state"][0]["text"] == "실제 구현"


def test_implementation_progress_allows_more_than_three_rounds(supervisor, tmp_path, monkeypatch):
    authorize(supervisor, tmp_path, monkeypatch)
    for number in range(5):
        snapshot = {"files": {"implementation.py": {"mode": "text", "hash": str(number)}}}
        supervisor._evaluation_snapshot = snapshot
        row = journal.review_checkpoint(supervisor, {"context": {"criteria_contract": {
            "criteria": [{"id": "C1", "text": "실제 구현"}]}}}, snapshot, tmp_path)
        assert journal.finish_review(supervisor, json.loads(evaluation(supervisor, "C1")), tmp_path)
    assert journal.read(row["task_id"], tmp_path)["status"] == "waiting_execution"


@pytest.mark.parametrize("legacy", [False, True])
def test_missing_temporary_screenshot_uses_frozen_bytes_but_changed_code_rejects(supervisor, tmp_path, monkeypatch, legacy):
    from final_evaluator import prepare, snapshot_error, Evaluator
    from repair_resume import restore_review
    authorize(supervisor, tmp_path, monkeypatch)
    image = tmp_path / "pytest-screen.png"
    image.write_bytes(b"actual screenshot bytes")
    code = tmp_path / "implementation.py"
    code.write_text("x = 1")
    encoded = base64.b64encode(image.read_bytes()).decode()
    monkeypatch.setattr(Evaluator, "_collect_visual_artifacts", lambda *a, **k:
        [{"_path": str(image), "base64": encoded, "media_type": "image/png"}])
    supervisor.store.put_response("검사 완료")
    prepare(supervisor, [])
    supervisor._evaluation_snapshot["files"][str(code)] = {
        "mode": "bytes", "hash": hashlib.sha256(code.read_bytes()).hexdigest()}
    if legacy:
        supervisor._evaluation_snapshot["files"][str(image)]["mode"] = "bytes"
    row = journal.review_checkpoint(supervisor, supervisor._evaluation_packet, supervisor._evaluation_snapshot, tmp_path)
    image.unlink()
    restore_review(supervisor, row)
    assert snapshot_error(supervisor) is None
    supervisor._evaluation_packet["images"][0]["base64"] = base64.b64encode(b"tampered").decode()
    assert "시각 증거" in snapshot_error(supervisor)
    supervisor._evaluation_packet["images"][0]["base64"] = encoded
    code.write_text("x = 2")
    assert "변경" in snapshot_error(supervisor)


def test_image_evaluation_keeps_ready_primary_and_rejects_unready_cache(monkeypatch):
    import model_resolver as mr
    mr.clear_provider_cache()
    primary = {"provider": "test", "model": "vision", "api_key": "", "input_modalities": ["image"]}
    unavailable = {"provider": "missing-cli", "model": "vision", "api_key": "", "input_modalities": ["image"]}
    monkeypatch.setattr(mr, "resolve", lambda *a: primary)
    monkeypatch.setattr(mr, "resolve_vision", lambda: unavailable)
    calls = []
    ready = SimpleNamespace(is_ready=True)
    def create(provider, **kw):
        calls.append(provider)
        return ready if provider == "test" else SimpleNamespace(is_ready=False)
    monkeypatch.setattr("providers.create_initialized_provider", create)
    try:
        assert mr.get_image_evaluation_provider()[0] is ready
        assert calls == ["test"]
        ready.is_ready = False
        assert mr.get_image_evaluation_provider()[0] is None
        assert not mr._provider_cache
    finally:
        mr.clear_provider_cache()


def test_visual_evaluation_never_falls_back_to_text_without_images(monkeypatch):
    import consciousness_agent as agent
    monkeypatch.setattr("model_resolver.get_image_evaluation_provider", lambda *a: (None, {}))
    monkeypatch.setattr(agent, "_resolve_oneshot_provider", lambda *a: pytest.fail("텍스트 폴백"))
    with pytest.raises(RuntimeError, match="이미지 평가"):
        agent.system_ai_call("judge", images=[{"base64": "abc"}], role="evaluate")


def test_test_helper_preserves_failure_details_and_timeout(tmp_path, monkeypatch, capsys):
    import importlib.util
    import subprocess
    spec = importlib.util.spec_from_file_location("test_helper_script", Path(__file__).parents[1] / "data/scripts/시험.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    (tmp_path / "test_failure.py").write_text("pass")
    monkeypatch.setattr(module, "_args", lambda: {"files": ["test_failure.py"]})
    output = "assert expected == actual\n" + "large output\n" * 1000 + "ACTUAL ERROR"
    monkeypatch.setattr(module, "_run", lambda *a: ({"failed": 1, "passed": 0, "errors": 0}, ["test_failure"], 1, output))
    module.main()
    item = json.loads(capsys.readouterr().out)["items"][0]
    assert not item["ok"] and "ACTUAL ERROR" in item["output"] and "assert expected" in item["output"]
    assert Path(item["output_path"]).read_text() == output
    def timeout(*a):
        raise subprocess.TimeoutExpired("pytest", 1, output=b"test diagnostic")
    monkeypatch.setattr(module, "_run", timeout)
    module.main()
    item = json.loads(capsys.readouterr().out)["items"][0]
    assert "test diagnostic" in Path(item["output_path"]).read_text()


@pytest.mark.parametrize("source_status,reused", [("staging", True), ("applied", False), ("discarded", False)])
def test_execution_resume_transfers_only_unfinished_staging(tmp_path, monkeypatch, source_status, reused):
    from test_repair_staging import _load_handler, _make_repo
    staging = _load_handler()._staging_mod()
    repo = _make_repo(tmp_path / "repo")
    monkeypatch.setattr(staging, "_repair_owner", lambda: "agent")
    original = staging.ensure_session(str(repo), "source")
    worktree = repo / original["worktree"]
    file = worktree / "backend/cognition/victim.py"
    file.write_text("VALUE = 'partially implemented'\n")
    original["status"] = source_status
    staging._save_session(str(repo), original)
    row = {"task_id": "root", "staging_task_id": "source", "phase": "execution", "resume_task_id": "next"}
    with tc.actor_context(agent_id="agent", task_id="next", origin="user"), journal.resuming(row):
        resumed = staging.load_session(str(repo), "next")
    assert bool(resumed) is reused
    if reused:
        assert resumed["worktree"] == original["worktree"]
        assert "partially implemented" in file.read_text()
        assert staging.read_session(str(repo), "source")["reused_by"] == "next"
    else:
        assert not staging.read_session(str(repo), "source").get("reused_by")


def test_user_cancel_prevents_queued_execution(supervisor, tmp_path, monkeypatch, consumer):
    authorize(supervisor, tmp_path, monkeypatch)
    monkeypatch.setattr("final_evaluator.invoke", lambda c, *a, **kw: evaluation(c, "C1"))
    finish(supervisor, "미완료")
    assert journal.read(supervisor.task, tmp_path)["status"] == "waiting_execution"
    journal.cancel_pending("project", supervisor.owner, tmp_path)
    worker, deliveries, settled = consumer
    worker.process_pending(tmp_path, "generation", lambda r: pytest.fail("취소 뒤 실행"))
    assert settled == ["cancelled"]


def test_completion_intent_survives_execution_without_accepting_new_goal(supervisor, tmp_path, monkeypatch):
    authorize(supervisor, tmp_path, monkeypatch)
    request = {"id": "pursuit", "goal_criteria": "전체 구현", "version": 1}
    binding = SimpleNamespace(row={**request, "version": 4})
    monkeypatch.setattr("pursuit_bind.current", lambda: binding)
    row = {"done_request": request, "criteria_contract": {"criteria": [{"id": "G1", "text": "전체 구현"}]}}
    framing = {"_framing_source": "repair_continuation", "achievement_criteria": "전체 구현"}
    with journal.resuming(row):
        supervisor.configure(framing, repair=True)
        assert supervisor.done_request["version"] == 4 and request["version"] == 1
        binding.row["goal_criteria"] = "사용자가 변경한 기준"
        with pytest.raises(ValueError, match="완료 기준"):
            supervisor.configure(framing, repair=True)


def test_image_evaluation_falls_back_to_ready_visual_provider(monkeypatch):
    import model_resolver as mr
    primary = {"provider": "test", "model": "primary", "input_modalities": ["image"]}
    fallback = {"provider": "test", "model": "fallback", "input_modalities": ["image"]}
    monkeypatch.setattr(mr, "resolve", lambda *a: primary)
    monkeypatch.setattr(mr, "resolve_vision", lambda: fallback)
    calls = []
    provider = object()
    def create(descriptor, **kw):
        calls.append(descriptor["model"])
        return None if descriptor is primary else provider
    monkeypatch.setattr(mr, "_provider_from_desc", create)
    assert mr.get_image_evaluation_provider() == (provider, fallback)
    assert calls == ["primary", "fallback"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
