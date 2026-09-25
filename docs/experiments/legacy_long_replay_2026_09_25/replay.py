"""Replay historical rewrites with real compiler/tables and frozen external leaves.

All unlisted effects are refused. ledger uses the actual handler on disposable
files, never the historical paths. Fixtures are synthetic, not historical returns.
"""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'backend'))
import boot_paths  # noqa: E402,F401
import copy
import json
import tempfile
import time
from ibl_v2_adapters import Adapter, Adapted, decode_envelope, load_registry
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime
from ibl_edition import source_context
from ibl_v2_ir import Fault

HERE=Path(__file__).resolve().parent
NAMES=sorted(p.stem for p in (HERE/'current').glob('*.ibl'))
VIDEO_COLUMNS=['video_id','title','uploader','view_count','duration','upload_date','url']
VIDEOS=[dict(zip(VIDEO_COLUMNS,[vid,'title '+vid,'channel',views,60,date,'https://example.invalid/'+vid]))
        for vid,views,date in [('seen',500,'2026-09-01'),('a',30,'2026-09-01'),('b',90,'2026-09-02'),('old',200,'2025-01-01')]]
NEWS=[dict(title='title '+str(i),url='https://example.invalid/'+str(i),date=d,
           summary='summary',query='fixture',meta='publisher',source='fixture',name='repo '+str(i))
      for i,d in [(1,'2026-09-14'),(2,'2026-08-01')]]
SHOPS=[{'category':c,'name':str(i)} for i,c in enumerate(['food','food','books'])]
PLACES=[dict(name='place',category='public',address='fixture address')]
QUEUE=[dict(slug='a',name='A',unit='시',tier=1,last_visited='',visits=0,verdict='미방문'),
       dict(slug='b',name='B',unit='시',tier=1,last_visited='2026-09-01',visits=1,verdict='관심')]
HOUSING={'molit_apt':[
 {'계약유형':'전세','보증금':20000,'전용면적':76,'아파트명':'A'},
 {'계약유형':'전세','보증금':40000,'전용면적':84,'아파트명':'A'},
 {'계약유형':'월세','보증금':30000,'전용면적':84,'아파트명':'B'},
 {'계약유형':'전세','보증금':19999,'전용면적':84,'아파트명':'C'}],
 'molit_trade':[{'전용면적':84,'법정동':'동','price':50000},{'전용면적':100,'법정동':'제외','price':90000}]}

class Leaves:
 def __init__(self,name,variant):
  self.name,self.variant,self.calls=name,variant,[]
 def run(self,key,args):
  self.calls.append({'action':key,'args':copy.deepcopy(args)})
  empty=self.variant=='empty'
  if self.variant=='failure' and ((key=='sense:video' and args.get('video_id')=='b') or
      (self.name not in ('videos','enterprise','transcripts','ledger') and (key.startswith('sense:') or key=='self:read'))):
   return {'success':False,'error':'frozen source unavailable'}
  if self.variant=='optional_failure' and key=='sense:crawl':
   return {'success':False,'error':'optional crawl unavailable'}
  if key in ('sense:search','sense:feed','sense:paper'):
   return {'items':[] if empty else copy.deepcopy(NEWS)}
  if key=='sense:crawl':return {'url':args['url'],'text':'fixture text','title':'fixture title','items':[] if empty else copy.deepcopy(NEWS[:1])}
  if key=='sense:commercial':return {'items':[] if empty else copy.deepcopy(SHOPS)}
  if key=='sense:place':return {'items':[] if empty else copy.deepcopy(PLACES)}
  if key=='sense:stock':return {'items':[] if empty else [dict(symbol=args['ticker'],name='quote',current_price=100,change_percent=2,as_of='2026-09-01')]}
  if key=='sense:search_youtube':return {'items':[] if empty else copy.deepcopy(VIDEOS)}
  if key=='sense:video':
   if args['op']=='transcript':return {'items':[{'text':'transcript'}],'text':'transcript'}
   return {'items':[copy.deepcopy(next(v for v in VIDEOS if v['video_id']==args['video_id']))]}
  if key=='self:struct':return {'items':[{'tip':'tip 1','timestamp':'00:01'},{'tip':'tip 2','timestamp':'00:02'}]}
  if key=='table:ai':
   section=next(s for s in ['투자','기술','논문','사례'] if "section='"+s+"'" in args['instruction'])
   return {'items':[{**r,'section':section,'event_id':r['url'],'label':'NEW','delta':'fixture'} for r in args['items']]}
  if key=='self:script':return {'value':{'items':[] if empty else copy.deepcopy(NEWS)}}
  if key=='self:time':return '2026-09-25'
  if key=='self:read':return {'text':'{}','blocks':[],'data':{}}
  if key=='self:file_find':return {'items':[] if empty else [{'name':'housing_report_b.md'},{'name':'housing_report_a.md'}]}
  if key=='self:ledger':
   if args.get('op') not in ('select',None):raise AssertionError('Unexpected historical ledger write')
   rows=QUEUE if args.get('target')=='queue' else ([{'id':'seen','verdict':'tips_1'}] if args.get('target')=='covered' else [])
   return {'items':[] if empty else copy.deepcopy(rows)}
  raise AssertionError('Unlisted external effect: '+key)

