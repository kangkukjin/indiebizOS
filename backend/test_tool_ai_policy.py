"""원샷 비교 실험: 같은 IBL의 앱/에이전트 차이, 도구 밖 인지 보존, 우회·스레드 경계."""
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest


@pytest.fixture(autouse=True)
def isolated_policy(monkeypatch, tmp_path):
    import thread_context as tc
    import tool_ai_policy as policy
    snapshot = tc.snapshot()
    tc.clear_all_context()
    (tmp_path / 'data').mkdir()
    (tmp_path / 'data/agent_tool_policy.json').write_text(
        '{"allow_agent_tool_oneshot":false}')
    monkeypatch.setattr(policy, 'get_base_path', lambda: tmp_path)
    yield tmp_path
    tc.restore(snapshot)


def test_policy_opt_in_and_reversible(isolated_policy):
    import tool_ai_policy as p
    path = isolated_policy / 'data/agent_tool_policy.json'
    assert not p.agent_tool_ai_allowed()
    path.write_text('{"allow_agent_tool_oneshot":true}')
    assert p.agent_tool_ai_allowed()
    path.unlink()
    assert p.agent_tool_ai_allowed()
    path.write_text('{invalid')
    assert not p.agent_tool_ai_allowed()


@pytest.mark.parametrize('api', ['oneshot_ai_call', 'system_ai_call'])
@pytest.mark.parametrize('role', ['execution', 'classify', 'background', 'evaluate'])
def test_nested_model_blocked_before_provider_even_when_role_changes(monkeypatch, api, role):
    import consciousness_agent as ca
    import tool_ai_policy as p
    import thread_context as tc
    tc.set_call_channel('agent')
    monkeypatch.setattr(ca, '_resolve_oneshot_provider', lambda *a: pytest.fail('provider reached'))
    with p.tool_ai_scope('test', 'semantic'):
        with pytest.raises(p.ToolAIBlocked):
            getattr(ca, api)('input', role=role)
    assert tc.get_tool_ai_scope() is None


@pytest.mark.parametrize('channel,inside', [('agent', False), ('app', True), ('scheduler', True)])
def test_app_and_harness_models_preserved(monkeypatch, channel, inside):
    from contextlib import nullcontext
    import consciousness_agent as ca
    import tool_ai_policy as p
    import thread_context as tc
    tc.set_call_channel(channel)
    calls = []
    provider = SimpleNamespace(system_prompt='old', process_message=lambda **kw: calls.append(kw) or 'ok')
    monkeypatch.setattr(ca, '_resolve_oneshot_provider', lambda role: provider)
    with p.tool_ai_scope('test', 'semantic') if inside else nullcontext():
        assert ca.oneshot_ai_call('input', system_prompt='new') == 'ok'
    assert len(calls) == 1 and provider.system_prompt == 'old'


@pytest.mark.parametrize('node,action', [('table','ai'), ('table','brief'), ('table','structure'),
                                        ('self','struct'), ('self','ask')])
def test_same_action_is_blocked_for_agent_but_app_reaches_handler(monkeypatch, node, action):
    import ibl_engine as engine
    import thread_context as tc
    calls = []
    monkeypatch.setattr(engine, '_execute_ibl_impl', lambda *a: calls.append(a) or {'items': []})
    ti = {'_node': node, 'action': action, 'params': {}}
    tc.set_call_channel('agent', override=True)
    result = engine.execute_ibl(ti, '.', 'system_ai')
    assert result['error_type'] == 'tool_ai_policy' and not calls
    tc.set_call_channel('app', override=True)
    assert engine.execute_ibl(ti, '.', 'system_ai') == {'items': []}
    assert len(calls) == 1


