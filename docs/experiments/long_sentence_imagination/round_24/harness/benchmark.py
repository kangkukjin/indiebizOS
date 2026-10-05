"""Compare the same operation on the preserved revision and working tree."""
import sys,json,subprocess,time,statistics,cProfile
from pathlib import Path
root=Path(__file__).resolve().parents[5];sys.path.insert(0,str(root/'backend'));import boot_paths
path=root/'data/packages/installed/tools/data-ops/handler.py'
old={'__file__':str(path),'__name__':'lsi24_before'};new={'__file__':str(path),'__name__':'lsi24_after'}
exec(compile(subprocess.check_output(['git','show',sys.argv[1]+':'+str(path.relative_to(root))],cwd=root,text=True),str(path),'exec'),old)
exec(compile(path.read_text(),str(path),'exec'),new)
params={'by':'team','agg':{'count':['count'],'total':['sum','score'],'average':['avg','score']}}
reports=[]
for n in [24,240,800]:
 rows=[{'team':'ABC'[i%3],'score':i+1,f'note_{i}':'optional',f'flag_{i}':True} for i in range(n)];env={'items':rows}
 before=old['_op_groupby'](env,params);after=new['_op_groupby'](env,params);assert before==after
 timings={};tables={}
 for label,module in [('before',old),('after',new)]:
  calls=[];original=module['_get_table']
  def observed(value):
   result=original(value)
   if result[0] is not None:calls.append(len(result[0].get('columns',[]))*len(result[0].get('rows',[])))
   return result
  module['_get_table']=observed
  module['_op_groupby'](env,params)
  module['_get_table']=original;tables[label]={'calls':len(calls),'cells':sum(calls)}
  samples=[]
  for _ in range(5):
   t=time.perf_counter();result=module['_op_groupby'](env,params);samples.append((time.perf_counter()-t)*1000);assert result==before
  timings[label]={'samples_ms':samples,'median_ms':statistics.median(samples)}
 reports.append({'rows':n,'equal':True,'tables':tables,'timing':timings})
print(json.dumps(reports,indent=2))
