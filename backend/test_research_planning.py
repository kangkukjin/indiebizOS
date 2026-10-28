"""의식의 연구계획 소유권, 저장→실행 순서와 일반 작업 경계."""
import boot_paths  # noqa: F401
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import research_planning as rp
from consciousness_agent import ConsciousnessAgent, FramingContractError
from test_conscious_supervisor import supervisor, finish  # noqa: F401


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    import runtime_utils
    import member_runtime
    import episode_logger
    monkeypatch.setattr(runtime_utils, "get_base_path", lambda: tmp_path)
    monkeypatch.setattr(member_runtime, "is_member", lambda: False)
    guide = tmp_path / "data/guides/deep_research.md"
    guide.parent.mkdir(parents=True)
    guide.write_text("의식용 교재 표식: 목적과 질문에 맞춰 계획한다.")
    events = []
    monkeypatch.setattr(episode_logger, "record_trajectory_event", lambda k, v: events.append((k, v)))
    return tmp_path, guide, events


def draft(**extra):
    return {"task_framing": "원고를 소개하는 영상 제작 방법을 연구한다.",
            "deep_research": True, "guide_files": ["video_workflow.md"],
            "achievement_criteria": "질문별 근거와 열람 범위·불확실성을 대조한다.",
            "research_plan": "# 제작 방법 연구\n목적: 이해하기 쉬운 원고 영상.\n"
                             "질문: 무엇이 이해를 돕는가?\n방법: 기존 자료와 비교 연구를 읽는다.\n"
                             "종합: 조건별 효과를 비교.\n멈춤: 적용 조건을 가르면 종료.\n미확인: 시청 지표.",
            **extra}


def agent():
    value = ConsciousnessAgent.__new__(ConsciousnessAgent)
    value._supervisor_prompt, value._prompt = "의식 역할", "의식 호환 역할"
    value._provider = SimpleNamespace(is_ready=True)
    value._reload_prompt_if_changed = lambda: None
    return value


def test_normal_task_has_no_guide_read_call_or_file(workspace):
    root, guide, events = workspace
    guide.unlink()  # 일반 작업은 교재가 없어도 영향을 받지 않는다.
    output = {"task_framing": "수치를 비교한다.", "deep_research": False}
    supervisor = SimpleNamespace(plan=lambda *a: pytest.fail("일반 작업의 추가 호출"))
    assert rp.prepare(agent(), output, "심층연구 기능을 수리해줘", supervisor=supervisor) is output
    assert events == [] and not (root / "outputs").exists()


@pytest.mark.parametrize("legacy", [False, True])
def test_consciousness_reads_guide_and_saved_bytes_reach_executor(workspace, legacy):
    root, guide, events = workspace
    calls = []

    def plan(prompt, system):
        assert guide.read_text() in prompt
        assert not (root / "outputs").exists()
        calls.append(prompt)
        return json.dumps(draft(), ensure_ascii=False)

    source = {"task_framing": "연구", "deep_research": True}
    if legacy:
        source = {"task_framing": "연구", "guide_files": [rp.GUIDE]}
    out = rp.prepare(agent(), source, "원래 사용자 맥락", supervisor=SimpleNamespace(plan=plan))
    receipt = out["_research_plan"]
    saved = Path(receipt["path"]).read_text()
    assert saved == receipt["body"]
    assert hashlib.sha256(saved.encode()).hexdigest() == receipt["sha256"]
    assert len(calls) == 1
    assert [k for k, v in events] == ["research.guide_supplied", "research.plan_saved"]
    from prompt_builder import compile_user_command
    from reframe import render_for_executor
    for rendered in (compile_user_command("원래 요청", out), render_for_executor({"revised": True, "output": out})):
        assert receipt["path"] in rendered
        assert "무엇이 이해를 돕는가" in rendered
        assert rp.GUIDE not in rendered
        assert "의식용 교재 표식" not in rendered


