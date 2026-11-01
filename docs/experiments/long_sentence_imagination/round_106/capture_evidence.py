"""로컬 실행 원본에서 보고용 증거를 추출한다. 제품/AI 원본은 바꾸지 않는다."""
import collections
import hashlib
import json
import pathlib
import shutil
import sqlite3
import sys

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUT = ROOT / 'outputs/long_sentence_imagination/2026-11-01_106회차'

def read(p):
    return json.loads(p.read_text())

def save(name, value):
    p = HERE / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

def copy(src, dest):
    p = HERE / dest
    p.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(OUT / src, p)

def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

start = read(HERE / 'start.json')
e = {'start': start, 'episodes': [], 'ibl_runs': []}
con = sqlite3.connect(f'file:{ROOT}/data/world_pulse.db?mode=ro', uri=True)
for ep, label in [(5670, 'ai_base'), (5671, 'ai_variant')]:
    row = con.execute('select started_at,ended_at,total_ms,task_id from episode_log where id=?', (ep,)).fetchone()
    assert row[1], '아직 실행 중'
    ev = [(ts, kind, json.loads(data)) for ts, kind, data in con.execute(
        'select ts,kind,data from trajectory_event where episode_id=? order by event_seq', (ep,))]
    usage = [d for _, k, d in ev if k == 'model.usage' and d.get('accounting') == 'billable_usage']
    assert len({(d['call_id'], d.get('round_index')) for d in usage}) == len(usage)
    cost = next(d['cost'] for _, k, d in ev if k == 'supervision.cost.summary')
    store = pathlib.Path(cost['events_path']).parent
    raw = [json.loads(l) for l in (store / 'events.jsonl').read_text().splitlines()]
    decision = next(d['decision'] for d in raw if d['kind'] == 'decision')
    audit = []
    for d in raw:
        if d['kind'] != 'tool.started':
            continue
        p = store / (d['input']['id'] + '.txt')
        s = p.read_text() if p.exists() else d['input'].get('excerpt', '')
        audit.append({'seq': d['seq'], 'name': d['name'], 'time': d['time'],
                      'input_sha256': hashlib.sha256(s.encode()).hexdigest(),
                      'complete': len(s) == d['input']['chars'],
                      'restricted_markers': [x for x in ['/trainer', '/private', 'heldout', 'gold.json'] if x in s]})
    plans = [{'timestamp': ts, **d} for ts, k, d in ev if k == 'research.plan_saved']
    for i, p in enumerate(plans):
        shutil.copyfile(p['path'], HERE / f'{label}_plan_final.md')
    rec = read(OUT / (label + '_run.json'))
    e['episodes'].append({'id': ep, 'started': row[0], 'ended': row[1], 'total_ms': row[2],
        'task_id': row[3], 'terminal_state': rec['latest']['state'], 'http_seconds': rec['seconds'],
        'guide_events': [{'timestamp': ts, **d} for ts,k,d in ev if k == 'research.guide_supplied'],
        'plans': plans, 'usage': usage, 'usage_sum': {k: sum(d.get(k, 0) for d in usage) for k in ['input','output','cache_read','cache_create']},
        'cost_summary': cost, 'evaluation': {k: decision.get(k) for k in ['status','goal_status','goal_reason','goal_evidence','remaining']},
        'tool_input_audit': audit,
        'tool_errors': [d for d in raw if d['kind'] == 'tool.finished' and d.get('is_error')]})
    copy(label + '_request.txt', label + '_request.txt')
    (HERE / (label + '_response.md')).write_text(rec['latest'].get('result') or '')
for p in sorted((OUT / 'runs').glob('*.json')):
    r = read(p); d = r['response']
    save('requests/' + p.name, r['request'])
    e['ibl_runs'].append({'label': p.stem, 'started': r['started'], 'ended': r.get('ended'),
        'check': r['request'].get('check',False), 'seconds': r['seconds'], 'success': d.get('success'),
        'issues': d.get('issues',[]), 'error': d.get('error'), 'diagnostic': d.get('diagnostic'),
        'model': d.get('usage',{}).get('model'), 'run_id': d.get('resume',{}).get('run_id'),
        'request_sha256': hashlib.sha256(json.dumps(r['request'],sort_keys=True,ensure_ascii=False).encode()).hexdigest()})
