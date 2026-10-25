"""Edition retirement: zero-effect refusals and native migration semantics."""
import importlib.util
from pathlib import Path

import pytest
import boot_paths  # noqa: F401
from ibl_v2_adapters import Adapter, load_registry
from ibl_v2_compile import compile_program
from ibl_v2_entry import handle_request
from ibl_v2_ir import Fault
from ibl_v2_runtime import Runtime

ROOT = Path(__file__).resolve().parents[1]


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


@pytest.fixture
def native():
    return module('scripts/ibl_edition1_candidates.py', 'retirement_candidates').candidates()


@pytest.fixture
def judgment():
    return module('data/scripts/judgment_idioms.py', 'retirement_judgment')


def execute(native, judgment, name, inputs, mocks):
    registry, calls = load_registry(), []
    def handler(key):
        def run(rt, args, **kwargs):
            calls.append((key, args))
            if key == 'self:script' and args['id'] == '판정관용구':
                return judgment.run(args['args'])
            target = mocks[key]
            return target(args) if callable(target) else target
        return run
    for key in set(mocks) | {'self:script'}:
        registry[key] = Adapter(registry[key].contract, handler(key))
    code = f'[fn:{name}]' + '{' + ','.join(k+':$'+k for k in inputs) + '}'
    plan = compile_program(code, registry, inputs, definitions=native)
    assert not plan.issues, plan.issues
    result = Runtime(plan, inputs).run()
    assert result['success'], result
    return result, calls


@pytest.mark.parametrize('payload,code', [
    ({'code':'[self:time]{}'}, 'EDITION_REQUIRED'),
    ({'code':'[self:time]{}','edition':1}, 'EDITION_UNSUPPORTED'),
    ({'code':'#!ibl edition=1\n[self:time]{}'}, 'EDITION_UNSUPPORTED'),
    ({'code':'#!ibl edition=1\n[self:time]{}','edition':2}, 'EDITION_UNSUPPORTED'),
    ({'code':'return 1','edition':2,'steps':[{}]}, 'REQUEST_FIELDS'),
    ({'code':'return 1','edition':2,'resume':{'vars_ref':'x'}}, 'RESUME_ARGUMENT'),
])
@pytest.mark.parametrize('check',[False,True])
def test_retired_request_never_loads_tools(monkeypatch, payload, code, check):
    monkeypatch.setattr('ibl_v2_adapters.load_registry', lambda *a,**k: pytest.fail('tools loaded'))
    out = handle_request({**payload,'check':check})
    assert not out['success'] and not out['executed']
    assert code in str(out)




def test_native_candidates_compile_without_legacy_adapters(native):
    registry = load_registry()
    assert not any(key.startswith('fn:') for key in registry)
    for name, source in native.items():
        assert not compile_program(source, registry, definitions=native).issues, name


def test_collection_preserves_order_failure_origin_and_source_truncation(native,judgment):
    def crawl(args):
        if args['url']=='bad':
            raise Fault('UNAVAILABLE','network unavailable')
        return {'text':'literal $it ${data}', 'title':'source', 'url':args['url'], 'items':[{'text':'literal $it ${data}','url':args['url']}],
                'truncated':True,'truncations':[{'scope':'source','total':2,'retained':1}]}
    out,calls=execute(native,judgment,'주소마다읽기',
        {'목록':[{'url':'a','title':'A'},{'url':'bad','title':'B'},{'url':'a','title':'duplicate'}],'개수':2},
        {'sense:crawl':crawl})
    value=out['value']
    assert [r['url'] for r in value['items']]==['a','bad']
    assert value['items'][0]['text']=='literal $it ${data}'
    assert value['items'][1]['_error']['code']=='UNAVAILABLE'
    assert value['error_count']==1 and value['partial'] and not out['source_complete']
    assert value['truncations']
    assert [a['url'] for k,a in calls if k=='sense:crawl']==['a','bad']


@pytest.mark.parametrize('rows',[[],[{'url':'a','title':'A'}]])
def test_empty_and_single_collection(native,judgment,rows):
    result,calls=execute(native,judgment,'주소마다읽기',{'목록':rows,'개수':10},
        {'sense:crawl':{'text':'','title':'','url':'a','items':[]}})
    assert result['value']['items']==[]
    assert result['value']['rows_processed']==len(rows)


def test_context_selection_has_page_boundaries_and_failure_rows(judgment):
    source={'items':[{'url':'a','text':'before'},{'url':'a','text':'hit'},
                     {'url':'b','text':'next page'},{'url':'bad','_error':'unavailable'}]}
    out=judgment.run({'op':'match','source':source,'pattern':'hit','limit':1,'context':1})
    assert [r.get('text') for r in out['items']]==['before','hit',None]


