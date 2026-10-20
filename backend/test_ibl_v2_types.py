"""Runtime contracts validate the declared depth, retaining strict typed fields."""
import boot_paths  # noqa: F401
from decimal import Decimal

import pytest

import ibl_v2_types as types
from ibl_v2_ir import Fault, ResultValue, UNIT


@pytest.mark.parametrize('spec,value', [
    ('Unknown', {'rows': [{'n': 1}, {'n': None}]}),
    ('Record', {'rows': [{'n': 1}, {'n': None}]}),
    ('List', [{'n': 1}, {'n': None}]),
    ('List<Unknown>', [{'n': 1}, {'n': None}]),
])
def test_unconstrained_contract_does_not_infer_nested_rows(monkeypatch, spec, value):
    def unexpected_inference(_value):
        pytest.fail('an unconstrained child must not be inferred')
    monkeypatch.setattr(types, 'infer', unexpected_inference)
    assert types.guard(value, spec, 'input') is value


@pytest.mark.parametrize('value', [
    None, True, 0, Decimal('1.25'), '2', [], {},
    [{'n': 1}, {'n': None}], [1, {'n': 1}], {'n': 1}, {'n': None},
    {'rows': [1, 2]}, {'rows': [1, '2']}, UNIT, ResultValue(True, 2),
])
@pytest.mark.parametrize('spec', [
    'Unknown', 'Record', 'List', 'List<Unknown>', 'List<Record>',
    {'n': 'Number'}, {'rows': 'List<Number>'}, 'Record|Null',
])
def test_guard_preserves_structural_contract_decisions(value, spec):
    expected = types.compatible(types.infer(value), types.declared(spec))
    if expected:
        assert types.guard(value, spec, 'field') is value
    else:
        with pytest.raises(Fault, match='field:') as exc:
            types.guard(value, spec, 'field')
        assert exc.value.code == 'TYPE_CONTRACT'


def test_required_fields_and_list_elements_remain_checked():
    for value, spec in [({'n': None}, {'n': 'Number'}),
                        ({}, {'n': 'Number'}),
                        ([{'n': 1}, 7], 'List<Record>'),
                        ({'rows': [1, 'x']}, {'rows': 'List<Number>'})]:
        with pytest.raises(Fault) as exc:
            types.guard(value, spec, 'strict')
        assert exc.value.code == 'TYPE_CONTRACT'


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))


def test_nested_wire_inference_and_diagnostics_are_bounded():
    """197 bytes used to expand for >5s; test a deeper independent input too."""
    import subprocess
    import sys
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    script = '''
import sys
sys.path.insert(0, 'backend')
import boot_paths
from ibl_v2_types import infer, plain, compatible
value = ['scalar', 1]
for _ in range(24):
    value = ['record', [['key', value]]]
a, b = infer(value), infer(value)
assert a == b and hash(a) == hash(b)
assert len(str(a)) < 2300 and len(repr(a)) < 2400
assert compatible(a, b)
assert plain(a) == plain(b)
assert a.positions[0].kind == 'Text'
'''
    result = subprocess.run([sys.executable, '-c', script], cwd=root,
                            capture_output=True, text=True, timeout=5)
    assert result.returncode == 0, result.stderr


def test_union_order_and_discriminants_do_not_depend_on_display(monkeypatch):
    def forbidden(_):
        raise AssertionError('display is not a structural sort key')
    monkeypatch.setattr(types.Type, '__str__', forbidden)
    monkeypatch.setattr(types.Type, '__repr__', forbidden)
    left = types.infer({'ok': True, 'rows': [1, 2]})
    right = types.infer({'ok': False, 'error': 'failed'})
    joined = types.join(left, right)
    assert joined.kind == 'Union' and set(joined.item) == {left, right}
    assert joined == types.join(right, left)
    assert types.join(types.TEXT, types.NUMBER) == types.join(types.NUMBER, types.TEXT)
    assert dict(left.fields)['rows'].positions == (types.NUMBER, types.NUMBER)