e['source_hashes_after'] = {p: sha(ROOT/p) for p in start['source_hashes']}
frozen = read(OUT / 'private/ai_base_frozen.json')
e['ai_base_frozen'] = frozen
e['ai_base_changed'] = [p for p,h in frozen['files'].items() if sha(OUT/'ai/base'/p) != h]
e['retriever_frozen'] = read(OUT/'trainer/frozen_retriever.json')
e['trainer_model_sum'] = {k: sum((r['model'] or {}).get(k,0) for r in e['ibl_runs']) for k in ['requests','measured_requests','unmeasured_requests','input','output','cache_read','cache_create']}

for variant in ['base','variant']:
    for name in ['manifest.json','queries.json']:
        copy(f'inputs/{variant}/{name}', f'fixtures/{variant}/{name}')
    for d in read(OUT/f'inputs/{variant}/manifest.json'):
        if d['kind'] != 'real':
            copy(f'inputs/{variant}/docs/'+d['file'], f'fixtures/{variant}/docs/'+d['file'])
for n in ['heldout.json','gold.json','ai_initial_plan.md']:
    copy('private/'+n, n)
copy('trainer/research_plan.md','trainer_plan.md')
for p in (OUT/'ai/base').rglob('*'):
    if p.is_file() and '__pycache__' not in p.parts and p.name != 'sources.json':
        copy(str(p.relative_to(OUT)), str(p.relative_to(OUT)))
for p in (OUT/'ai/variant').rglob('*'):
    if p.is_file() and '__pycache__' not in p.parts:
        copy(str(p.relative_to(OUT)), str(p.relative_to(OUT)))
comparison = HERE / 'ai/variant/compare_base_variant.json'
e['comparison_original_sha256'] = sha(comparison)
comparison.write_text(json.dumps(read(comparison), ensure_ascii=False) + '\n')
for name in ['ai_heldout_results.json','ai_heldout_matched_runtime.json']:
    copy('private/'+name, 'heldout/'+name)
for name in ['base_answers','heldout_answers','variant_answers','base_followup','heldout_followup','variant_followup']:
    data = read(OUT/f'trainer/{name}.json')
    if isinstance(data, dict):
        data = data['items']
    cleaned=[]
    for row in data:
        r=dict(row.get('result',row));r.pop('documents',None);r.pop('contexts',None)
        if 'reused' in row:r['reused']=row['reused']
        cleaned.append(r)
    p=HERE/f'trainer/{name}.jsonl';p.parent.mkdir(exist_ok=True)
    p.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in cleaned))
for name in ['base_retrieval','heldout_retrieval','variant_retrieval']:
    copy(f'trainer/{name}.json',f'trainer/{name}.json')
base=read(OUT/'ai/base/runs/results_base.json')
pas=read(OUT/'ai/base/runs/passage_ranks.json')
e['L106_1']={
    'actual_output':next(r for r in base['results'] if r['question_id']=='Q01' and r['method']=='rrf_bm25ko_dense@paragraph'),
    'auxiliary_analysis':next(r for r in pas['rows'] if r['question_id']=='Q01'),
    'interpretation':'주 프로그램: 문단 점수→문서별 최대값→문서 RRF→문서별 대표 문단. 보조 분석: 전체 문단 순위→문단 RRF. 보조 순위 계산은 유효하나 실제 반환 근거의 실패 판정과 동일하지 않다.'}
e['L106_2']={}
for name in ['ai_heldout_results','ai_heldout_matched_runtime']:
    d=read(OUT/f'private/{name}.json')
    e['L106_2'][name]={'rows':len(d['results']),'skipped':d['skipped'],'config_unchanged':d['config_unchanged']}
save('evidence.json',e)
print(json.dumps({'episodes':[(x['id'],x['terminal_state']) for x in e['episodes']], 'base_changed':e['ai_base_changed'],'trainer_usage':e['trainer_model_sum'],'ibl_runs':len(e['ibl_runs'])},ensure_ascii=False))
