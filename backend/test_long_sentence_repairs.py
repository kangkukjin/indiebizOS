"""Long-sentence report regressions: refinement, documents and inspection cost."""
import boot_paths  # noqa: F401
import json
from pathlib import Path

import pytest

from ibl_v2_adapters import load_registry
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime
from ibl_v2_ir import unpack, Fault

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'docs/experiments/long_sentence_imagination/round_1'


@pytest.fixture(scope='module')
def registry():
    return load_registry(str(ROOT))


def run(code, registry, inputs=None):
    plan = compile_program(code, registry, inputs)
    assert not plan.issues, plan.issues
    result = Runtime(plan, inputs).run()
    assert result['success'], result
    return unpack(result['value_wire']['data'])


@pytest.mark.parametrize('body', [
    'return $it.a == null ? "-" : text($it.a)',
    '[if:$it.a == null]{return "-"};return text($it.a)',
    '$v=$it.a;return $v == null ? "-" : f"${v}"',
    'return $it.a != null and $it.a > 0 ? text($it.a) : "-"',
])
def test_null_branches_and_early_return(registry, body):
    assert run('[{a:null},{a:3}] >> [table:each]{' + body + '}', registry) == ['-', '3']


def test_discriminated_filter_and_sibling_safety(registry):
    prefix = '$rows=[{ok:true,value:3},{ok:false,error:"missing"}];'
    assert run(prefix + '$rows >> [table:filter]{where:($r)=>not $r.ok} >> '
               '[table:each]{return $it.error}', registry) == ['missing']
    assert compile_program(prefix + '$rows >> [table:each]{return $it.error}', registry).issues
    assert compile_program('[{a:null},{a:3}] >> [table:each]{'
                           '$x=$it.a == null ? "-" : text($it.a); return text($it.a)}', registry).issues
    assert compile_program('[{a:null},{a:3}] >> [table:each]{'
                           '[if:$it.a == null]{return text($it.a)};return "-"}', registry).issues


@pytest.mark.parametrize('expr', ['len(x.a)', 'len($x.a)', 'x.a[0]', '$x.a[0]', "join(', ',x.a)"])
def test_interpolation_names_at_every_depth(registry, expr):
    result = run('$x={a:["p","q"]};return f"${' + expr + '}"', registry)
    assert result == ('2' if expr.startswith('len') else 'p, q' if expr.startswith('join') else 'p')


def test_quote_diagnostic_and_unbound_name(registry):
    with pytest.raises(Fault, match='따옴표'):
        compile_program('$x={a:["p"]};return f"${join(", ",$x.a)}"', registry)
    plan = compile_program('return f"${len(missing.a)}"', registry)
    assert any(i['code'] == 'UNBOUND' for i in plan.issues)


@pytest.mark.parametrize('extension,content,expected', [
    ('csv', 'name,note,price\n"A, B","two\nlines",0\nC,,\n',
     [{'name': 'A, B', 'note': 'two\nlines', 'price': '0'}, {'name': 'C', 'note': '', 'price': ''}]),
    ('tsv', 'name\tprice\nA\t0\n', [{'name': 'A', 'price': '0'}]),
])
def test_delimited_document_real_reader(tmp_path, extension, content, expected):
    path = tmp_path / ('quotes.' + extension)
    path.write_text(content)
    value = run('[self:read]{path:$path}', load_registry(str(tmp_path)), {'path': str(path)})
    assert value['data']['items'] == expected
    assert value['text'] == content
    assert value['data']['table']['columns'] == list(expected[0])
    assert not {'success', 'message', 'text', 'path'} & value['data'].keys()


@pytest.mark.parametrize('value', [{'private_key_name': 3}, [1, 2], 3, None])
def test_json_structure_contract(tmp_path, value):
    path = tmp_path / 'value.json'
    path.write_text(json.dumps(value))
    result = run('[self:read]{path:$path}', load_registry(str(tmp_path)), {'path': str(path)})
    assert result['data'] == ({'items': value, 'count': len(value)} if isinstance(value, list) else value)


def test_missing_file_code_and_plain_text_data(tmp_path):
    registry = load_registry(str(tmp_path))
    assert run('[try]{[self:read]{path:"missing.csv"}}[catch]{return $error.code}', registry) == 'NOT_FOUND'
    path = tmp_path / 'notes.txt'
    path.write_text('hello')
    value = run('[self:read]{path:$path}', registry, {'path': str(path)})
    assert value['text'] == 'hello'
    assert not {'text', 'message', 'items', 'success'} & value['data'].keys()


def test_read_description_does_not_publish_content_keys(monkeypatch):
    import ibl_access
    from model_result_view import describe_actions
    monkeypatch.setattr(ibl_access, '_SHAPES_CACHE', {'mtime': None, 'data': {}})
    result = describe_actions(['self:read'], None)['actions'][0]['definition']
    assert 'observed_returns' not in result
    assert 'CSV/TSV' in result['target_description']
    assert result['callable_contract']['result']['data'] == 'Unknown'


def test_check_information_can_be_read_without_reexecution(registry):
    from ibl_v2_analysis import compact_check
    from model_result_view import read_result
    # Open declared values produce guards while a known absent field stays an error.
    plan = compile_program('[def:f]($r){return $r.field}', registry)
    result = compact_check(plan)
    assert result['ok'] and result['guards'] == []
    args = {**result['guards_ref']['read_args'], 'path': ['guards', 0]}
    assert json.loads(read_result(args)['text']) == plan.guards[0]


@pytest.mark.parametrize('version', ['v2', 'v4', 'repaired'])
def test_original_full_programs_compile(registry, version):
    inputs = json.loads((FIXTURE / 'inputs_main.json').read_text())['inputs']
    plan = compile_program((FIXTURE / 'drafts' / (version + '.ibl')).read_text(), registry, inputs)
    assert not plan.issues, plan.issues


@pytest.mark.parametrize('variant', [False, True])
@pytest.mark.parametrize('version', ['v4', 'repaired'])
def test_full_report_and_missing_source(tmp_path, variant, version):
    from thread_context import actor_context
    inputs = json.loads((FIXTURE / 'inputs_main.json').read_text())['inputs']
    inputs.update(폴더=str(FIXTURE / ('input_variant' if variant else 'input')),
                  출력=str(tmp_path / 'report.md'))
    with actor_context(origin='training'):
        result = run((FIXTURE / 'drafts' / (version + '.ibl')).read_text(), load_registry(str(tmp_path)), inputs)
    assert result['verified'] is True
    assert result['pick'] == (None if variant else 'C')
    assert result['all_sources_read'] is not variant
    totals = {r['vendor']: r['required_total'] for r in result['totals']}
    assert totals['A'] == (2550000 if variant else 1740000)
    if variant:
        assert [r['vendor'] for r in result['unread']] == ['C']
        assert '재송부 요청' in (tmp_path / 'report.md').read_text()
    else:
        assert totals['C'] == 1670000
        assert result['unread'] == []
    assert '업체별 합계' in (tmp_path / 'report.md').read_text()


def test_member_csv_uses_same_document_contract(tmp_path):
    import base64
    import importlib.util
    from ibl_document_value import document_value
    path = ROOT / 'data/packages/installed/tools/system_essentials/member_documents.py'
    spec = importlib.util.spec_from_file_location('lsi_member_documents', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.read_document({'path': 'quotes.csv', 'blocks': True}, {},
                                  lambda _: {'success': True, 'content': base64.b64encode(b'a,b\n1,0\n').decode()}, tmp_path)
    assert document_value(result)['data']['items'] == [{'a': '1', 'b': '0'}]


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__] + sys.argv[1:]))
