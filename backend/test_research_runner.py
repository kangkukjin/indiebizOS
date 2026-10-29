"""연구 실행자가 기존 인지 파이프라인/감독 신원을 공유하되 주제 세션은 섞이지 않는다."""
import boot_paths  # noqa: F401
from types import SimpleNamespace
import pytest
import thread_context
from research_store import ResearchStore
from research_context import scope, current, bind_execution, adopt_execution, capture_stream
import research_runner
from agent_runner import AgentRunner


def test_topics_use_distinct_temporary_registry_and_real_cognitive_entry(tmp_path, monkeypatch):
    store = ResearchStore(tmp_path, 'runner-test')
    seen = []
    def init(runner):
        runner.ai = SimpleNamespace(agent_id=None, _provider=SimpleNamespace(agent_id=None))
    def cognitive(runner, message, history, **kwargs):
        key = thread_context.get_current_registry_key()
        assert AgentRunner.agent_registry[key] is runner
        assert kwargs['utterance_author'] == 'owner'
        assert runner.config['id'] == thread_context.get_current_agent_id()
        assert runner.ai.agent_id == runner.config['id']
        assert not history
        seen.append(key)
        yield {'type':'final','content':message}
    monkeypatch.setattr(research_runner.ResearchRunner,'_init_ai',init)
    monkeypatch.setattr(research_runner.ResearchRunner,'cognitive_stream',cognitive)
    monkeypatch.setattr(research_runner,'_search',None)
    for topic in ('교육','경제'):
        tid=store.create_thread(topic)['id'];run,_=store.begin_run(tid,topic,topic)
        import threading
        with scope(dict(project_uid=store.uid,thread_id=tid,run_id=run,path=str(store.path),epoch=store.epoch,mode='research')):
            assert list(research_runner.stream(store,tid,run,topic,threading.Event()))[-1]['content']==topic
        assert seen[-1] not in AgentRunner.agent_registry
    assert len(set(seen))==2
    thread_context.clear_all_context()


@pytest.mark.parametrize('provider', ['codex', 'claude_code', 'anthropic'])
def test_research_uses_execution_gear_without_auxiliary_substitution(tmp_path, monkeypatch, provider):
    import model_resolver
    from ai_agent import AIAgent
    config = {'provider': provider, 'model': 'execution-test'}
    calls = []
    def resolve(ai, project, agent):
        calls.append((project, agent))
        return config
    monkeypatch.setattr(model_resolver, 'resolve_agent_ai', resolve)
    monkeypatch.setattr(model_resolver, 'resolve', lambda *a, **k: pytest.fail('unexpected auxiliary model'))
    monkeypatch.setattr(AIAgent, '_init_provider', lambda self: None)
    runner = research_runner.ResearchRunner({'_project_id': 'project', '_project_path': str(tmp_path),
                                             '_selected_agent': 'selected'})
    with scope({'project_uid': 'test'}):
        actual = runner._resolve_execution_config({}, None)
        ai = AIAgent(actual, 'research role', tools=[])
    assert calls == [('project', 'selected')]
    assert ai.provider_name == provider and ai.model == 'execution-test'


def test_history_and_cli_session_identity_are_per_topic_and_resume(tmp_path, monkeypatch):
    import threading
    from providers.cli_provider import CliSubprocessProvider
    store = ResearchStore(tmp_path, 'history-test')
    seen = []
    def init(runner):
        runner.ai = SimpleNamespace(agent_id=None, _provider=SimpleNamespace(agent_id=None))
    def cognitive(runner, message, history, **kwargs):
        session = CliSubprocessProvider._get_session_key(runner.ai._provider)
        seen.append((session, history))
        yield {'type': 'final', 'content': '응답: ' + message}
    monkeypatch.setattr(research_runner.ResearchRunner, '_init_ai', init)
    monkeypatch.setattr(research_runner.ResearchRunner, 'cognitive_stream', cognitive)
    monkeypatch.setattr(research_runner, '_search', None)
    a = store.create_thread('교육')['id']
    b = store.create_thread('경제')['id']
    try:
        for n, (tid, msg) in enumerate([(a, '교육 질문'), (b, '경제 질문'), (a, '교육 후속')]):
            run, _ = store.begin_run(tid, msg, str(n))
            ctx = dict(project_uid=store.uid, thread_id=tid, run_id=run, path=str(store.path), epoch=store.epoch, mode='research')
            with scope(ctx):
                events = list(research_runner.stream(store, tid, run, msg, threading.Event()))
            store.write_response(tid, run, events[-1]['content'], 'completed')
        assert seen[0][0] == seen[2][0] != seen[1][0]
        assert not seen[0][1] and not seen[1][1]
        assert seen[2][1] == [{'role': 'user', 'content': '교육 질문'}, {'role': 'assistant', 'content': '응답: 교육 질문'}]
    finally:
        thread_context.clear_all_context()


