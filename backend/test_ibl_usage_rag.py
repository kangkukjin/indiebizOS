"""마법책 선택도 현재 describe 계약·권한을 소비한다."""
import json
import xml.etree.ElementTree as ET

import boot_paths  # noqa: F401
import pytest

from ibl_usage_rag import build_execution_memory_from_hint
from model_result_view import describe_actions


@pytest.mark.parametrize('name', ['table:filter', 'table:select', 'table:compute', 'table:each', 'self:write'])
def test_selected_action_uses_current_description_and_contract(name):
    xml, score, code = build_execution_memory_from_hint(name, {'table', 'self'})
    selected = ET.fromstring(xml).find('user_selected_action')
    assert selected.attrib['edition'] == '2'
    assert score == 1.0 and code == '[' + name + ']'
    taught = json.loads(selected.attrib['contract'])
    current = describe_actions([name], {'table', 'self'}, edition=2)['actions'][0]['definition']
    assert taught == {key: current[key] for key in taught}
    assert taught['callable_contract'] == current['callable_contract']
    assert taught['target_description']
    assert '$return' not in xml
    assert '반환 목록은 자동으로 합쳐진다' not in xml
    assert '기본 20' not in xml
    if name == 'table:filter':
        assert 'context:' not in json.dumps(taught, ensure_ascii=False)
        assert taught['callable_contract']['params']['where'] == 'Callable'
    if name == 'self:write':
        assert taught['callable_contract']['params']['content'] == 'Text|List<Record>'
        assert '$문서.text' in taught['target_description']
        assert '$본.items' not in xml and 'message 있으면 산문' not in xml


@pytest.mark.parametrize('name', ['', 'invalid', 'missing:action', 'sense:search'])
def test_unavailable_hint_falls_back_without_injecting_raw_metadata(name):
    assert build_execution_memory_from_hint(name, {'self'}) == ('', 0.0, '')


def test_inactive_action_is_not_taught(monkeypatch):
    import ibl_registry
    monkeypatch.setattr(ibl_registry, 'self_can_run', lambda *a: False)
    assert build_execution_memory_from_hint('table:filter', {'table'}) == ('', 0.0, '')


def test_hint_xml_preserves_contract_text(monkeypatch):
    import model_result_view
    expected = {'description': 'A & B < C "인용"', 'target_description': "x's text",
                'callable_contract': {'params': {'x': 'Text'}}}
    monkeypatch.setattr(model_result_view, 'describe_actions',
                        lambda *a, **kw: {'actions': [{'definition': expected}]})
    xml, _, _ = build_execution_memory_from_hint('test:action')
    assert json.loads(ET.fromstring(xml).find('user_selected_action').attrib['contract']) == expected


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
