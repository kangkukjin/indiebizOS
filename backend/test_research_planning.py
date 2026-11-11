"""의식의 전문가 접근·계획 인계와 재사용, 실패·취소·판본 경계를 검증한다."""
import boot_paths  # noqa: F401
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import research_planning as rp
from consciousness_agent import ConsciousnessAgent, ConsciousnessCallSkipped
from prompt_builder import compile_user_command

PLAN = '# 연구계획\n경쟁 설명을 비교할 관측을 먼저 정하고 자료의 조건을 맞춰 판단한다.\n'


def planner():
    return SimpleNamespace(_provider=object())


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr('runtime_utils.get_base_path', lambda: tmp_path)
    monkeypatch.setattr('prompt_builder.get_base_path', lambda: tmp_path)
    monkeypatch.setattr('guide_registry.record_use', lambda *a: None)
    monkeypatch.setattr('guide_registry.mark_injected', lambda *a: None)
    monkeypatch.setattr('member_runtime.is_member', lambda: False)
    monkeypatch.setattr('episode_logger.record_trajectory_event', lambda *a: None)
    guide = tmp_path / 'data/guides/deep_research.md'
    guide.parent.mkdir(parents=True)
    guide.write_text('분야의 연구방식을 참고하여 증거·분석·종합을 계획한다.')
    guide.with_name(rp.EXECUTION_GUIDE).write_text('실행 지침: 핵심 주장을 실제 읽은 원문과 대조한다.')
    monkeypatch.setattr('consciousness_agent.call_oneshot_provider', lambda *a, **kw: PLAN)
    return tmp_path


def draft(**kw):
    return {'task_framing': '기존 자료로 사용자 질문에 답한다', 'deep_research': True, **kw}


def topic(root, mode='research'):
    from research_store import ResearchStore
    store = ResearchStore(root, 'p')
    tid = store.create_thread('교육', mode=mode)['id']
    run, _ = store.begin_run(tid, '교육에 관해 이야기해보자', 'first')
    return store, tid, run


def test_general_task_has_no_plan_or_call(workspace):
    framing = draft(deep_research=False)
    assert rp.prepare(None, framing, '', project_path=workspace) == framing
    assert not (workspace / 'outputs').exists()


@pytest.mark.parametrize('deep', [False, True])
def test_only_deep_research_adds_one_consciousness_plan_call(workspace, monkeypatch, deep):
    agent = ConsciousnessAgent.__new__(ConsciousnessAgent)
    agent._provider = SimpleNamespace(is_ready=True)
    agent._prompt = agent._supervisor_prompt = '사용자 요청 명료화'
    agent._prompt_path = None
    calls = []
    def invoke(*a, **kw):
        calls.append((a, kw))
        return PLAN if kw.get('role') == 'research_plan' else json.dumps(draft(
            deep_research=deep, capability_focus={'hint': '비교 조건을 맞추면 경쟁 설명을 구별할 수 있다'}))
    monkeypatch.setattr('consciousness_agent.call_oneshot_provider', invoke)
    out = agent.process('교육을 연구해줘', [], '', project_path=workspace)
    assert len(calls) == (2 if deep else 1)
    assert ('_research_plan' in out) is deep
    command = compile_user_command('교육을 연구해줘', out)
    hint = '비교 조건을 맞추면 경쟁 설명을 구별할 수 있다'
    assert command.count(hint) == (0 if deep else 1)
    if deep:
        assert out['_research_plan']['author'] == 'consciousness'
        assert PLAN.strip() in out['_research_plan']['body']
        assert json.dumps(out['_research_plan']['body'], ensure_ascii=False) in command
        assert 'deep_research.md' not in out.get('guide_files', [])
        planning_input = calls[1][0][1]
        assert 'research_planning_guide' in planning_input
        assert hint in planning_input
        assert 'capability_focus' not in out
        assert '실행 지침: 핵심 주장을 실제 읽은 원문과 대조한다.' in command
        assert '실행 지침: 핵심 주장을 실제 읽은 원문과 대조한다.' not in planning_input
        assert calls[1][1]['step_role'] == 'consciousness'


