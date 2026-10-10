"""연구 실행자가 기존 인지 파이프라인/감독 신원을 공유하되 주제 세션은 섞이지 않는다."""
import boot_paths  # noqa: F401
from types import SimpleNamespace
import pytest
import thread_context
from research_store import ResearchStore
from research_context import scope, model_config
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


def test_role_switch_cannot_escape_api_capture_path(monkeypatch):
    import model_resolver
    monkeypatch.setattr(model_resolver,'resolve',lambda role: {'provider':'anthropic','model':'test'})
    config={'provider':'codex'}
    assert model_config(config) is config
    with scope({'project_uid':'test'}):
        assert model_config(config)['provider']=='anthropic'
        monkeypatch.setattr(model_resolver,'resolve',lambda role: {'provider':'claude_code'})
        with pytest.raises(ValueError):model_config(config)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
