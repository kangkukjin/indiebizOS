"""공개·알림은 최종 승인의 바이트/지문에 묶이고, 검수 전에는 밖으로 나가지 않는다."""
import importlib.util
import io
import json
import sys
from pathlib import Path

import boot_paths  # noqa: F401
import pytest

from supervision_delivery import DeliveryQueue, STAGING_ENV, stage_artifact
from test_conscious_supervisor import supervisor, finish, verdict  # noqa: F401


def prepare(controller, tmp_path, monkeypatch):
    public = tmp_path / "공유창고"
    public.mkdir()
    target = public / "report.html"
    target.write_text("old", encoding="utf-8")
    controller.delivery = DeliveryQueue(tmp_path / "drafts", public, controller.log)
    monkeypatch.setenv(STAGING_ENV, str(controller.delivery.directory))
    artifact = stage_artifact(target, b"new reviewed bytes", public)
    sent = []
    monkeypatch.setattr("notify_dispatch.notify_user", lambda **kw: sent.append(kw) or True)
    from system_tools import execute_send_notification
    for body in ("15 tips", "14 tips"):
        result = json.loads(execute_send_notification({"title": "Report", "message": body}, "."))
        assert result["queued_for_review"] and not result["delivered_to_launcher"]
    assert not sent and target.read_text() == "old"
    return target, artifact, sent


def test_final_approval_publishes_exact_artifact_and_latest_notice_once(supervisor, tmp_path, monkeypatch):
    target, artifact, sent = prepare(supervisor, tmp_path, monkeypatch)

    def approve(c, *a, **k):
        manifest = c.state()["pending_delivery"]
        assert Path(manifest["artifacts"][0]["staged"]).read_bytes() == b"new reviewed bytes"
        assert target.read_text() == "old" and not sent
        return verdict(c, delivery_hash=manifest["hash"])
    monkeypatch.setattr("final_evaluator.invoke", approve)
    assert finish(supervisor, "The report is ready.")[-1]["content"] == "The report is ready."
    assert target.read_bytes() == Path(artifact["staged"]).read_bytes()
    assert len(sent) == 1 and sent[0]["body"] == "14 tips"
    supervisor.delivery.deliver(None)
    assert len(sent) == 1


@pytest.mark.parametrize("status", ["UNKNOWN", "REWORK"])
def test_unapproved_draft_never_publishes_or_notifies(supervisor, tmp_path, monkeypatch, status):
    target, _, sent = prepare(supervisor, tmp_path, monkeypatch)
    supervisor.config["max_repairs"] = 0
    monkeypatch.setattr("final_evaluator.invoke", lambda c, *a, **k: verdict(c, status))
    assert "미승인" in finish(supervisor, "draft")[-1]["content"]
    assert target.read_text() == "old" and not sent


def test_changed_artifact_invalidates_approval(supervisor, tmp_path, monkeypatch):
    target, artifact, sent = prepare(supervisor, tmp_path, monkeypatch)

    def approve(c, *a, **k):
        fingerprint = c.delivery.manifest()["hash"]
        Path(artifact["staged"]).write_bytes(b"changed after review")
        return verdict(c, delivery_hash=fingerprint)
    monkeypatch.setattr("final_evaluator.invoke", approve)
    assert "미승인" in finish(supervisor, "draft")[-1]["content"]
    assert target.read_text() == "old" and not sent


def test_publication_failure_is_not_achieved_and_does_not_notify(supervisor, tmp_path, monkeypatch):
    import thread_context as tc
    target, _, sent = prepare(supervisor, tmp_path, monkeypatch)
    monkeypatch.setattr("final_evaluator.invoke", lambda c, *a, **k:
                        verdict(c, delivery_hash=c.delivery.manifest()["hash"]))
    target.unlink()
    target.mkdir()  # cannot replace a directory with the approved file
    assert "전달하지 못했습니다" in finish(supervisor, "draft")[-1]["content"]
    assert not sent and tc.get_goal_eval_outcome()["achieved"] is False


def test_cancellation_keeps_private_draft(supervisor, tmp_path, monkeypatch):
    target, _, sent = prepare(supervisor, tmp_path, monkeypatch)
    supervisor.cancel_check = lambda: True
    finish(supervisor, "draft")
    assert target.read_text() == "old" and not sent


def test_changed_goal_does_not_publish_approved_draft(supervisor, tmp_path, monkeypatch):
    from types import SimpleNamespace
    target, _, sent = prepare(supervisor, tmp_path, monkeypatch)
    supervisor.done_request = {"id": "goal", "version": 1}
    monkeypatch.setattr("pursuit_bind.resolve_session", lambda *a: SimpleNamespace(row={"id": "goal", "version": 2}))
    monkeypatch.setattr("final_evaluator.invoke", lambda c, *a, **k:
                        verdict(c, delivery_hash=c.delivery.manifest()["hash"], pursuit_status="APPROVED"))
    assert "미승인" in finish(supervisor, "draft")[-1]["content"]
    assert target.read_text() == "old" and not sent


