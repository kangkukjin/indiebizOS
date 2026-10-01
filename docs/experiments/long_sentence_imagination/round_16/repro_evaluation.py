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




def replay_recorded():
    """Rebuild evaluation traces from original receipts, without model/tool execution."""
    from supervision_store import tool_index_at

    here = Path(__file__).resolve().parent
    episodes = json.loads((here / 'ai_metrics.json').read_text())
    rounds = json.loads((here / 'round_costs.json').read_text())
    cases = []
    for episode in episodes:
        paths = sorted({r['rollout'] for r in rounds if r['episode'] == episode['id']
                        and r['role'] == 'execution' and r.get('rollout')})
        calls, by_id = [], {}
        for path in paths:
            for line in Path(path).open():
                row = json.loads(line)
                if row.get('type') != 'response_item':
                    continue
                item = row.get('payload', {})
                if item.get('type') == 'function_call' and item.get('name') == 'execute_ibl':
                    call = {'id': item['call_id'], 'name': 'execute_ibl',
                            'input': json.loads(item['arguments']), 'result': ''}
                    calls.append(call)
                    by_id[item['call_id']] = call
                elif item.get('type') == 'function_call_output' and item.get('call_id') in by_id:
                    output = item.get('output', [])
                    texts = ([x.get('text', '') for x in output if isinstance(x, dict)]
                             if isinstance(output, list) else [str(output)])
                    by_id[item['call_id']]['result'] = next(
                        (s for s in texts if s.lstrip().startswith('{')), '\n'.join(texts))
        directory = Path(episode['evaluation'][0]['store'])
        class RecordedStore:
            def tool_index(self, **kwargs):
                return tool_index_at(directory, **kwargs)

            def read_evidence(self, ref, *_):
                return {'text': (directory / (ref + '.txt')).read_text()}

        merged = execution_trace(SimpleNamespace(store=RecordedStore()), calls)
        shown = serialize_tool_trace(merged, total_budget=24000, head_keep=12,
                                     tail_keep=12, per_result_chars=3000)
        blocked = sum('"not_executed":true' in c['result'].replace(' ', '') for c in calls)
        cases.append({'episode': episode['id'], 'case': episode['case'],
                      'native_ibl_calls': len(calls), 'native_not_executed': blocked,
                      'stored_calls': len(tool_index_at(directory, limit=10000)),
                      'merged_calls': len(merged), 'trace_chars': len(shown),
                      'terminal_verified_visible': '"verified": true' in shown,
                      'headers': sum(s.startswith('[') for s in shown.splitlines())})
    result = {'source': 'original round-16 native rollout + stored evidence; no tool/model re-execution',
              'cases': cases,
              'note': 'cold의 차단 호출 1개와 warm의 작업대 전용 기록 5개는 별도 증거이므로 보존한다.'}
    (here / 'repair_replay.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    if "--recorded" in sys.argv:
        replay_recorded()
    else:
        main()
