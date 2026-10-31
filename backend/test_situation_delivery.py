"""Transport request bodies, lazy failures, and opaque client history boundaries."""
import boot_paths  # noqa: F401
import json
from types import SimpleNamespace

import pytest
from test_situation_evidence import active  # noqa: F401
from test_conscious_supervisor import supervisor  # noqa: F401
from execution_situation import emit
from situation_delivery import PREFIX, prepare, observed_stream


def fact():
    emit({'kind': 'service', 'device': 'test'}, 'health', 'unavailable', source='probe')


@pytest.mark.parametrize('name', ['openai', 'anthropic', 'ollama'])
def test_sdk_final_turn_receives_same_observations(active, name):
    from providers import get_provider
    provider = get_provider(name, api_key='test', model='test', system_prompt='fixed')
    fact()
    captured = []
    def create(**args):
        captured.append(args)
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content='done'))],
                               content=[SimpleNamespace(text='done')])
    provider._client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
                                       messages=SimpleNamespace(create=create))
    assert provider._final_turn_text([{'role': 'user', 'content': 'finish'}], 100) == 'done'
    assert 'unavailable' in captured[0]['messages'][-1]['content']
    assert active.situation.cursors


@pytest.mark.parametrize('name', ['gemini_http', 'deepseek_http'])
def test_rest_actual_body_has_context_and_failed_request_keeps_cursor(active, name, monkeypatch):
    from providers import get_provider
    provider = get_provider(name, api_key='test', model='test', system_prompt='fixed')
    fact()
    captured = []
    def post(*args, **kw):
        captured.append(kw['json'])
        return SimpleNamespace(status_code=503, text='unavailable')
    monkeypatch.setattr('requests.post', post)
    call = provider._generate if name == 'gemini_http' else provider._chat
    with pytest.raises(RuntimeError):
        call([], None)
    field = 'contents' if name == 'gemini_http' else 'messages'
    assert 'Execution situation' in json.dumps(captured[0][field])
    assert not active.situation.cursors
    monkeypatch.setattr('requests.post', lambda *a, **kw: SimpleNamespace(status_code=200, json=lambda: {}))
    call([], None)
    assert active.situation.cursors


def test_anthropic_lazy_enter_failure_is_not_delivery(active):
    from providers.anthropic import AnthropicProvider
    provider = AnthropicProvider(api_key='test', model='test', system_prompt='fixed')
    fact()
    class Stream:
        def __enter__(self):
            raise RuntimeError('connection failed')
        def __exit__(self, *args):
            pass
    provider._client = SimpleNamespace(messages=SimpleNamespace(stream=lambda **kw: Stream()))
    with pytest.raises(RuntimeError):
        with provider._create_stream_with_retry({'messages': []}):
            pass
    assert not active.situation.cursors


def test_gemini_sdk_message_shape_and_lazy_ack(active):
    from providers.gemini import GeminiProvider
    from google.genai import types
    provider = GeminiProvider(api_key='test', model='test', system_prompt='fixed')
    provider._genai_types = types
    fact()
    messages = [types.Content(role='user', parts=[types.Part.from_text(text='finish')])]
    delivery = prepare(messages, provider, shape='gemini')
    assert messages[-1].parts[0].text.startswith(PREFIX)
    def failed():
        raise RuntimeError('500')
        yield
    with pytest.raises(RuntimeError):
        list(observed_stream(failed(), delivery))
    assert not active.situation.cursors
    assert list(observed_stream(iter(['recovered']), delivery)) == ['recovered']
    assert active.situation.cursors


def test_compaction_restores_baseline_and_does_not_remove_user_text(active):
    provider = SimpleNamespace(agent_role='execution')
    fact()
    user_text = PREFIX + '{"delivery_id":"not-issued-by-harness"}'
    messages = [{'role': 'user', 'content': user_text}]
    first = prepare(messages, provider)
    assert messages[0]['content'] == user_text
    first.acknowledge()
    assert prepare(messages, provider) is None
    messages[:] = [{'role': 'user', 'content': 'compacted summary'}]
    second = prepare(messages, provider)
    assert second.payload['mode'] == 'baseline'


def test_native_context_is_additional_data_and_does_not_change_permission(active):
    from supervision_hook import context_output
    fact()
    context = prepare([], SimpleNamespace(agent_role='execution')).payload
    output = context_output({'tool_name': 'Read', 'tool_input': {'path': 'x'}}, json.dumps(context))
    assert set(output['hookSpecificOutput']) == {'hookEventName', 'additionalContext'}
    shell = context_output({'tool_name': 'Bash', 'tool_input': {'command': 'echo ok'}}, json.dumps(context))
    assert shell['hookSpecificOutput']['updatedInput']['command'] == 'set -o pipefail\necho ok'
    assert 'permissionDecision' not in shell['hookSpecificOutput']


def test_other_role_does_not_consume_executor_cursor(active):
    fact()
    assert prepare([], SimpleNamespace(agent_role='consciousness')) is None
    assert not active.situation.cursors


def test_supervisor_reads_owner_projection_without_consuming_executor_cursor(supervisor):
    import execution_turn
    from situation_evidence import attach
    from thread_context import actor_context
    token = execution_turn.enter(supervisor.runner, request='original')
    try:
        binding = execution_turn.current()
        attach(binding, supervisor.store)
        fact()
        with actor_context(agent_id=supervisor.supervisor_id):
            snapshot = supervisor.state()['execution_situation']
        assert snapshot['projection_revision'] == binding.situation.revision
        assert not binding.situation.cursors
    finally:
        execution_turn.leave(token)


if __name__ == '__main__':
    import sys
    import pytest
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
