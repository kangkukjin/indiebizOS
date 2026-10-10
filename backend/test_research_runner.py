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


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
