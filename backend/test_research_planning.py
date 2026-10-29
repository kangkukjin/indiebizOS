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
    supervisor = SimpleNamespace(plan=lambda *a, **kw: pytest.fail("일반 작업의 추가 호출"))
    assert rp.prepare(agent(), output, "심층연구 기능을 수리해줘", supervisor=supervisor) is output
    assert events == [] and not (root / "outputs").exists()


@pytest.mark.parametrize("legacy", [False, True])
def test_consciousness_reads_guide_and_saved_bytes_reach_executor(workspace, legacy):
    root, guide, events = workspace
    calls = []

    def plan(prompt, system, **kwargs):
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
    supervisor = SimpleNamespace(plan=lambda *a, **kw: json.dumps(response))
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
                     supervisor=SimpleNamespace(plan=lambda p, s, **kw: seen.append(p) or json.dumps(draft())))
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

    def plan(prompt, system, revision=None, **kwargs):
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
    supervisor = SimpleNamespace(plan=lambda *a, **kw: json.dumps({"task_framing": "연구", "deep_research": True}))
    with pytest.raises(FramingContractError):
        agent().process("깊이 연구해줘", [], "", supervisor=supervisor)


def test_missing_prior_plan_is_explicit_not_a_block_for_new_research(workspace):
    root, guide, events = workspace
    seen = []
    out = rp.prepare(agent(), {"deep_research": True}, "새 주제를 연구해", previous_plan={
        "path": str(root / "outputs/research_plans/missing/research_plan.md")},
        supervisor=SimpleNamespace(plan=lambda p, s, **kw: seen.append(p) or json.dumps(draft())))
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


def test_initial_exploration_cannot_starve_required_plan(workspace, supervisor, monkeypatch):
    """초기 판단이 soft 예산을 넘긴 실제 5600 경로에서도 저장 뒤 실행에 인계한다."""
    from providers.base import ProviderMetrics
    calls = []

    class Model:
        def __init__(self, *args, **kwargs):
            self.kwargs = kwargs
            self._provider = SimpleNamespace(metrics=ProviderMetrics())
            self.model, self.provider_name = "test", "test"

        def process_message_stream(self, prompt, **kwargs):
            calls.append(self.kwargs)
            completion = self.kwargs["role"] == "oneshot:plan_completion"
            if completion:
                assert self.kwargs["tools"] == [] and self._provider.no_tools
                assert "tool_context=" not in prompt
                assert not supervisor.model_admitted("plan")
                assert not list(workspace[0].glob("outputs/research_plans/*/research_plan.md"))
            self._provider.metrics.record_usage(1, {
                "input_tokens": 17066 if not completion else 30000,
                "cache_read_input_tokens": 218487 if not completion else 0,
                "output_tokens": 3483 if not completion else 2000,
            })
            yield {"type": "final", "content": json.dumps(
                draft() if completion else {"task_framing": "연구", "deep_research": True})}

    monkeypatch.setattr("ai_agent.AIAgent", Model)
    monkeypatch.setattr("model_resolver.resolve", lambda *a: {})
    out = agent().process("기존 대화에서 출발해 연구해줘", [], "", supervisor=supervisor)
    assert len(calls) == 2
    assert Path(out["_research_plan"]["path"]).exists()
    assert supervisor.phase_usage["plan"]["input"] == 235553
    assert supervisor.phase_usage["plan_completion"]["input"] == 30000
    assert supervisor.usage["input"] == 265553  # 초과량·완성 비용을 모두 보존
    assert supervisor.reviews == 0


@pytest.mark.parametrize("stop", ["budget", "cancelled"])
def test_unstarted_plan_preserves_reason_without_json_retry(workspace, supervisor, monkeypatch, stop):
    from consciousness_agent import ConsciousnessCallSkipped
    if stop == "budget":
        supervisor.config["budget_mode"] = "hard"
        supervisor.usage["input"] = supervisor.config["max_input_tokens"]
    else:
        supervisor.cancel_check = lambda: True
    monkeypatch.setattr("ai_agent.AIAgent", lambda *a, **kw: pytest.fail("생략된 호출 시작"))
    with pytest.raises(ConsciousnessCallSkipped) as exc:
        rp.prepare(agent(), {"deep_research": True}, "연구", supervisor=supervisor)
    assert exc.value.kind == stop
    assert "JSON" not in str(exc.value)
    rows = [json.loads(line) for line in (supervisor.store.directory / "events.jsonl").read_text().splitlines()]
    skipped = [row for row in rows if row["kind"] == "model.skipped"]
    assert len(skipped) == 1 and skipped[0]["phase"] == "plan_completion"
    assert skipped[0]["role"] == "consciousness"
    assert workspace[2][-1][0] == "research.plan_skipped"
    assert not (workspace[0] / "outputs").exists()


def test_invalid_completion_is_bounded_and_never_delivered(workspace):
    calls = []
    def plan(*args, **kwargs):
        calls.append(kwargs)
        return json.dumps(draft(research_plan=""))
    with pytest.raises(FramingContractError, match="실제 계획 본문"):
        rp.prepare(agent(), {"deep_research": True}, "연구", supervisor=SimpleNamespace(plan=plan))
    assert calls == [{"completion": True}, {"completion": True}]
    assert not (workspace[0] / "outputs").exists()


