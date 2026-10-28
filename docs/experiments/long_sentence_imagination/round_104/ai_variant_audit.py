import json
from pathlib import Path
ROOT = Path(__file__).resolve().parents[4]
BASE = ROOT / "outputs/long_sentence_imagination/2026-10-28_104회차"
from verify import region
import copy,hashlib
raw=json.loads((BASE/'ai/variant/plan.json').read_text());a=copy.deepcopy(raw['scenarios']);a['transfers']=raw['transfers'];a['transfer_cost']=raw['transfer_cost']
for mode in ['base','with_transfer']:
 for policy in ['deadline','budget']:
  for lib in a[mode][policy]['libraries']:
   for r in lib['lines']:
    if r['status']=='selected':r['status']='ready'
    if r['status']=='transfer':
     assert r['shortage']==0 and r['transfer_in']>0;r['status']='stock'
checks=region(a)
for source in raw["sources"]:
 assert hashlib.sha256(Path(source["file"]).read_bytes()).hexdigest()==source["sha256"]
assert raw['transfer_qty']==147
for mode in ['base','with_transfer']:
 for policy in ['deadline','budget']:
  p=raw['scenarios'][mode][policy];assert p['grand_total']==p['total_cost']+(1029 if mode=='with_transfer' else 0)
summary={'line_field_checks':checks,'rows':2400,'total_costs':{mode:{p:raw['scenarios'][mode][p]['grand_total'] for p in ['deadline','budget']} for mode in ['base','with_transfer']},'transfer_quantity':147,'transfer_cost':1029,'status_mapping':{'selected':'ready','transfer':'stock only when shortage=0 and transfer_in>0'}}
print(summary)
