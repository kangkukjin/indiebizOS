"""실행 코어 불변식: 값 보존·알파 이름변경·함수 추출·행 격리·전송 왕복."""
import copy
import json
import random
import sys
from pathlib import Path

import boot_paths  # noqa: F401
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from ibl_boundary_cases_round3 import each
from ibl_boundary_cases import literal as q


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








def test_old_wire_parameters_cannot_dispatch():
    from ibl_engine import _execute_ibl_impl
    for version in [1,999]:
        out = _execute_ibl_impl({'_node':'self','action':'time',
            'params':{'_ibl_ir':{'version':version,'params':['value',{}]}}}, '.')
        assert out['code']=='PARAMS' and not out['executed']






def native_run(source, inputs=None):
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    result = Runtime(compile_program(source, {}, inputs or {}), inputs or {}).run()
    assert result['success'], result
    return result['value']




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
    assert not out['executed'] and 'EDITION_UNSUPPORTED' in str(out)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