@pytest.mark.parametrize("interrupted", [False, True])
def test_completion_real_agent_has_no_tools_and_keeps_interruption_reason(workspace, supervisor, monkeypatch, interrupted):
    from providers.base import ProviderMetrics
    calls = []

    class Provider:
        is_ready = True

        def __init__(self, **kwargs):
            self.metrics, self._client = ProviderMetrics(), None
            assert kwargs["tools"] == []

        def init_client(self):
            pass

        def process_message_stream(self, message, history, images, execute_tool, cancel_check):
            calls.append(message)
            assert self.no_tools and self.tools == []
            assert self.agent_role == "oneshot:plan_completion"
            if interrupted:
                supervisor.call_deadline = 0
                assert cancel_check()
                yield {"type": "error", "content": "시간 한도"}
            else:
                yield {"type": "final", "content": json.dumps(draft())}

    monkeypatch.setattr("providers.get_provider", lambda name, **kw: Provider(**kw))
    monkeypatch.setattr("model_resolver.resolve", lambda role: {"provider": "openai", "model": "fake"})
    if interrupted:
        with pytest.raises(FramingContractError, match="시간 한도"):
            rp.prepare(agent(), {"deep_research": True}, "연구", supervisor=supervisor)
        assert not (workspace[0] / "outputs").exists()
    else:
        out = rp.prepare(agent(), {"deep_research": True}, "연구", supervisor=supervisor)
        assert Path(out["_research_plan"]["path"]).exists()
    assert len(calls) == 1


def research_topic(workspace, mode='research'):
    from research_store import ResearchStore
    root = workspace[0] / 'project'
    root.mkdir()
    store = ResearchStore(root, 'p')
    tid = store.create_thread('교육', mode=mode)['id']
    run, _ = store.begin_run(tid, 'AI와 교육을 이야기해보자', 'first')
    return store, tid, run


def test_topic_creates_without_keyword_then_keeps_and_revises_one_plan(workspace):
    store, tid, run = research_topic(workspace)
    calls = []
    action = 'revise'

    def plan(prompt, system, revision=None, **kwargs):
        calls.append(prompt)
        if not kwargs.get('completion'):
            assert '하나의 연구' in prompt
            assert tid in prompt
            return json.dumps({'task_framing': '이번 질문만 다룬다', 'deep_research': False,
                               'research_plan_action': action})
        return json.dumps(draft(research_plan='# 전체 연구: 교육\n교사 역할과 학생 자율성.\n'
                               '변경 이유: 한국의 적용 조건을 확인한다.'))

    def turn():
        return agent().process('한국에서도 가능할까?', [], '',
                               supervisor=SimpleNamespace(plan=plan), project_path=store.path,
                               research_topic=rp.topic_context(store.path, store.uid, tid, run))

    initial = turn()
    first = initial['_research_plan']
    assert len(calls) == 2 and first['revision'] == 1
    assert initial['deep_research'] is False  # 계획 작성이 깊은 조사 강제가 아니다.
    path = Path(first['path'])
    path.write_text(path.read_text() + '\n실행 관측: 반박 근거 A, 다음 확인 B.\n')
    store.write_response(tid, run, '응답', 'completed')
    run, _ = store.begin_run(tid, '이 용어를 설명해줘', 'followup')
    action = 'keep'
    kept = turn()
    assert len(calls) == 3  # 유지에는 교재/계획 작성 호출을 추가하지 않는다.
    assert kept['_research_plan']['path'] == str(path)
    assert kept['_research_plan']['revision'] == 1
    assert '반박 근거 A' in calls[-1] and '반박 근거 A' in rp.execution_block(kept)
    assert rp.GUIDE not in rp.execution_block(kept)
    action = 'revise'
    revised = turn()
    assert len(calls) == 5
    assert '반박 근거 A' in calls[-1]
    assert revised['_research_plan']['revision'] == 2
    assert revised['_research_plan']['previous_path'] == str(path)
    assert '반박 근거 A' in path.read_text()  # 이전 판본·근거 보존
    other = store.create_thread('경제')['id']
    other_run, _ = store.begin_run(other, '경제', 'other')
    assert rp.topic_context(store.path, store.uid, other, other_run)['receipt'] is None