def test_publication_protocol_rejects_paths_outside_owned_workbench(tmp_path, monkeypatch):
    queue = DeliveryQueue(tmp_path / "drafts", tmp_path / "public", lambda *a, **k: None)
    monkeypatch.setenv(STAGING_ENV, str(queue.directory))
    record = stage_artifact(tmp_path / "public" / "a.html", b"bytes", queue.public_root)
    record["target"] = str(tmp_path / "unrelated")
    next(queue.directory.glob("*.publication.json")).write_text(json.dumps(record))
    with pytest.raises(ValueError, match="범위"):
        queue.deliver("forged")


def test_report_renderer_writes_private_draft_with_correct_public_target(tmp_path, monkeypatch, capsys):
    root = Path(__file__).resolve().parents[1]
    spec = importlib.util.spec_from_file_location("report_renderer_delivery", root / "data/scripts/보고서HTML.py")
    renderer = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(renderer)
    monkeypatch.setattr(renderer, "_ROOT", tmp_path)
    monkeypatch.setenv(STAGING_ENV, str(tmp_path / "drafts"))
    (tmp_path / "source.md").write_text("# Report\n\nReviewed **content**.", encoding="utf-8")
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(
        {"src": "source.md", "dst": "공유창고/report.html"})))
    renderer.main()
    out = json.loads(capsys.readouterr().out)
    assert out["publication_pending"]
    assert "<strong>content</strong>" in Path(out["items"][0]["path"]).read_text()
    assert not Path(out["items"][0]["public_target"]).exists()


def test_supervisor_mcp_tools_rejoin_episode_and_cost(monkeypatch):
    from api_supervision import dispatch
    import episode_logger as ep
    from providers.base import ProviderMetrics, turn_token_scope, read_turn_tokens
    from types import SimpleNamespace
    parent = ep._Episode("worker", "fixture", task_id="supervisor-mcp-fixture")
    parent.episode_id = parent.trajectory.episode_id = 33520002
    monkeypatch.setitem(ep._live_episodes, parent.episode_id, parent)
    monkeypatch.setattr(ep, "record_trajectory_event", lambda *a, **k: None)

    def tool(payload):
        assert ep.EpisodeLogger.current() is parent
        ProviderMetrics().record_usage(1, {"prompt_tokens": 10, "completion_tokens": 2})
        return '{"success": true}'
    import thread_context as tc
    with ep.trajectory_scope(task_id=parent.task_id, episode_id=parent.episode_id):
        context = tc.snapshot()  # MCP 진입은 기존 trajectory 손잡이부터 복원한다.
    controller = SimpleNamespace(owner="worker", context=context, episode_id=parent.episode_id, tool=tool)
    monkeypatch.setattr("supervision_bus.current", lambda *a: controller)
    with turn_token_scope("worker", parent.task_id):
        assert dispatch("worker:manager", parent.task_id, {})["success"]
        assert read_turn_tokens() == 12
    assert len(parent.steps) == 1 and ep.EpisodeLogger.current() is None


@pytest.mark.parametrize("background", [False, True])
@pytest.mark.parametrize("conscious", [False, True])
def test_script_runner_passes_private_workbench_to_child_process(supervisor, tmp_path, monkeypatch, background, conscious):
    from test_script_args_coercion import S
    from types import SimpleNamespace
    target = tmp_path / "script.py"
    target.write_text("print('fixture')")
    monkeypatch.setattr(S, "_read_registry", lambda: {"fixture": {"file": "script.py"}})
    monkeypatch.setattr(S, "_script_path", lambda entry: target)
    monkeypatch.setattr(S, "_read_state", lambda: {})
    monkeypatch.setattr(S, "_write_state", lambda st: None)
    monkeypatch.setattr(S, "_RUN_DIR", tmp_path / "runs")
    monkeypatch.setattr(S, "_JOB_DIR", tmp_path / "runs/jobs")
    observed = []
    supervisor.configure({"task_framing": "의식 규정"} if conscious else None)

    def child(*args, **kwargs):
        observed.append((kwargs.get("env") or {}).get(STAGING_ENV))
        return SimpleNamespace(returncode=0, stdout='{"items": []}', stderr="", pid=123)
    monkeypatch.setattr(S.subprocess, "run", child)
    monkeypatch.setattr(S.platform_utils, "spawn_detached", child)
    assert S.op_run({"id": "fixture", "background": background})["success"]
    assert observed == [str(supervisor.delivery.directory) if conscious else None]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
