"""Reviewed lessons: real parser/runtime, deterministic external adapters, no external effects."""
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
    reviewed = json.loads(Path(__file__).with_name('corpus_review.json').read_text())
    registry = load_registry()
    checks = []
    for case in reviewed:
        for scenario in ('empty', 'rows', 'first_failure'):
            seen = []
            def external(key):
                def call(runtime, args):
                    seen.append((key, args))
                    if scenario == 'first_failure' and len(seen) == 1:
                        raise Fault('FIXTURE_FAILURE', 'first operation failed')
                    if key == 'self:read':
                        return {'text':'fixture text','blocks':[],'data':{}}
                    row = {'id':'site', 'title':'fixture', 'meta':'', 'name':'fixture', 'album':'album',
                           'station_id':'kbs_classicfm', 'stream_url':'https://example.invalid/radio',
                           'year':1997, 'duration':90, 'size':120, 'lat':0, 'lng':0,
                           'path':'fixture.png', 'label':'desktop', 'page':1, 'prescreen':''}
                    rows = [] if scenario == 'empty' else [row, {**row,'title':'second','year':None}]
                    return {'message':'fixture', 'success':True, 'items':rows, 'sites':rows, 'count':len(rows),
                            'path':'fixture.png', 'pdf_path':'fixture.pdf', 'passed':True, 'score':9, 'issues':[], 'notes':''}
                return call
            fake = {key:(adapter if adapter.contract.get('adapter', {}).get('protocol') == 'core-table/2'
                         else Adapter(copy.deepcopy(adapter.contract), external(key)))
                    for key, adapter in registry.items()}
            plan = compile_program(case['after'], fake)
            assert plan.report()['status'] != 'invalid', (case['id'], plan.report())
            result = Runtime(plan).run()
            retry = case['id'] in (4282,4292)
            if scenario == 'first_failure' and not retry:
                assert not result['success'] and len(seen) == 1, (case['id'], result, seen)
            else:
                assert result['success'], (case['id'], scenario, result.get('diagnostic'), result.get('issues'))
            # Paths/references must be values, never literal legacy interpolation.
            for key,args in seen:
                for arg in ('path','station_id','stream_url','image_path','content','markers'):
                    if isinstance(args.get(arg), str):
                        assert '$it.' not in args[arg] and '${곡' not in args[arg], (case['id'],key,arg)
            if scenario == 'rows':
                if case['id'] in (3820,4222):
                    assert seen[-1][1]['content'] == 'fixture\nsecond'
                if case['id'] == 3677:
                    assert len(result['value']) == 1 and result['value'][0]['year'] == 1997
                if case['id'] == 3973:
                    assert seen[-1][1]['station_id'] == 'kbs_classicfm'
            checks.append({'id':case['id'],'scenario':scenario,'passed':True,'calls':len(seen)})
    return {'lessons':len(reviewed),'checks':checks,'external_calls':0}


if __name__ == '__main__':
    result = verify()
    Path(__file__).with_name('repair_verification.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(f"{result['lessons']} lessons, {len(result['checks'])} checks passed; no external calls")