@pytest.mark.parametrize('rows',[[],[{'path':'old','name':'old','mtime':1,'is_dir':False},
                                      {'path':'new','name':'new','mtime':2,'is_dir':False}]])
def test_latest_file_reads_explicit_path_or_no_file(native,judgment,rows):
    result,calls=execute(native,judgment,'최신범위읽기',{'폴더':'x','패턴':'*','시작줄':7,'줄수':3},
        {'self:list':rows,'self:read':{'text':'body','blocks':[],'data':None}})
    reads=[args for key,args in calls if key=='self:read']
    assert reads==([{'path':'new','start_line':7,'limit':3}] if rows else [])
    if not rows: assert result['value']['found'] is False


def test_write_happens_before_summary_and_preserves_literal_content(native,judgment):
    out,calls=execute(native,judgment,'덜어내고요지만',{'주소':'u','스필경로':'out.json','지시':'summarize'},
        {'sense:crawl':{'text':'$unknown','title':'','url':'u','items':[{'text':'$unknown'}]},'self:write':{},'table:brief':{'items':[{'text':'summary'}]}})
    assert [k for k,_ in calls]==['sense:crawl','self:write','table:brief']
    assert '$unknown' in calls[1][1]['content']
    assert calls[2][1]['items']==[{'text':'$unknown'}]


def test_news_migration_preserves_publish_then_status(native,judgment):
    steps=[]
    def scripts(args):
        assert args['id']=='AI시대뉴스동기화'
        op=args['args']['op'];steps.append(op)
        return {'items':[{'key':'k','url':'u','report_date':'2026-01-01'}]} if op=='prepare' else {'items':[]}
    out,calls=execute(native,judgment,'AI시대출처뉴스갱신',{},
        {'self:script':scripts,'sense:crawl':{'text':'','title':'T','url':'u','items':[{'title':'T'}]},
         'table:ai':{'items':[]}})
    assert steps==['prepare','normalize','publish','status']
    normalized=next(a for k,a in calls if k=='self:script' and a['args'].get('op')=='normalize')
    assert normalized['args']['data']['items'][0]['key']=='k'


def test_all_native_functions_have_explicit_input_and_output(native,judgment):
    # Real contracts remain on the adapters; invalid producer shapes cannot pass.
    fixtures=[
        ('관문배터리돌리기',{}, {'self:script':{'items':[{'gate':'x','ok':False,'summary':'bad'}]}}),
        ('본문에서찾기',{'목록':[{'text':'hit','url':'u'}],'패턴':'hit','개수':1},{}),
        ('위치마다읽기',{'위치':[{'파일':'a','줄번호':1}],'개수':1,'줄수':2},
         {'self:read':{'text':'a','blocks':[],'data':None}}),
        ('각각읽고요약',{'목록':[{'title':'a','url':'u'}],'개수':1,'지시':'brief'},
         {'sense:crawl':{'text':'a','title':'a','url':'u','items':[{'text':'a'}]},'table:brief':{'items':[{'text':'b'}]}}),
        ('잘라각각종합',{'목록':[{'text':'a'}],'덩이지시':'brief','종합지시':'combine'},
         {'table:chunk':{'items':[{'text':'a'}]},'table:brief':{'items':[{'text':'b'}]}}),
        ('좁혀서읽기',{'패턴':'p','루트':'.','파일패턴':'*'},
         {'self:grep':{'items':[{'파일':'a','줄번호':1,'내용':'x'}],'total':1,'truncated':False},'self:read':{'text':'a','blocks':[],'data':None}}),
        ('화면검수',{'path':'a.html','intent':'readable'},
         {'engines:render':{'items':[{'path':'a.png','label':'desktop','prescreen':{}}]},'engines:image_read':{'items':[{'verdict':True}]}}),
    ]
    for name,inputs,mocks in fixtures:
        out,_=execute(native,judgment,name,inputs,mocks)
        assert out['success'], name


@pytest.mark.parametrize('name',['의미로본문찾기','관련자료골라읽기'])
def test_judgment_preserves_unknown_and_failure_rows(native,judgment,name):
    def judge(args):
        return {'items':[{**row,'judgment_result_value':True,'judgment_result_status':'decided'} for row in args['items']]}
    source=[{'url':'u','title':'title','text':'body'},{'url':'bad','_error':'source failed'}]
    out,_=execute(native,judgment,name,{'목록':source,'질문':'question','개수':2},
        {'table:judge':judge,'sense:crawl':{'title':'title','url':'u','text':'body','items':[{'text':'body'}]}})
    assert out['value']['error_count']==1
    assert any(row.get('_error') for row in out['value']['items'])


def test_collect_preserves_empty_and_non_record_failure(judgment):
    assert judgment.run({'op':'collect','results':[]})['items']==[]
    with pytest.raises(ValueError,match='Record'):
        judgment.run({'op':'collect','results':[{'ok':True,'value':['oops']}]})


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__]))
