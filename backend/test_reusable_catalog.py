"""Discover by task intent, then distinguish invocation from mention."""
import boot_paths  # noqa: F401
from reusable_catalog import ranked
from associative_recall import _used_capabilities


def test_task_without_component_name_finds_contract_and_unrelated_task_does_not():
    entry = {'id': 'script:opaque7', 'description': 'sensor statistics and missing rows validation',
             'contract': {'params': {'rows': 'List<Record>'}, 'result': 'Record'}}
    assert ranked('check missing sensor rows', [entry]) == [entry]
    assert ranked('translate a poem', [entry]) == []


def test_mentions_and_unsuccessful_calls_do_not_count_as_use():
    ids = ['script:opaque7']
    mentioned = _used_capabilities(ids, {}, {'response': 'opaque7', 'tool_calls': []})
    assert mentioned['used'] == []
    invoked = _used_capabilities(ids, {}, {'tool_calls': [{'result': {'capability_usage': [
        {'id': ids[0], 'success': True}]}}]})
    assert invoked['used'] == ids and invoked['quality_contribution'] == 'not_inferred'


def test_local_function_shadow_is_not_counted_as_stored_capability():
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    out = Runtime(compile_program('[def:opaque]($n){return $n*2}\n[fn:opaque]{n:3}', {})).run()
    assert out['success'] and not out.get('capability_usage')


def test_stored_function_retains_derived_contract_and_dependencies(tmp_path, monkeypatch):
    import yaml
    import ibl_v2_store, ibl_v2_adapters, workflow_store
    monkeypatch.setattr(workflow_store, '_get_workflows_path', lambda: tmp_path)
    monkeypatch.setattr(ibl_v2_store, 'definitions', lambda: {})
    monkeypatch.setattr(ibl_v2_adapters, 'load_registry', lambda *a: {})
    out = ibl_v2_store.action('save', {'code': '[def:opaque]($n){return $n*2}', 'description': 'sensor calibration'}, str(tmp_path))
    assert out['success'], out
    saved = yaml.safe_load((tmp_path / (out['workflow_id'] + '.yaml')).read_text())
    assert saved['capability_contract']['name'] == 'opaque'
    assert saved['source_hash'] and saved['dependencies'] and saved['plan_hash']


if __name__ == "__main__":
    import pytest
    raise SystemExit(pytest.main([__file__]))