def test_reused_plan_keeps_new_question_hint_and_current_execution_guide(workspace):
    prior = rp.prepare(planner(), draft(), '', project_path=workspace)['_research_plan']
    hint = '이번 하위 질문은 표본의 연령 차이를 확인한다'
    out = rp.prepare(None, draft(capability_focus={'hint': hint}), '',
                     project_path=workspace, previous_plan=prior)
    assert hint in compile_user_command('연령별로 설명해줘', out)
    guide = workspace / 'data/guides' / rp.EXECUTION_GUIDE
    guide.write_text('새 실행 지침: 연령·기간·분모를 맞춘다.')
    # 같은 프로세스의 후속·명시 실행 인계도 현재 지침을 받는다.
    assert '새 실행 지침: 연령·기간·분모를 맞춘다.' in rp.execution_block(out)
    assert rp.execution_block(draft()) == ''
    guide.unlink()
    assert '연구 실행 지침 미제공: read_guide' in rp.execution_block(out)
    assert Path(prior['path']).read_text() == prior['body']


@pytest.mark.parametrize('mode', ['research', 'library'])
def test_topic_preserves_executor_edits_without_replanning(workspace, mode):
    store, tid, run = topic(workspace, mode)
    context = lambda: rp.topic_context(workspace, store.uid, tid, run)
    first = rp.prepare(planner(), draft(), '', project_path=workspace, topic=context())
    path = Path(first['_research_plan']['path'])
    body = '# 실행자가 작성한 계획\n질문 q1\n확보한 자료 A\n남은 질문 B\n'
    path.write_text(body)
    second = rp.prepare(None, draft(task_framing='A에 대해 설명'), '', project_path=workspace, topic=context())
    assert second['_research_plan']['path'] == str(path)
    assert second['_research_plan']['body'] == body
    assert second['_research_plan']['revision'] == 1
    block = rp.execution_block(second)
    assert body in json.loads(block.split('\n')[1])['body']
    assert ('파일 쓰기·외부 획득은 하지 않는다' in block) is (mode == 'library')
    assert path.read_text() == body


def test_revision_keeps_plan_and_rejects_stale_observation(workspace):
    store, tid, run = topic(workspace)
    context = lambda: rp.topic_context(workspace, store.uid, tid, run)
    first = rp.prepare(planner(), draft(), '', project_path=workspace, topic=context())
    observed = context()
    updated = rp.apply_revision_plan({**first, 'task_framing': '증가량만 비교'}, {}, observed, workspace)
    assert updated['task_framing'] == '증가량만 비교'
    assert updated['_research_plan']['path'] == first['_research_plan']['path']
    Path(first['_research_plan']['path']).write_text('실행자의 새 관측')
    with pytest.raises(ValueError, match='변경'):
        rp.apply_revision_plan(first, {}, observed, workspace)
    assert Path(first['_research_plan']['path']).read_text() == '실행자의 새 관측'


@pytest.mark.parametrize('field', ['needs_clarification', 'needs_repair'])
def test_clarification_and_repair_do_not_open_plan(workspace, field):
    out = rp.prepare(None, draft(**{field: True}), '', project_path=workspace)
    assert '_research_plan' not in out and not (workspace / 'outputs').exists()


def test_cancelled_preparation_does_not_write(workspace):
    with pytest.raises(ConsciousnessCallSkipped):
        rp.prepare(None, draft(), '', project_path=workspace, supervisor=SimpleNamespace(cancelled=lambda: True))
    assert not (workspace / 'outputs').exists()


def test_plan_cannot_cross_workspace(workspace, tmp_path):
    first = rp.prepare(planner(), draft(), '', project_path=workspace / 'one')
    with pytest.raises(ValueError, match='작업공간 밖'):
        rp.prepare(None, draft(), '', project_path=workspace / 'two', previous_plan=first['_research_plan'])


