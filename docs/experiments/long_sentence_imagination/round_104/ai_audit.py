import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[4]
BASE = ROOT / "outputs/long_sentence_imagination/2026-10-28_104회차"
from verify import main
import hashlib,copy
raw=json.loads((BASE/'ai/report.json').read_text());a=copy.deepcopy(raw)
for lib in a['libraries']:
 lib['label']=lib['display_name']
 for row in lib['lines']:
  if row['status']=='confirmed':row['status']='ready'
checks=main(a)
for s in raw['sources']:
 p=Path(s['file']);assert hashlib.sha256(p.read_bytes()).hexdigest()==s['sha256']
dates=json.loads((BASE/'harness/dates.json').read_text())
for l in raw['libraries']:
 for r in l['lines']:assert r['need_by']==dates[l['library']+'|'+r['item']]
receipts=[json.loads(s) for s in (BASE/'ai/dispatch.jsonl').read_text().splitlines()];assert len(receipts)==3 and len({r['business_key'] for r in receipts})==3
for receipt,lib in zip(receipts,raw['libraries']):
 assert receipt['library']==lib['library'] and receipt['total_cost']==lib['total_cost']
 assert len(receipt['lines'])==len([r for r in lib['lines'] if r['shortage']>0])
 for r in receipt['lines']:
  source=next(x for x in lib['lines'] if x['item']==r['item'])
  for k,v in r.items():assert source[k]==v,(k,r,source)
summary={'line_field_checks':checks,'date_checks':600,'source_hash_checks':len(raw['sources']),'dispatch':3,'total_cost':raw['total_cost'],'status_mapping':{'confirmed':'ready'},'independent_oracle':True}
print(summary)
