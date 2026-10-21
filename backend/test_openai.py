"""도구 오류가 대화를 중단하거나 이전 이미지와 섞이지 않는 계약."""
import boot_paths  # noqa: F401

import pytest

from providers.openai import OpenAIProvider
from providers.deepseek import DeepSeekProvider
from providers.anthropic import AnthropicProvider
from providers.ollama import OllamaProvider


def _run(provider, calls, execute):
    messages = []
    kwargs = dict(messages=messages, collected_text="", execute_tool=execute, depth=0)
    if isinstance(provider, AnthropicProvider):
        kwargs['tool_uses'] = [dict(id=k, name=v['name'], input={}) for k, v in calls.items()]
    else:
        kwargs.update(tool_calls=calls, openai_tools=[])
        if isinstance(provider, OpenAIProvider):
            kwargs['collected_reasoning'] = ""
    provider._agentic_loop = lambda *a, **k: iter([{'type': 'final', 'content': 'recovered'}])
    events = list(provider._execute_tools_and_continue(**kwargs))
    assert events[-1] == {'type': 'final', 'content': 'recovered'}
    return [e for e in events if e['type'] == 'tool_result'], messages


@pytest.mark.parametrize('cls', [OpenAIProvider, DeepSeekProvider, AnthropicProvider, OllamaProvider])
@pytest.mark.parametrize('failure', ['exception', 'missing_handler', 'image_then_exception'])
def test_tool_failure_continues_without_stale_images(cls, failure):
    provider = cls(api_key='test', model='test', system_prompt='', tools=[])
    image = {'base64': 'cGl4ZWw=', 'media_type': 'image/png'}
    calls = {'bad': {'name': 'bad', 'arguments': '{}'}}
    if failure == 'image_then_exception':
        calls = {'good': {'name': 'good', 'arguments': '{}'}, **calls}

    def execute(name, args, *_context):
        if name == 'good':
            return {'content': 'image result', 'images': [image]}
        raise ValueError('recoverable tool failure')

    results, messages = _run(provider, calls, None if failure == 'missing_handler' else execute)
    assert results[-1]['is_error'] is True
    if failure != 'missing_handler':
        assert 'recoverable tool failure' in results[-1]['result']
    assert 'images' not in results[-1]
    # The failing call must not inherit/replay the preceding successful image.
    import json
    assert json.dumps(messages).count(image['base64']) == int(failure == 'image_then_exception')
    if hasattr(provider, '_last_tool_images'):
        assert provider._last_tool_images == ([image] if failure == 'image_then_exception' else [])


@pytest.mark.parametrize('cls', [OpenAIProvider, DeepSeekProvider, OllamaProvider])
def test_malformed_tool_json_is_returned_to_model(cls):
    provider = cls(api_key='test', model='test', system_prompt='', tools=[])
    results, _ = _run(provider, {'bad': {'name': 'supervision', 'arguments': '{broken'}},
                      lambda *args: pytest.fail('invalid JSON must not execute'))
    assert results[0]['is_error'] is True
    assert '파싱 오류' in results[0]['result']


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
