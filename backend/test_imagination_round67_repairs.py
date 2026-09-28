"""Decimal boundaries, native scalars and Unicode composition from round 67."""
import boot_paths  # noqa: F401
import importlib.util
import json
from decimal import Decimal
from pathlib import Path
import unicodedata

import pytest

from common.expression_ir import UNIT, unpack
from common.expression_ops import pure_call
from common.value_semantics import public_result
from ibl_v2_adapters import load_registry
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope='module')
def registry():
    return load_registry(str(ROOT))


def run(code, registry, inputs=None):
    plan = compile_program(code, registry, inputs)
    assert not plan.issues, plan.report()
    return Runtime(plan, inputs).run()


def value(code, registry, inputs=None):
    result = run(code, registry, inputs)
    assert result['success'], result
    return unpack(result['value_wire']['data'])


@pytest.mark.parametrize('code,expected', [
    ('return json({평균:3.5})', {'평균': 3.5}),
    ('return json([{평점:4.5}])', [{'평점': 4.5}]),
    ('$r=[1.5,2.5] >> [table:each]{return {p:$it}}; return json($r)',
     [{'p': 1.5}, {'p': 2.5}]),
])
def test_json_decimals_are_business_values(registry, code, expected):
    assert json.loads(value(code, registry)) == expected


@pytest.mark.parametrize('bad', [UNIT, Decimal('0.10000000000000001')])
def test_json_failure_stops_write_and_can_be_caught(registry, tmp_path, bad):
    local = load_registry(str(tmp_path))
    result = run('[self:write]{path:"must_not_exist.json",content:json($bad)}',
                 local, {'bad': bad})
    assert result['success'] is False
    assert result['diagnostic']['code'] == 'NON_JSON_RESULT'
    assert not list(tmp_path.rglob('must_not_exist.json'))
    assert value('[try]{return json($bad)}[catch]{return $error.code}',
                 registry, {'bad': bad}) == 'NON_JSON_RESULT'


def test_decimal_json_write_contains_actual_rows(tmp_path):
    result = run('[self:write]{path:"area.json",content:json([{면적:72.5}])}',
                 load_registry(str(tmp_path)))
    assert result['success'], result
    files = list(tmp_path.rglob('area.json'))
    assert len(files) == 1
    assert json.loads(files[0].read_text()) == [{'면적': 72.5}]


def test_error_shaped_business_record_remains_serializable():
    row = {'success': False, 'error': 'business data'}
    assert json.loads(pure_call('json', [row])) == row
    assert public_result({'n': Decimal('1.5')}) == {'n': 1.5}
    assert public_result({'n': Decimal('Infinity')})['error_code'] == 'NONFINITE_RESULT'


@pytest.mark.parametrize('expression,expected', [
    ('19.9*3', Decimal('59.7')), ('0.1+0.2==0.3', True),
    ('sum([0.1,0.2])', Decimal('0.3')), ('round(2.675,2)', Decimal('2.68')),
    ('round(12.345,2)', Decimal('12.34')),
    ('-1.5', Decimal('-1.5')), ('abs(-1.5)', Decimal('1.5')),
    ('1.5/2', Decimal('0.75')), ('-5.5//2', Decimal('-3')),
    ('-5.5%2', Decimal('0.5')), ('5.5%-2', Decimal('-0.5')),
    ('sum([0.1,1/5])', Decimal('0.3')),
])
def test_decimal_arithmetic_is_preserved(registry, expression, expected):
    assert value('return ' + expression, registry) == expected


def test_human_decimal_view_and_typed_wire(registry):
    result = run('return {n:19.9*3, exact:0.10000000000000001}', registry)
    assert result['value']['n'] == 59.7
    assert result['value']['exact']['text'] == '0.10000000000000001'
    assert unpack(result['value_wire']['data'])['n'] == Decimal('59.7')


@pytest.mark.parametrize('expression,expected', [
    ('replace($n,"음악","music")', 'music'), ('$n[0:1]', '음'),
    ('$n[0]', '음'), ('$n[-1]', '악'), ('len($n)', 2),
    ('strip($n,"악")', '음'), ('split($n,"악")', ['음', '']),
    ('join("-",[$n,$n])', '음악-음악'), ('upper($n)', '음악'),
    ('lower($n)', '음악'), ('f"${$n}"', '음악'), ('text($n)', '음악'),
    ('$n+"!"', '음악!'),
])
def test_nfd_text_operations_use_nfc_without_mutating_input(registry, expression, expected):
    original = unicodedata.normalize('NFD', '음악')
    inputs = {'n': original}
    assert value('return ' + expression, registry, inputs) == expected
    assert inputs['n'] == original
    assert value('return $n', registry, inputs) == original


