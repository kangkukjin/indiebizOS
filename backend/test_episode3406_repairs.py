"""ep3405/3406: receipts, bounded recheck, source handoff and actual tool arguments."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import boot_paths  # noqa: F401
from supervision_store import TurnStore
from supervisor_content import discover, validate
from supervisor_review import content_changes, final_state
from test_conscious_supervisor import supervisor, manager_tool, finish, verdict  # noqa: F401


def test_short_execute_records_exact_visible_source(supervisor):
    supervisor.executor_paused = True
    raw = {"success": True, "title": '원문 "표현"', "body": "증거"}
    supervisor._execute = lambda *a, **kw: raw
    visible = manager_tool(supervisor, {"op": "execute", "name": "inspect"})["result"]
    key = visible["evidence"]["id"]
    assert json.loads(visible["page"]["text"]) == raw
    assert supervisor.store.evidence_fully_read(key)
    assert supervisor.store.evidence_quote_read(key, raw["title"])


def test_hidden_tail_and_gaps_do_not_become_read(tmp_path):
    store = TurnStore(tmp_path)
    page = store.present_evidence("x" * 12000 + "보지 않은 출처")
    key = page["evidence"]["id"]
    assert not store.evidence_fully_read(key)
    assert not store.evidence_quote_read(key, "보지 않은 출처")
    key = store.evidence("123456789")["id"]
    store.read_evidence(key, 0, 4, mark=True)
    store.read_evidence(key, 5, 4, mark=True)
    assert not store.evidence_quote_read(key, "3456")
    store.read_evidence(key, 4, 1, mark=True)
    assert store.evidence_quote_read(key, "3456")


def setup_report(controller, tmp_path):
    path = tmp_path / "report.md"
    path.write_text("취업자 증가는 AI의 인과 효과를 식별하지 못한다.")
    controller.content_artifacts = discover(controller, str(path), [])
    return path


@pytest.mark.parametrize("confirmation,approved", [("ACHIEVED", True), ("NOT_ACHIEVED", False), ("UNKNOWN", False), ("MUTATED", False), ("ERROR", False)])
def test_evaluator_receives_body_without_extra_receipt_round(supervisor, tmp_path, monkeypatch, confirmation, approved):
    path = setup_report(supervisor, tmp_path)
    supervisor.config["max_repairs"] = 0
    calls = []

    def evaluate(prompt, **kwargs):
        calls.append(kwargs["role"])
        assert path.read_text() in prompt
        if confirmation == "MUTATED":
            path.write_text("평가 뒤 바뀐 다른 주장")
            return "ACHIEVED"
        if confirmation == "ERROR":
            raise RuntimeError("평가 모델 실패")
        return confirmation + "\n자료에 근거한 판정"

    monkeypatch.setattr("consciousness_agent.system_ai_call", evaluate)
    monkeypatch.setattr("supervisor_runtime.invoke", lambda *a, **kw: pytest.fail("최종평가에 의식 호출"))
    events = finish(supervisor, str(path))
    assert calls == ["evaluate"]
    assert ("검수 미승인" not in events[-1]["content"]) is approved
    assert not supervisor.calls


def test_fabricated_quote_does_not_trigger_receipt_approval(supervisor, monkeypatch):
    from supervisor_review import recover_citations
    from supervisor_content import ContentIssue
    source = supervisor.store.evidence("실제 원문")
    decision = {"status": "APPROVED", "content_checks": [{"sources": {
        "evidence": [{"id": source["id"], "quote": "원문에 없는 주장"}]}}]}
    monkeypatch.setattr("supervisor_runtime.invoke", lambda *a, **kw: pytest.fail("fabricated quote"))
    assert recover_citations(supervisor, decision, ContentIssue("불일치", kind="citation")) is decision
    assert not supervisor.store.evidence_fully_read(source["id"])


def test_changed_artifact_presents_delta_and_preserves_read_provenance(supervisor, tmp_path):
    path = setup_report(supervisor, tmp_path)
    old = "유지되는 줄\n" * 2000 + "잘못된 결론\n" + "유지되는 끝\n" * 2000
    path.write_text(old)
    supervisor.content_artifacts = discover(supervisor, str(path), [])
    assert content_changes(supervisor)[0]["mode"] == "full_read_required"
    art = supervisor.content_artifacts[0]
    supervisor.store.read_evidence(art["evidence_id"], 0, None, mark=True)
    path.write_text(old.replace("잘못된 결론", "확인한 범위로 수정"))
    supervisor.content_artifacts = discover(supervisor, str(path), [])
    changes = content_changes(supervisor)
    new_key = supervisor.content_artifacts[0]["evidence_id"]
    assert "확인한 범위로 수정" in json.dumps(changes, ensure_ascii=False)
    assert len(json.dumps(changes, ensure_ascii=False)) < 2000
    assert supervisor.store.evidence_fully_read(new_key)
    assert supervisor.store.evidence_quote_read(new_key, "수정\n유지되는 끝")
    assert content_changes(supervisor)[0]["mode"] == "unchanged"


def test_large_unseen_change_requires_remainder_read(supervisor, tmp_path):
    path = setup_report(supervisor, tmp_path)
    content_changes(supervisor)
    supervisor.store.read_evidence(supervisor.content_artifacts[0]["evidence_id"], mark=True)
    path.write_text("완전히 새로운 주장\n" * 3000)
    supervisor.content_artifacts = discover(supervisor, str(path), [])
    changes = content_changes(supervisor)
    assert changes[0]["pages"][0]["remaining_offset"]
    assert not supervisor.store.evidence_fully_read(supervisor.content_artifacts[0]["evidence_id"])


def test_unread_old_artifact_cannot_seed_new_coverage(supervisor, tmp_path):
    path = setup_report(supervisor, tmp_path)
    content_changes(supervisor)
    path.write_text(path.read_text() + "추가")
    supervisor.content_artifacts = discover(supervisor, str(path), [])
    assert content_changes(supervisor)[0]["mode"] == "full_read_required"
    assert not supervisor.store.evidence_fully_read(supervisor.content_artifacts[0]["evidence_id"])


def test_repair_index_preserves_existing_source_handles(supervisor):
    from supervisor_handoff import handoff_state
    key = supervisor._start("inspect", {"url": "https://example.test/source"})
    supervisor._finish(key, {"body": "기존 원문"})
    for i in range(5):
        supervisor.store.log("tool.supervisor", operation="evidence", result=supervisor.store.evidence(str(i)))
    state = handoff_state(supervisor, {"status": "REWORK"})
    row = state["evidence"]["tool_index"][0]
    assert "https://example.test/source" in row["input"]["excerpt"]
    assert "기존 원문" in supervisor.store.read_evidence(row["result"]["id"])["text"]
    assert not supervisor.store.evidence_fully_read(row["result"]["id"])
    assert "events" not in final_state(supervisor)


def test_planning_receives_actual_idiom_map_only_when_requested(supervisor, monkeypatch):
    from supervisor_runtime import tool_context
    monkeypatch.setattr("ibl_access.idioms_map", lambda allowed: "[fn:주소마다읽기]{urls:...}")
    assert "available_idioms" not in tool_context(supervisor)
    assert "주소마다읽기" in tool_context(supervisor, include_idioms=True)["available_idioms"]


def package_module(package, name):
    from common.pkg_utils import load_sibling
    root = Path(__file__).resolve().parents[1] / "data/packages/installed/tools" / package
    return load_sibling(str(root / "handler.py"), name)


@pytest.mark.parametrize("extra,expected", [({}, {}), ({"obj_l2": "ALL"}, {"objL2": "ALL"}),
    ({"obj_l2": "A", "obj_l3": "ALL"}, {"objL2": "A", "objL3": "ALL"})])
def test_kosis_preserves_explicit_dimensions(monkeypatch, extra, expected):
    api = package_module("kosis", "tool_kosis_api")
    sent = []
    monkeypatch.setattr(api, "_make_request", lambda endpoint, params: sent.append(params) or {"success": True, "data": []})
    api.get_statistics_data("101", "fixture", **extra)
    assert {k: v for k, v in sent[0].items() if k in {"objL2", "objL3"}} == expected


def test_kosis_classification_error_reports_what_was_sent(monkeypatch):
    api = package_module("kosis", "tool_kosis_api")
    monkeypatch.setattr(api, "_make_request", lambda *a: {"success": True, "data": {"err": "30", "errMsg": "objL 항목 오류"}})
    result = api.get_statistics_data("101", "fixture", obj_l2="ALL")
    assert not result["success"] and result["error_code"] == "30"
    assert result["classification_request"]["objL2"] == "ALL"
    assert "반복하지" in result["hint"]


@pytest.mark.parametrize("filename,explicit,expected", [("chart.html", None, "html"),
    ("chart.htm", None, "html"), ("chart.png", None, "png"), ("chart.html", "png", None)])
def test_chart_output_contract_applies_before_renderer(tmp_path, monkeypatch, filename, explicit, expected):
    handler = package_module("visualization", "handler")
    captured = []
    renderer = SimpleNamespace(render_spec=lambda spec, **kw: captured.append(kw) or {"success": True})
    monkeypatch.setattr(handler, "load_module", lambda name: renderer)
    context = SimpleNamespace(tool_name="chart", output_dir=lambda: str(tmp_path),
        resolve_output_path=lambda p: {"path": str(tmp_path / p)})
    args = {"output_path": filename, "spec": {"data": [{"y": [1, 2]}]}}
    if explicit:
        args["output_format"] = explicit
    result = handler.execute(args, context)
    if expected:
        assert captured[0]["output_format"] == expected
    else:
        assert not json.loads(result)["success"] and not captured
    assert args["output_path"] == filename  # Caller input remains reusable.


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
