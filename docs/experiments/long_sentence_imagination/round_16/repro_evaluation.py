"""Read-only minimal reproductions of the two final-evidence observations in ep4215."""
import json
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT/'backend'))
import boot_paths  # noqa: E402,F401
from final_evaluator import execution_trace  # noqa: E402
from cognitive_trace import serialize_tool_trace  # noqa: E402


class Store:
    def tool_index(self, **_):
        return [{'name':'execute_ibl','input':{'id':'in'},'result':{'id':'out'},'is_error':False}]

    def read_evidence(self, ref, *_):
        value=({'code':'return 1','edition':2} if ref=='in' else {'success':True,'value':1})
        return {'text':json.dumps(value)}


def main():
    native=[{'name':'execute_ibl','input':{'code':'return 1','project_path':'.'},
             'result':json.dumps({'success':True,'value':1}),'is_error':False}]
    merged=execution_trace(SimpleNamespace(store=Store()),native)
    calls=[{'name':'execute_ibl','input':{'code':f'return {i}'},
            'result':json.dumps({'success':True,'value':{'large':'x'*4000}}),'is_error':False}
           for i in range(10)]
    calls.append({'name':'execute_ibl','input':{'code':'return {verified:true}'},
                  'result':json.dumps({'success':True,'value':{'verified':True,'rows':320}}),'is_error':False})
    shown=serialize_tool_trace(calls,total_budget=24000,head_keep=12,tail_keep=12,per_result_chars=3000)
    result={'native_calls':1,'store_calls':1,'merged_calls':len(merged),
            'same_invocation_payload_shapes':[r['input'] for r in merged],
            'tail_header_kept':'[11]' in shown,'tail_verification_kept':'"verified": true' in shown,
            'omission_declared':'일부 결과 본문 생략됨' in shown}
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
