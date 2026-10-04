"""Stored and member legacy functions return values, with diagnostics in evidence."""
import json

import boot_paths  # noqa: F401
import pytest

from ibl_v2_compat import decode_function_result
from ibl_v2_ir import Fault
from ibl_v2_entry import handle_request
from test_ibl_v2_assets import memory, example  # noqa: F401


@pytest.mark.parametrize('value', [None, False, 17, 'plain', '17', 'null', [], [1, 2],
    {'rows': [{'id': '007'}]}, {'success': False, 'error': 'business', 'final_result': 7}])
def test_stored_identity_preserves_selected_value(memory, value):
    memory.add_examples_batch([example('$return = $입력', '그대로')])
    result = handle_request({'edition': 2, 'code': '[fn:그대로]{입력:' + json.dumps(value) + '}'})
    assert result['success'], result
    assert result['value'] == value
    assert type(result['value']) is type(value)


def test_member_and_owner_share_return_boundary(memory):
    from ibl_member_library import library, adapters
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    with library('[def:반환]{$return = $입력}'):
        registry = adapters(None, None)
    result = Runtime(compile_program('[fn:반환]{입력:[1,2]}', registry)).run()
    assert result['success'] and result['value'] == [1, 2], result


def test_selected_records_compose_without_execution_paths(memory):
    memory.add_examples_batch([example('$return = $입력', '그대로')])
    result = handle_request({'edition': 2, 'code':
        '$r=[fn:그대로]{입력:{rows:[{id:"007"},{id:"b"}]}}; '
        'return $r.rows >> [table:take]{n:1}'})
    assert result['success'] and result['value'] == [{'id': '007'}], result


def test_legacy_leaf_record_has_no_function_execution_wrapper(memory):
    memory.add_examples_batch([example('$return = $목록 >> [table:take]{n:1}', '앞줄')])
    result = handle_request({'edition': 2, 'code': '[fn:앞줄]{목록:[{id:1},{id:2}]}'})
    assert result['success'] and result['value']['items'] == [{'id': 1}], result
    assert not set(result['value']) & {'final_result', 'results', '_fn_result', 'params_injected', 'fn_source'}


def test_execution_trace_is_separate_and_business_keys_are_untouched():
    value = {'results': ['business'], 'final_result': 9}
    ref = {'id': 'evidence-1', 'read_args': {'id': 'evidence-1', 'path': ['results']}}
    out = decode_function_result({'_fn_result': True, 'success': True, 'final_result': value,
                                  'results': [{'success': True}], 'execution_ref': ref})
    assert out.value == value
    assert out.evidence['attachments']['execution_ref'] == ref
    assert 'results' not in out.evidence


def test_explicit_text_return_is_not_json_decoded():
    out = decode_function_result({'_fn_result': True, 'success': True,
                                  '_return_encoding': 'text', 'final_result': '[1]'})
    assert out.value == '[1]'


def test_function_failure_and_partial_source_remain_failures():
    with pytest.raises(Fault) as failed:
        decode_function_result({'_fn_result': True, 'success': False, 'error': 'failed',
                                'failure_origin': {'kind': 'input_shape'}, 'execution_ref': {'id': 'ref'}})
    assert failed.value.code == 'TOOL'
    assert failed.value.details['execution_ref'] == {'id': 'ref'}
    with pytest.raises(Fault) as partial:
        decode_function_result({'_fn_result': True, 'success': True, 'final_result': [1],
                                'rows_unprocessed': 1})
    assert partial.value.code == 'PARTIAL_SOURCE' and partial.value.partial == [1]


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__]))
