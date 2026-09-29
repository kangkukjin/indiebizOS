"""Round-80 reviewed lessons, isolated external adapters and real language runtime."""
from pathlib import Path
import sys
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / 'backend'))
import boot_paths  # noqa: E402,F401
import copy
import json
from ibl_v2_adapters import Adapter, load_registry
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime
from ibl_v2_ir import Fault


def verify():
    cases = json.loads(Path(__file__).with_name('corpus_review.json').read_text())
    registry = load_registry()
    checks = []
    for case in cases:
        for scenario in ('empty','rows','first_failure'):
            seen = []
            def external(key):
                def call(runtime, args):
                    seen.append((key,args))
                    if scenario == 'first_failure' and len(seen) == 1:
                        raise Fault('FIXTURE_FAILURE','source unavailable')
                    row = {'id':'1','title':'AI fixture','url':'https://example.invalid/1','name':'fixture',
                        'meta':'2026-09-29','summary':'text','mode':'media','favorite':1,'unreplied':2,
                        'alive':False,'post_count':3,'is_draft':True,'is_mine':True,'hashtag':'fixture',
                        'channel':'email','to':'fixture@example.invalid','project':'fixture','rating':4,
                        'info_level':1,'role_description':'fixture'}
                    rows = [] if scenario == 'empty' else [row,{**row,'id':'2','title':'second','unreplied':None,'alive':None}]
                    if key == 'self:read':return {'text':'fixture text','data':{},'blocks':[]}
                    if key == 'sense:crawl':return {'text':'fixture text','title':'fixture','url':args['url'],'items':rows}
                    if key == 'table:brief':return {'message':'yes','rows_in':len(args.get('items',[]))}
                    if key == 'table:since':
                        # A changing source eventually ends. Key streams retain their distinct boundary.
                        count = sum(k==key for k,_ in seen)
                        rows = rows if count < 2 else []
                    if key == 'self:trigger':
                        nested=compile_program(args['do'],fake)
                        assert nested.report()['status'] != 'invalid', (case['id'],nested.report())
                        result=Runtime(nested).run()
                        assert result['success'],(case['id'],result)
                    return {'success':True,'items':rows,'count':len(rows),'path':'fixture.json','message':'fixture'}
                return call
            fake={key:(adapter if adapter.contract.get('effects') == ['pure'] else
                       Adapter(copy.deepcopy(adapter.contract),external(key))) for key,adapter in registry.items()}
            plan=compile_program(case['after'],fake)
            assert plan.report()['status'] != 'invalid',(case['id'],plan.report())
            result=Runtime(plan).run()
            recovers=case['id'] in (3850,4189,4191,4198)
            if scenario=='first_failure' and not recovers:
                assert not result['success'] and len(seen)==(2 if case['id']==4784 else 1),(case['id'],result,seen)
            else:
                assert result['success'],(case['id'],scenario,result.get('diagnostic'))
            if scenario=='rows':
                if case['id'] in (3337,3686,4004,3690):assert len(result['value'])==1
                if case['id']==3704:
                    sends=[a for k,a in seen if k=='others:channel_send']
                    assert len(sends)==1 and sends[0]['to']=='fixture@example.invalid'
                if case['id']==3711:assert len(seen)==1
                if case['id'] in (4105,4111,4190):assert result['value']['limit_reached'] is False
            checks.append({'id':case['id'],'scenario':scenario,'passed':True,'calls':len(seen)})
    return {'lessons':len(cases),'checks':checks,'external_calls':0}


if __name__=='__main__':
    result=verify()
    Path(__file__).with_name('repair_verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(f"{result['lessons']} lessons; {len(result['checks'])} checks passed")
