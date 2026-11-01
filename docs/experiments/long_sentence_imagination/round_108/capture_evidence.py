"""완료한 최종·초기 시도와 실제 지문·비용을 보존한다. 모델은 호출하지 않는다."""
import hashlib,json,shutil,sqlite3
from pathlib import Path
H=Path(__file__).resolve().parent;R=H.parents[3];O=R/'outputs/long_sentence_imagination/2026-11-01_108회차'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
e={'start':read(H/'start.json'),'cases':[],'preliminary':[]}
con=sqlite3.connect(f'file:{R}/data/world_pulse.db?mode=ro',uri=True)
keep={'request.received','research.guide_supplied','research.plan_saved','research.plan_failed','framing.revised','model.usage','consciousness.contract_invalid','consciousness.contract_corrected','consciousness.contract_failed'}
case_map={c['id']:c for c in read(H/'cases.json')}
for cid,attempt,group in [(c,c+'_final','cases') for c in case_map]+[(c,c,'preliminary') for c in ['R01','R02']]:
 src=O/attempt;receipt=read(src/'receipt.json');assert receipt['status']!='running',attempt
 dest=H/('results' if group=='cases' else 'preliminary')/cid;dest.mkdir(parents=True,exist_ok=True)
 names=['receipt.json','framing.json','research_plan.md','calls.json','recovery_input.json','recovery_response.json','recovered_framing.json','recovered_plan.md']
 for name in names:
  if (src/name).exists():shutil.copyfile(src/name,dest/name)
 for file in src.glob('call_*_response.txt'):shutil.copyfile(file,dest/file.name)
 events=[{'timestamp':ts,'kind':kind,'data':json.loads(data)} for ts,kind,data in con.execute('select ts,kind,data from trajectory_event where episode_id=? order by event_seq',(receipt['episode_id'],)) if kind in keep]
 (dest/'events.json').write_text(json.dumps(events,ensure_ascii=False,indent=2)+'\n')
 audits=[]
 for file in sorted(src.glob('call_*_input.txt')):
  s=file.read_text();g=s.split('<research_planning_guide>\n',1)[1].split('\n</research_planning_guide>',1)[0] if '<research_planning_guide>\n' in s else None
  audits.append({'file':file.name,'sha256':sha(file),'guide_sha256':hashlib.sha256(g.encode()).hexdigest() if g else None,'operator_check_text_present':any(x in s for x in case_map[cid]['checks'])})
 raw=[json.loads(l) for l in (src/'supervision/events.jsonl').read_text().splitlines()]
 entry={'id':cid,'attempt':attempt,'episode_id':receipt['episode_id'],'episode_source':con.execute('select source from episode_log where id=?',(receipt['episode_id'],)).fetchone()[0],'status':receipt['status'],'initial_calls':receipt.get('initial_calls',receipt.get('calls')),'calls':receipt.get('calls'),'seconds':receipt['seconds'],'model':receipt.get('model'),'usage':{k:v for k,v in receipt['usage'].items() if k!='calls'},'input_audit':audits,'tool_events':[x for x in raw if x['kind'] in ['model.native_tool','tool.started','tool.finished']],'artifact_sha256':{p.name:sha(p) for p in dest.iterdir() if p.is_file()}}
 e[group].append(entry)
keys=['requests','measured_requests','unmeasured_requests','input','output','cache_read','cache_create','reasoning']
e['final_usage']={k:sum(c['usage'][k] for c in e['cases']) for k in keys}
e['total_usage']={k:sum(c['usage'][k] for c in e['cases']+e['preliminary']) for k in keys}
e['source_sha256_end']={f:sha(R/f) for f in e['start']['after_sha256']}
e['cases_sha256_end']=sha(H/'cases.json')
(H/'evidence.json').write_text(json.dumps(e,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'cases':len(e['cases']),'final_usage':e['final_usage'],'total_usage':e['total_usage']},ensure_ascii=False))