def test_mcp_reentry_preserves_capture_scope_and_rejects_stale_identity(tmp_path, monkeypatch):
    import asyncio
    import api_ibl
    import system_tools
    import research_context
    from research_library import ResearchLibrary
    import research_capture
    monkeypatch.setattr(research_capture, 'schedule_index', lambda *a: None)
    monkeypatch.setattr(research_context, '_capture', research_capture.capture)
    monkeypatch.setattr(api_ibl, '_attach_steer', lambda value, *a: value)
    store = ResearchStore(tmp_path, 'bridge-test')
    a = store.create_thread('교육')['id']
    b = store.create_thread('경제')['id']
    run, _ = store.begin_run(a, '조사', '1')
    actor = f'research:{store.uid}:{a}'
    ctx = dict(project_uid=store.uid, thread_id=a, run_id=run, path=str(store.path), epoch=store.epoch, mode='research')
    def execute(*args, **kwargs):
        assert current() is ctx
        return research_context.observe({'router': 'handler', 'tool': 'crawl'}, {'url': 'https://example.org/education'}, {'text': '교육 자료의 전체 반환 본문'})
    monkeypatch.setattr(system_tools, '_execute_ibl_unified', execute)
    with scope(ctx), bind_execution(actor, run):
        # FastAPI가 다른 worker에 진입해도 동일한 원장에 보존한다.
        result = asyncio.run(api_ibl.execute_ibl_code(api_ibl.IBLRequest(
            code='probe', project_path=str(tmp_path), agent_id=actor, task_id=run)))
        assert result.get('success') is not False, result
        with pytest.raises(PermissionError):
            with adopt_execution(actor, run, tmp_path / 'other'):
                pass
        with adopt_execution('ordinary', 'other', tmp_path):
            assert current() is None
        assert current() is ctx
    assert len(ResearchLibrary(store, a).sources()['items']) == 1
    assert not ResearchLibrary(store, b).sources()['items']
    with pytest.raises(PermissionError):
        with adopt_execution(actor, run, tmp_path):
            pass


def test_native_results_preserved_without_double_capturing_ibl(monkeypatch):
    import research_context
    captured = []
    monkeypatch.setattr(research_context, '_capture', lambda ctx, config, params, result, call: captured.append((config['tool'], result)))
    events = [
        {'type': 'tool_start', 'id': '1', 'name': 'Read', 'input': {'file_path': '/tmp/paper.txt'}},
        {'type': 'tool_result', 'id': '1', 'name': '', 'result': '원문 본문'},
        {'type': 'tool_result', 'id': '2', 'name': 'mcp__indiebizos__execute_ibl', 'result': '이미 저장'},
        {'type': 'tool_result', 'id': '3', 'name': 'execute_ibl', 'result': '이미 저장'},
        {'type': 'tool_result', 'id': '4', 'name': 'Read', 'is_error': True, 'result': '실패'},
    ]
    with scope({'thread_id': 'topic'}):
        assert list(capture_stream(iter(events))) == events
    assert captured == [('Read', '원문 본문')]


@pytest.mark.parametrize('provider_name', ['codex', 'claude_code'])
def test_cli_library_mode_keeps_local_only_tools(provider_name, monkeypatch):
    from providers import get_provider
    monkeypatch.setattr('repair_context.active', lambda: False)
    provider = get_provider(provider_name, api_key='', model='test', system_prompt='')
    provider._binary_path = '/tmp/fake-cli'
    provider._completion_channel = ''
    with scope({'mode': 'library'}):
        command = provider._build_command(system_prompt_file='/tmp/prompt', mcp_config_path='http')
    if provider_name == 'codex':
        assert '--dangerously-bypass-approvals-and-sandbox' not in command
        assert command[command.index('--sandbox') + 1] == 'read-only'
        assert 'web_search="disabled"' in command
    else:
        assert command[command.index('--tools') + 1] == ''
        assert 'mcp__indiebizos__execute_ibl' in command[command.index('--allowed-tools') + 1]