def inputs_for(name,variant,tmp):
 if name=='housing':return {k:[] if variant=='empty' else copy.deepcopy(v) for k,v in HOUSING.items()}
 if name=='transcripts':return {'심사':[] if variant=='empty' else [{**v,'selected':True,'reason':'fixture'} for v in VIDEOS if v['video_id'] in ('a','b')]}
 if name=='ledger':
  ledger=Path(tmp)/'ledger.json';covered=Path(tmp)/'covered.json'
  ledger.write_text(json.dumps({'covered':[],'recent_topics':[]}));covered.write_text('[]')
  return {'ledger_path':str(ledger),'covered_path':str(covered),
          '절제':[] if variant=='empty' else [{'video_id':'a','tip':'one'},{'video_id':'a','tip':'two'},{'video_id':'b','tip':'three'}],
          '선정':[] if variant=='empty' else [{**v} for v in VIDEOS if v['video_id'] in ('a','b')]}
 return {}

def registry_for(base,leaves,name):
 registry={}
 for key,adapter in base.items():
  if key.startswith('table:') and key!='table:ai': registry[key]=adapter;continue
  if key=='self:ledger' and name=='ledger':registry[key]=adapter;continue
  def run(rt,args,key=key,contract=adapter.contract):
   raw=leaves.run(key,args)
   if isinstance(raw,dict) and raw.get('success') is False:
    raise Fault('TOOL',raw['error'])
   if key in ('self:read','self:time'):return raw
   value,evidence=decode_envelope(raw,contract['adapter'],args)
   return Adapted(value,evidence)
  registry[key]=Adapter(adapter.contract,run)
 return registry

def validate(name,variant,result,leaves,inputs):
 """Business expectations independent of the compiler's success flag."""
 if variant=='failure' and name not in ('videos','enterprise','transcripts','ledger'):
  assert not result['success'] and result['source_complete'] is False,result
  return
 assert result['success'],result
 assert result['source_complete'] is (variant not in ('failure','optional_failure')),result
 v=result['value'];empty=variant=='empty'
 if name in ('videos','enterprise'):
  assert [r['video_id'] for r in v]==([] if empty else ['a'] if variant=='failure' else ['b','a']),v
  calls=[c['args']['video_id'] for c in leaves.calls if c['action']=='sense:video']
  assert sorted(calls)==([] if empty else ['a','b','old']),calls
 elif name=='transcripts':
  assert [(r['video_id'],r['tip']) for r in v]==([] if empty else [(i,t) for i in (['a'] if variant=='failure' else ['a','b']) for t in ['tip 1','tip 2']]),v
 elif name=='housing':
  assert len(v['items'])==(0 if empty else 2),v
  if not empty:
   assert v['items'][0]['건수']==2 and v['items'][0]['평균보증금']==30000,v
   assert v['items'][1]['평균가']==50000,v
 elif name=='rotation':assert [r['slug'] for r in v['items']]==([] if empty else ['a','b']),v
 elif name=='shops':
  assert v['hospitals']==v['libraries']==([] if empty else PLACES),v
  assert v['shops']==([[],[]] if empty else [[{'category':'food','수':2},{'category':'books','수':1}]]*2),v
 elif name=='stocks':
  assert v['news']==([] if empty else [{k:r[k] for k in ('title','meta','summary')} for r in NEWS]),v
  assert [r['items'][0]['symbol'] for r in v['stocks'] if r['items']]==([] if empty else ['NVDA','AAPL','ORCL','ADBE','AVGO','MU','XLE','XLU','SMH','TLT']),v
  assert len([c for c in leaves.calls if c['action']=='sense:stock'])==10
 elif name=='forex':
  assert v['news']==([] if empty else [{k:r[k] for k in ('title','summary','date')} for r in NEWS]),v
  assert [r['1년변화율%'] for r in v['year']]==[-2.77,5.57,-6.02,2.93,1.75],v
  assert [r['변화율%'] for r in v['period']]==[-12.42,-2.24],v
  assert [r['symbol'] for r in v['quotes']]==([] if empty else ['^KS11','102110']),v
 elif name=='news':
  assert len(v['items'])==(0 if empty else 4),v
  if not empty:assert {r['section']:r['count'] for r in v['items']}=={'투자':1,'기술':1,'논문':2,'사례':4},v
 elif name=='sources':assert len(v['items'])==(0 if empty else 5),v
 elif name=='reinforce':assert len(v)==(0 if empty else 8),v
 elif name=='ledger':
  stored=json.loads(Path(inputs['ledger_path']).read_text())
  assert [(r['id'],r['verdict']) for r in stored['covered']]==([] if empty else [('a','tips_2'),('b','tips_1')]),stored
  assert stored['recent_topics']==[{'date':'2026-09-06','topic':'평가'}],stored
  assert len(v['items'])==(0 if empty else 2),v

