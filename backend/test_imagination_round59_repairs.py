"""Empty nested collections and source evidence must survive flattening."""
import boot_paths  # noqa: F401
import copy
import json

import pytest

from ibl_v2_adapters import decode_envelope, load_registry
from ibl_v2_compile import compile_program
from ibl_v2_ir import Fault
from ibl_v2_runtime import Runtime


@pytest.fixture(scope='module')
def registry(tmp_path_factory):
    return load_registry(str(tmp_path_factory.mktemp('round59')))


def flatten(registry, rows):
    inputs = {'rows': rows}
    return Runtime(compile_program('$rows >> [table:flatten]{field:"refs"}',
                                   registry, inputs), inputs).run()


@pytest.mark.parametrize('rows', [[], [{'refs': []}], [{'refs': []}, {'refs': []}],
                                 [{'refs': {'items': []}}], [{'refs': '[]'}]])
def test_empty_nested_collections_are_success(registry, rows):
    result = flatten(registry, rows)
    assert result['success'], result
    assert result['source_complete'] is True
    assert result['value']['items'] == []


@pytest.mark.parametrize('invalid', [None, 7, 'invalid'])
@pytest.mark.parametrize('valid', [[], [{'title': 'A'}]])
def test_missing_nested_rows_are_partial_even_with_empty_valid_rows(registry, invalid, valid):
    result = flatten(registry, [{'refs': valid}, {'refs': invalid}])
    assert not result['success'], result
    assert result['diagnostic']['code'] == 'PARTIAL_SOURCE'
    partial = result['diagnostic']['partial']
    assert partial['items'] == valid
    assert partial['rows_dropped'] == 1
    assert partial['skipped_row_indices'] == [1]


@pytest.mark.parametrize('markers', [
    {'truncated': True}, {'rows_dropped': 1}, {'rows_unprocessed': 2},
    {'error_count': 1}, {'success': False, 'error': 'search failed'},
    {'error': 'search failed'},
])
@pytest.mark.parametrize('serialized', [False, True])
def test_nested_envelope_failure_survives_unwrapping(registry, markers, serialized):
    envelope = {'items': [{'title': 'A'}], **markers}
    rows = [{'refs': json.dumps(envelope) if serialized else envelope}]
    original = copy.deepcopy(rows)
    result = flatten(registry, rows)
    assert not result['success'], result
    assert result['source_complete'] is False
    assert result['diagnostic']['code'] == 'PARTIAL_SOURCE'
    partial = result['diagnostic']['partial']
    assert partial['items'] == [{'title': 'A'}]
    assert partial['row_honesty'][0]['row_index'] == 0
    assert rows == original


@pytest.mark.parametrize('refs', [
    [{'title': 'A', 'error': 'business', 'truncated': True, 'rows_dropped': 3}],
    {'title': 'A', 'error': 'business', 'truncated': True},
    {'items': [{'title': 'A'}], 'truncated': True,
     'truncations': [{'scope': 'selection'}]},
])
def test_business_records_and_intentional_selection_are_not_source_failures(registry, refs):
    result = flatten(registry, [{'refs': refs}])
    assert result['success'], result
    assert result['source_complete'] is True


def test_all_invalid_rows_still_report_a_field_error(registry):
    result = flatten(registry, [{'wrong': []}, {'refs': None}])
    assert not result['success']
    assert result['diagnostic']['code'] == 'TOOL'
    assert "field 'refs'" in result['error']


@pytest.mark.parametrize('location', ['row_honesty', 'branches_honesty', 'incomplete_steps'])
def test_dropped_rows_are_completion_evidence_at_every_envelope_boundary(location):
    envelope = {'items': [], location: [{'markers': {'rows_dropped': 2}}]}
    with pytest.raises(Fault) as error:
        decode_envelope(envelope, {})
    assert error.value.kind == 'partial'


def test_selection_cannot_hide_another_sources_unknown_truncation():
    envelope = {'items': [], 'row_honesty': [
        {'markers': {'truncated': True, 'truncations': [{'scope': 'selection'}]}},
        {'markers': {'truncated': True}},
    ]}
    with pytest.raises(Fault) as error:
        decode_envelope(envelope, {})
    assert error.value.kind == 'partial'


@pytest.mark.parametrize('field,rows', [
    ('items', [{'items': [{'title': 'A'}], 'truncated': True}]),
    ('refs.items', [{'refs': {'items': [], 'error_count': 1}}]),
    ('refs.0.items', [{'refs': [{'items': [], 'rows_dropped': 1}]}]),
    ('refs.*.items', [{'refs': [{'items': [], 'rows_dropped': 1}, {'items': []}]}]),
])
def test_explicit_items_paths_preserve_the_consumed_envelope(registry, field, rows):
    inputs = {'rows': rows}
    result = Runtime(compile_program(f'$rows >> [table:flatten]{{field:"{field}"}}',
                                    registry, inputs), inputs).run()
    assert not result['success'], result
    assert result['source_complete'] is False
    assert result['diagnostic']['code'] == 'PARTIAL_SOURCE'


def test_path_observer_never_scans_unrelated_sibling_envelopes(registry):
    inputs = {'rows': [{'refs': {'items': [{'title': 'A'}]},
                        'unrelated': {'items': [], 'truncated': True}}]}
    result = Runtime(compile_program('$rows >> [table:flatten]{field:"refs.items"}',
                                    registry, inputs), inputs).run()
    assert result['success'], result
    assert result['value']['items'] == [{'title': 'A'}]


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__, '-q']))
