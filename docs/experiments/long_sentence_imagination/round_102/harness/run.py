from api import *
import sys
label=sys.argv[1];file=sys.argv[2];check='--check' in sys.argv
inputs={'root':str(BASE/'source'),'ledger':str(BASE/'trainer'/'dispatch.jsonl')}
r=ibl(label,(BASE/'trainer'/file).read_text(),inputs=inputs,check=check)
print(json.dumps({k:r[k] for k in ['success','valid','issues','warnings','error','diagnostic','resume','result_ref','run_status'] if k in r},ensure_ascii=False)[:9000])
if 'value' in r:
 (BASE/'trainer'/f'{label}_value.json').write_text(json.dumps(r['value'],ensure_ascii=False,indent=2));print(str(r['value'])[:400])
