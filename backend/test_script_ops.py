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


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