def test_compatibility_provider_uses_same_planning_contract(workspace, monkeypatch):
    import consciousness_agent as ca
    calls = []
    monkeypatch.setattr(ca, "call_oneshot_provider", lambda *a, **kw:
                        calls.append((a, kw)) or json.dumps(draft()))
    out = rp.prepare(agent(), {"deep_research": True}, "연구")
    assert Path(out["_research_plan"]["path"]).exists()
    assert calls[0][1]["role"] == "research_plan"


@pytest.mark.parametrize("failure", ["guide", "write", "invalid", "leak"])
def test_failed_planning_never_returns_an_executable_framing(workspace, monkeypatch, failure):
    root, guide, events = workspace
    if failure == "guide":
        guide.unlink()
    if failure == "write":
        monkeypatch.setattr(rp, "persist", lambda *a: (_ for _ in ()).throw(OSError("disk unavailable")))
    response = draft()
    if failure == "invalid":
        response["research_plan"] = ""
    if failure == "leak":
        response["capability_focus"] = {"hint": "deep_research.md를 읽으세요"}
    supervisor = SimpleNamespace(plan=lambda *a: json.dumps(response))
    with pytest.raises(FramingContractError, match="조사를 시작하지 않았습니다"):
        rp.prepare(agent(), {"deep_research": True}, "연구", supervisor=supervisor)
    assert not any(k == "research.plan_saved" for k, v in events)


def test_followup_and_evaluation_read_current_plan_without_overwriting_original(workspace):
    root, guide, events = workspace
    old = rp.persist("# 기존 연구\n진행: 아직 조사 전", guide.read_text())
    path = Path(old["path"])
    path.write_text(path.read_text() + "\n실행 관측: 자료 A는 차단됨. 다음 확인은 B.\n")
    seen = []
    out = rp.prepare(agent(), {"deep_research": True}, "같은 연구를 계속해", previous_plan=old,
                     supervisor=SimpleNamespace(plan=lambda p, s: seen.append(p) or json.dumps(draft())))
    assert "자료 A는 차단됨" in seen[0]
    assert out["_research_plan"]["previous_path"] == str(path)
    assert out["_research_plan"]["path"] != str(path)
    assert "자료 A는 차단됨" in path.read_text()
    from research_planning import evaluation_block
    text = evaluation_block({"_research_plan": old})
    assert "자료 A는 차단됨" in text and old["sha256"] in text


def test_prior_plan_cannot_cross_workspaces(workspace, tmp_path):
    root, guide, events = workspace
    foreign = tmp_path / "other.md"
    foreign.write_text("다른 작업공간")
    with pytest.raises(ValueError, match="작업공간 밖"):
        rp.read_current({"path": str(foreign)})


def test_guide_is_absent_from_executor_recommendations(workspace, monkeypatch):
    import prompt_builder as pb
    from guide_registry import execution_guide_map
    root, guide, events = workspace
    (guide.parent / "video_workflow.md").write_text("영상 제작 교재")
    monkeypatch.setattr(pb, "get_base_path", lambda: root)
    monkeypatch.setattr(pb, "get_prompt_builder", lambda: pb.PromptBuilder(root))
    monkeypatch.setattr(pb, "_repair_turn_block", lambda _: "")
    import guide_registry as gr
    monkeypatch.setattr(gr, "freshness_note", lambda *a: "")
    monkeypatch.setattr(gr, "record_use", lambda *a: None)
    monkeypatch.setattr(gr, "mark_injected", lambda *a: None)
    recall = '<guide_map note="목차">\n- 연구: deep_research.md\n- 영상: deep_research.md, video_workflow.md\n</guide_map>'
    assert rp.GUIDE not in execution_guide_map(recall)
    assert "video_workflow.md" in execution_guide_map(recall)
    for co in ({}, {"guide_files": [rp.GUIDE]}, {"guide_files": ["video_workflow.md", rp.GUIDE]}):
        assert rp.GUIDE not in pb._build_dynamic_context(co, execution_memory=recall)
        assert rp.GUIDE not in pb.compile_user_command("조사", co)
    assert rp.GUIDE in recall  # 의식 입력 원문은 보존한다.