def test_missing_existing_plan_is_not_silently_replaced(workspace):
    out = rp.prepare(planner(), draft(), '', project_path=workspace)
    Path(out['_research_plan']['path']).unlink()
    with pytest.raises(FileNotFoundError):
        rp.prepare(None, draft(), '', project_path=workspace, previous_plan=out['_research_plan'])


def test_guide_available_to_executor():
    from guide_registry import execution_guides, execution_guide_map
    assert execution_guides(['deep_research.md', 'deep_research.md']) == ['deep_research.md']
    text = '<guide_map>조사: deep_research.md</guide_map>'
    assert execution_guide_map(text) == text


def test_research_topic_discussion_does_not_create_placeholder(workspace):
    store, tid, run = topic(workspace)
    out = rp.prepare(None, draft(deep_research=False), '', project_path=workspace,
                     topic=rp.topic_context(workspace, store.uid, tid, run))
    assert '_research_plan' not in out
    assert not (workspace / 'outputs').exists()


@pytest.mark.parametrize('guide_name', ['deep_research.md', 'data/guides/deep_research.md',
                                      'data\\guides\\deep_research.md'])
def test_supervisor_plan_receives_guide_once_and_publishes_before_handoff(workspace, guide_name):
    calls = []
    def invoke(prompt, system, **kw):
        calls.append((prompt, system, kw))
        assert not list(workspace.glob('outputs/research_plans/*/research_plan.md'))
        return PLAN
    supervisor = SimpleNamespace(plan=invoke, cancelled=lambda: False)
    out = rp.prepare(planner(), draft(deep_research=False, guide_files=[guide_name, 'statistics.md']),
                     '사용자 원문·관련 대화', supervisor=supervisor, project_path=workspace)
    assert len(calls) == 1 and calls[0][2] == {'completion': True}
    assert calls[0][0].count('분야의 연구방식을 참고하여 증거·분석·종합을 계획한다.') == 1
    assert '사용자 원문·관련 대화' in calls[0][0]
    receipt = out['_research_plan']
    assert Path(receipt['path']).read_text() == receipt['body']
    assert receipt['author'] == 'consciousness' and receipt['guide_sha256']
    assert out['guide_files'] == ['statistics.md']


def test_revised_plan_preserves_current_progress_and_advances_topic(workspace, monkeypatch):
    store, tid, run = topic(workspace)
    context = lambda: rp.topic_context(workspace, store.uid, tid, run)
    first = rp.prepare(planner(), draft(), '', project_path=workspace, topic=context())
    path = Path(first['_research_plan']['path'])
    path.write_text(PLAN + '확인한 근거 A, 남은 질문 B\n')
    calls = []
    def invoke(provider, prompt, **kw):
        calls.append(prompt)
        assert '확인한 근거 A, 남은 질문 B' in prompt
        return PLAN + '확인한 근거 A를 보존하고 새 범위에서 B를 조사한다.\n'
    monkeypatch.setattr('consciousness_agent.call_oneshot_provider', invoke)
    out = rp.prepare(planner(), draft(revise_research_plan=True), '범위가 바뀌었다',
                     project_path=workspace, topic=context())
    assert len(calls) == 1 and out['_research_plan']['revision'] == 2
    assert out['_research_plan']['previous_path'] == str(path)
    assert 'revise_research_plan' not in out
    assert path.read_text() == PLAN + '확인한 근거 A, 남은 질문 B\n'
    assert context()['current_plan']['body'] == out['_research_plan']['body']


