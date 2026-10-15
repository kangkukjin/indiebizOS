"""Structured reads preserve CSV cell bytes across newline conventions."""
import boot_paths  # noqa: F401
import csv
import importlib.util
import io
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'data/packages/installed/tools/system_essentials'


def module(name):
    spec = importlib.util.spec_from_file_location('newline_' + name, PACKAGE / (name + '.py'))
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def source(delimiter, terminator):
    rows = [{'name': 'a', 'note': 'CR\rLF\nCRLF\r\nend'},
            {'name': 'b', 'note': 'comma, tab\t quote"'},
            {'name': 'c', 'note': ''}]
    stream = io.StringIO(newline='')
    writer = csv.DictWriter(stream, fieldnames=['name', 'note'], delimiter=delimiter,
                            lineterminator=terminator, quoting=csv.QUOTE_ALL)
    writer.writeheader()
    writer.writerows(rows)
    return '\ufeff' + stream.getvalue(), rows


@pytest.mark.parametrize('delimiter', [',', '\t'])
@pytest.mark.parametrize('terminator', ['\r\n', '\r'])
def test_delimited_parser_preserves_cell_newlines(delimiter, terminator):
    content, expected = source(delimiter, terminator)
    assert module('essentials_file_io').delimited_data(content, delimiter)['items'] == expected


@pytest.mark.parametrize('extension,delimiter', [('csv', ','), ('tsv', '\t')])
@pytest.mark.parametrize('terminator', ['\r\n', '\r'])
def test_document_read_and_csv_save_preserve_source(tmp_path, extension, delimiter, terminator):
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    from thread_context import actor_context

    content, expected = source(delimiter, terminator)
    path = tmp_path / ('source.' + extension)
    path.write_bytes(content.encode('utf-8'))
    inputs = {'source': str(path), 'output': str(tmp_path / 'saved.csv')}
    code = ('$r=[self:read]{path:$source};'
            '$w=[self:write]{path:$output,format:"csv",content:$r.data.items};'
            '$b=[self:read]{path:$w.path};return {source:$r,back:$b}')
    plan = compile_program(code, load_registry(str(ROOT)), inputs)
    assert not plan.issues, plan.issues
    with actor_context(origin='training'):
        result = Runtime(plan, inputs).run()
    assert result['success'], result.get('diagnostic')
    assert result['value']['source']['text'] == content
    assert result['value']['source']['data']['items'] == expected
    assert result['value']['back']['data']['items'] == expected
    with Path(inputs['output']).open(encoding='utf-8', newline='') as stream:
        assert list(csv.DictReader(stream)) == expected


def test_plain_text_window_preserves_original_line_endings(tmp_path):
    path = tmp_path / 'text.txt'
    path.write_bytes(b'first\r\nsecond\rthird\n')
    file_io = module('essentials_file_io')
    bounds = module('fs_read_range').text_read_bounds
    text, total, start, end, ranged, truncated = file_io.read_text_window(
        path, {'offset': 1, 'limit': 1, 'numbered': True}, bounds)
    assert (text, total, start, end, ranged, truncated) == ('2\tsecond\r', 3, 1, 2, True, False)


@pytest.mark.parametrize('variant', ['base', 'missing', 'bom_cr', 'empty'])
def test_manifest_reconciliation_preserves_original_notes(tmp_path, variant):
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    from thread_context import actor_context

    fixture = ROOT / 'docs/experiments/long_sentence_imagination/round_20'
    spec = importlib.util.spec_from_file_location('manifest_fixture', fixture / 'harness/generate.py')
    generator = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(generator)
    original = generator.generate(tmp_path / 'input',
                                  terminator='\r' if variant == 'bom_cr' else '\r\n',
                                  bom=variant == 'bom_cr', empty_last=variant == 'empty')
    sources = [str(tmp_path / 'input' / f'part{n}.csv') for n in range(3)]
    if variant == 'missing':
        sources[2] = str(tmp_path / 'absent.csv')
    inputs = {'sources': sources, 'actual': str(tmp_path / 'input/actual.json'),
              'out': str(tmp_path / 'report')}
    plan = compile_program((fixture / 'drafts/main_v0.ibl').read_text(), load_registry(str(ROOT)), inputs)
    assert not plan.issues, plan.issues
    with actor_context(origin='training'):
        result = Runtime(plan, inputs).run()
    assert result['success'], result.get('diagnostic')
    assert result['source_complete'] is (variant != 'missing')
    value = result['value']
    assert value['json_verified'] and value['csv_verified']
    report = value['report']
    count = 12 if variant in {'missing', 'empty'} else 18
    assert len(report['rows']) == count
    assert len(report['unexpected']) == (7 if count == 12 else 1)
    assert len(report['failures']) == (1 if variant == 'missing' else 0)
    expected = {row['path']: row['note'] for row in original[:count]}
    assert {row['path']: row['note'] for row in report['rows']} == expected
    assert {row['status']: row['count'] for row in report['summary']} == {
        'missing': 1, 'mismatch': 1, 'duplicate': 1, 'ok': count - 3}
    with (tmp_path / 'report.csv').open(encoding='utf-8', newline='') as stream:
        assert {row['path']: row['note'] for row in csv.DictReader(stream)} == expected


