"""Prepare checked IBL requests. No task calculations are performed here."""
import argparse
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[4]
HERE=Path(__file__).resolve().parent
OUT=ROOT/'outputs/long_sentence_imagination/2026-10-22_88회차'
ap=argparse.ArgumentParser();ap.add_argument('phase',type=int);ap.add_argument('--execute',action='store_true');a=ap.parse_args()
n=a.phase
if a.execute:
    checked=json.loads((OUT/'runs'/f'trainer_T{n}_check.json').read_text())['response']
    assert checked.get('ok'),checked
    body=checked['execute_args'];label=f'trainer_T{n}'
else:
    assert n>=2
    dest=OUT/'trainer'/f'T{n}';dest.mkdir(exist_ok=True)
    body={'code':(HERE/'continuation_v0.ibl').read_text(),'check':True,'budget':{'steps':1000000,'rows':100000},
      'inputs':{'source':str(OUT/'inputs'),'output':str(dest),'previous':str(OUT/'trainer'/f'T{n-1}'/'state.json'),
        'phase':f'T{n}','policy':{'budget':4200000,'deadline':'2026-11-20','cancel_optional':True,'external_saas':False,'face':False},
        'expected_ids':[f'D{i:04d}' for i in range(1,1801)],'reload_data':n in (5,7,8),'reload_tasks':n in (2,3),
        'receipts_path':str(OUT/'inputs/receipts.json') if n>=3 else ''}}
    label=f'trainer_T{n}_check'
(OUT/'runs'/f'{label}_request.json').write_text(json.dumps(body,ensure_ascii=False))
print(label)
