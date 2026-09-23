"""Shared typed contracts reject invalid programs before external calls."""
import boot_paths  # noqa: F401
import pytest
from ibl_v2_adapters import Adapter, load_registry
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime
from ibl_callable_contract import selected


@pytest.fixture
def registry():
    return load_registry()


@pytest.mark.parametrize('source',[
    '[self:edit]{path:"a",new_string:"x"}',
    '[self:edit]{path:"a",old_string:"x",new_string:3}',
    '[self:edit]{path:"a",start_line:0,new_string:"x"}',
    '[self:grep]{pattern:"x",output_mode:"invented"}',
    '[sense:search]{source:"ddg"}',
    '[sense:crawl]{url:3}',
    '[sense:crawl]{url:"https://example.org",op:"invented"}',
    '[sense:crawl]{url:"https://example.org"} >> [table:take]{n:2}',
])
def test_known_contract_error_precedes_effect(source, registry):
    plan = compile_program(source, registry)
    assert plan.issues, plan.report()
    assert Runtime(plan).run()['executed'] is False


def test_variants_and_aliases_share_compile_runtime(registry):
    plan = compile_program('[self:grep]{query:"x",output_mode:"count"} >> [table:each]{return $it}', registry)
    assert plan.issues  # Record is not automatically converted into a list.
    assert not compile_program('[self:edit]{file_path:"a",old_string:"x",new_string:"y"}', registry).issues
    assert compile_program('[self:edit]{path:"a",old_string:"x",new_string:"y"} & [self:edit]{file_path:"a",old_string:"x",new_string:"z"}',registry).issues
    assert not compile_program('[sense:search]{source:"gnews",headlines:true}',registry).issues
    assert selected(registry['sense:search'].contract, {'source':'gnews','headlines':True})['effects'] == ['read_external']
    assert 'model' in selected(registry['sense:search'].contract, {'query':'x','curate':3})['effects']


def test_dynamic_argument_contract_checked_before_call(registry):
    calls=[]
    native=registry['self:grep']
    mock={'self:grep':Adapter(native.contract, lambda *_:calls.append(1))}
    plan=compile_program('[self:grep]{pattern:"x",output_mode:$mode}',mock,{'mode':'invented'})
    assert not plan.issues
    result=Runtime(plan,{'mode':'invented'}).run()
    assert not result['success'] and not calls


def test_actual_edit_grep_and_empty_result(tmp_path, monkeypatch):
    import ibl_run_journal
    from ibl_v2_entry import handle_request
    monkeypatch.setattr(ibl_run_journal,'journal_root',lambda _:tmp_path/'runs')
    target=tmp_path/'file.txt';target.write_text('needle\nneedle\n')
    result=handle_request({'edition':2,'code':'[self:edit]{path:$p,old_string:"needle",new_string:"changed",replace_all:true}','inputs':{'p':str(target)}},str(tmp_path))
    assert result['success'],result
    assert target.read_text()=='changed\nchanged\n'
    for pattern,expected in [('changed',2),('absent',0)]:
        result=handle_request({'edition':2,'code':'[self:grep]{path:$p,pattern:$q,file_pattern:"*.txt",output_mode:"count"}','inputs':{'p':str(tmp_path),'q':pattern}},str(tmp_path))
        assert result['success'],result
        assert result['value']['total']==expected


def test_typed_list_preserves_all_fields_and_partial_failure(registry):
    from ibl_v2_types import guard
    from ibl_v2_adapters import decode_envelope
    from ibl_v2_ir import Fault
    contract=selected(registry['self:grep'].contract, {'output_mode':'count'})
    raw={'items':[{'파일':'a','매칭 수':2,'extra':'kept'}],'total':2,'truncated':False,'evidence':'kept'}
    value,_=decode_envelope(raw,contract['adapter'])
    assert guard(value,contract['result'],'grep') == raw
    with pytest.raises(Fault) as exc:
        decode_envelope({**raw,'truncated':True},contract['adapter'])
    assert exc.value.partial == raw | {'truncated':True}


def test_function_describe_uses_compiler_without_body(monkeypatch):
    import ibl_v2_store
    from model_result_view import describe_actions
    monkeypatch.setattr(ibl_v2_store, 'definitions', lambda: {'배수':'[def:배수]($x,$n=3){return $x * $n}'})
    answer = describe_actions(['fn:배수'], {'self','table'}, edition=2)['actions'][0]['definition']
    assert answer['callable_contract']['required'] == ['x']
    assert answer['callable_contract']['params']['n'] == 'Number'
    assert answer['callable_contract']['result'] == 'Number'
    assert '[def:' not in str(answer)


if __name__ == '__main__':
    raise SystemExit(pytest.main([__file__,'-q']))