@pytest.mark.parametrize('value', [
    {'note': '줄\r\n다음\ufeff본문', 'zero': 0, 'empty': '', 'missing': None},
    [{'id': 'V01', 'n': 23000}], '일반 문자열', 123, True, None,
])
def test_json_bom_is_encoding_marker_without_changing_values(value):
    import json
    body = '\ufeff' + json.dumps(value, ensure_ascii=False)
    assert module('essentials_file_io').structured_data(body, 'json', 'phone.json') == value


@pytest.mark.parametrize('content', [
    '{"x":1,"x":2}', '{"nested":{"x":1,"x":2}}',
    '{"n":NaN}', '[Infinity]', 'NaN', '1e999',
    '{"text":"ok",}', '\ufeff{}',
])
def test_json_bom_does_not_hide_invalid_source(content):
    with pytest.raises(ValueError, match='JSON 원문 오류'):
        module('essentials_file_io').structured_data('\ufeff' + content, 'json', 'phone.json')


def test_json_structure_is_decoded_once(monkeypatch):
    import json
    file_io = module('essentials_file_io')
    loads = json.loads
    calls = []
    def counted(body, *args, **kwargs):
        calls.append(body)
        return loads(body, *args, **kwargs)
    monkeypatch.setattr(json, 'loads', counted)
    body = '[{"id":"V01","amount":23000}]'
    assert file_io.structured_data(body, 'json', 'costs.json') == [{'id': 'V01', 'amount': 23000}]
    assert calls == [body]


def test_json_bom_full_ibl_read_preserves_raw_text_and_structure(tmp_path):
    import json
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    from thread_context import actor_context

    value = {'note': '본문\ufeff표식\r\n원문', 'count': 0, 'items': []}
    body = '\ufeff' + json.dumps(value, ensure_ascii=False, indent=2).replace('\n', '\r\n')
    source_path = tmp_path / 'phone.json'
    source_path.write_bytes(body.encode('utf-8'))
    inputs = {'source': str(source_path), 'copy': str(tmp_path / 'copy.txt')}
    code = ('$d=[self:read]{path:$source};'
            '[self:write]{path:$copy,content:$d.text}; return $d')
    plan = compile_program(code, load_registry(str(ROOT)), inputs)
    assert not plan.issues, plan.issues
    with actor_context(origin='training'):
        result = Runtime(plan, inputs).run()
    assert result['success'], result.get('diagnostic')
    assert result['value']['text'] == body
    assert result['value']['data'] == value
    assert Path(inputs['copy']).read_bytes() == source_path.read_bytes()


def test_member_json_bom_uses_same_parser_and_preserves_source(tmp_path):
    import base64
    import json
    member = module('member_documents')
    value = [{'id': 'V01', 'note': '그대로\ufeff보존'}]
    body = '\ufeff' + json.dumps(value, ensure_ascii=False)
    calls = []
    def exchange(command):
        calls.append(command)
        return {'success': True, 'content': base64.b64encode(body.encode()).decode()}
    result = member.read_document({'path': 'phone.json', 'blocks': True}, {}, exchange, tmp_path)
    assert result['structured_data'] == value
    assert result['text'] == body
    assert len(calls) == 1


@pytest.mark.parametrize('terminator', ['\n', '\r\n', '\r'])
def test_numbered_read_remains_visible_in_document_contract(tmp_path, terminator):
    from ibl_v2_adapters import load_registry
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    from thread_context import actor_context

    source_path = tmp_path / 'manual.txt'
    source_path.write_bytes((terminator.join(['private', 'public  ', 'tail']) + terminator).encode())
    code = 'return [self:read]{path:$source,start_line:2,end_line:2,numbered:true}'
    plan = compile_program(code, load_registry(str(ROOT)), {'source':str(source_path)})
    assert not plan.issues, plan.issues
    with actor_context(origin='training'):
        result = Runtime(plan, {'source':str(source_path)}).run()
    assert result['success'], result.get('diagnostic')
    assert result['value']['text'] == '2\tpublic  ' + terminator


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
