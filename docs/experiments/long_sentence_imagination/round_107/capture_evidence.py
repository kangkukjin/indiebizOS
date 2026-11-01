"""완료된 사례의 원본 산출물과 실제 호출·저장 증거를 보존한다."""
import hashlib,json,shutil,sqlite3
from pathlib import Path
H=Path(__file__).resolve().parent;R=H.parents[3]
O=R/'outputs/long_sentence_imagination/2026-11-01_107회차'
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
read=lambda p:json.loads(p.read_text())
e={'start':read(H/'start.json'),'cases':[]}
con=sqlite3.connect(f'file:{R}/data/world_pulse.db?mode=ro',uri=True)
for case in read(H/'cases.json'):
 attempt=case['id']+'_recheck' if case.get('previous') else case['id']
 src=O/attempt;rec=read(src/'receipt.json')
 assert rec['status']!='running',case['id']
 dest=H/'results'/case['id'];dest.mkdir(parents=True,exist_ok=True)
 for name in ['receipt.json','framing.json','research_plan.md','calls.json']:
  if (src/name).exists():shutil.copyfile(src/name,dest/name)
 for file in src.glob('call_*_response.txt'):shutil.copyfile(file,dest/file.name)
 events=[{'timestamp':ts,'kind':kind,'data':json.loads(data)} for ts,kind,data in con.execute('select ts,kind,data from trajectory_event where episode_id=? order by event_seq',(rec['episode_id'],))]
 keep={'request.received','research.guide_supplied','research.plan_saved','research.plan_failed','consciousness.contract_invalid','consciousness.contract_corrected','consciousness.contract_failed','model.usage'}
 observed=[x for x in events if x['kind'] in keep]
 raw=[json.loads(l) for l in (src/'supervision/events.jsonl').read_text().splitlines()]
 tool_events=[x for x in raw if x['kind'] in ['model.native_tool','tool.started','tool.finished']]
 checks=[]
 for file in sorted(src.glob('call_*_input.txt')):
  checks.append({'file':file.name,'sha256':sha(file),'guide_supplied':(H/'deep_research.md').read_text() in file.read_text(),'operator_checks_present':any(check in file.read_text() for check in case['checks'])})
 entry={'id':case['id'],'attempt':attempt,'episode_id':rec['episode_id'],'status':rec['status'],'episode_source':con.execute('select source from episode_log where id=?',(rec['episode_id'],)).fetchone()[0],'seconds':rec['seconds'],'calls':rec.get('calls'),'model':rec.get('model'),'usage':{k:v for k,v in rec['usage'].items() if k!='calls'},'events':observed,'tool_events':tool_events,'input_audit':checks,'artifact_sha256':{p.name:sha(p) for p in dest.iterdir() if p.is_file() and p.name!='events.json'}}
 e['cases'].append(entry)
# 최초 후속은 하네스 경로가 잘못된 시도로 따로 보존한다.
e['invalid_attempts']=[]
for cid in ['C09','C10']:
 src=O/cid;dest=H/'invalid_attempts'/cid;dest.mkdir(parents=True,exist_ok=True)
 rec=read(src/'receipt.json');assert rec['status']!='running'
 e['invalid_attempts'].append({'id':cid,'episode_id':rec['episode_id'],'status':rec['status'],'seconds':rec['seconds'],'episode_source':con.execute('select source from episode_log where id=?',(rec['episode_id'],)).fetchone()[0],'input_sha256':{p.name:sha(p) for p in src.glob('call_*_input.txt')},'previous_read_error':'연구계획이 현재 작업공간 밖에 있습니다' in (src/'call_1_input.txt').read_text(),'usage':{k:v for k,v in rec['usage'].items() if k!='calls'}})
 for name in ['receipt.json','framing.json','research_plan.md','calls.json']:
  if (src/name).exists():shutil.copyfile(src/name,dest/name)
 for file in src.glob('call_*_response.txt'):shutil.copyfile(file,dest/file.name)
 e['invalid_attempts'][-1]['artifact_sha256']={p.name:sha(p) for p in dest.iterdir() if p.is_file()}

e['source_sha256_after']={n:sha(R/n) for n in e['start']['source_sha256']}
e['cases_sha256_after']=sha(H/'cases.json')
e['valid_attempt_usage']={k:sum((c['usage'].get(k) or 0) for c in e['cases']) for k in ['requests','measured_requests','unmeasured_requests','input','output','cache_read','cache_create','reasoning']}
e['total_usage']={k:sum((c['usage'].get(k) or 0) for c in e['cases']+e['invalid_attempts']) for k in ['requests','measured_requests','unmeasured_requests','input','output','cache_read','cache_create','reasoning']}
# 사례별 긴 이벤트는 별도 파일에 보존해 파일 1500줄 제한을 지킨다.
for c in e['cases']:
 events=c.pop('events');event_path=H/'results'/c['id']/'events.json';event_path.write_text(json.dumps(events,ensure_ascii=False,indent=2)+'\n');c['artifact_sha256']['events.json']=sha(event_path)
(H/'evidence.json').write_text(json.dumps(e,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'cases':len(e['cases']),'usage':e['total_usage']},ensure_ascii=False))
