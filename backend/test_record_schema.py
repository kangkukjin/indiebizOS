"""AI schema names, scalar types and nullable outputs share one contract."""
import boot_paths  # noqa: F401
import json
import sys

import pytest

from common.record_schema import records_schema_error, schema_fields, schema_types
from test_struct_body_seam import aiops  # noqa: F401


def test_only_explicit_type_labels_are_interpreted():
    schema = 'n(숫자), t(문자열 또는 null), b(Bool|Null), note(숫자라는 단어), day(YYYY-MM-DD)'
    assert schema_types(schema) == {'n': 'Number', 't': 'Text', 'b': 'Bool'}
    assert schema_fields('a(설명(중첩, 유지)), b') == ['a', 'b']
    assert schema_types('finance') == schema_types('팁(tip)') == {}
    with pytest.raises(ValueError, match='두 번'):
        schema_types('n(숫자), n(문자열)')


@pytest.mark.parametrize('value,valid', [
    (None, True), (30, True), (1.25, True), (0, True),
    ('30', False), (False, False), ([], False), (float('inf'), False),
])
def test_numeric_schema_preserves_null_and_rejects_wrong_json_type(value, valid):
    error = records_schema_error([{'n': value, 'label': 'x'}], 'n(숫자), label(문자열)')
    assert (error is None) == valid


@pytest.mark.parametrize('value,kind,valid', [
    (True, '불리언', True), (None, '불리언', True), ('true', '불리언', False),
    (1, 'Bool', False), ('x', '문자열', True), (None, 'Text', True), (1, 'Text', False),
])
def test_scalar_types(value, kind, valid):
    error = records_schema_error([{'v': value, 'other': 1}], f'v({kind}), other')
    assert (error is None) == valid


@pytest.mark.parametrize('value,valid', [(None, True), (30, True), ('thirty', False)])
@pytest.mark.parametrize('transform', [False, True])
def test_extraction_and_transform_enforce_same_schema(aiops, monkeypatch, value, valid, transform):
    mod, seen = aiops

    def answer(prompt, system):
        seen['system'] = system
        return [{'_i': 0, 'n': value, 'label': 'x'}], None

    monkeypatch.setattr(sys.modules['oneshot_facade'], 'oneshot_json', answer)
    schema = 'n(숫자), label(문자열)'
    if transform:
        result = mod._transform({'items': [{'id': 'a'}], 'instruction': 'extract',
                                 'schema': schema, 'preserve_rows': True})
    else:
        result = mod._struct({'text': 'source', 'schema': schema})
    result = json.loads(result)
    assert result['success'] == valid, result
    assert 'Number' in seen['system'] and 'null' in seen['system']
    if valid:
        assert result['items'][0]['n'] == value
    else:
        assert result['error_type'] == 'schema'


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
