"""Registry publication rechecks callers that arrived after candidate preparation."""
import base64

import boot_paths  # noqa: F401
import pytest
import yaml
from script_mutation import activation_scope
from test_capability_changes import body, register  # noqa: F401


def test_new_live_caller_prevents_prepared_contract_break(body):
    root, ops = body
    path = root / 'data/scripts/sample.py'
    path.write_text('print("{}")')
    contract = {'version': 1, 'params': {'x': 'Number'}, 'required': ['x'], 'result': 'Record',
                'effects': ['pure'], 'adapter': {'protocol': 'registered-json/1'}}
    assert ops.op_register({'id': 'sample', 'path': str(path), 'callable_contract': contract})['success']
    registry = root / 'data/scripts/registry.yaml'
    before = registry.read_bytes()
    broken = {**contract, 'params': {'y': 'Number'}, 'required': ['y']}
    # Staging passes with no consumers. A consumer appears before live apply.
    assert ops.op_register({'id': 'sample', 'path': str(path), 'callable_contract': broken})['success']
    after = registry.read_bytes()
    registry.write_bytes(before)
    register('new_caller', '[def:new_caller](){return [self:script]{id:"sample",args:{x:1}}}')
    session = {'sealed': {'data/scripts/registry.yaml': {
        'before_data': base64.b64encode(before).decode(), 'data': base64.b64encode(after).decode()}}}
    with pytest.raises(ValueError, match='호출자'):
        with activation_scope(root, session):
            pytest.fail('an incompatible registry must not reach apply')
    assert registry.read_bytes() == before
    # Changing only metadata keeps the existing consumer contract intact.
    compatible = yaml.safe_load(before)
    compatible['sample']['description'] = 'revised'
    session['sealed']['data/scripts/registry.yaml']['data'] = base64.b64encode(
        yaml.safe_dump(compatible).encode()).decode()
    with activation_scope(root, session):
        assert registry.read_bytes() == before


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