def evaluate(name,variant,base,tmp):
 code=(HERE/'current'/f'{name}.ibl').read_text()
 inputs=inputs_for(name,variant,tmp);leaves=Leaves(name,variant)
 started=time.monotonic()
 try:
  registry=registry_for(base,leaves,name)
  plan=compile_program(code,registry,inputs)
  with source_context(2):
   result=Runtime(plan,inputs).run()
  try:validate(name,variant,result,leaves,inputs);passed=True;error=None
  except AssertionError as exc:passed=False;error=str(exc)[:2500]
  return dict(name=name,variant=variant,passed=passed,error=error,
              check=plan.report(),result=result,calls=leaves.calls,seconds=round(time.monotonic()-started,4))
 except Exception as exc:return dict(name=name,variant=variant,passed=False,error=f'{type(exc).__name__}: {exc}')

def compact(row):
 row=copy.deepcopy(row)
 result=row.get('result',{})
 trace=result.pop('evidence',[])
 result['evidence_events']=len(trace)
 result['failure_evidence']=[e for e in trace if e['kind'] in ('tool_failure','recovered','collected_error')]
 for key in ('source_map','recordings','value_wire'):
  result.pop(key,None)
 check=row.get('check',{})
 for key in ('source_map','functions','preflight'):
  check.pop(key,None)
 # Calls retain arguments, including unchanged original AI instructions.
 return row

def main():
 phase=sys.argv[1] if len(sys.argv)>1 else 'after'
 if phase=='before':
  import subprocess, types
  module=types.ModuleType('historical_baseline_runtime')
  sys.modules[module.__name__]=module
  source=subprocess.check_output(['git','show','968aa186:backend/ibl/ibl_v2_runtime.py'],cwd=ROOT,text=True)
  exec(compile(source,'baseline_runtime.py','exec'),module.__dict__)
  globals()['Runtime']=module.Runtime
 with tempfile.TemporaryDirectory(prefix='ibl-historical-', dir=ROOT/'outputs') as tmp:
  base=load_registry(tmp);results=[]
  for name in NAMES:
   for variant in (['normal','empty'] if name=='ledger' else ['normal','empty','failure'] + (['optional_failure'] if name=='news' else [])):
    result=evaluate(name,variant,base,tmp);results.append(result)
    print(name,variant,'PASS' if result['passed'] else 'FAIL',str(result.get('error') or '')[:1400],flush=True)
  (HERE/f'{phase}.json').write_text('[\n'+',\n'.join(json.dumps(compact(r),ensure_ascii=False,default=str) for r in results)+'\n]\n')
  print(sum(r['passed'] for r in results),'/',len(results))
if __name__=='__main__':main()
