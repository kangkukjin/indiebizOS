"""Optional live read-only probes; no model, writes, notifications or corpus edits."""
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'backend'))
import boot_paths  # noqa: E402,F401
import json
import time
from ibl_v2_adapters import load_registry
from ibl_v2_compile import compile_program
from ibl_v2_runtime import Runtime
from ibl_edition import source_context

HERE=Path(__file__).resolve().parent

def main():
 registry=load_registry(str(ROOT));rows=[]
 for name in ('rotation','forex'):
  started=time.monotonic()
  code=(HERE/'current'/f'{name}.ibl').read_text()
  plan=compile_program(code,registry)
  with source_context(2):
   result=Runtime(plan).run()
  value=result.get('value',{})
  summary={'name':name,'check_status':plan.report()['status'],'issues':plan.issues,
           'success':result.get('success'),'source_complete':result.get('source_complete'),
           'error':result.get('error'),'diagnostic':result.get('diagnostic'),
           'seconds':round(time.monotonic()-started,3),
           'calls':[e['action'] for e in result.get('evidence',[]) if e['kind']=='invoke'],
           'row_counts':{k:len(v) for k,v in value.items() if isinstance(v,list)} if isinstance(value,dict) else {}}
  rows.append(summary)
  (HERE/'live.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2)+'\n')
  print(json.dumps(summary,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