def test_research_reuses_forage_distillation_queue_with_topic_identity(tmp_path, monkeypatch):
    import threading
    import unified_distill
    import distill_queue
    queued = []
    monkeypatch.setattr(unified_distill, 'snapshot', lambda runner, payload, ident, **kw: payload)
    monkeypatch.setattr(distill_queue.DistillQueue, 'get', lambda: SimpleNamespace(
        enqueue=lambda runner, payload, **kw: queued.append((payload, kw['ident']))))
    monkeypatch.setattr(research_runner.ResearchRunner, '_init_ai', lambda runner: setattr(
        runner, 'ai', SimpleNamespace(agent_id=None, _provider=None)))
    def cognitive(runner, message, history, **kwargs):
        # 일반 AgentRunner가 소유한 영속 증류 큐 입구를 그대로 호출한다.
        runner._after_response_async(message, '자료를 탐색한 답변', write_deep=True)
        yield {'type': 'final', 'content': '답변'}
    monkeypatch.setattr(research_runner.ResearchRunner, 'cognitive_stream', cognitive)
    monkeypatch.setattr(research_runner, '_search', None)
    store = ResearchStore(tmp_path, 'memory-test')
    try:
        for title in ('교육', '경제'):
            tid = store.create_thread(title)['id']
            run, _ = store.begin_run(tid, title, title)
            list(research_runner.stream(store, tid, run, title, threading.Event()))
        assert len(queued) == 2
        assert all(payload['write_forage'] and payload['write_experience'] for payload, ident in queued)
        assert queued[0][1]['agent_id'] != queued[1][1]['agent_id']
    finally:
        thread_context.clear_all_context()


def test_independent_research_cannot_delegate():
    from research_context import before
    with scope({'project_uid': 'test', 'thread_id': 'education'}):
        with pytest.raises(PermissionError, match='독립 실행'):
            before({'router': 'system', 'func': 'delegate'}, {'agent_id': 'another'})
        before({'router': 'handler', 'tool': 'search'}, {'query': 'education'})


def test_topic_title_is_agent_name_and_role_template_survives_rename(tmp_path, monkeypatch):
    import threading
    from episode_logger import EpisodeLogger
    (tmp_path / 'agents.yaml').write_text('agents:\n  - id: agent_001\n    name: 집사\n')
    (tmp_path / 'agent_집사_role.txt').write_text('기본 역할의 공통 지침')
    store = ResearchStore(tmp_path, 'display-name')
    tid = store.create_thread('교육')['id']
    seen = []
    monkeypatch.setattr(research_runner, '_search', None)
    def init(runner):
        assert '기본 역할의 공통 지침' in runner._load_role()
        runner.ai = SimpleNamespace(agent_id=None, _provider=None)
    def cognitive(runner, message, history, **kwargs):
        assert runner.config['name'] == thread_context.get_current_agent_name() == kwargs['agent_name']
        seen.append((runner.config['name'], runner.config['id'], runner.config['_selected_agent']))
        yield {'type': 'final', 'content': '답변'}
    logged = []
    monkeypatch.setattr(research_runner.ResearchRunner, '_init_ai', init)
    monkeypatch.setattr(research_runner.ResearchRunner, 'cognitive_stream', cognitive)
    monkeypatch.setattr(EpisodeLogger, 'start_episode', lambda name, *args, **kw: logged.append(name))
    monkeypatch.setattr(EpisodeLogger, 'end_episode', lambda: None)
    try:
        for title in ('교육', '교육 정책'):
            store.update_thread(tid, title=title)
            run, _ = store.begin_run(tid, '계속', title)
            list(research_runner.stream(store, tid, run, '계속', threading.Event()))
            store.write_response(tid, run, '답변', 'completed')
        assert logged == ['교육', '교육 정책']
        assert seen[0][1] == seen[1][1]  # 표시 이름 변경은 기억·CLI 신원을 바꾸지 않는다.
        assert seen[0][2] == seen[1][2] == 'agent_001'
    finally:
        thread_context.clear_all_context()



def test_perspective_is_always_context_and_user_statements_are_bounded(tmp_path, monkeypatch):
    import json
    store = ResearchStore(tmp_path, 'perspective-context')
    tid = store.create_thread('교육')['id']
    other = store.create_thread('경제')['id']
    store.update_thread(tid, notes='기존에 직접 쓴 관점')
    for i in range(22):
        run, _ = store.begin_run(tid, f'사용자 주장 {i}', str(i))
        store.write_response(tid, run, 'AI의 독자적인 주장', 'completed')
    run, _ = store.begin_run(other, '다른 대화의 비공개 관점', 'other')
    store.write_response(other, run, '다른 답변', 'completed')
    monkeypatch.setattr(research_runner, '_search', None)
    context = research_runner._context(store, store.thread(tid), '질문')
    data = json.loads(context.split('\n')[2])
    assert data['user_perspective']['document'] == '기존에 직접 쓴 관점'
    assert data['user_perspective']['revision'] == store.thread(tid)['revision']
    assert len(data['perspective_user_messages']) == 20
    assert data['earlier_user_messages_available']
    assert 'AI의 독자적인 주장' not in context
    assert '다른 대화의 비공개 관점' not in context
    run, _ = store.begin_run(tid, '긴 주장' * 6000, 'long')
    data = json.loads(research_runner._context(store, store.thread(tid), '질문').split('\n')[2])
    assert sum(len(item['content']) for item in data['perspective_user_messages']) <= 16000
    assert data['perspective_user_messages'][-1]['truncated']