def test_deep_research_inheritance_calls_full_consciousness(workspace, monkeypatch):
    import framing_inheritance as fi
    monkeypatch.setattr(fi, "_candidate", lambda *a: ("followup", {"framing": {"deep_research": True}}))
    monkeypatch.setattr(fi, "_patch", lambda *a, **kw: pytest.fail("경량 패치로 연구계획을 대체함"))
    assert fi.inherit(object(), "계속해", [{"role": "user", "content": "연구"}]) is None


@pytest.mark.parametrize("deep", [False, True])
def test_process_classifies_then_plans_only_deep_research(workspace, deep):
    root, guide, events = workspace
    calls = []
    project = root / "project"

    def plan(prompt, system, revision=None):
        calls.append(prompt)
        if len(calls) == 1:
            assert guide.read_text() not in prompt
            return json.dumps({"task_framing": "이번 과제", "deep_research": deep})
        assert guide.read_text() in prompt
        assert not list(project.glob("outputs/research_plans/*/research_plan.md"))
        return json.dumps(draft())

    out = agent().process("이번 요청", [], "", supervisor=SimpleNamespace(plan=plan),
                          project_path=project)
    assert len(calls) == (2 if deep else 1)
    if deep:
        assert Path(out["_research_plan"]["path"]).is_relative_to(project)
        assert Path(out["_research_plan"]["path"]).exists()
    else:
        assert "_research_plan" not in out and not project.exists()


def test_process_does_not_swallow_plan_failure(workspace):
    root, guide, events = workspace
    guide.unlink()
    supervisor = SimpleNamespace(plan=lambda *a: json.dumps({"task_framing": "연구", "deep_research": True}))
    with pytest.raises(FramingContractError):
        agent().process("깊이 연구해줘", [], "", supervisor=supervisor)


def test_missing_prior_plan_is_explicit_not_a_block_for_new_research(workspace):
    root, guide, events = workspace
    seen = []
    out = rp.prepare(agent(), {"deep_research": True}, "새 주제를 연구해", previous_plan={
        "path": str(root / "outputs/research_plans/missing/research_plan.md")},
        supervisor=SimpleNamespace(plan=lambda p, s: seen.append(p) or json.dumps(draft())))
    assert '"read_error"' in seen[0]
    assert out["_research_plan"]["previous_path"] is None


def test_guide_search_does_not_recommend_consciousness_material():
    from ibl_routing import _search_guide
    assert "deep_research" not in json.dumps(_search_guide("", {"read": False}))
    assert rp.GUIDE not in json.dumps(_search_guide("심층연구", {"read": False}))
    assert "의식" in json.dumps(_search_guide(rp.GUIDE, {"read": True}), ensure_ascii=False)


def test_final_evaluator_receives_updated_project_plan(workspace, supervisor, monkeypatch):
    root, guide, events = workspace
    project = root / "research-project"
    supervisor.project_path = str(project)
    receipt = rp.persist("# 초기 계획\n질문: 어떤 방법인가?", guide.read_text(), project)
    Path(receipt["path"]).write_text(receipt["body"] + "\n실측 근거 위치: 관찰기록 17쪽.\n")
    supervisor.framing["_research_plan"] = receipt
    seen = []

    def evaluate(prompt, **kwargs):
        seen.append(prompt)
        assert "실측 근거 위치: 관찰기록 17쪽" in prompt
        assert receipt["sha256"] in prompt
        assert rp.GUIDE not in prompt and guide.read_text() not in prompt
        return "ACHIEVED"

    monkeypatch.setattr("consciousness_agent.system_ai_call", evaluate)
    finish(supervisor, "연구 결과입니다.")
    assert len(seen) == 1


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
