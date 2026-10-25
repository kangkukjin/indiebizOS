"""실행 코어 불변식: 값 보존·알파 이름변경·함수 추출·행 격리·전송 왕복."""
import copy
import json
import random
import sys
from pathlib import Path

import boot_paths  # noqa: F401
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ibl_boundary_probe import probe
from ibl_boundary_cases_round3 import each
from ibl_boundary_cases import literal as q
from ibl_code_ir import compile_code, bind_code, Code, Literal, pack, unpack


def values():
    fixed = ['', '007', 0, False, None, [], {},
             '$it.id ${x.items.*.v} {{_step_0_result.items}} {{_prev_result}}',
             "'\"\\\n# } [def:fake] $return = 999", {'a': ['$items', '$x', False]}]
    rng = random.Random(20260908)
    alphabet = "abc한글'\"\\\n\t$[]{}:#0123"
    return fixed + [''.join(rng.choice(alphabet) for _ in range(rng.randrange(2, 55)))
                    for _ in range(20)]


@pytest.mark.parametrize('value', values())
@pytest.mark.parametrize('shape', ['direct', 'renamed', 'nested', 'function', 'pipeline', 'parallel'])
def test_value_survives_equivalent_program_shapes(value, shape):
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    body = 'return {v:$it.v}'
    if shape == 'renamed':
        body = '$행=$it; return {v:$행.v}'
    if shape == 'nested':
        body = '$outer=$it; return ([0] >> [table:each]{return {v:$outer.v}})[0]'
    source = '$rows >> [table:each]{parallel:' + ('4' if shape=='parallel' else '1') + '}{' + body + '}'
    if shape == 'function':
        source = '[def:f]($input){return {v:$input.v}}; $rows >> [table:each]{return [fn:f]{input:$it}}'
    if shape == 'pipeline':
        source = '$r=$rows; $r >> [table:each]{return {v:$it.v}}'
    rows = [{'v':value}] * (4 if shape=='parallel' else 1)
    plan = compile_program(source, {}, {'rows':rows})
    out = Runtime(plan, {'rows':rows}).run()
    assert out['success'] and out['value'] == rows, out


def test_rows_bind_without_parsing_again(monkeypatch):
    import ibl_parser
    plan = compile_code('[table:take]{items:[{v:$it.v}],n:1}')
    before = pack(plan)
    monkeypatch.setattr(ibl_parser, 'parse_function_body', lambda *_: pytest.fail('행 바인딩 중 재파싱'))
    for value in values():
        bound = bind_code(plan, lambda name, path: (True, value))
        assert bound.tree[0]['params']['items'][0]['v'] == value
    assert pack(plan) == before


def test_compiled_program_and_captures_survive_json_and_copy():
    plan = bind_code('[table:take]{items:[{v:$outer, row:$it.id}],n:1}',
                     lambda name, path: (True, "$it.id 'quoted'") if name == 'outer' else (False, None))
    for restored in [copy.deepcopy(plan), unpack(json.loads(json.dumps(pack(plan))))]:
        bound = bind_code(restored, lambda name, path: (True, 7) if name == 'it' else (False, None))
        assert bound.tree[0]['params']['items'] == [{'v': "$it.id 'quoted'", 'row': 7}]
        assert isinstance(bound.tree[0]['params']['items'][0]['v'], Literal)


def test_partial_string_binding_does_not_rescan_inserted_data():
    plan = compile_code('[table:take]{items:[{v:"${a} / ${b}"}],n:1}')
    first = bind_code(plan, lambda n, p: (True, '${b}') if n == 'a' else (False, None))
    second = bind_code(first, lambda n, p: (True, 'done') if n == 'b' else (False, None))
    assert second.tree[0]['params']['items'] == [{'v': '${b} / done'}]


def test_old_wire_parameters_cannot_dispatch():
    from ibl_engine import _execute_ibl_impl
    for version in [1,999]:
        out = _execute_ibl_impl({'_node':'self','action':'time',
            'params':{'_ibl_ir':{'version':version,'params':['value',{}]}}}, '.')
        assert out['code']=='EDITION_RETIRED' and not out['executed']


def test_unknown_wire_version_is_rejected():
    from ibl_code_ir import receive_params
    with pytest.raises(ValueError, match='버전'):
        receive_params({'_ibl_ir': {'version': 999}})


@pytest.mark.parametrize('raw', ['1e-3', '-2.5e+4', '0x10', '.25', '+3',
                                '"\\uD83D\\uDE80"', "'\\x41'", '"\\d+"',
                                '[1e2, {v:"\\uD83D\\uDE80"}]', '[1, /* { ignored } */ 2]',
                                '{a:1/* note */, /* other */ b:2}'])
def test_literal_grammar_matches_existing_parser(raw):
    from ibl_parser import parse_function_body
    code = '[table:take]{items:[{v:' + raw + '}],n:1}'
    expected = parse_function_body(code)[0]['params']['items']
    assert compile_code(code).tree[0]['params']['items'] == expected


def native_run(source, inputs=None):
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    result = Runtime(compile_program(source, {}, inputs or {}), inputs or {}).run()
    assert result['success'], result
    return result['value']


def test_live_execution_does_not_use_legacy_source_substitution(monkeypatch):
    import ibl_code_binding
    monkeypatch.setattr(ibl_code_binding, 'bind_scoped_code', lambda *a, **k: pytest.fail('옛 코드 치환 경로 사용'))
    value = native_run('$r="outer"; $rows >> [table:each]{return {outer:$r,row:$it.v}}',
                       {'rows':[{'v':"$it.no 'quote'"}]})
    assert value == [{'outer':'outer','row':"$it.no 'quote'"}]


@pytest.mark.parametrize('nested', [False, True])
def test_outer_and_local_step_zero_are_different_scopes(nested):
    body = '$local=7; return {a:$outer,b:$local}'
    if nested:
        body = 'return ([0] >> [table:each]{' + body + '})[0]'
    assert native_run('$outer=99; [0] >> [table:each]{'+body+'}') == [{'a':99,'b':7}]


def test_outer_result_and_row_in_expression_use_values():
    assert native_run('$outer=99; [{n:3}] >> [table:each]{return {v:$outer+$it.n}}') == [{'v':102}]


@pytest.mark.parametrize('parallel', [1,4])
def test_hundred_rows_parse_the_body_once(monkeypatch, parallel):
    import ibl_v2_parser
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    rows = [{'v':n} for n in range(100)]
    source = '$rows >> [table:each]{parallel:'+str(parallel)+'}{return {v:$it.v}}'
    plan = compile_program(source, {}, {'rows':rows})
    monkeypatch.setattr(ibl_v2_parser, 'parse', lambda *a, **k: pytest.fail('행마다 재파싱'))
    out = Runtime(plan, {'rows':rows}).run()
    assert out['success'] and out['value'] == rows


def test_episode3148_historical_sentence_is_immutable_and_not_replayed(monkeypatch):
    import hashlib
    from ibl_v2_entry import handle_request
    import ibl_engine
    root = Path(__file__).resolve().parents[1]
    fixture = json.loads((root/'docs/experiments/ibl_ir_episode3148_fixture.json').read_text())
    assert hashlib.sha256(fixture['code'].encode()).hexdigest() == fixture['code_sha256']
    monkeypatch.setattr(ibl_engine, 'execute_ibl', lambda *a, **k: pytest.fail('과거 문장 재실행'))
    out = handle_request({'edition':1,'code':fixture['code']})
    assert not out['executed'] and 'EDITION_RETIRED' in str(out)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