def test_library_mode_allows_only_same_thread_perspective_updates():
    from research_context import before
    local = {'research_local': True}
    params = {'op': 'thread_update', 'project_ref': 'p', 'thread_ref': 't', 'expected_revision': 1, 'notes': '관점'}
    with scope({'project_uid': 'p', 'thread_id': 't', 'mode': 'library'}):
        before(local, params)
        for invalid in ({**params, 'mode': 'research'}, {**params, 'thread_ref': 'other'},
                        {**params, 'title': '다른 제목'}, {**params, 'project_ref': 'other'}):
            with pytest.raises(PermissionError):
                before(local, invalid)
        with pytest.raises(PermissionError):
            before({}, params)


@pytest.mark.parametrize('execution_memory', ['', '저장 자료를 확인한다'])
def test_execution_refresh_keeps_research_role_sources_and_perspective(tmp_path, monkeypatch, execution_memory):
    store = ResearchStore(tmp_path, 'prompt-delivery')
    tid = store.create_thread('교육')['id']
    store.update_thread(tid, notes='사용자의 고유한 교육 관점')
    monkeypatch.setattr(research_runner, '_search', lambda *a: {'items': [
        {'text': '저장한 원문에서 가져온 고유한 문단', 'citation': '[자료:sample:¶1]'}]})
    cfg = {'name': '교육', '_project_id': 'prompt-delivery', '_project_path': str(tmp_path),
           '_research_base_role': '상속한 기본 역할'}
    runner = research_runner.ResearchRunner(cfg)
    runner.ai = SimpleNamespace(system_prompt='', _provider=SimpleNamespace(system_prompt=''))
    for perspective in ('사용자의 고유한 교육 관점', '사용자가 정정한 새 관점'):
        store.update_thread(tid, notes=perspective)
        runner.config['_research_role'] = research_runner.PERSPECTIVE_ROLE + research_runner._context(store, store.thread(tid), '질문')
        # 초기화 시 포함됐어도 실제 호출 직전 조립에서 사라지면 회귀다.
        runner.ai.system_prompt = runner._build_system_prompt(runner._load_role())
        message = runner._refresh_execution_prompt('이번 질문', execution_memory=execution_memory)
        delivered = runner.ai._provider.system_prompt + message
        assert '상속한 기본 역할' in delivered
        assert perspective in delivered
        assert '저장한 원문에서 가져온 고유한 문단' in delivered
        assert '[자료:sample:¶1]' in delivered
        assert 'expected_revision' in delivered
        assert runner.ai.system_prompt == runner.ai._provider.system_prompt

def test_research_plan_routing_ignores_initial_toggle_but_keeps_explicit_tags(monkeypatch):
    import model_resolver
    monkeypatch.setattr(model_resolver, 'consciousness_enabled', lambda: False)
    runner = research_runner.ResearchRunner.__new__(research_runner.ResearchRunner)
    assert runner._decide_request_type('한국에서도 가능할까?', 0, '') == ('THINK', None)
    assert runner._decide_request_type('#execute 용어만 설명', 0, '') == ('EXECUTE', None)
    assert runner._decide_request_type('#repair 고쳐줘', 0, '') == ('REPAIR', None)
    ordinary = AgentRunner.__new__(AgentRunner)
    assert ordinary._decide_request_type('한국에서도 가능할까?', 0, '') == ('EXECUTE', None)


def test_research_never_uses_24_hour_framing_cache_or_silent_fallback(monkeypatch):
    import framing_inheritance
    from consciousness_agent import FramingContractError
    monkeypatch.setattr(framing_inheritance, 'inherit', lambda *a: pytest.fail('단기 계승을 사용함'))
    runner = research_runner.ResearchRunner.__new__(research_runner.ResearchRunner)
    monkeypatch.setattr(runner, '_run_consciousness', lambda *a: {'task_framing': '계획 유지'})
    assert runner._run_consciousness_or_reuse('설명', [])['task_framing'] == '계획 유지'
    monkeypatch.setattr(runner, '_run_consciousness', lambda *a: None)
    with pytest.raises(FramingContractError, match='의식 모델'):
        runner._run_consciousness_or_reuse('설명', [])


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
