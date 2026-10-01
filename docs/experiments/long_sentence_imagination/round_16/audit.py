"""Preserve actual tool inputs, accounting and per-response usage for fixture episodes only."""
import hashlib
import json
import sqlite3
from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo
from pathlib import Path

from fixture import ROOT, WORK, HERE, dump


def stored(data, key):
    ref=data.get(key,{})
    if not ref.get('id') or not data.get('store'):return None
    path=Path(data['store'])/(ref['id']+'.txt')
    return json.loads(path.read_text()) if path.exists() else None


def main():
    db=sqlite3.connect('file:'+str(ROOT/'data/world_pulse.db')+'?mode=ro',uri=True)
    db.row_factory=sqlite3.Row
    episodes=[dict(r) for r in db.execute("SELECT id,started_at,ended_at,agent,task_id,run_id,total_ms FROM episode_log WHERE agent LIKE 'LSI16_%' ORDER BY id")]
    observed={}; all_events={}; tools=[]; rounds=[]; summaries=[]
    seed_cases=iter(('seed','cold','warm'))
    for ep in episodes:
        eid=ep['id']
        ep['case']='baseline' if ep['agent']=='LSI16_baseline' else next(seed_cases,'unexpected')
        events=[dict(r) for r in db.execute('SELECT event_seq,ts,kind,data FROM trajectory_event WHERE episode_id=? ORDER BY event_seq',(eid,))]
        for e in events:e['data']=json.loads(e['data'])
        all_events[eid]=events; finished={e['data']['id']:e['data'] for e in events if e['kind']=='supervision.tool.finished'}
        usage=[e['data'] for e in events if e['kind']=='model.usage' and e['data'].get('accounting')=='billable_usage']
        for e in events:
            d=e['data']
            if e['kind']=='model.response_observed': observed[d['response_id']]=(eid,d)
            if e['kind']=='supervision.tool.started':
                result=finished.get(d['id'],{}); response=stored(result,'evidence'); request=stored(d,'input')
                full=response if isinstance(response,dict) else {}
                ref=full.get('result_ref',{}).get('id')
                raw_path=Path(d['store'])/(str(ref)+'.txt')
                if ref and raw_path.exists():full=json.loads(raw_path.read_text())
                leaves=dict(Counter(r.get('action') for r in full.get('recordings',[])))
                tools.append(dict(episode=eid,seq=e['event_seq'],ts=e['ts'],call_id=d.get('call_id'),id=d['id'],
                    request=request,leaf_counts=leaves,source_complete=full.get('source_complete'),elapsed_s=result.get('elapsed_s'),is_error=result.get('is_error'),check_rejected=result.get('check_rejected'),
                    ok=response.get('ok') if isinstance(response,dict) else None,success=response.get('success') if isinstance(response,dict) else None,
                    diagnostic=response.get('diagnostic') if isinstance(response,dict) else None,
                    issues=response.get('issues') if isinstance(response,dict) else None,
                    result_ref=response.get('result_ref') if isinstance(response,dict) else None,
                    input_ref=d.get('input',{}).get('id'),result_evidence_id=result.get('evidence',{}).get('id')))
        summaries.append({**ep,'usage':usage,'totals':{k:sum(x.get(k,0) or 0 for x in usage) for k in ('input','output','cache_read','cache_create')},
            'route':[e['data'] for e in events if e['kind']=='cognition.route'],
            'evaluation':[e['data'] for e in events if e['kind']=='supervision.evaluation.finished'],
            'input_shapes':[e['data'] for e in events if e['kind']=='model.input'],
            'recall':[e['data'] for e in events if e['kind'] in ('recall.presented','recall.used')],
            'tool_calls':sum(e['kind']=='supervision.tool.started' for e in events),
            'tool_errors':sum(e['data'].get('is_error',False) for e in events if e['kind']=='supervision.tool.finished')})
    for path in (Path.home()/'.codex/sessions/2026/10/01').glob('*.jsonl'):
        if path.stat().st_mtime < json.loads((HERE/'timing.json').read_text())['started_epoch']:continue
        for line in path.open():
            if '"token_usage_record"' not in line:continue
            record=json.loads(line)
            if record.get('type')!='token_usage_record':continue
            d=record['payload']; ident=d.get('response_id')
            if ident not in observed:continue
            eid,meta=observed[ident]
            rounds.append(dict(episode=eid,call_id=meta['call_id'],role=meta['role'],phase=meta['phase'],
                               round=meta['round_index'],ts=record['timestamp'],usage=d['usage'],
                               response_id=ident,thread_id=d['thread_id'],turn_id=d['turn_id'],rollout=str(path)))
    known_calls={x['call_id'] for x in rounds}
    for eid,events in all_events.items():
        for e in events:
            d=e['data']
            if e['kind']=='model.usage' and d.get('accounting')=='billable_usage' and d['call_id'] not in known_calls:
                rounds.append(dict(episode=eid,call_id=d['call_id'],role=d['role'],phase=d['phase'],round=d.get('round_index'),ts=e['ts'],usage={'input_tokens':d.get('input',0),'output_tokens':d.get('output',0),'cached_input_tokens':d.get('cache_read',0)},response_id=None,source='trajectory single call usage'))
    for row in rounds:
        stamp=datetime.fromisoformat(str(row['ts']).replace('Z','+00:00'))
        if stamp.tzinfo is None:stamp=stamp.replace(tzinfo=ZoneInfo('Asia/Seoul'))
        row['ts_epoch']=stamp.timestamp()
        row['call_input_shapes']=[e['data'] for e in all_events[row['episode']] if e['kind']=='model.input' and e['data']['call_id']==row['call_id']]
    rounds.sort(key=lambda x:(x['episode'],x['ts_epoch']))
    previous_boundary={}
    for row in rounds:
        events=all_events[row['episode']]
        boundary=next(e['event_seq'] for e in events if (e['kind']=='model.response_observed' and e['data']['response_id']==row['response_id']) or (row['response_id'] is None and e['kind']=='model.usage' and e['data']['call_id']==row['call_id']))
        before=previous_boundary.get(row['call_id'],0)
        prior=[x for x in tools if x['episode']==row['episode'] and x['seq']<before]
        row['prior_observed_tool_inputs']=[x['seq'] for x in prior]
        row['issued_tool_inputs']=[x['seq'] for x in tools if x['episode']==row['episode'] and before<=x['seq']<boundary and x['call_id']==row['call_id']]
        row['input_scope_note']='실제 전체 입력의 원본 위치는 rollout+turn_id. 도구 목록은 이전 응답 경계까지 관측된 입력이며 모델 선택·문맥 포함의 완전한 재구성은 아님.'
        previous_boundary[row['call_id']]=boundary
        row['purpose']='검토 전: '+row['phase']
    dump(HERE/'ai_metrics.json',summaries);dump(HERE/'round_costs.json',rounds)
    (HERE/'ai_programs.jsonl').write_text(''.join(json.dumps(t,ensure_ascii=False)+'\n' for t in tools))
    dump(WORK/'trajectory.json',all_events)
    print(json.dumps([{k:v for k,v in s.items() if k in ('id','agent','ended_at','total_ms','totals','tool_calls','tool_errors')} for s in summaries],ensure_ascii=False,indent=2))


if __name__=='__main__':main()
