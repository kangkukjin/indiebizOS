"""실행자 소유 연구 문서: 모델 왕복 없이 전달하고 작업·판본 경계는 보존한다."""
import boot_paths  # noqa: F401
import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import research_planning as rp
from consciousness_agent import ConsciousnessAgent, ConsciousnessCallSkipped


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr('runtime_utils.get_base_path', lambda: tmp_path)
    monkeypatch.setattr('member_runtime.is_member', lambda: False)
    monkeypatch.setattr('episode_logger.record_trajectory_event', lambda *a: None)
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
def test_consciousness_returns_after_one_call(workspace, monkeypatch, deep):
    agent = ConsciousnessAgent.__new__(ConsciousnessAgent)
    agent._provider = SimpleNamespace(is_ready=True)
    agent._prompt = agent._supervisor_prompt = '사용자 요청 명료화'
    agent._prompt_path = None
    calls = []
    def invoke(*a, **kw):
        calls.append(a)
        return json.dumps(draft(deep_research=deep))
    monkeypatch.setattr('consciousness_agent.call_oneshot_provider', invoke)
    out = agent.process('교육을 연구해줘', [], '', project_path=workspace)
    assert len(calls) == 1
    assert ('_research_plan' in out) is deep
    if deep:
        assert out['_research_plan']['author'] == 'execution'
        assert '연구 작업 메모' in out['_research_plan']['body']
        assert out['guide_files'][0] == 'deep_research.md'


@pytest.mark.parametrize('mode', ['research', 'library'])
def test_topic_preserves_executor_edits_without_replanning(workspace, mode):
    store, tid, run = topic(workspace, mode)
    context = lambda: rp.topic_context(workspace, store.uid, tid, run)
    first = rp.prepare(None, draft(deep_research=False), '', project_path=workspace, topic=context())
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
    first = rp.prepare(None, draft(), '', project_path=workspace, topic=context())
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
    first = rp.prepare(None, draft(), '', project_path=workspace / 'one')
    with pytest.raises(ValueError, match='작업공간 밖'):
        rp.prepare(None, draft(), '', project_path=workspace / 'two', previous_plan=first['_research_plan'])


def test_missing_existing_plan_is_not_silently_replaced(workspace):
    out = rp.prepare(None, draft(), '', project_path=workspace)
    Path(out['_research_plan']['path']).unlink()
    with pytest.raises(FileNotFoundError):
        rp.prepare(None, draft(), '', project_path=workspace, previous_plan=out['_research_plan'])


def test_guide_available_to_executor():
    from guide_registry import execution_guides, execution_guide_map
    assert execution_guides(['deep_research.md', 'deep_research.md']) == ['deep_research.md']
    text = '<guide_map>조사: deep_research.md</guide_map>'
    assert execution_guide_map(text) == text
