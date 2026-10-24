"""등록 스크립트 검색은 검색 실패와 빈 원장을 구분한다."""
import importlib.util
from pathlib import Path

import boot_paths  # noqa: F401
import pytest


@pytest.fixture
def ops(monkeypatch):
    path = Path(__file__).resolve().parents[1] / (
        'data/packages/installed/tools/system_essentials/script_ops.py')
    spec = importlib.util.spec_from_file_location('script_ops_search_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, '_read_state', lambda: {})
    monkeypatch.setattr(module, '_read_registry', lambda: {
        '압축': {'file': 'pack.py', 'description': 'ZIP archives'},
        '시험': {'file': 'check.py', 'description': 'run checks'}})
    return module


@pytest.mark.parametrize('query', ['압축', '시험'])
def test_list_finds_short_registered_names(ops, query):
    result = ops.op_list({'query': query})
    assert result['success'] and result['count'] == 1
    assert result['items'][0]['id'] == query


@pytest.mark.parametrize('filters', [{'query': '없는기능'}, {'id': '없는ID'},
                                     {'id': '압축', 'query': '없는기능'}])
def test_no_match_does_not_claim_registry_is_empty(ops, filters):
    result = ops.op_list(filters)
    assert result['success'] and result['items'] == [] and result['count'] == 0
    assert '검색 조건' in result['message'] and 'register' not in result['message']
    assert ops.op_list({})['count'] == 2


def test_truly_empty_registry_still_explains_registration(ops, monkeypatch):
    monkeypatch.setattr(ops, '_read_registry', lambda: {})
    result = ops.op_list({'query': '압축'})
    assert result['count'] == 0 and 'op:register' in result['message']


def test_filtered_script_discovery_includes_brief_only_for_runnable_matches(ops, monkeypatch):
    import guide_registry
    seen = []
    monkeypatch.setattr(ops, '_entry_item', lambda sid, e, state: {
        'id': sid, 'runnable': sid == '압축'})

    def briefs(names):
        names = list(names)
        seen.append(names)
        return [{'file': 'pack.md'}] if names else []

    monkeypatch.setattr(guide_registry, 'callable_control_briefs', briefs)
    assert ops.op_list({'id': '압축'})['control_briefs'] == [{'file': 'pack.md'}]
    assert seen == [['script:압축']]
    assert 'control_briefs' not in ops.op_list({'id': '시험'})
    assert seen[-1] == []
    ops.op_list({})
    assert len(seen) == 2  # broad inventory is not a reason to inject every guide


def test_reregistration_preserves_birth_and_legacy_unknown(ops, tmp_path, monkeypatch):
    script = tmp_path / 'sample.py'
    script.write_text('print(1)')
    registry = {}
    monkeypatch.setattr(ops, '_read_registry', lambda: registry)
    monkeypatch.setattr(ops, '_write_registry', lambda value: registry.update(value))
    monkeypatch.setattr(ops, '_resolve_path', lambda *a: script)
    monkeypatch.setattr(ops, '_path', lambda name: tmp_path)
    args = {'id': 'sample', 'path': str(script)}
    assert ops.op_register(args)['success']
    created = registry['sample']['created_at']
    registered = registry['sample']['registered_at']
    assert created
    assert ops.op_register({**args, 'description': 'changed'})['success']
    assert registry['sample']['created_at'] == created
    assert registry['sample']['registered_at'] == registered
    registry['sample'].pop('created_at')
    assert ops.op_register(args)['success']
    assert registry['sample']['created_at'] is None
    assert registry['sample']['registered_at'] == registered


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
