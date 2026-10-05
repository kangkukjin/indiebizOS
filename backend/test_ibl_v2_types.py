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
