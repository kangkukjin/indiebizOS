"""ep3176에서 발견한 비용 관측 경계: 블록≠응답, 추론⊆출력, trajectory≠Episode."""
import sys
import json
from pathlib import Path

import boot_paths  # noqa: F401
import pytest


def test_response_fragments_count_once_and_keep_usage_detail(monkeypatch):
    import episode_logger as el
    import providers.cli_provider as cp
    from providers import get_provider
    from providers.base import begin_turn_token_ledger, read_turn_tokens, _turn_token_ledger
    events, rounds = [], []
    monkeypatch.setattr(el, 'record_trajectory_event', lambda k, d: events.append((k, d)))
    monkeypatch.setattr(cp, 'notify_round', lambda *a: rounds.append(a))
    p = get_provider('claude_code', api_key='', model='opus', system_prompt='')
    token = _turn_token_ledger.set(None)
    begin_turn_token_ledger()
    try:
        for kind in ['thinking', 'text', 'tool_use']:
            block = {'type': kind, 'text': 'text', 'thinking': 'private', 'id': 'tool1',
                     'name': 'execute_ibl', 'input': {'code': 'private'}}
            p._translate_stream_event({'type': 'assistant', 'message': {
                'id': 'response1', 'model': 'opus', 'content': [block],
                'usage': {'input_tokens': 10, 'output_tokens': 100,
                          'output_tokens_details': {'thinking_tokens': 60}}}}, '', 0)
        assert len(rounds) == 1
        snapshots = [d for k, d in events if k == 'model.response_snapshot']
        assert len(snapshots) == 3
        assert {d['response_id'] for d in snapshots} == {'response1'}
        assert all(d['reasoning'] == 60 and d['output'] == 100 for d in snapshots)
        assert 'private' not in str(snapshots)
        assert read_turn_tokens() is None  # 분석 내역을 관측하며 총계를 이중 계상하지 않는다.
        p._reset_turn_state()
        p._translate_stream_event({'type': 'assistant', 'message': {
            'id': 'response1', 'model': 'opus', 'content': []}}, '', 0)
        assert len(rounds) == 2
    finally:
        _turn_token_ledger.reset(token)


@pytest.mark.parametrize('kind', ['round', 'usage'])
def test_model_observation_survives_mcp_trajectory_without_episode(monkeypatch, kind):
    import episode_logger as el
    saved = []
    monkeypatch.setattr(el, '_save_trajectory_event',
                        lambda trace, event, data: saved.append((trace.episode_id, event, data)) or len(saved))
    token = el._current_episode.set(None)
    role = el._current_role.set('oneshot:execution')
    trace_token = el._current_trajectory.set(None)
    try:
        with el.trajectory_scope(task_id='test-reentry', episode_id=123):
            if kind == 'round':
                el.notify_round('p', 'm', 1, 0)
            else:
                el.notify_usage('p', 'm', 1234, {'input': 20, 'output': 10, 'reasoning': 6})
        assert len(saved) == 1 and saved[0][0] == 123
        assert saved[0][1] == 'model.' + kind
        assert 'oneshot:execution' in saved[0][2]
    finally:
        el._current_episode.reset(token)
        el._current_role.reset(role)
        el._current_trajectory.reset(trace_token)


@pytest.mark.parametrize('usage,expected', [
    ({'input_tokens': 1, 'output_tokens': 100,
      'output_tokens_details': {'thinking_tokens': 60}}, (100, 60)),
    ({'prompt_tokens': 1, 'completion_tokens': 100,
      'completion_tokens_details': {'reasoning_tokens': 60}}, (100, 60)),
    ({'promptTokenCount': 1, 'candidatesTokenCount': 40, 'thoughtsTokenCount': 60}, (100, 60)),
    ({'input_tokens': 1, 'output_tokens': 100,
      'output_tokens_details': {'reasoning_tokens': 0}}, (100, 0)),
    ({'input_tokens': 1, 'output_tokens': 100}, (100, None)),
])
def test_reasoning_is_an_optional_subset_not_extra_output(usage, expected):
    from providers.base import normalize_usage
    result = normalize_usage(usage)
    assert (result['output'], result.get('reasoning')) == expected


@pytest.mark.parametrize('episode', [3090, 3176])
def test_recorded_response_fragment_shapes_count_true_responses(monkeypatch, episode):
    import episode_logger as el
    import providers.cli_provider as cp
    from providers import get_provider
    audit = json.loads((Path(__file__).parents[1] / 'docs/experiments/episode3176_cost_audit.json').read_text())
    row = next(r for r in audit['episodes'] if r['episode_id'] == episode)
    rounds, snapshots = [], []
    monkeypatch.setattr(cp, 'notify_round', lambda *a: rounds.append(a))
    monkeypatch.setattr(el, 'record_trajectory_event', lambda k, d: snapshots.append(d))
    p = get_provider('claude_code', api_key='', model='opus', system_prompt='')
    for response in row['responses']:
        usage = dict(response['usage'])
        usage['output_tokens_details'] = {'thinking_tokens': usage.pop('thinking_tokens')}
        for block_types in response['fragments']:
            # 실행 내용 없이 실측 ID·사용량·블록 분할만 재생한다.
            p._observe_response({'id': response['response_id'], 'model': response['model'],
                                 'usage': usage, 'content': [{'type': t} for t in block_types]})
    assert len(rounds) == row['unique_responses']
    assert len(snapshots) == row['assistant_events']
    latest = {s['response_id']: s for s in snapshots}
    assert sum(s['output'] for s in latest.values()) == row['output_tokens']
    assert sum(s['reasoning'] for s in latest.values()) == row['thinking_tokens']


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