@pytest.mark.parametrize('failure', ['empty', 'provider', 'save', 'cancel', 'changed'])
def test_planning_failure_never_hands_off_placeholder_or_repeats(workspace, monkeypatch, failure):
    from consciousness_agent import FramingContractError
    prior = rp.prepare(planner(), draft(), '', project_path=workspace)['_research_plan']
    path = Path(prior['path'])
    calls = []
    cancelled = [False]
    def invoke(*args, **kwargs):
        calls.append(args)
        if failure == 'provider':
            raise RuntimeError('provider failed')
        if failure == 'cancel':
            cancelled[0] = True
        if failure == 'changed':
            path.write_text('새 관측')
        return '' if failure == 'empty' else PLAN
    monkeypatch.setattr('consciousness_agent.call_oneshot_provider', invoke)
    if failure == 'save':
        def fail_save(*args, **kwargs):
            raise OSError('disk failed')
        monkeypatch.setattr(rp, 'persist', fail_save)
    with pytest.raises((FramingContractError, ValueError, OSError)):
        rp.prepare(planner(), draft(revise_research_plan=True), '', project_path=workspace,
                   previous_plan=prior, supervisor=SimpleNamespace(
                       cancelled=lambda: cancelled[0], plan=invoke))
    assert len(calls) == 1
    assert len(list(workspace.glob('outputs/research_plans/*/research_plan.md'))) == 1
    assert path.read_text() == ('새 관측' if failure == 'changed' else prior['body'])


def test_existing_general_plan_is_seen_by_initial_consciousness_and_reused(workspace, monkeypatch):
    prior = rp.prepare(planner(), draft(), '', project_path=workspace)['_research_plan']
    Path(prior['path']).write_text(PLAN + '수집된 근거 C\n')
    agent = ConsciousnessAgent.__new__(ConsciousnessAgent)
    agent._provider = SimpleNamespace(is_ready=True)
    agent._prompt = agent._supervisor_prompt = '요청·접근 판단'
    agent._prompt_path = None
    calls = []
    def invoke(provider, prompt, **kwargs):
        calls.append(prompt)
        assert '수집된 근거 C' in prompt
        return json.dumps(draft())
    monkeypatch.setattr('consciousness_agent.call_oneshot_provider', invoke)
    out = agent.process('이어서 조사해줘', [], '', project_path=workspace, previous_research_plan=prior)
    assert len(calls) == 1
    assert out['_research_plan']['path'] == prior['path']
    assert '수집된 근거 C' in out['_research_plan']['body']


@pytest.mark.parametrize('existing,revise,expected', [(False, False, False),
                                                   (True, False, True), (True, True, False)])
def test_inheritance_reuses_plan_or_returns_to_consciousness(workspace, monkeypatch, existing, revise, expected):
    import framing_inheritance as fi
    framing = draft()
    if existing:
        framing = rp.prepare(planner(), framing, '', project_path=workspace)
    previous = {'message': '같은 연구', 'framing': framing}
    monkeypatch.setattr(fi, '_candidate', lambda *args: ('repeat', previous))
    monkeypatch.setattr(fi, '_patch', lambda *args, **kw: {'revise_research_plan': revise})
    result = fi.inherit(SimpleNamespace(project_path=workspace), '같은 연구', [])
    assert bool(result) is expected
    if expected:
        assert result['_research_plan']['path'] == framing['_research_plan']['path']


@pytest.mark.parametrize('error', [RuntimeError('project changed'), OSError('save failed'),
                                  ConsciousnessCallSkipped('budget', 'budget exhausted')])
def test_process_does_not_fall_back_to_execution_on_plan_handoff_failure(workspace, monkeypatch, error):
    from consciousness_agent import FramingContractError
    agent = ConsciousnessAgent.__new__(ConsciousnessAgent)
    agent._provider = SimpleNamespace(is_ready=True)
    agent._prompt = agent._supervisor_prompt = '요청·접근 판단'
    agent._prompt_path = None
    monkeypatch.setattr('consciousness_agent.call_oneshot_provider', lambda *a, **kw: json.dumps(draft()))
    def fail(*args, **kw):
        raise error
    monkeypatch.setattr(rp, 'prepare', fail)
    expected = ConsciousnessCallSkipped if isinstance(error, ConsciousnessCallSkipped) else FramingContractError
    with pytest.raises(expected):
        agent.process('연구해줘', [], '', project_path=workspace)
