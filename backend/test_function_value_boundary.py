"""Native function values remain separate from execution evidence after v1 retirement."""
import json
import pytest
import boot_paths  # noqa: F401
from ibl_v2_entry import handle_request
from function_library import register


def identity():
    register('그대로','#!ibl edition=2\n[def:그대로]($입력){return $입력}',edition=2)


@pytest.mark.parametrize('value',[None,False,17,'plain','17','null',[],[1,2],
    {'rows':[{'id':'007'}]},{'success':False,'error':'business','final_result':7}])
def test_stored_identity_preserves_selected_value(value):
    identity()
    result=handle_request({'edition':2,'code':'[fn:그대로]{입력:$x}','inputs':{'x':value}})
    assert result['success'] and result['value']==value
    assert type(result['value']) is type(value)


def test_member_and_owner_share_return_boundary():
    from ibl_member_library import library,definitions
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    with library('#!ibl edition=2\n[def:반환]($입력){return $입력}'):
        plan=compile_program('[fn:반환]{입력:[1,2]}',definitions=definitions())
    out=Runtime(plan).run()
    assert out['success'] and out['value']==[1,2]


def test_selected_records_compose_without_execution_paths():
    identity()
    out=handle_request({'edition':2,'code':'$r=[fn:그대로]{입력:{rows:[{id:"007"},{id:"b"}]}}; return $r.rows >> [table:take]{n:1}'})
    assert out['success'] and out['value']==[{'id':'007'}]


def test_native_leaf_record_has_no_function_execution_wrapper():
    register('앞줄','#!ibl edition=2\n[def:앞줄]($목록){return $목록 >> [table:take]{n:1}}',edition=2)
    out=handle_request({'edition':2,'code':'[fn:앞줄]{목록:[{id:1},{id:2}]}'})
    assert out['success'] and out['value']==[{'id':1}]
    assert any(e['kind']=='function_result' for e in out['evidence'])


def test_execution_trace_is_separate_and_business_keys_are_untouched():
    identity()
    value={'results':['business'],'final_result':9}
    out=handle_request({'edition':2,'code':'[fn:그대로]{입력:$x}','inputs':{'x':value}})
    assert out['value']==value
    assert out['evidence'] and out['value'] is not out['evidence']


def test_explicit_text_return_is_not_json_decoded():
    identity()
    out=handle_request({'edition':2,'code':'[fn:그대로]{입력:"[1]"}'})
    assert out['value']=='[1]'


def test_function_failure_and_partial_source_remain_failures():
    from ibl_v2_compile import compile_program
    from ibl_v2_runtime import Runtime
    from ibl_v2_adapters import Adapter
    from ibl_v2_ir import Fault
    def fail(rt,args):
        raise Fault('PARTIAL_SOURCE','unprocessed rows',partial=[1])
    reg={'test:partial':Adapter({'version':1,'params':{},'result':'Unknown','effects':['read_external']},fail)}
    plan=compile_program('[def:f](){return [test:partial]{}}; [fn:f]{}',reg)
    out=Runtime(plan).run()
    assert not out['success'] and out['diagnostic']['code']=='PARTIAL_SOURCE'
    assert out['diagnostic']['partial']==[1]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