@pytest.mark.parametrize('reverse', [False, True])
def test_sorted_field_matches_table_sort(registry, reverse):
    rows = [{'id': 'missing'}, {'p': None}, {'p': 3}, {'p': 1}, {'p': 3}]
    inputs = {'rows': rows, 'reverse': reverse}
    expected = value('$rows >> [table:sort]{by:"p",descending:$reverse}', registry, inputs)
    assert value('return sorted($rows,"p",$reverse)', registry, inputs) == expected
    result = run('return sorted([{id:1}],"p")', registry)
    assert result['diagnostic']['code'] == 'MISSING_FIELD'
    assert value('return sorted([],"p")', registry) == []


@pytest.mark.parametrize('count', ['2.0', '4/2', '2', '0.0'])
def test_take_accepts_integer_valued_numbers(registry, count):
    expected = [] if count == '0.0' else [1, 2]
    assert value('[1,2,3] >> [table:take]{n:' + count + '}', registry) == expected


@pytest.mark.parametrize('count', ['2.5', '-1.0'])
def test_take_rejects_fractional_and_negative_numbers(registry, count):
    result = run('[1,2,3] >> [table:take]{n:' + count + '}', registry)
    assert result['diagnostic']['code'] == 'TAKE_COUNT'


def test_pure_list_transform_already_composes_with_reduce(registry):
    code = '''[{t:" 강의 , 음악 "}] >> [table:compute]{set:($r)=>{
      tags:reduce(split($r.t,","),[],($acc,$tag)=>$acc+[strip($tag)])}}'''
    assert value(code, registry)[0]['tags'] == ['강의', '음악']


def test_python_decimal_inputs_form_numeric_columns(registry):
    code = '''$t=[self:script]{id:"python_libraries",args:{op:"call",target:"pandas:DataFrame",
      args:[[{면적:84.5},{면적:59.5}]]}}
    $m=[self:script]{id:"python_libraries",args:{receiver:$t,op:"call",name:"mean",kwargs:{numeric_only:true}}}
    return [self:script]{id:"python_libraries",args:{receiver:$m,op:"call",name:"to_dict"}}'''
    assert value(code, registry) == {'면적': 72.0}


@pytest.mark.parametrize('mode', ['auto', 'value'])
def test_numpy_mean_is_directly_composable(registry, mode):
    code = '''$n=[self:script]{id:"python_libraries",args:{op:"call",target:"numpy:mean",
      args:[[1.5,2.5]],result:"%s"}}; return $n+1''' % mode
    assert value(code, registry) == 3.0


def test_explicit_decimal_object_can_be_preserved(registry):
    code = '''$d=[self:script]{id:"python_libraries",args:{op:"call",target:"decimal:Decimal",
      args:["0.10000000000000001"],result:"ref"}}
    return [self:script]{id:"python_libraries",args:{op:"call",target:"builtins:str",args:[$d]}}'''
    assert value(code, registry) == '0.10000000000000001'


def test_numpy_scalar_conversion_is_lossless_and_bounded():
    np = pytest.importorskip('numpy')
    path = ROOT / 'data/scripts/python_library/python_bridge_values.py'
    spec = importlib.util.spec_from_file_location('round67_bridge', path)
    bridge = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(bridge)
    for number in [np.int64(2**60 + 1), np.uint64(2**64 - 1), np.float32(.1), np.float64(.1)]:
        result = bridge.value_copy({'n': [number]})['n'][0]
        assert type(result) in (int, float)
        assert number == result
    for bad in [np.bool_(True), np.complex128(1+2j), np.float64('nan'), np.float64('inf')]:
        with pytest.raises(ValueError):
            bridge.value_copy(bad)
    wide = np.longdouble('0.10000000000000000001')
    if type(wide.item()) not in (int, float):
        with pytest.raises(ValueError):
            bridge.value_copy(wide)
    with pytest.raises(ValueError):
        bridge.value_copy(np.int64(2), budget=[1, 8])


if __name__ == '__main__':
    import sys
    raise SystemExit(pytest.main([__file__, *sys.argv[1:]]))