def test_topic_plan_failure_preserves_current_link_and_library_mode(workspace, monkeypatch):
    from research_plans import ResearchPlans
    store, tid, run = research_topic(workspace, 'library')
    topic = rp.topic_context(store.path, store.uid, tid, run)
    assert '저장 자료만' in rp.topic_prompt(topic) and '"mode": "library"' in rp.topic_prompt(topic)
    out = rp.prepare(agent(), {'research_plan_action': 'revise'}, '최초 대화',
                     topic=topic, project_path=store.path,
                     supervisor=SimpleNamespace(plan=lambda *a, **k: json.dumps(draft())))
    topic = rp.topic_context(store.path, store.uid, tid, run)
    monkeypatch.setattr(ResearchPlans, 'bind', lambda *a: (_ for _ in ()).throw(OSError('disk full')))
    with pytest.raises(FramingContractError, match='disk full'):
        rp.prepare(agent(), {'research_plan_action': 'revise'}, '범위 변경',
                   topic=topic, project_path=store.path,
                   supervisor=SimpleNamespace(plan=lambda *a, **k: json.dumps(draft())))
    assert rp.topic_context(store.path, store.uid, tid, run)['receipt']['path'] == out['_research_plan']['path']
    Path(out['_research_plan']['path']).unlink()
    with pytest.raises(FileNotFoundError):
        rp.topic_context(store.path, store.uid, tid, run)  # 없는 계획을 초기화해 진행하지 않는다.


def test_topic_clarification_and_repair_leave_plan_untouched(workspace):
    store, tid, run = research_topic(workspace)
    topic = rp.topic_context(store.path, store.uid, tid, run)
    for framing in ({'needs_clarification': True}, {'needs_repair': True}):
        out = rp.prepare(agent(), framing, '요청', topic=topic, project_path=store.path,
                         supervisor=SimpleNamespace(plan=lambda *a, **k: pytest.fail('계획 작성 금지')))
        assert '_research_plan' not in out
    assert rp.topic_context(store.path, store.uid, tid, run)['receipt'] is None


def test_topic_missing_choice_uses_existing_contract_correction(workspace):
    store, tid, run = research_topic(workspace)
    calls = []

    def plan(prompt, system, revision=None, **kwargs):
        calls.append(prompt)
        if kwargs.get('completion'):
            return json.dumps(draft())
        if len(calls) == 1:
            return json.dumps({'task_framing': '연구를 이어간다'})
        assert 'research_plan_action' in prompt
        return json.dumps({'task_framing': '연구를 이어간다', 'research_plan_action': 'revise'})

    out = agent().process('교육에 관해', [], '', supervisor=SimpleNamespace(plan=plan),
                          project_path=store.path,
                          research_topic=rp.topic_context(store.path, store.uid, tid, run))
    assert len(calls) == 3 and out['_research_plan']['revision'] == 1


def test_research_stream_delivers_persistent_plan_through_real_consciousness_entry(workspace, monkeypatch):
    import threading
    import consciousness_agent as ca
    import research_runner as rr
    import framing_inheritance
    import supervision_bus
    import thread_context
    from research_context import scope
    store, tid, run = research_topic(workspace)
    calls, delivered = [], []
    action = 'revise'

    def plan(prompt, system, revision=None, **kwargs):
        calls.append(prompt)
        if kwargs.get('completion'):
            return json.dumps(draft(research_plan='# 하나의 교육 연구\n질문: 교사 역할과 학생 자율성'))
        return json.dumps({'task_framing': '전체 연구에서 이번 질문을 설명한다',
                           'deep_research': False, 'research_plan_action': action})

    monkeypatch.setattr(ca, 'get_consciousness_agent', agent)
    monkeypatch.setattr(ca, 'get_world_pulse_text', lambda: '')
    monkeypatch.setattr(supervision_bus, 'current', lambda *a: SimpleNamespace(plan=plan))
    monkeypatch.setattr(framing_inheritance, '_load', lambda *a: pytest.fail('단기 캐시 접근'))
    monkeypatch.setattr(rr, '_search', None)
    monkeypatch.setattr(rr.ResearchRunner, '_get_available_tools', lambda self: [])
    monkeypatch.setattr(rr.ResearchRunner, '_init_ai', lambda runner: setattr(
        runner, 'ai', SimpleNamespace(agent_id=None, system_prompt='',
                                     _provider=SimpleNamespace(agent_id=None, system_prompt=''))))

    def cognitive(runner, message, history, **kwargs):
        assert runner._decide_request_type(message, 0, '', history)[0] == 'THINK'
        output = runner._run_consciousness_or_reuse(message, history)
        command = runner._refresh_execution_prompt(message, output)
        delivered.append(runner.ai._provider.system_prompt + command)
        assert Path(output['_research_plan']['path']).exists()
        yield {'type': 'final', 'content': '이번 질문의 답변'}

    monkeypatch.setattr(rr.ResearchRunner, 'cognitive_stream', cognitive)
    try:
        for n in range(2):
            if n:
                action = 'keep'
                run, _ = store.begin_run(tid, '학생의 자율성은?', 'second')
            with scope(dict(project_uid=store.uid, thread_id=tid, run_id=run,
                            path=str(store.path), epoch=store.epoch, mode='research')):
                list(rr.stream(store, tid, run, '학생의 자율성은?', threading.Event()))
            store.write_response(tid, run, '답변', 'completed')
        assert len(calls) == 3
        assert all('하나의 교육 연구' in text for text in delivered)
        assert all(workspace[1].read_text() not in text for text in delivered)
        assert rp.topic_context(store.path, store.uid, tid, run)['revision'] == 1
    finally:
        thread_context.clear_all_context()


if __name__ == "__main__":
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
