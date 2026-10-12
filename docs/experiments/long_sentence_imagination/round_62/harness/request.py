"""Build IBL requests. This module never calculates training answers."""
import argparse,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[5]
from prepare import OUT
p=argparse.ArgumentParser();p.add_argument('program');p.add_argument('label');p.add_argument('--check',action='store_true');p.add_argument('--reuse');p.add_argument('--case',default='base');p.add_argument('--who',default='trainer');a=p.parse_args()
code=(ROOT/'docs/experiments/long_sentence_imagination/round_62/programs'/a.program).read_text()
payload={'code':code,'origin':'training','project_id':'수동모드','inputs':{'input':str(OUT/a.who/'input'),'out':str(OUT/a.who/'out'),'case':a.case},'budget':{'steps':5000000,'rows':100000}}
if a.check:payload['check']=True
if a.reuse:
 v=json.loads((OUT/'runs'/f'{a.reuse}.json').read_text());payload.update(v['continuation']['reuse_args'])
(OUT/f'{a.label}_request.json').write_text(json.dumps(payload,ensure_ascii=False))
