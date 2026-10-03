"""Structured source completeness is independent of model preview size."""
import base64
import json
from types import SimpleNamespace

import boot_paths  # noqa: F401
import pytest

from ibl_v2_adapters import load_registry
from system_tools_ibl import _execute_ibl_unified_impl
from test_ibl_general_capabilities import boundary  # noqa: F401
from test_repair_capability_parity import repair_handler, setup  # noqa: F401
from test_repair_workspace_completion import module
from thread_context import repair_workspace_scope


@pytest.fixture
def reader(boundary, monkeypatch, tmp_path):
    # Retain the real file adapter; isolate evidence/journals, not the read path.
    monkeypatch.setattr('ibl_v2_adapters.load_registry', load_registry)

    def run(code, **request):
        raw = _execute_ibl_unified_impl({'edition': 2, 'code': code, **request}, str(tmp_path))
        return raw, json.loads(raw)

    return run


@pytest.mark.parametrize('array', [False, True])
def test_large_json_aggregate_and_reference_retain_last_item(reader, tmp_path, array):
    rows = [{'n': i, 'label': '자료' * 180} for i in range(3000)]
    body = json.dumps(rows if array else {'rows': rows}, ensure_ascii=False)
    assert len(body) > 1_000_000
    path = tmp_path / 'large.json'
    path.write_text(body)
    field = 'items' if array else 'rows'
    expression = f'{{count:len($d.data.{field}),last:$d.data.{field}[-1].n}}'
    _, result = reader('$d=[self:read]{path:"large.json"}; return ' + expression)
    assert result['success'] and result['source_complete'], result.get('error')
    assert result['value'] == {'count': 3000, 'last': 2999}

    raw, full = reader('return [self:read]{path:"large.json"}')
    assert full['success'] and full['source_complete']
    assert len(raw) < 20_000  # The document itself never floods model context.
    ref = full['result_ref']
    # No source file re-read: the stored value must retain the complete data/text.
    path.unlink()
    _, reused = reader('return ' + expression, inputs={'d': {'$ref': ref['id']}})
    assert reused['success'] and reused['value'] == result['value']
    _, length = reader('return len($d.text)', inputs={'d': {'$ref': ref['id']}})
    assert length['value'] == len(body)


@pytest.mark.parametrize('fmt,separator', [('csv', ','), ('tsv', '\t')])
def test_large_delimited_source_preserves_quoted_newlines(reader, tmp_path, fmt, separator):
    cell = '한글' * 180 + separator + '\ncontinued'
    body = f'id{separator}label\n' + ''.join(f'{i}{separator}"{cell}"\n' for i in range(3000))
    assert len(body) > 1_000_000
    (tmp_path / f'large.{fmt}').write_text(body)
    _, result = reader(f'$d=[self:read]{{path:"large.{fmt}"}}; '
                       'return {count:len($d.data.items),last:$d.data.items[-1]}')
    assert result['success'] and result['source_complete'], result.get('error')
    assert result['value'] == {'count': 3000, 'last': {'id': '2999', 'label': cell}}


@pytest.mark.parametrize('suffix', [',"broken":}', ',"x":2}', ',"bad":NaN}'])
def test_invalid_json_after_old_cutoff_is_not_hidden(reader, tmp_path, suffix):
    (tmp_path / 'bad.json').write_text('{"x":1,"padding":"' + 'x' * 1_000_010 + '"' + suffix)
    _, result = reader('return [self:read]{path:"bad.json"}')
    assert not result['success']
    assert result['diagnostic']['code'] != 'PARTIAL_SOURCE'
    assert 'JSON 원문 오류' in result['error']


def test_explicit_text_and_line_selection_keep_their_contract(reader, tmp_path):
    path = tmp_path / 'large.json'
    path.write_text('{"padding":"' + 'x' * 1_000_010 + '",\n"last":7}\n')
    # Default plain text is still a preview and must not claim full-source success.
    _, plain = reader('return [self:read]{path:"large.json",format:"text"}')
    assert not plain['success'] and plain['diagnostic']['code'] == 'PARTIAL_SOURCE'
    _, selected = reader('return [self:read]{path:"large.json",offset:1,limit:1}')
    assert selected['success'] and selected['source_complete']
    assert selected['value']['text'] == '"last":7}\n'
    assert 'padding' not in selected['value']['data']


def test_large_json_uses_repair_candidate(repair_handler, setup):
    root, candidate, _, _ = setup
    (root / 'rows.json').write_text('{"source":"live"}')
    data = {'padding': '수리' * 510_000, 'source': 'candidate'}
    (candidate / 'rows.json').write_text(json.dumps(data, ensure_ascii=False))
    with repair_workspace_scope(str(candidate)):
        raw = repair_handler.execute({'path': str(root / 'rows.json'), 'blocks': True},
                                     SimpleNamespace(tool_name='read_op', project_path=str(root), agent_id='owner'))
    result = json.loads(raw)
    assert result['structured_data'] == data
    assert json.loads((root / 'rows.json').read_text()) == {'source': 'live'}


def test_member_structured_read_uses_complete_source_and_keeps_receive_budget(tmp_path, monkeypatch):
    member = module('member_documents')
    data = {'padding': '기기' * 510_000, 'last': 7}
    body = json.dumps(data, ensure_ascii=False).encode()
    calls = []

    def exchange(command):
        calls.append(command)
        return {'success': True, 'content': base64.b64encode(body).decode()}

    params = {'path': 'device.json', 'blocks': True}
    result = member.read_document(params, {}, exchange, tmp_path)
    assert result['structured_data'] == data and 'truncated' not in result
    assert calls == [{'op': 'read', 'path': 'device.json', 'encoding': 'base64'}]
    # Invalid source beyond the old preview boundary must still fail validation.
    body = ('{"padding":"' + 'x' * 1_000_010 + '","x":1,"x":2}').encode()
    with pytest.raises(ValueError, match='JSON 원문 오류'):
        member.read_document(params, {}, exchange, tmp_path)
    monkeypatch.setattr(member, 'MAX_BYTES', len(body) - 1)
    with pytest.raises(ValueError, match='파일 크기 초과'):
        member.read_document(params, {}, exchange, tmp_path)


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
