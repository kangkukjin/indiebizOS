"""동결 모델 복원도 증류의 원샷 요청 계약을 유지한다."""
import boot_paths  # noqa: F401

from types import SimpleNamespace as NS

import pytest

import model_resolver as mr
from providers.deepseek import DeepSeekProvider


@pytest.mark.parametrize('mode,budget', [('default', 0), ('on', 2048), ('off', 0)])
def test_frozen_distill_disables_thinking_without_mutating_execution(monkeypatch, mode, budget):
    cached = DeepSeekProvider(api_key='test', model='deepseek-flash', system_prompt='', tools=[])
    cached.reasoning_mode = mode
    cached.thinking_budget = budget
    cached.disable_thinking = False
    monkeypatch.setattr(mr, 'env_key_for_provider', lambda _: 'test')
    monkeypatch.setattr(mr, '_provider_from_desc', lambda *a, **k: cached)
    monkeypatch.setattr(mr, 'resolve', lambda *a, **k: pytest.fail('must retain frozen model'))
    descriptor = {'provider': 'deepseek', 'model': 'deepseek-flash',
                  'reasoning_mode': mode, 'thinkingBudget': budget}
    frozen = mr.provider_from_frozen(descriptor)
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        # Replay the server failure if the outgoing request enables reasoning.
        off = kwargs.get('extra_body', {}).get('thinking') == {'type': 'disabled'}
        return iter([NS(choices=[NS(delta=NS(content='{"deep":[]}' if off else None,
                         tool_calls=None, reasoning_content=None),
                         finish_reason='stop' if off else 'length')], usage=None)])

    frozen._client = NS(chat=NS(completions=NS(create=create)))
    from consciousness_agent import call_oneshot_provider
    assert call_oneshot_provider(frozen, 'distill', step_role='unified_distill') == '{"deep":[]}'
    assert len(calls) == 1
    assert calls[0]['model'] == 'deepseek-flash'
    assert frozen.reasoning_mode == 'off' and frozen.thinking_budget == 0
    assert cached.reasoning_mode == mode and cached.thinking_budget == budget
    assert cached.disable_thinking is False
    assert descriptor['reasoning_mode'] == mode


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