def test_ai_capability_is_data_not_action_name(monkeypatch):
    import ibl_engine as engine
    import thread_context as tc
    tc.set_call_channel('agent')
    monkeypatch.setattr(engine, 'load_nodes_installed', lambda: {
        'nodes': {'future': {'actions': {'semantic': {'ai_call': True}}}}})
    monkeypatch.setattr(engine, '_execute_ibl_impl', lambda *a: pytest.fail('handler reached'))
    result = engine.execute_ibl({'_node':'future','action':'semantic','params':{}}, '.')
    assert result['error_type'] == 'tool_ai_policy'


def test_criteria_blocked_before_side_effect(monkeypatch):
    import ibl_engine as engine
    import thread_context as tc
    tc.set_call_channel('agent')
    monkeypatch.setattr(engine, '_execute_ibl_impl', lambda *a: pytest.fail('side effect reached'))
    result = engine.execute_ibl({'_node':'self','action':'write',
                                'params':{'path':'never.txt','content':'x','criteria':'좋은 글'}}, '.')
    assert result['error_type'] == 'tool_ai_policy'


def test_hidden_model_inside_ordinary_action_is_blocked(monkeypatch):
    import ibl_engine as engine
    import consciousness_agent as ca
    import thread_context as tc
    tc.set_call_channel('agent')
    monkeypatch.setattr(ca, '_resolve_oneshot_provider', lambda *a: pytest.fail('provider reached'))
    monkeypatch.setattr(engine, '_execute_ibl_impl', lambda *a: ca.oneshot_ai_call('hidden'))
    result = engine.execute_ibl({'_node':'sense','action':'search','params':{}}, '.')
    assert result['error_type'] == 'tool_ai_policy'


def test_snapshot_propagates_policy_and_restores_worker():
    import thread_context as tc
    import tool_ai_policy as p
    tc.set_call_channel('agent')
    def worker(snap):
        old = tc.snapshot()
        try:
            tc.restore(snap)
            tc.set_call_channel('app', override=True)
            with p.tool_ai_scope('test', 'nested'):
                with pytest.raises(p.ToolAIBlocked):
                    p.require_tool_ai_allowed()
        finally:
            tc.restore(old)
        return tc.get_tool_ai_scope()
    with p.tool_ai_scope('test', 'parent'):
        with ThreadPoolExecutor(max_workers=1) as pool:
            assert pool.submit(worker, tc.snapshot()).result() is None
    assert tc.get_tool_ai_scope() is None


def test_catalog_reflects_policy_and_can_restore(isolated_policy, monkeypatch):
    import ibl_access as access
    monkeypatch.setattr(access, '_idioms_block', lambda *a: '')
    blocked = access.build_environment()
    assert '<tool_ai_policy>' in blocked
    for qualified in ('self:ask','self:struct','table:ai','table:brief','table:structure'):
        assert not any(line.strip().startswith(qualified + ' ::') for line in blocked.splitlines())
    assert any(line.strip().startswith('table:filter ::') for line in blocked.splitlines())
    (isolated_policy / 'data/agent_tool_policy.json').write_text('{"allow_agent_tool_oneshot":true}')
    allowed = access.build_environment()
    assert '<tool_ai_policy>' not in allowed
    assert any(line.strip().startswith('table:ai ::') for line in allowed.splitlines())


def test_real_nested_ibl_calls_are_blocked():
    import thread_context as tc
    from system_tools import _execute_ibl_unified
    tc.set_call_channel('agent')
    root = str(Path(__file__).resolve().parents[1])
    for code in (
        '[self:ask]{prompt:"차단 시험"}',
        '[table:take]{items:[{x:1}],n:1} >> [table:ai]{instruction:"복사"}',
        '[table:each]{items:[{x:1}],parallel:2,do:"[self:ask]{prompt:\'차단 시험\'}"}',
        '[def:차단시험]{[self:ask]{prompt:"차단 시험"}}\n[fn:차단시험]{}',
    ):
        result = _execute_ibl_unified({'code':code}, root, agent_id='test_policy')
        text = result if isinstance(result,str) else json.dumps(result,ensure_ascii=False)
        assert '비교 실험' in text, text
        assert '_param_hint' not in text, text


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
